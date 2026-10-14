'use strict';
// Tarefa 12.9 - texto literal (Requisito 10.9).
// O que o consumidor digita (<b>x</b>, <img src=x onerror=alert(1)>) aparece como texto e
// é gravado como texto; nenhum elemento HTML é criado a partir dele e nenhum script roda.
const assert = require('node:assert/strict');
const { cenario } = require('../cenarios');

const HTML_B = '<b>x</b>';
const HTML_IMG = '<img src=x onerror=alert(1)>';

/** Abre a Tela_de_Chamado e instrumenta a página: conta elementos de risco e intercepta alert. */
async function abrirFormulario(ctx) {
  await ctx.abrir('#/suporte/1');
  await ctx.esperar('(function(){var f=document.querySelector("#form-chamado");return !!f && !f.hidden;})()', 1500, 'formulário visível');
  await ctx.avaliar(function () {
    window.__alertas = [];
    window.alert = function (m) { window.__alertas.push(String(m)); };
    window.__antes = {
      b: document.querySelectorAll('b').length,
      img: document.querySelectorAll('img').length,
      script: document.querySelectorAll('script').length,
      onerror: document.querySelectorAll('[onerror]').length
    };
  });
}

/** Nada foi criado a partir do texto digitado e nenhum alert foi disparado. */
async function exigirSemElementosNovos(ctx, onde) {
  // Dá tempo a uma imagem <img src=x> (se existisse) falhar e disparar onerror.
  await ctx.avaliar(() => new Promise((r) => setTimeout(r, 150)));
  const r = await ctx.avaliar(function () {
    return {
      alertas: window.__alertas,
      antes: window.__antes,
      depois: {
        b: document.querySelectorAll('b').length,
        img: document.querySelectorAll('img').length,
        script: document.querySelectorAll('script').length,
        onerror: document.querySelectorAll('[onerror]').length
      },
      imgX: document.querySelectorAll('img[src="x"]').length
    };
  });
  assert.deepEqual(r.depois, r.antes, onde + ': nenhum elemento b/img/script/[onerror] pode ser criado pelo texto digitado');
  assert.equal(r.imgX, 0, onde + ': nenhuma <img src="x">');
  assert.deepEqual(r.alertas, [], onde + ': alert(1) não pode ter sido executado');
}

/** Os controles do formulário guardam exatamente o que foi digitado. */
async function exigirCamposLiterais(ctx, nome, descricao) {
  assert.equal(await ctx.valor('#c-nome'), nome, 'o campo nome mostra o texto digitado');
  assert.equal(await ctx.valor('#c-descricao'), descricao, 'o campo descrição mostra o texto digitado');
  assert.equal(await ctx.contar('#form-chamado b, #form-chamado img'), 0, 'o formulário não contém b nem img');
}

const EMAIL = 'maria@exemplo.com.br';
const TELEFONE = '(11) 91234-5678';

cenario('Modo_Prototipo: <b> no nome e <img onerror> na descrição ficam como texto na tela, na confirmação e no armazenamento', async (ctx) => {
  await abrirFormulario(ctx);
  await ctx.preencherFormulario({ nome: HTML_B, email: EMAIL, telefone: TELEFONE, descricao: HTML_IMG, aceite: true });

  await exigirCamposLiterais(ctx, HTML_B, HTML_IMG);
  assert.equal(await ctx.lerTexto('#c-descricao-contador'), HTML_IMG.length + ' de 500 caracteres');
  await exigirSemElementosNovos(ctx, 'formulário preenchido');

  await ctx.enviar();
  await ctx.esperar('location.hash === "#/chamado/1" && !document.querySelector("#view-chamado").hidden', 1000, 'Tela_de_Confirmacao');
  await exigirSemElementosNovos(ctx, 'confirmação');
  assert.equal(await ctx.contar('#view-chamado b, #view-chamado img'), 0, 'a confirmação não contém b nem img');

  // O texto digitado não aparece como marcação em lugar nenhum do corpo da página.
  const html = await ctx.avaliar('document.body.innerHTML');
  assert.ok(!html.includes(HTML_B), 'o HTML do corpo não pode conter <b>x</b> como marcação');
  assert.ok(!html.includes('<img src=x'), 'o HTML do corpo não pode conter a marcação <img src=x');

  // Armazenamento: o chamado guarda o texto exatamente como digitado.
  const chamados = await ctx.chamadosLocais();
  assert.equal(chamados.length, 1);
  assert.equal(chamados[0].nome, HTML_B);
  assert.equal(chamados[0].descricao, HTML_IMG);

  ctx.semErros();
});

