'use strict';
// Tarefa 12.7 - navegação entre a Tela_de_Chamado e a Tela_de_Confirmacao (Requisitos 1.7, 8.14, 8.15, 8.17, 8.18).
// Cenários curtos e independentes, em Modo_Prototipo (exceto os de envio em andamento do feedback, em Modo_API falso).
// Tarefa 10.14 (resolved-feedback-comment): navegação na Tela_de_Resolvido com o comentário (Requisitos 4.5, 7.8, 7.9, 7.10).
const assert = require('node:assert/strict');
const { cenario } = require('../cenarios');

const DADOS = {
  nome: 'Maria da Silva',
  email: 'Maria.Silva@Exemplo.com.br',
  telefone: '(11) 91234-5678',
  descricao: 'A máquina não liga mesmo depois de trocar a tomada.',
  aceite: true
};

const PROTOCOLO = /^TRES-\d{8}-[A-Z0-9]{6}$/;

/** Abre #/suporte/ID, preenche, envia e espera a confirmação. Devolve o protocolo exibido. */
async function abrirChamado(ctx, id) {
  await ctx.abrir('#/suporte/' + id);
  await ctx.esperar('(function(){var f=document.querySelector("#form-chamado");return !!f && !f.hidden;})()', 1500, 'formulário visível');
  await ctx.preencherFormulario(DADOS);
  await ctx.enviar();
  await ctx.esperar('location.hash === "#/chamado/' + id + '" && !document.querySelector("#view-chamado").hidden', 1500, 'confirmação do chamado ' + id);
  const protocolo = await ctx.lerTexto('#chamado-protocolo');
  assert.match(protocolo, PROTOCOLO);
  return protocolo;
}

/** Dois ids de problema distintos de js/data.js (só leitura). */
function doisProblemas(ctx) {
  return ctx.avaliar(() => {
    const ps = window.TRES_DATA.PROBLEMAS;
    return { a: { id: ps[0].id, titulo: ps[0].titulo }, b: { id: ps[1].id, titulo: ps[1].titulo } };
  });
}

/** Confere que a confirmação está visível com os dados do chamado já aberto. */
async function conferirConfirmacao(ctx, protocolo) {
  assert.ok(await ctx.visivel('#view-chamado'), 'a Tela_de_Confirmacao deve estar visível');
  assert.equal(await ctx.visivel('#view-suporte'), false, 'a Tela_de_Chamado deve ficar oculta');
  assert.equal(await ctx.lerTexto('#chamado-protocolo'), protocolo, 'o protocolo deve ser o mesmo');
  assert.equal(await ctx.lerTexto('#chamado-email'), 'maria.silva@exemplo.com.br');
  assert.equal(await ctx.lerTexto('#chamado-telefone'), '11912345678');
}

cenario('Voltar depois de abrir o chamado mostra a confirmação existente, sem formulário vazio nem novo chamado (8.14)', async (ctx) => {
  await ctx.abrir('#/');
  const { a } = await doisProblemas(ctx);
  const protocolo = await abrirChamado(ctx, a.id);

  // Sai da confirmação e volta pelo botão "voltar" do navegador.
  await ctx.abrir('#/problemas');
  await ctx.esperar('!document.querySelector("#view-problema").hidden', 1000, 'tela de problemas');
  await ctx.avaliar('history.back()');
  await ctx.esperar('location.hash === "#/chamado/' + a.id + '" && !document.querySelector("#view-chamado").hidden', 1500, 'voltar à confirmação');
  await conferirConfirmacao(ctx, protocolo);

  // Abrir a URL da Tela_de_Chamado do mesmo problema também leva à confirmação existente.
  await ctx.abrir('#/suporte/' + a.id);
  await ctx.esperar('location.hash === "#/chamado/' + a.id + '" && !document.querySelector("#view-chamado").hidden', 1500, 'redirecionar de #/suporte/ID para a confirmação');
  await conferirConfirmacao(ctx, protocolo);

  // Nenhum chamado novo: um único registro local e um único evento "chamado".
  const chamados = await ctx.chamadosLocais();
  assert.equal(chamados.length, 1);
  assert.equal(chamados[0].protocolo, protocolo);
  const eventos = await ctx.eventos();
  assert.equal(eventos.filter((e) => e && e.tipo === 'chamado').length, 1);
  assert.deepEqual(ctx.api.requisicoes(), []);
  ctx.semErros();
});

