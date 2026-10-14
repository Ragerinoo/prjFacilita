'use strict';
// Tarefa 12.5 - Cenário: Modo_API (API falsa em /api/chamados).
// Cada cenário é independente, em carga nova e curto (< 4 s).
// Requisitos: 7.8, 7.9, 7.10, 7.11, 7.14, 7.17, 8.11, 9.4
// resolved-feedback-comment 10.15: independência entre Modo_API do chamado e do feedback (10.5, 10.6).
const assert = require('node:assert/strict');
const { cenario } = require('../cenarios');

const DADOS = {
  nome: 'Maria da Silva',
  email: 'maria@exemplo.com.br',
  telefone: '11987654321',
  descricao: 'A máquina não liga mesmo na tomada.',
  aceite: true
};
const ROTA = '#/suporte/1';
const ROTULO_ABRIR = 'Abrir meu chamado';

async function preencherEEnviar(ctx) {
  await ctx.abrir(ROTA);
  await ctx.esperar('!!document.querySelector("#view-suporte:not([hidden]) #c-nome")', 1500, 'formulário do chamado');
  await ctx.preencherFormulario(DADOS);
  await ctx.enviar();
}

async function estadoDoFormulario(ctx) {
  return {
    nome: await ctx.valor('#c-nome'),
    email: await ctx.valor('#c-email'),
    telefone: await ctx.valor('#c-telefone'),
    descricao: await ctx.valor('#c-descricao'),
    aceite: await ctx.avaliar('document.querySelector("#c-aceite").checked'),
    botaoDesabilitado: await ctx.avaliar('document.querySelector("#btn-abrir-chamado").disabled'),
    botaoTexto: await ctx.lerTexto('#btn-abrir-chamado'),
    falhaVisivel: await ctx.visivel('#chamado-falha-area .msg-falha')
  };
}

async function exigirFalhaComDadosMantidos(ctx) {
  await ctx.esperar(
    '!!document.querySelector("#chamado-falha-area .msg-falha") && !document.querySelector("#btn-abrir-chamado").disabled',
    2500,
    'bloco de falha e botão reabilitado'
  );
  const e = await estadoDoFormulario(ctx);
  assert.equal(e.falhaVisivel, true, 'o bloco de falha deve estar visível');
  assert.equal(await ctx.atributo('#chamado-falha-area .msg-falha', 'role'), 'alert');
  assert.equal(e.botaoDesabilitado, false, 'o botão deve voltar a ficar habilitado');
  assert.equal(e.botaoTexto, ROTULO_ABRIR, 'o botão deve voltar ao rótulo original');
  assert.equal(await ctx.atributo('#form-chamado', 'aria-busy'), null, 'aria-busy deve sair do formulário');
  assert.equal(e.nome, DADOS.nome);
  assert.equal(e.email, DADOS.email);
  assert.equal(e.descricao, DADOS.descricao);
  assert.equal(e.telefone.replace(/\D/g, ''), DADOS.telefone, 'o telefone digitado deve ser mantido');
  assert.equal(e.aceite, true, 'o aceite deve continuar marcado');
  assert.equal(await ctx.hash(), ROTA, 'a tela continua na Tela_de_Chamado');
  assert.match(await ctx.lerTexto('#chamado-falha-area'), /N[ãa]o conseguimos abrir o chamado/);
}

async function exigirSemEventoChamado(ctx) {
  const eventos = await ctx.eventos();
  assert.equal(eventos.filter((ev) => ev.tipo === 'chamado').length, 0, 'nenhum evento "chamado" em caso de falha');
  assert.deepEqual(await ctx.chamadosLocais(), [], 'o repositório local deve continuar vazio');
}

cenario('sucesso: protocolo da API, sem aviso de protótipo e repositório local vazio',
  { modoApi: true, api: { modo: 'sucesso' } },
  async (ctx) => {
    await preencherEEnviar(ctx);
    await ctx.esperar('location.hash === "#/chamado/1"', 2500, 'ir para a confirmação');
    await ctx.esperar('document.querySelector("#chamado-protocolo").textContent.trim() !== ""', 1000, 'protocolo exibido');

    assert.equal(await ctx.lerTexto('#chamado-protocolo'), 'API-00001', 'deve exibir o protocolo devolvido pela API');
    assert.equal(ctx.api.requisicoes().length, 1, 'uma única requisição à API');
    const req = ctx.api.requisicoes()[0];
    assert.equal(req.metodo, 'POST');
    assert.equal(typeof req.chaveIdempotencia, 'string');
    assert.ok(req.chaveIdempotencia.length > 0, 'a requisição leva a chave de idempotência');

    // Aviso de protótipo: ausente do DOM ou, se o elemento existir, oculto e vazio.
    const textoAviso = await ctx.lerTexto('#chamado-aviso-prototipo');
    assert.ok(textoAviso === null || textoAviso === '', 'o aviso de protótipo não pode ter texto em Modo_API');
    assert.equal(await ctx.visivel('#chamado-aviso-prototipo'), false, 'o aviso de protótipo não pode aparecer');
    const corpo = await ctx.lerTexto('#view-chamado');
    assert.doesNotMatch(corpo, /prot[óo]tipo/i, 'a confirmação não menciona protótipo em Modo_API');

    // Repositório local vazio e evento de métrica com modo "api".
    assert.deepEqual(await ctx.chamadosLocais(), [], 'o repositório local deve ficar vazio em Modo_API');
    const chamados = (await ctx.eventos()).filter((ev) => ev.tipo === 'chamado');
    assert.equal(chamados.length, 1, 'um evento "chamado"');
    assert.equal(chamados[0].protocolo, 'API-00001');
    assert.equal(chamados[0].modo, 'api');
    ctx.semErros();
  });