cenario('Modo_Prototipo: <img onerror> no nome e <b> na descrição ficam como texto (valores trocados)', async (ctx) => {
  const descricao = 'Texto com ' + HTML_B + ' no meio e ' + HTML_IMG + ' no fim';
  await abrirFormulario(ctx);
  await ctx.preencherFormulario({ nome: HTML_IMG, email: EMAIL, telefone: TELEFONE, descricao: descricao, aceite: true });

  await exigirCamposLiterais(ctx, HTML_IMG, descricao);
  await exigirSemElementosNovos(ctx, 'formulário preenchido');

  await ctx.enviar();
  await ctx.esperar('location.hash === "#/chamado/1" && !document.querySelector("#view-chamado").hidden', 1000, 'Tela_de_Confirmacao');
  await exigirSemElementosNovos(ctx, 'confirmação');

  const chamados = await ctx.chamadosLocais();
  assert.equal(chamados.length, 1);
  assert.equal(chamados[0].nome, HTML_IMG);
  assert.equal(chamados[0].descricao, descricao);

  ctx.semErros();
});

cenario('Modo_Prototipo: mensagens de erro de validação não transformam o texto digitado em elementos', async (ctx) => {
  await abrirFormulario(ctx);
  // E-mail inválido de propósito: o envio é recusado e as mensagens de erro aparecem.
  await ctx.preencherFormulario({ nome: HTML_B, email: HTML_IMG, telefone: HTML_B, descricao: HTML_IMG, aceite: true });
  await ctx.enviar();
  await ctx.esperar('!document.querySelector("#c-email-erro").hidden', 1000, 'erro do e-mail');

  assert.notEqual(await ctx.hash(), '#/chamado/1', 'com dados inválidos não há confirmação');
  assert.equal(await ctx.valor('#c-email'), HTML_IMG, 'o campo mantém o texto digitado');
  await exigirSemElementosNovos(ctx, 'formulário com erros');
  assert.equal(await ctx.contar('#form-chamado b, #form-chamado img'), 0);
  assert.deepEqual(await ctx.chamadosLocais(), [], 'nada é gravado com dados inválidos');

  ctx.semErros();
});

// ---------------------------------------------------------------------------
// resolved-feedback-comment 10.9 (Requisitos 6.3, 6.4, 6.5): comentário da Tela_de_Resolvido
// ---------------------------------------------------------------------------

/** Contagem de elementos de risco em #view-resolvido e no documento inteiro. */
const CONTAR_RISCO = function () {
  const conta = (raiz) => ({
    b: raiz.querySelectorAll('b').length,
    img: raiz.querySelectorAll('img').length,
    script: raiz.querySelectorAll('script').length,
    onerror: raiz.querySelectorAll('[onerror]').length
  });
  return {
    resolvido: conta(document.querySelector('#view-resolvido')),
    documento: conta(document)
  };
};

/** Chega a #/resolvido/1 pelo caminho do consumidor e instrumenta a página. */
async function abrirResolvido(ctx) {
  await ctx.abrir('#/');
  await ctx.avaliar('location.hash = "#/confirma/1"');
  await ctx.esperar('!document.querySelector("#view-confirma").hidden', 1000, 'tela "O problema foi solucionado?"');
  await ctx.clicar('#btn-sim');
  await ctx.esperar('location.hash === "#/resolvido/1" && !document.querySelector("#view-resolvido").hidden', 1000, 'tela de problema resolvido');
  await ctx.esperar('!document.querySelector("#form-feedback").hidden', 500, 'formulário de comentário visível');
  await ctx.avaliar(function (contar) {
    window.__alertas = [];
    window.alert = function (m) { window.__alertas.push(String(m)); };
    window.__antes = (0, eval)('(' + contar + ')')();
  }, CONTAR_RISCO.toString());
}

/** Nenhum elemento novo em #view-resolvido nem no documento e nenhum alert disparado. */
async function exigirResolvidoSemElementosNovos(ctx, onde) {
  // Dá tempo a uma <img src=x> (se existisse) falhar e disparar onerror.
  await ctx.avaliar(() => new Promise((r) => setTimeout(r, 150)));
  const r = await ctx.avaliar(function (contar) {
    return {
      alertas: window.__alertas,
      antes: window.__antes,
      depois: (0, eval)('(' + contar + ')')(),
      imgX: document.querySelectorAll('img[src="x"]').length
    };
  }, CONTAR_RISCO.toString());
  assert.deepEqual(r.depois.resolvido, r.antes.resolvido, onde + ': nenhum b/img/script/[onerror] novo em #view-resolvido');
  assert.deepEqual(r.depois.documento, r.antes.documento, onde + ': nenhum b/img/script/[onerror] novo no documento');
  assert.equal(r.imgX, 0, onde + ': nenhuma <img src="x">');
  assert.deepEqual(r.alertas, [], onde + ': alert(1) não pode ter sido executado');
}