cenario('"Tenho outro problema" abre a seleção de problemas e mantém o chamado (8.17)', async (ctx) => {
  await ctx.abrir('#/');
  const { a } = await doisProblemas(ctx);
  const protocolo = await abrirChamado(ctx, a.id);
  const antes = await ctx.chamadosLocais();

  await ctx.clicar('#view-chamado a[href="#/problemas"]');
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1000, 'tela de seleção de problemas');
  assert.equal(await ctx.visivel('#view-chamado'), false);

  const depois = await ctx.chamadosLocais();
  assert.deepEqual(depois, antes, 'o chamado registrado não pode ser apagado nem alterado');
  assert.equal(depois.length, 1);
  assert.equal(depois[0].protocolo, protocolo);
  ctx.semErros();
});

cenario('"Voltar ao início" abre a tela inicial e mantém o chamado (8.18)', async (ctx) => {
  await ctx.abrir('#/');
  const { a } = await doisProblemas(ctx);
  const protocolo = await abrirChamado(ctx, a.id);
  const antes = await ctx.chamadosLocais();

  await ctx.clicar('#view-chamado a[href="#/"]');
  await ctx.esperar('(location.hash === "#/" || location.hash === "") && !document.querySelector("#view-modelo").hidden', 1000, 'tela inicial');
  assert.equal(await ctx.visivel('#view-chamado'), false);

  const depois = await ctx.chamadosLocais();
  assert.deepEqual(depois, antes, 'o chamado registrado não pode ser apagado nem alterado');
  assert.equal(depois[0].protocolo, protocolo);
  ctx.semErros();
});

cenario('Outro problema depois de abrir um chamado: formulário vazio, novo protocolo e chamado anterior intacto (8.15)', async (ctx) => {
  await ctx.abrir('#/');
  const { a, b } = await doisProblemas(ctx);
  assert.notEqual(a.id, b.id);
  const protocolo1 = await abrirChamado(ctx, a.id);
  const antes = await ctx.chamadosLocais();

  // "Tenho outro problema" e escolha de um problema diferente pela lista, como o consumidor faria.
  await ctx.clicar('#view-chamado a[href="#/problemas"]');
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1000, 'tela de problemas');
  await ctx.avaliar((titulo) => {
    const t = Array.from(document.querySelectorAll('.problema .problema__titulo'))
      .find((n) => n.textContent.trim() === titulo);
    t.closest('button').click();
  }, b.titulo);
  await ctx.esperar('location.hash === "#/solucao/' + b.id + '"', 1000, 'tela de solução do outro problema');
  await ctx.avaliar('location.hash = "#/confirma/' + b.id + '"');
  await ctx.esperar('!document.querySelector("#view-confirma").hidden', 1000, 'tela "O problema foi solucionado?"');
  await ctx.clicar('#btn-nao');
  await ctx.esperar('location.hash === "#/suporte/' + b.id + '" && !document.querySelector("#view-suporte").hidden', 1000, 'Tela_de_Chamado do outro problema');

  // Formulário vazio, aceite desmarcado, sem o protocolo anterior.
  for (const sel of ['#c-nome', '#c-email', '#c-telefone', '#c-descricao']) {
    assert.equal(await ctx.valor(sel), '', 'campo ' + sel + ' deve estar vazio');
  }
  assert.equal(await ctx.avaliar('document.querySelector("#c-aceite").checked'), false, 'aceite deve estar desmarcado');
  assert.equal(await ctx.visivel('#view-chamado'), false);
  const textoTela = await ctx.avaliar('document.querySelector("#view-suporte").textContent');
  assert.ok(!textoTela.includes(protocolo1), 'a Tela_de_Chamado não pode exibir o protocolo anterior');

  // Novo chamado: novo protocolo, e o primeiro continua como estava.
  await ctx.preencherFormulario(DADOS);
  await ctx.enviar();
  await ctx.esperar('location.hash === "#/chamado/' + b.id + '" && !document.querySelector("#view-chamado").hidden', 1500, 'confirmação do segundo chamado');
  const protocolo2 = await ctx.lerTexto('#chamado-protocolo');
  assert.match(protocolo2, PROTOCOLO);
  assert.notEqual(protocolo2, protocolo1, 'o novo chamado deve ter outro protocolo');

  const depois = await ctx.chamadosLocais();
  assert.equal(depois.length, 2);
  assert.deepEqual(depois[0], antes[0], 'o chamado anterior não pode ser alterado');
  assert.equal(depois[1].protocolo, protocolo2);
  assert.notEqual(depois[1].chaveIdempotencia, depois[0].chaveIdempotencia, 'o novo chamado deve ter outra chave de idempotência');
  ctx.semErros();
});