cenario('falha 500: bloco de falha, botão reabilitado, valores mantidos e sem evento',
  { modoApi: true, api: { modo: 'erro500' } },
  async (ctx) => {
    await preencherEEnviar(ctx);
    await exigirFalhaComDadosMantidos(ctx);
    assert.equal(ctx.api.requisicoes().length, 1, 'sem retentativa automática');
    await exigirSemEventoChamado(ctx);
  });

cenario('resposta 2xx sem protocolo: mesmo bloco de falha, sem protocolo local',
  { modoApi: true, api: { modo: 'sem-protocolo' } },
  async (ctx) => {
    await preencherEEnviar(ctx);
    await exigirFalhaComDadosMantidos(ctx);
    assert.equal(ctx.api.requisicoes().length, 1);
    await exigirSemEventoChamado(ctx);
  });

cenario('tempo limite: API que não responde cai na falha (TIMEOUT_ENVIO_MS reduzido em memória)',
  { modoApi: true, api: { modo: 'sem-resposta' }, configNumerica: { TIMEOUT_ENVIO_MS: 700 } },
  async (ctx) => {
    // O valor real (10 s) não cabe nos 4 s do cenário; o servidor de teste serve
    // js/data.js com TIMEOUT_ENVIO_MS: 700. O arquivo em disco não muda.
    await ctx.abrir(ROTA);
    assert.equal(await ctx.avaliar('window.TRES_DATA.CHAMADO.config.TIMEOUT_ENVIO_MS'), 700, 'override do tempo limite ativo');
    await ctx.esperar('!!document.querySelector("#view-suporte:not([hidden]) #c-nome")', 1500, 'formulário do chamado');
    await ctx.preencherFormulario(DADOS);
    await ctx.enviar();
    await ctx.esperar('document.querySelector("#btn-abrir-chamado").disabled', 1000, 'estado "Enviando"');
    await exigirFalhaComDadosMantidos(ctx);
    assert.equal(ctx.api.requisicoes().length, 1, 'a requisição chegou à API, que não respondeu');
    await exigirSemEventoChamado(ctx);
  });

cenario('retentativa reaproveita a mesma chave de idempotência e então abre o chamado',
  { modoApi: true, api: { sequencia: ['erro500', 'sucesso'] } },
  async (ctx) => {
    await preencherEEnviar(ctx);
    await exigirFalhaComDadosMantidos(ctx);
    await exigirSemEventoChamado(ctx);

    // Retentativa manual: o mesmo botão, sem mexer nos campos.
    await ctx.enviar();
    await ctx.esperar('location.hash === "#/chamado/1"', 2500, 'ir para a confirmação após a retentativa');

    const chaves = ctx.api.chaves();
    assert.equal(chaves.length, 2, 'duas requisições: a falha e a retentativa');
    assert.ok(chaves[0], 'a primeira requisição tem chave');
    assert.equal(chaves[1], chaves[0], 'a retentativa reaproveita a mesma chaveIdempotencia');
    assert.equal(await ctx.lerTexto('#chamado-protocolo'), 'API-00001');

    const chamados = (await ctx.eventos()).filter((ev) => ev.tipo === 'chamado');
    assert.equal(chamados.length, 1, 'um único evento "chamado", só depois do sucesso');
    assert.deepEqual(await ctx.chamadosLocais(), []);
    // O 500 simulado gera um log de rede do próprio navegador; qualquer outro erro é falha.
    const inesperados = ctx.erros().filter((e) => !/Failed to load resource.*status of 500/.test(e));
    assert.deepEqual(inesperados, [], 'sem erros de script além do log de rede do 500 simulado');
  });