cenario('Tela_de_Resolvido: <b> e <img onerror> no comentário ficam como texto no campo travado e no armazenamento, sem criar elementos', async (ctx) => {
  const comentario = HTML_B + ' ' + HTML_IMG + ' & "aspas" \'simples\' \\ </textarea><script>alert(1)</script>';
  await abrirResolvido(ctx);

  await ctx.digitar('#f-comentario', comentario);
  assert.equal(await ctx.valor('#f-comentario'), comentario, 'o campo mostra o texto digitado');
  assert.equal(await ctx.lerTexto('#f-comentario-contador'), comentario.length + ' de 500 caracteres');
  await exigirResolvidoSemElementosNovos(ctx, 'comentário digitado');

  await ctx.clicar('#btn-enviar-comentario');
  await ctx.esperar('document.querySelector("#feedback-agradecimento").textContent.trim().length > 0', 500, 'agradecimento do comentário');

  // Campo travado: continua mostrando exatamente o texto enviado.
  const campo = await ctx.avaliar(function () {
    const c = document.querySelector('#f-comentario');
    return { valor: c.value, desabilitado: c.disabled, filhos: c.children.length, html: c.innerHTML };
  });
  assert.equal(campo.desabilitado, true, 'o campo fica travado depois do envio');
  assert.equal(campo.valor, comentario, 'o campo travado mostra o texto digitado');
  assert.equal(campo.filhos, 0, 'o campo não ganha elementos filhos');
  await exigirResolvidoSemElementosNovos(ctx, 'depois do envio');
  assert.equal(await ctx.contar('#view-resolvido b, #view-resolvido img'), 0, '#view-resolvido não contém b nem img');
  assert.equal(await ctx.contar('#view-resolvido script'), 0, '#view-resolvido não contém script');

  // O texto não aparece como marcação em nenhum lugar do corpo da página.
  const html = await ctx.avaliar('document.body.innerHTML');
  assert.ok(!html.includes(HTML_B), 'o HTML do corpo não pode conter <b>x</b> como marcação');
  assert.ok(!html.includes('<img src=x'), 'o HTML do corpo não pode conter a marcação <img src=x');
  assert.ok(!html.includes('<script>alert(1)'), 'o HTML do corpo não pode conter <script>alert(1)');

  // Armazenamento: o registro guarda o texto exatamente como digitado (sem escapar nem remover).
  const regs = await ctx.feedbacksLocais();
  assert.equal(regs.length, 1);
  assert.equal(regs[0].comentario, comentario);
  assert.equal(await ctx.avaliar('localStorage.getItem("tres-autoatendimento-chamados")'), null);

  ctx.semErros();
});

cenario('Modo_API: o corpo enviado e a confirmação trazem o texto digitado, sem criar elementos', { modoApi: true, api: { modo: 'sucesso', atraso: 0 } }, async (ctx) => {
  await abrirFormulario(ctx);
  await ctx.preencherFormulario({ nome: HTML_B, email: EMAIL, telefone: TELEFONE, descricao: HTML_IMG, aceite: true });
  await exigirCamposLiterais(ctx, HTML_B, HTML_IMG);

  await ctx.enviar();
  await ctx.esperar('location.hash === "#/chamado/1" && !document.querySelector("#view-chamado").hidden', 2000, 'Tela_de_Confirmacao');
  await exigirSemElementosNovos(ctx, 'confirmação em Modo_API');
  assert.equal(await ctx.contar('#view-chamado b, #view-chamado img'), 0);

  assert.equal(ctx.api.requisicoes().length, 1);
  const corpo = ctx.api.requisicoes()[0].json;
  assert.equal(corpo.nome, HTML_B, 'o nome segue como texto no Payload_do_Chamado');
  assert.equal(corpo.descricao, HTML_IMG, 'a descrição segue como texto no Payload_do_Chamado');
  assert.deepEqual(await ctx.chamadosLocais(), [], 'Modo_API não grava chamado local');

  ctx.semErros();
});