cenario('#/suporte/999 vai para #/problemas sem exibir a Tela_de_Chamado (1.7)', async (ctx) => {
  await ctx.abrir('#/suporte/999');
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1500, 'redirecionar para #/problemas');
  assert.equal(await ctx.visivel('#view-suporte'), false, 'nenhum conteúdo da Tela_de_Chamado');
  assert.equal(await ctx.visivel('#form-chamado'), false);
  assert.equal(await ctx.visivel('#view-chamado'), false);
  ctx.semErros();
});

cenario('#/suporte sem ID vai para #/problemas (1.7)', async (ctx) => {
  await ctx.abrir('#/suporte');
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1500, 'redirecionar para #/problemas');
  assert.equal(await ctx.visivel('#view-suporte'), false, 'nenhum conteúdo da Tela_de_Chamado');
  ctx.semErros();
});

cenario('#/chamado/999 vai para #/problemas sem exibir a confirmação (1.7)', async (ctx) => {
  await ctx.abrir('#/chamado/999');
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1500, 'redirecionar para #/problemas');
  assert.equal(await ctx.visivel('#view-chamado'), false, 'nenhum conteúdo da Tela_de_Confirmacao');
  assert.equal(await ctx.visivel('#view-suporte'), false);
  ctx.semErros();
});

// ---------------------------------------------------------------------------
// Tarefa 10.14 (resolved-feedback-comment) - botão voltar/avançar e rotas na Tela_de_Resolvido
// com o Formulario_de_Feedback (Requisitos 4.5, 7.8, 7.9, 7.10). Texto sem dados pessoais.
// ---------------------------------------------------------------------------

const COMENTARIO = 'O passo a passo resolveu em dois minutos.';
const COMENTARIO_2 = 'Segundo comentário, depois de recomeçar a jornada.';

/** Abre #/resolvido/ID e espera o formulário do comentário aparecer. */
async function abrirResolvido(ctx, id) {
  await ctx.abrir('#/resolvido/' + id);
  await esperarResolvido(ctx, id);
}

async function esperarResolvido(ctx, id) {
  await ctx.esperar(
    'location.hash === "#/resolvido/' + id + '" && !document.querySelector("#view-resolvido").hidden && ' +
      '(function(){var f=document.querySelector("#form-feedback");return !!f && !f.hidden;})()',
    1500, 'Tela_de_Resolvido com o formulário do comentário'
  );
}

/** Digita o comentário e toca em "Enviar comentário" (não espera a resposta). */
async function digitarEEnviarComentario(ctx, texto) {
  await ctx.digitar('#f-comentario', texto);
  await ctx.clicar('#btn-enviar-comentario');
}

/** Espera o estado "já enviado" (campo e botão desabilitados). */
function esperarEnviado(ctx) {
  return ctx.esperar(
    'document.querySelector("#f-comentario").disabled && document.querySelector("#btn-enviar-comentario").disabled && ' +
      'document.querySelector("#feedback-agradecimento").textContent.trim() !== ""',
    1500, 'estado "já enviado" do comentário'
  );
}

/** Retrato do formulário do comentário. */
function retratoFeedback(ctx) {
  return ctx.avaliar(() => {
    const c = document.querySelector('#f-comentario');
    const b = document.querySelector('#btn-enviar-comentario');
    const f = document.querySelector('#form-feedback');
    return {
      valor: c.value,
      campoDesabilitado: c.disabled,
      campoSomenteLeitura: c.readOnly,
      botaoDesabilitado: b.disabled,
      ocupado: f.getAttribute('aria-busy'),
      agradecimento: document.querySelector('#feedback-agradecimento').textContent.trim(),
      falha: !!document.querySelector('#feedback-falha-area .msg-falha'),
      erroVisivel: !document.querySelector('#f-comentario-erro').hidden
    };
  });
}

