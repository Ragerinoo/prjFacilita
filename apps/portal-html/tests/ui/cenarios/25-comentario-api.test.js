'use strict';
// Tarefa 10.6 (resolved-feedback-comment): comentário opcional em Modo_API (API falsa em /api/feedbacks).
// Cada cenário é independente, em carga nova e curto (< 4 s).
// Requisitos: 2.4, 8.6, 10.5, 10.6, 10.7, 10.9, 10.10
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { cenario } = require('../cenarios');

// Lê js/data.js só para leitura, para comparar os textos esperados.
const D = (() => {
  const w = {};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', '..', '..', 'js', 'data.js'), 'utf8'), { window: w });
  return JSON.parse(JSON.stringify(w.TRES_DATA));
})();
const TEXTOS = D.FEEDBACK.textos;

const ID = 1;
const ROTA_RESOLVIDO = '#/resolvido/' + ID;
const ROTA_CHAMADO = '#/suporte/' + ID;
const COMENTARIO = 'O passo a passo resolveu em dois minutos. 👍 <b>obrigado</b> & "ok"';
const CAMPOS = ['chaveIdempotencia', 'comentario', 'enviadoEm', 'modelo', 'nota', 'problemaId', 'versaoContrato'];

// Dados que o consumidor digita no formulário do chamado (e que NUNCA podem ir ao feedback).
const PESSOAIS = {
  nome: 'Maria da Silva',
  email: 'maria@exemplo.com.br',
  telefone: '11987654321',
  descricao: 'A máquina não liga mesmo na tomada.',
  aceite: true
};

// Espião instalado antes da página: registra fetch, XHR e sendBeacon; `window.__rejeitar` = quantos
// fetch seguintes falham como falha de rede (TypeError), sem chegar ao servidor.
const ESPIAO = `(function () {
  var original = window.fetch;
  window.__rede = [];
  window.__rejeitar = 0;
  window.fetch = function (u, i) {
    window.__rede.push({ via: 'fetch', url: String((u && u.url) || u), corpo: (i && i.body) || null });
    if (window.__rejeitar > 0) { window.__rejeitar -= 1; return Promise.reject(new TypeError('Failed to fetch')); }
    return original.apply(this, arguments);
  };
  var abrir = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (m, u) { window.__rede.push({ via: 'xhr', url: String(u), corpo: null }); return abrir.apply(this, arguments); };
  if (navigator.sendBeacon) {
    var beacon = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = function (u, d) { window.__rede.push({ via: 'beacon', url: String(u), corpo: null }); return beacon(u, d); };
  }
})();`;

/** Clica o botão do modelo pelo nome (como o consumidor). */
async function escolherModelo(ctx, nome) {
  await ctx.avaliar((n) => {
    const t = Array.from(document.querySelectorAll('#lista-modelos .modelo__nome')).find((x) => x.textContent.trim() === n);
    t.closest('button').click();
  }, nome);
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1500, 'tela de problemas');
}

async function abrirResolvido(ctx) {
  await ctx.abrir(ROTA_RESOLVIDO);
  await ctx.esperar('location.hash === "' + ROTA_RESOLVIDO + '" && !!document.querySelector("#form-feedback:not([hidden]) #f-comentario")', 1500, 'formulário do comentário');
}

async function digitarEEnviar(ctx, texto = COMENTARIO) {
  await ctx.digitar('#f-comentario', texto);
  await ctx.clicar('#btn-enviar-comentario');
}

/** Preenche o formulário do chamado (sem enviar) e vai à tela de resolvido na mesma carga. */
async function preencherChamadoEIrParaResolvido(ctx) {
  await ctx.abrir(ROTA_CHAMADO);
  await ctx.esperar('!!document.querySelector("#view-suporte:not([hidden]) #c-nome")', 1500, 'formulário do chamado');
  await ctx.preencherFormulario(PESSOAIS);
  await abrirResolvido(ctx);
}

async function exigirAgradecimento(ctx) {
  await ctx.esperar('document.querySelector("#feedback-agradecimento").textContent.trim() !== ""', 2500, 'agradecimento');
  assert.equal(await ctx.lerTexto('#feedback-agradecimento'), TEXTOS.agradecimento, 'mesmo agradecimento de data.js');
  assert.equal(await ctx.atributo('#feedback-agradecimento', 'role'), 'status');
  assert.equal(await ctx.avaliar('document.querySelector("#f-comentario").disabled'), true, 'campo desabilitado');
  assert.equal(await ctx.avaliar('document.querySelector("#btn-enviar-comentario").disabled'), true, 'botão desabilitado');
  assert.equal(await ctx.valor('#f-comentario'), COMENTARIO, 'o texto enviado continua visível');
  assert.equal((await ctx.foco()).id, 'feedback-agradecimento', 'foco no agradecimento');
  assert.equal(await ctx.existe('#feedback-falha-area .msg-falha'), false, 'sem bloco de falha');
}