// ---------------------------------------------------------------------------
// resolved-feedback-comment 10.15 (Requisitos 10.5, 10.6): o feedback tem configuração
// própria (API_FEEDBACK_URL) e é independente de API_CHAMADOS_URL. O Modo_API do chamado
// (cenários acima) continua igual.
// ---------------------------------------------------------------------------
const COMENTARIO = 'Atendimento rápido, obrigado pela ajuda.';

/** Chega a #/resolvido/1 pelo caminho do consumidor e espera o formulário de comentário. */
async function abrirResolvido(ctx) {
  await ctx.abrir('#/');
  await ctx.avaliar('location.hash = "#/confirma/1"');
  await ctx.esperar('!document.querySelector("#view-confirma").hidden', 1000, 'tela "O problema foi solucionado?"');
  await ctx.clicar('#btn-sim');
  await ctx.esperar('location.hash === "#/resolvido/1" && !document.querySelector("#view-resolvido").hidden', 1000, 'tela de problema resolvido');
  await ctx.esperar('!document.querySelector("#form-feedback").hidden', 500, 'formulário de comentário visível');
}

async function enviarComentario(ctx) {
  await ctx.digitar('#f-comentario', COMENTARIO);
  await ctx.clicar('#btn-enviar-comentario');
  await ctx.esperar('document.querySelector("#feedback-agradecimento").textContent.trim().length > 0', 800, 'agradecimento do comentário');
}

cenario('feedback: API_CHAMADOS_URL preenchida e API_FEEDBACK_URL vazia → Modo_Prototipo, nada vai ao endpoint de chamados',
  { modoApi: true },
  async (ctx) => {
    await abrirResolvido(ctx);
    // O override do chamado está ativo e o do feedback não.
    assert.equal(await ctx.avaliar('window.TRES_DATA.CHAMADO.config.API_CHAMADOS_URL'), ctx.api.apiUrl, 'API_CHAMADOS_URL preenchida');
    assert.equal(await ctx.avaliar('window.TRES_DATA.FEEDBACK.config.API_FEEDBACK_URL'), '', 'API_FEEDBACK_URL continua vazia');

    await enviarComentario(ctx);

    // Modo_Prototipo: o comentário fica no repositório local de feedbacks.
    const registros = await ctx.feedbacksLocais();
    assert.equal(registros.length, 1, 'um registro no repositório de feedbacks');
    assert.equal(registros[0].comentario, COMENTARIO);
    // Nenhuma requisição ao endpoint de chamados (nem de outro método) nem ao de feedback.
    assert.equal(ctx.api.requisicoes().length, 0, 'nenhum POST ao endpoint de chamados');
    assert.equal(ctx.api.outras().length, 0, 'nenhuma outra requisição ao endpoint de chamados');
    assert.equal(ctx.apiFeedback.requisicoes().length, 0, 'nenhuma requisição ao endpoint de feedback');
    // O comentário não vira chamado.
    assert.deepEqual(await ctx.chamadosLocais(), [], 'nenhum chamado gravado');
    assert.equal((await ctx.eventos()).filter((ev) => ev.tipo === 'comentario').length, 1, 'um evento "comentario"');
    assert.equal((await ctx.eventos()).filter((ev) => ev.tipo === 'chamado').length, 0, 'nenhum evento "chamado"');
    ctx.semErros();
  });

cenario('feedback: API_FEEDBACK_URL preenchida e API_CHAMADOS_URL vazia → só o endpoint de feedback recebe o comentário',
  { modoApiFeedback: true, apiFeedback: { modo: 'sucesso' } },
  async (ctx) => {
    await abrirResolvido(ctx);
    assert.equal(await ctx.avaliar('window.TRES_DATA.CHAMADO.config.API_CHAMADOS_URL'), '', 'API_CHAMADOS_URL continua vazia');
    assert.equal(await ctx.avaliar('window.TRES_DATA.FEEDBACK.config.API_FEEDBACK_URL'), ctx.apiFeedback.apiUrl, 'API_FEEDBACK_URL preenchida');

    await enviarComentario(ctx);

    assert.equal(ctx.apiFeedback.requisicoes().length, 1, 'um POST ao endpoint de feedback');
    const req = ctx.apiFeedback.requisicoes()[0];
    assert.equal(req.metodo, 'POST');
    assert.equal(req.json && req.json.comentario, COMENTARIO);
    assert.equal(ctx.api.requisicoes().length, 0, 'nenhum POST ao endpoint de chamados');
    assert.equal(ctx.api.outras().length, 0, 'nenhuma outra requisição ao endpoint de chamados');
    // Modo_API do feedback: nada no repositório local.
    assert.deepEqual(await ctx.feedbacksLocais(), [], 'repositório local de feedbacks vazio em Modo_API');
    assert.deepEqual(await ctx.chamadosLocais(), [], 'nenhum chamado gravado');
    ctx.semErros();
  });