/** Confere o formulário no estado inicial: vazio, editável, botão ativo, sem agradecimento nem erro. */
async function conferirFormularioVazio(ctx) {
  const r = await retratoFeedback(ctx);
  assert.equal(r.valor, '', 'o campo deve estar vazio');
  assert.equal(r.campoDesabilitado, false, 'o campo deve estar habilitado');
  assert.equal(r.campoSomenteLeitura, false);
  assert.equal(r.botaoDesabilitado, false, 'o botão deve estar habilitado');
  assert.equal(r.ocupado, null, 'sem aria-busy');
  assert.equal(r.agradecimento, '', 'sem agradecimento');
  assert.equal(r.falha, false);
  assert.equal(r.erroVisivel, false);
}

/** Confere o estado "já enviado" com o comentário enviado exibido. */
async function conferirJaEnviado(ctx, texto) {
  const r = await retratoFeedback(ctx);
  assert.equal(r.valor, texto, 'o comentário enviado deve aparecer no campo');
  assert.equal(r.campoDesabilitado, true, 'o campo deve ficar desabilitado');
  assert.equal(r.botaoDesabilitado, true, 'o botão deve ficar desabilitado');
  assert.equal(r.ocupado, null);
  assert.notEqual(r.agradecimento, '', 'o agradecimento deve aparecer');
  assert.equal(r.falha, false);
}

const comentariosGravados = (ctx) => ctx.eventos().then((ev) => ev.filter((e) => e && e.tipo === 'comentario'));

/** "Tenho outro problema" na Tela_de_Resolvido, escolhe o problema pelo título e segue até "Sim, resolvi". */
async function recomecarJornada(ctx, titulo, id) {
  await ctx.clicar('#view-resolvido a[href="#/problemas"]');
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1000, 'tela de problemas');
  await ctx.avaliar((t) => {
    const n = Array.from(document.querySelectorAll('.problema .problema__titulo')).find((x) => x.textContent.trim() === t);
    n.closest('button').click();
  }, titulo);
  await ctx.esperar('location.hash === "#/solucao/' + id + '"', 1000, 'tela de solução');
  await ctx.avaliar('location.hash = "#/confirma/' + id + '"');
  await ctx.esperar('!document.querySelector("#view-confirma").hidden', 1000, 'tela "O problema foi solucionado?"');
  await ctx.clicar('#btn-sim');
  await esperarResolvido(ctx, id);
}

cenario('Voltar e avançar do navegador depois do envio mostram o estado "já enviado", sem novo registro (7.8)', async (ctx) => {
  await ctx.abrir('#/');
  const { a } = await doisProblemas(ctx);
  await abrirResolvido(ctx, a.id);
  await digitarEEnviarComentario(ctx, COMENTARIO);
  await esperarEnviado(ctx);

  // Sai da tela e volta pelo botão "voltar" do navegador.
  await ctx.abrir('#/problemas');
  await ctx.esperar('!document.querySelector("#view-problema").hidden', 1000, 'tela de problemas');
  await ctx.avaliar('history.back()');
  await esperarResolvido(ctx, a.id);
  await conferirJaEnviado(ctx, COMENTARIO);

  // "Avançar" depois de voltar mais uma vez, e de novo "voltar".
  await ctx.avaliar('history.forward()');
  await ctx.esperar('location.hash === "#/problemas"', 1000, 'avançar para os problemas');
  await ctx.avaliar('history.back()');
  await esperarResolvido(ctx, a.id);
  await conferirJaEnviado(ctx, COMENTARIO);

  // Mesma jornada: sair para a confirmação e responder "Sim" de novo também mostra "já enviado".
  await ctx.avaliar('location.hash = "#/confirma/' + a.id + '"');
  await ctx.esperar('!document.querySelector("#view-confirma").hidden', 1000, 'tela "O problema foi solucionado?"');
  await ctx.clicar('#btn-sim');
  await esperarResolvido(ctx, a.id);
  await conferirJaEnviado(ctx, COMENTARIO);

  // Nenhum envio novo: um registro, um evento "comentario".
  const gravados = await ctx.feedbacksLocais();
  assert.equal(gravados.length, 1);
  assert.equal(gravados[0].comentario, COMENTARIO);
  assert.equal((await comentariosGravados(ctx)).length, 1);
  assert.deepEqual(ctx.api.requisicoes(), []);
  ctx.semErros();
});