async function exigirFalhaComTextoPreservado(ctx) {
  await ctx.esperar(
    '!!document.querySelector("#feedback-falha-area .msg-falha") && !document.querySelector("#btn-enviar-comentario").disabled',
    2500,
    'bloco de falha e botão reabilitado'
  );
  assert.equal(await ctx.atributo('#feedback-falha-area .msg-falha', 'role'), 'alert');
  assert.equal(await ctx.lerTexto('#feedback-falha-area .msg-falha'), TEXTOS.falha);
  assert.equal(await ctx.valor('#f-comentario'), COMENTARIO, 'o texto digitado é preservado');
  assert.equal(await ctx.avaliar('document.querySelector("#f-comentario").readOnly'), false, 'campo editável de novo');
  assert.equal(await ctx.avaliar('document.querySelector("#f-comentario").disabled'), false);
  assert.equal(await ctx.atributo('#form-feedback', 'aria-busy'), null, 'aria-busy sai do formulário');
  assert.equal(await ctx.lerTexto('#feedback-agradecimento'), '', 'sem agradecimento na falha');
  assert.equal(await ctx.hash(), ROTA_RESOLVIDO, 'a tela continua em resolvido');
  assert.deepEqual(await ctx.feedbacksLocais(), [], 'Modo_API não grava no repositório local');
  const comentarios = (await ctx.eventos()).filter((ev) => ev.tipo === 'comentario');
  assert.equal(comentarios.length, 0, 'nenhum evento "comentario" em caso de falha');
}

/** Falha de rede/HTTP/tempo limite geram só o log de rede do navegador; qualquer outro erro é falha do cenário. */
function exigirSemErrosInesperados(ctx) {
  const inesperados = ctx.erros().filter((e) => !/Failed to load resource.*status of 500/.test(e));
  assert.deepEqual(inesperados, [], 'sem erros de script além do log de rede do 500 simulado');
}

/** A retentativa chegou à API falsa com a mesma chave da primeira tentativa e agora há agradecimento. */
async function exigirRetentativaComMesmaChave(ctx, chavePrimeira) {
  await ctx.clicar('#btn-enviar-comentario');
  await exigirAgradecimento(ctx);
  const chaves = ctx.apiFeedback.chaves();
  assert.equal(chaves.length, 2, 'duas requisições chegaram à API: a que falhou e a retentativa');
  assert.ok(chaves[0], 'a primeira requisição tem chave');
  assert.equal(chaves[1], chaves[0], 'a retentativa reaproveita a mesma chaveIdempotencia');
  if (chavePrimeira !== undefined) assert.equal(chaves[1], chavePrimeira);
  const comentarios = (await ctx.eventos()).filter((ev) => ev.tipo === 'comentario');
  assert.equal(comentarios.length, 1, 'um único evento "comentario", só depois do sucesso');
  assert.deepEqual(await ctx.feedbacksLocais(), []);
  assert.equal(ctx.api.requisicoes().length, 0, 'nada vai a api/chamados');
}

