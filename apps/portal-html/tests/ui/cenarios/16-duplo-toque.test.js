'use strict';
// Tarefa 12.6 - duplo toque em "Abrir meu chamado" (Requisito 7.13).
// Dois acionamentos rápidos da mesma jornada geram uma única requisição e um único chamado.
const assert = require('node:assert/strict');
const { cenario } = require('../cenarios');

const DADOS = {
  nome: 'Maria da Silva',
  email: 'maria@exemplo.com.br',
  telefone: '(11) 91234-5678',
  descricao: 'A máquina não liga mesmo depois de trocar a tomada.',
  aceite: true
};

async function abrirFormularioPreenchido(ctx) {
  await ctx.abrir('#/suporte/1');
  await ctx.esperar('(function(){var f=document.querySelector("#form-chamado");return !!f && !f.hidden;})()', 1500, 'formulário visível');
  await ctx.preencherFormulario(DADOS);
}

cenario(
  'Modo_API: dois cliques no mesmo instante geram uma única requisição e um único chamado',
  { modoApi: true, api: { modo: 'lenta', atraso: 400 } },
  async (ctx) => {
    await abrirFormularioPreenchido(ctx);

    // Dois cliques na mesma tarefa do navegador, sem nenhuma pausa entre eles.
    await ctx.avaliar(function () {
      var b = document.querySelector('#btn-abrir-chamado');
      b.click();
      b.click();
    });

    // Durante o envio: botão desabilitado, texto "Enviando" e aria-busy.
    assert.equal(await ctx.avaliar('document.querySelector("#btn-abrir-chamado").disabled'), true, 'botão deve ficar desabilitado durante o envio');
    assert.match(await ctx.lerTexto('#btn-abrir-chamado'), /Enviando/i);
    assert.equal(await ctx.atributo('#form-chamado', 'aria-busy'), 'true');

    // Um terceiro toque com o envio ainda em andamento também é ignorado.
    await ctx.clicar('#btn-abrir-chamado');

    await ctx.esperar(function () { return location.hash.indexOf('#/chamado/') === 0; }, 2500, 'ir para #/chamado/ID');

    assert.equal(ctx.api.requisicoes().length, 1, 'a API deve receber exatamente uma requisição');
    assert.equal(ctx.api.chaves().length, 1);
    assert.deepEqual(ctx.api.outras(), []);

    const eventos = await ctx.eventos();
    assert.equal(eventos.filter((e) => e && e.tipo === 'chamado').length, 1, 'deve haver um único evento "chamado"');
    assert.deepEqual(await ctx.chamadosLocais(), [], 'Modo_API não grava chamado local');
    assert.equal(ctx.api.requisicoes().length, 1, 'nenhuma requisição extra depois da confirmação');
    ctx.semErros();
  }
);

cenario('Modo_API: Enter no campo durante o envio também não gera segunda requisição', { modoApi: true, api: { modo: 'lenta', atraso: 400 } }, async (ctx) => {
  await abrirFormularioPreenchido(ctx);

  await ctx.enviar();
  // Submissão pelo teclado (Enter em campo de texto) enquanto o primeiro envio segue em andamento.
  await ctx.digitar('#c-nome', DADOS.nome);
  await ctx.teclar('Enter');

  await ctx.esperar(function () { return location.hash.indexOf('#/chamado/') === 0; }, 2500, 'ir para #/chamado/ID');
  assert.equal(ctx.api.requisicoes().length, 1, 'a API deve receber exatamente uma requisição');
  ctx.semErros();
});

cenario('Modo_Prototipo: dois cliques rápidos gravam um único chamado, com um único protocolo', async (ctx) => {
  await abrirFormularioPreenchido(ctx);

  await ctx.avaliar(function () {
    var b = document.querySelector('#btn-abrir-chamado');
    b.click();
    b.click();
  });

  await ctx.esperar(function () { return location.hash.indexOf('#/chamado/') === 0; }, 2500, 'ir para #/chamado/ID');

  const chamados = await ctx.chamadosLocais();
  assert.equal(chamados.length, 1, 'o repositório local deve ter um único chamado');
  const eventos = await ctx.eventos();
  assert.equal(eventos.filter((e) => e && e.tipo === 'chamado').length, 1, 'deve haver um único evento "chamado"');
  assert.deepEqual(ctx.api.requisicoes(), [], 'sem API configurada, nenhuma requisição é feita');
  ctx.semErros();
});

// ---------------------------------------------------------------------------
// resolved-feedback-comment 10.13 (Requisito 7.3): duplo toque em "Enviar comentário".
// Toques repetidos geram no máximo um registro (Modo_Prototipo) ou uma requisição (Modo_API),
// um único evento `comentario`, e o botão fica desabilitado depois do envio.
// ---------------------------------------------------------------------------

const COMENTARIO = 'O passo a passo resolveu rápido.';

/** Chega a #/resolvido/1 pelo caminho do consumidor e digita o comentário. */
async function abrirResolvidoComComentario(ctx) {
  await ctx.abrir('#/');
  await ctx.avaliar('location.hash = "#/confirma/1"');
  await ctx.esperar('!document.querySelector("#view-confirma").hidden', 1000, 'tela "O problema foi solucionado?"');
  await ctx.clicar('#btn-sim');
  await ctx.esperar('location.hash === "#/resolvido/1" && !document.querySelector("#view-resolvido").hidden', 1000, 'tela de problema resolvido');
  await ctx.esperar('!document.querySelector("#form-feedback").hidden', 500, 'formulário de comentário visível');
  await ctx.digitar('#f-comentario', COMENTARIO);
}