for (const [rotulo, indice] of [['o mesmo problema', 'a'], ['outro problema', 'b']]) {
  cenario('Escolher ' + rotulo + ' na lista depois do envio zera o estado: campo vazio e novo envio permitido (7.9)', async (ctx) => {
    await ctx.abrir('#/');
    const dois = await doisProblemas(ctx);
    const { a } = dois;
    const alvo = dois[indice];
    await abrirResolvido(ctx, a.id);
    await digitarEEnviarComentario(ctx, COMENTARIO);
    await esperarEnviado(ctx);

    await recomecarJornada(ctx, alvo.titulo, alvo.id);
    await conferirFormularioVazio(ctx);
    assert.equal(await ctx.lerTexto('#f-comentario-contador'), '0 de 500 caracteres');

    // Nova jornada: um segundo comentário é aceito, com outra chave de idempotência.
    await digitarEEnviarComentario(ctx, COMENTARIO_2);
    await esperarEnviado(ctx);
    const gravados = await ctx.feedbacksLocais();
    assert.equal(gravados.length, 2);
    assert.equal(gravados[0].comentario, COMENTARIO);
    assert.equal(gravados[1].comentario, COMENTARIO_2);
    assert.equal(gravados[1].problemaId, alvo.id);
    assert.notEqual(gravados[1].chaveIdempotencia, gravados[0].chaveIdempotencia, 'a nova jornada usa outra chave');
    assert.equal((await comentariosGravados(ctx)).length, 2);
    ctx.semErros();
  });
}

cenario('Sair sem enviar e voltar mostra o campo vazio, sem registro nem evento (7.8, 7.10)', async (ctx) => {
  await ctx.abrir('#/');
  const { a } = await doisProblemas(ctx);
  await abrirResolvido(ctx, a.id);
  await ctx.digitar('#f-comentario', 'Rascunho que não deve voltar.');
  assert.equal(await ctx.valor('#f-comentario'), 'Rascunho que não deve voltar.');

  await ctx.abrir('#/problemas');
  await ctx.esperar('!document.querySelector("#view-problema").hidden', 1000, 'tela de problemas');
  await ctx.avaliar('history.back()');
  await esperarResolvido(ctx, a.id);
  await conferirFormularioVazio(ctx);
  assert.equal(await ctx.lerTexto('#f-comentario-contador'), '0 de 500 caracteres');

  assert.deepEqual(await ctx.feedbacksLocais(), []);
  assert.deepEqual(await comentariosGravados(ctx), []);
  ctx.semErros();
});

cenario('Recarregar a página depois do envio zera o estado em memória (7.10)', async (ctx) => {
  await ctx.abrir('#/');
  const { a } = await doisProblemas(ctx);
  await abrirResolvido(ctx, a.id);
  await digitarEEnviarComentario(ctx, COMENTARIO);
  await esperarEnviado(ctx);
  const antes = await ctx.feedbacksLocais();
  assert.equal(antes.length, 1);

  await ctx.recarregar();
  await esperarResolvido(ctx, a.id);
  await conferirFormularioVazio(ctx);

  // O que já foi gravado continua gravado; o consumidor pode enviar de novo, com outra chave.
  assert.deepEqual(await ctx.feedbacksLocais(), antes);
  await digitarEEnviarComentario(ctx, COMENTARIO_2);
  await esperarEnviado(ctx);
  const depois = await ctx.feedbacksLocais();
  assert.equal(depois.length, 2);
  assert.notEqual(depois[1].chaveIdempotencia, depois[0].chaveIdempotencia);
  ctx.semErros();
});