cenario('sucesso 201 sem corpo: um POST JSON com os 7 campos, sem repositório local e mesmo agradecimento',
  { modoApiFeedback: true, apiFeedback: { modo: 'sucesso' }, antes: ESPIAO },
  async (ctx) => {
    await ctx.abrir('#/');
    await escolherModelo(ctx, 'LOV');
    await abrirResolvido(ctx);
    await ctx.avaliar(() => document.querySelectorAll('#estrelas button')[3].click());
    await digitarEEnviar(ctx);
    await exigirAgradecimento(ctx);

    const reqs = ctx.apiFeedback.requisicoes();
    assert.equal(reqs.length, 1, 'uma única requisição à API de feedback');
    const req = reqs[0];
    assert.equal(req.metodo, 'POST');
    assert.match(req.cabecalhos['content-type'], /^application\/json/, 'Content-Type: application/json');
    assert.ok(req.json && typeof req.json === 'object', 'o corpo é JSON');
    assert.deepEqual(Object.keys(req.json).sort(), CAMPOS, 'exatamente os 7 campos do contrato');
    assert.equal(req.json.versaoContrato, D.FEEDBACK.config.VERSAO_CONTRATO_FEEDBACK);
    assert.match(req.json.chaveIdempotencia, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/, 'UUID v4');
    assert.match(req.json.enviadoEm, /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:\d{2}|Z)$/, 'ISO 8601 com fuso');
    assert.equal(req.json.comentario, COMENTARIO, 'texto literal, sem escape');
    assert.equal(req.json.nota, 4);
    assert.equal(req.json.problemaId, ID);
    assert.equal(req.json.modelo, 'lov');

    // Nada em repositório local: o Modo_API não grava o feedback.
    assert.deepEqual(await ctx.feedbacksLocais(), [], 'nenhum registro em tres-autoatendimento-feedbacks');
    assert.deepEqual(await ctx.chamadosLocais(), []);
    const eventos = await ctx.eventos();
    assert.equal(eventos.filter((ev) => ev.tipo === 'comentario').length, 1, 'um evento "comentario"');
    assert.equal(eventos.filter((ev) => ev.tipo === 'avaliacao').length, 1, 'só o evento da estrela, nenhum novo no envio');
    assert.equal(ctx.api.requisicoes().length, 0, 'nada vai a api/chamados');
    const rede = await ctx.avaliar('window.__rede');
    assert.equal(rede.length, 1, 'uma única chamada de rede feita pela página');
    ctx.semErros();
  });

cenario('falha 500: bloco de falha, texto preservado e nova tentativa com a mesma chaveIdempotencia',
  { modoApiFeedback: true, apiFeedback: { sequencia: ['erro500', 'sucesso'] }, antes: ESPIAO },
  async (ctx) => {
    await abrirResolvido(ctx);
    await digitarEEnviar(ctx);
    await exigirFalhaComTextoPreservado(ctx);
    assert.equal(ctx.apiFeedback.requisicoes().length, 1, 'sem retentativa automática');
    const chave = ctx.apiFeedback.chaves()[0];
    assert.ok(chave, 'a primeira tentativa levou a chave');

    await exigirRetentativaComMesmaChave(ctx, chave);
    exigirSemErrosInesperados(ctx);
  });

cenario('falha de rede: bloco de falha, texto preservado e nova tentativa com a mesma chaveIdempotencia',
  { modoApiFeedback: true, apiFeedback: { modo: 'sucesso' }, antes: ESPIAO },
  async (ctx) => {
    await abrirResolvido(ctx);
    await ctx.avaliar('window.__rejeitar = 1'); // o primeiro fetch rejeita como falha de rede
    await digitarEEnviar(ctx);
    await exigirFalhaComTextoPreservado(ctx);
    assert.equal(ctx.apiFeedback.requisicoes().length, 0, 'a requisição não chegou à API');
    const rede = await ctx.avaliar('window.__rede');
    assert.equal(rede.length, 1, 'uma tentativa, sem retentativa automática');
    const chaveEnviada = JSON.parse(rede[0].corpo).chaveIdempotencia;
    assert.ok(chaveEnviada, 'a tentativa que falhou levou a chave');

    await ctx.clicar('#btn-enviar-comentario');
    await exigirAgradecimento(ctx);
    assert.deepEqual(ctx.apiFeedback.chaves(), [chaveEnviada], 'a retentativa chegou à API com a mesma chaveIdempotencia');
    assert.equal(ctx.api.requisicoes().length, 0, 'nada vai a api/chamados');
    assert.deepEqual(await ctx.feedbacksLocais(), []);
    assert.equal((await ctx.eventos()).filter((ev) => ev.tipo === 'comentario').length, 1);
    ctx.semErros();
  });

cenario('tempo limite: API que não responde cai na falha (TIMEOUT_FEEDBACK_MS: 800) e a nova tentativa reaproveita a chave',
  { modoApiFeedback: true, apiFeedback: { modo: 'sem-resposta' }, configNumerica: { TIMEOUT_FEEDBACK_MS: 800 }, antes: ESPIAO },
  async (ctx) => {
    // O valor real (10 s) não cabe nos 4 s do cenário; o servidor de teste serve js/data.js com 800 ms em memória.
    await ctx.abrir(ROTA_RESOLVIDO);
    assert.equal(await ctx.avaliar('window.TRES_DATA.FEEDBACK.config.TIMEOUT_FEEDBACK_MS'), 800, 'override do tempo limite ativo');
    await ctx.esperar('!!document.querySelector("#form-feedback:not([hidden]) #f-comentario")', 1500, 'formulário do comentário');
    await digitarEEnviar(ctx);
    await ctx.esperar('document.querySelector("#btn-enviar-comentario").disabled', 1000, 'estado "Enviando"');
    await exigirFalhaComTextoPreservado(ctx);
    assert.equal(ctx.apiFeedback.requisicoes().length, 1, 'a requisição chegou à API, que não respondeu');
    const chave = ctx.apiFeedback.chaves()[0];
    assert.ok(chave);

    ctx.apiFeedback.definirApi({ modo: 'sucesso', sequencia: null });
    await exigirRetentativaComMesmaChave(ctx, chave);
    ctx.semErros();
  });