const eventosComentario = async (ctx) => (await ctx.eventos()).filter((e) => e && e.tipo === 'comentario');
const agradecimentoVisivel = 'document.querySelector("#feedback-agradecimento").textContent.trim().length > 0';

cenario('Modo_Prototipo: dois cliques rápidos em "Enviar comentário" gravam um único feedback e um único evento', async (ctx) => {
  await abrirResolvidoComComentario(ctx);

  // Dois cliques na mesma tarefa do navegador, sem pausa entre eles.
  await ctx.avaliar(function () {
    var b = document.querySelector('#btn-enviar-comentario');
    b.click();
    b.click();
  });
  await ctx.esperar(agradecimentoVisivel, 1000, 'agradecimento do comentário');

  // Toques depois do envio também são ignorados.
  await ctx.clicar('#btn-enviar-comentario', 2);
  await ctx.avaliar('document.querySelector("#form-feedback").requestSubmit()');

  const regs = await ctx.feedbacksLocais();
  assert.equal(regs.length, 1, 'o repositório de feedbacks deve ter um único registro');
  assert.equal(regs[0].comentario, COMENTARIO);
  assert.equal((await eventosComentario(ctx)).length, 1, 'deve haver um único evento "comentario"');
  assert.deepEqual(ctx.apiFeedback.requisicoes(), [], 'sem API de feedback configurada, nenhuma requisição é feita');
  assert.equal(await ctx.avaliar('document.querySelector("#btn-enviar-comentario").disabled'), true, 'botão desabilitado depois do envio');
  assert.equal(await ctx.avaliar('document.querySelector("#f-comentario").disabled'), true, 'campo desabilitado depois do envio');
  ctx.semErros();
});

cenario(
  'Modo_API: dois cliques no mesmo instante em "Enviar comentário" geram uma única requisição e um único evento',
  { modoApiFeedback: true, apiFeedback: { modo: 'lento', atraso: 400 } },
  async (ctx) => {
    await abrirResolvidoComComentario(ctx);

    await ctx.avaliar(function () {
      var b = document.querySelector('#btn-enviar-comentario');
      b.click();
      b.click();
    });

    // Durante o envio: botão desabilitado, texto "Enviando" e aria-busy.
    assert.equal(await ctx.avaliar('document.querySelector("#btn-enviar-comentario").disabled'), true, 'botão desabilitado durante o envio');
    assert.match(await ctx.lerTexto('#btn-enviar-comentario'), /Enviando/i);
    assert.equal(await ctx.atributo('#form-feedback', 'aria-busy'), 'true');

    // Um terceiro toque, por clique e por submissão, com o envio em andamento, também é ignorado.
    await ctx.clicar('#btn-enviar-comentario');
    await ctx.avaliar('document.querySelector("#form-feedback").requestSubmit()');

    await ctx.esperar(agradecimentoVisivel, 2500, 'agradecimento do comentário');

    assert.equal(ctx.apiFeedback.requisicoes().length, 1, 'a API de feedback deve receber exatamente uma requisição');
    assert.equal(ctx.apiFeedback.chaves().length, 1);
    assert.deepEqual(ctx.apiFeedback.outras(), []);
    assert.deepEqual(ctx.api.requisicoes(), [], 'nenhuma requisição ao endpoint de chamados');
    assert.equal((await eventosComentario(ctx)).length, 1, 'deve haver um único evento "comentario"');
    assert.deepEqual(await ctx.feedbacksLocais(), [], 'Modo_API não grava feedback local');
    assert.equal(await ctx.avaliar('document.querySelector("#btn-enviar-comentario").disabled'), true, 'botão desabilitado depois do envio');

    // Toque depois do envio: nenhuma requisição extra.
    await ctx.clicar('#btn-enviar-comentario');
    assert.equal(ctx.apiFeedback.requisicoes().length, 1, 'nenhuma requisição extra depois da confirmação');
    ctx.semErros();
  }
);

cenario(
  'Modo_API: Enter repetido no botão "Enviar comentário" não gera segunda requisição',
  { modoApiFeedback: true, apiFeedback: { modo: 'lento', atraso: 400 } },
  async (ctx) => {
    await abrirResolvidoComComentario(ctx);

    await ctx.avaliar('document.querySelector("#btn-enviar-comentario").focus()');
    assert.equal((await ctx.foco()).id, 'btn-enviar-comentario');

    // Enter no botão envia; Enter de novo com o envio em andamento é ignorado.
    await ctx.teclar('Enter');
    await ctx.teclar('Enter');
    await ctx.teclar('Enter');

    await ctx.esperar(agradecimentoVisivel, 2500, 'agradecimento do comentário');
    assert.equal(ctx.apiFeedback.requisicoes().length, 1, 'a API de feedback deve receber exatamente uma requisição');
    assert.equal((await eventosComentario(ctx)).length, 1, 'deve haver um único evento "comentario"');
    assert.equal(await ctx.avaliar('document.querySelector("#btn-enviar-comentario").disabled'), true, 'botão desabilitado depois do envio');
    ctx.semErros();
  }
);