cenario('Sair da rota com o envio em andamento: o resultado chega fora da tela e ao voltar aparece "já enviado" (7.8)',
  { modoApiFeedback: true, apiFeedback: { modo: 'lento', atraso: 700 } },
  async (ctx) => {
    await ctx.abrir('#/');
    const { a } = await doisProblemas(ctx);
    await abrirResolvido(ctx, a.id);
    await digitarEEnviarComentario(ctx, COMENTARIO);
    await ctx.esperar('document.querySelector("#form-feedback").getAttribute("aria-busy") === "true"', 1000, 'envio em andamento');

    // Sai antes da resposta.
    await ctx.abrir('#/problemas');
    await ctx.esperar('!document.querySelector("#view-problema").hidden', 1000, 'tela de problemas');

    // A resposta chega com o consumidor em outra tela: a métrica é gravada, mas a tela não é mexida.
    await ctx.esperar('JSON.parse(localStorage.getItem("tres-autoatendimento-eventos")||"[]").some(function(e){return e.tipo==="comentario";})', 1500, 'evento comentario depois da resposta');
    assert.equal(await ctx.hash(), '#/problemas');
    assert.ok(await ctx.visivel('#view-problema'));
    assert.equal(await ctx.visivel('#view-resolvido'), false, 'a tela de resolvido não pode reaparecer sozinha');
    const foco = await ctx.foco();
    assert.notEqual(foco && foco.id, 'feedback-agradecimento', 'o foco não pode ser roubado pelo agradecimento');

    // Ao voltar: já enviado, sem reenvio.
    await ctx.avaliar('history.back()');
    await esperarResolvido(ctx, a.id);
    await conferirJaEnviado(ctx, COMENTARIO);
    assert.equal(ctx.apiFeedback.requisicoes().length, 1, 'uma única requisição');
    assert.equal((await comentariosGravados(ctx)).length, 1);
    assert.deepEqual(await ctx.feedbacksLocais(), [], 'Modo_API não grava no repositório local');
    ctx.semErros();
  });

cenario('Voltar à rota antes da resposta mantém o estado "enviando" e depois vira "já enviado", sem segundo envio (7.8)',
  { modoApiFeedback: true, apiFeedback: { modo: 'lento', atraso: 700 } },
  async (ctx) => {
    await ctx.abrir('#/');
    const { a } = await doisProblemas(ctx);
    await abrirResolvido(ctx, a.id);
    await digitarEEnviarComentario(ctx, COMENTARIO);
    await ctx.esperar('document.querySelector("#form-feedback").getAttribute("aria-busy") === "true"', 1000, 'envio em andamento');

    await ctx.abrir('#/problemas');
    await ctx.esperar('!document.querySelector("#view-problema").hidden', 1000, 'tela de problemas');
    await ctx.avaliar('history.back()');
    await esperarResolvido(ctx, a.id);

    // Ainda sem resposta: continua "enviando", com o texto preservado e sem permitir novo toque.
    const r = await retratoFeedback(ctx);
    assert.equal(r.ocupado, 'true');
    assert.equal(r.valor, COMENTARIO);
    assert.equal(r.campoSomenteLeitura, true);
    assert.equal(r.botaoDesabilitado, true);
    await ctx.clicar('#btn-enviar-comentario', 2);

    await esperarEnviado(ctx);
    await conferirJaEnviado(ctx, COMENTARIO);
    assert.equal(ctx.apiFeedback.requisicoes().length, 1, 'uma única requisição');
    assert.equal((await comentariosGravados(ctx)).length, 1);
    ctx.semErros();
  });

cenario('#/chamado/ID sem chamado aberto volta ao formulário vazio de #/suporte/ID', async (ctx) => {
  await ctx.abrir('#/');
  const { a } = await doisProblemas(ctx);
  await ctx.abrir('#/chamado/' + a.id);
  await ctx.esperar('location.hash === "#/suporte/' + a.id + '" && !document.querySelector("#view-suporte").hidden', 1500, 'voltar para o formulário');
  assert.ok(await ctx.visivel('#form-chamado'), 'o formulário deve estar visível');
  assert.equal(await ctx.visivel('#view-chamado'), false, 'a confirmação não pode aparecer sem chamado');
  assert.equal(await ctx.valor('#c-nome'), '');
  assert.deepEqual(await ctx.chamadosLocais(), []);
  ctx.semErros();
});