cenario('destino: com API_CHAMADOS_URL preenchida e API_FEEDBACK_URL vazia, nenhuma requisição vai a api/chamados nem a api/feedbacks',
  { modoApi: true, api: { modo: 'sucesso' }, apiFeedback: { modo: 'sucesso' }, antes: ESPIAO },
  async (ctx) => {
    assert.ok(ctx.api.apiUrl, 'a API falsa do chamado existe');
    await preencherChamadoEIrParaResolvido(ctx);
    assert.equal(
      await ctx.avaliar('window.TRES_DATA.CHAMADO.config.API_CHAMADOS_URL'), ctx.api.apiUrl,
      'API_CHAMADOS_URL preenchida (Modo_API do chamado)'
    );
    assert.equal(await ctx.avaliar('window.TRES_DATA.FEEDBACK.config.API_FEEDBACK_URL'), '', 'API_FEEDBACK_URL vazia');

    await digitarEEnviar(ctx);
    await exigirAgradecimento(ctx);

    assert.equal(ctx.api.requisicoes().length, 0, 'nenhuma requisição a api/chamados');
    assert.equal(ctx.api.outras().length, 0);
    assert.equal(ctx.apiFeedback.requisicoes().length, 0, 'nenhuma requisição a api/feedbacks');
    assert.equal(ctx.apiFeedback.outras().length, 0);
    assert.deepEqual(await ctx.avaliar('window.__rede'), [], 'a página não fez nenhuma requisição de rede');

    // Modo_Prototipo do feedback: o comentário foi para o repositório local, sem dados do chamado.
    const locais = await ctx.feedbacksLocais();
    assert.equal(locais.length, 1, 'um registro em tres-autoatendimento-feedbacks');
    assert.deepEqual(Object.keys(locais[0]).sort(), CAMPOS);
    assert.equal(locais[0].comentario, COMENTARIO);
    const gravado = JSON.stringify(locais);
    for (const valor of [PESSOAIS.nome, PESSOAIS.email, PESSOAIS.telefone, PESSOAIS.descricao]) {
      assert.ok(!gravado.includes(valor), 'o feedback gravado não pode conter "' + valor + '"');
    }
    assert.deepEqual(await ctx.chamadosLocais(), [], 'nenhum chamado foi aberto');
    ctx.semErros();
  });

cenario('privacidade: a API de feedback não recebe nome, e-mail nem telefone digitados no formulário do chamado',
  { modoApi: true, api: { modo: 'sucesso' }, modoApiFeedback: true, apiFeedback: { modo: 'sucesso' }, antes: ESPIAO },
  async (ctx) => {
    await preencherChamadoEIrParaResolvido(ctx);
    await digitarEEnviar(ctx);
    await exigirAgradecimento(ctx);

    const reqs = ctx.apiFeedback.requisicoes();
    assert.equal(reqs.length, 1, 'uma requisição a api/feedbacks');
    assert.deepEqual(Object.keys(reqs[0].json).sort(), CAMPOS, 'só os 7 campos do contrato');
    const tudo = reqs[0].corpoTexto + '\n' + JSON.stringify(reqs[0].cabecalhos) + '\n' + reqs[0].caminho;
    const digitosTel = PESSOAIS.telefone;
    for (const valor of [PESSOAIS.nome, PESSOAIS.email, digitosTel, PESSOAIS.descricao]) {
      assert.ok(!tudo.includes(valor), 'a requisição de feedback não pode conter "' + valor + '"');
    }
    assert.ok(!/maria|exemplo\.com|98765/i.test(tudo), 'nenhum fragmento dos dados pessoais na requisição');
    assert.equal(ctx.api.requisicoes().length, 0, 'nada vai a api/chamados');
    assert.equal(ctx.api.outras().length, 0);
    assert.deepEqual(await ctx.feedbacksLocais(), []);
    assert.equal(
      (await ctx.avaliar('window.__rede')).filter((r) => /api\/chamados/.test(r.url)).length, 0,
      'a página não chamou api/chamados'
    );
    ctx.semErros();
  });
