'use strict';
// Tarefa 12.4 — Botão "Ler os termos" (Requisitos 6.8, 6.9, 6.10).
// Cada cenário é curto e independente (carga nova). Abre a Tela_de_Chamado direto em #/suporte/1.
const assert = require('node:assert/strict');
const { cenario } = require('../cenarios');

const ROTA = '#/suporte/1';
const BOTAO = '#btn-ler-termos';
const MENSAGEM = '#termos-msg';
const ACEITE = '#c-aceite';
const TEXTO = 'Texto dos termos em elaboração';

/** Mensagens visíveis com role="status" dentro da tela de chamado que contêm o texto dos termos. */
const mensagensDeTermos = (ctx) =>
  ctx.avaliar(function (texto) {
    return Array.prototype.filter.call(
      document.querySelectorAll('#view-suporte [role="status"], #view-suporte [aria-live]'),
      function (e) { return !e.hidden && e.textContent.indexOf(texto) >= 0; }
    ).length;
  }, TEXTO);

async function abrirComBotaoFocado(ctx) {
  await ctx.abrir(ROTA);
  assert.ok(await ctx.visivel(BOTAO), 'o botão "Ler os termos" deve estar visível');
  await ctx.avaliar('document.querySelector(' + JSON.stringify(BOTAO) + ').focus()');
  assert.equal((await ctx.foco()).id, 'btn-ler-termos');
}

cenario('antes de acionar: botão logo depois do aceite e mensagem oculta e vazia', async (ctx) => {
  await ctx.abrir(ROTA);

  assert.equal(await ctx.lerTexto(BOTAO), 'Ler os termos');
  assert.equal(await ctx.atributo(BOTAO, 'type'), 'button', 'o botão não pode enviar o formulário');
  assert.equal(await ctx.atributo(MENSAGEM, 'role'), 'status');
  assert.equal(await ctx.visivel(MENSAGEM), false, 'a mensagem não aparece antes de acionar o botão');
  assert.equal(await ctx.lerTexto(MENSAGEM), '');
  assert.equal(await ctx.avaliar('document.querySelector("#c-aceite").checked'), false, 'o aceite começa desmarcado');

  // Req. 6.7: o botão vem imediatamente depois do Aceite_dos_Termos.
  const seguinte = await ctx.avaliar(function () {
    var grupo = document.querySelector('#c-aceite').closest('.campo, div');
    var el = grupo && grupo.nextElementSibling;
    return el ? el.id : null;
  });
  assert.equal(seguinte, 'btn-ler-termos', 'o botão deve vir logo depois do bloco do aceite');
  ctx.semErros();
});

cenario('acionar 3 vezes: uma única mensagem, foco no botão, hash, janelas e aceite inalterados', async (ctx) => {
  await abrirComBotaoFocado(ctx);

  const hashAntes = await ctx.hash();
  const urlAntes = await ctx.url();
  const janelasAntes = (await ctx.janelas()).length;
  const regioesAntes = await ctx.contar('#view-suporte [role="status"]');
  const regioesTermosAntes = await ctx.contar(MENSAGEM);

  // Espiões: window.open e diálogos não podem ser chamados.
  await ctx.avaliar(function () {
    window.__abriu = 0;
    window.open = function () { window.__abriu += 1; return null; };
    ['alert', 'confirm', 'prompt'].forEach(function (n) {
      window[n] = function () { window.__abriu += 1; return null; };
    });
    window.__dialogosNativos = document.querySelectorAll('dialog[open], [role="dialog"], [aria-modal="true"]').length;
  });

  await ctx.clicar(BOTAO, 3);

  assert.equal(await ctx.lerTexto(MENSAGEM), TEXTO, 'a mensagem fixa deve ser exibida');
  assert.ok(await ctx.visivel(MENSAGEM), 'a mensagem deve ficar visível');
  assert.equal(await ctx.atributo(MENSAGEM, 'role'), 'status');
  assert.equal(await mensagensDeTermos(ctx), 1, 'deve haver uma única mensagem em role="status"');
  assert.equal(await ctx.contar(MENSAGEM), regioesTermosAntes, 'o elemento da mensagem não pode ser duplicado');
  assert.equal(await ctx.contar('#view-suporte [role="status"]'), regioesAntes, 'não podem surgir novas regiões de status');
  assert.equal(
    await ctx.avaliar('document.body.textContent.split(' + JSON.stringify(TEXTO) + ').length - 1'),
    1,
    'o texto dos termos deve aparecer uma única vez na página'
  );

  // Foco continua no botão.
  const foco = await ctx.foco();
  assert.equal(foco.id, 'btn-ler-termos', 'o foco deve continuar no botão');

  // Sem navegação, sem janela, sem diálogo.
  assert.equal(await ctx.hash(), hashAntes);
  assert.equal(await ctx.url(), urlAntes);
  assert.equal((await ctx.janelas()).length, janelasAntes, 'nenhuma aba ou janela nova');
  assert.equal(await ctx.avaliar('window.__abriu'), 0, 'window.open, alert, confirm e prompt não podem ser chamados');
  assert.equal(
    await ctx.contar('dialog[open], [role="dialog"], [aria-modal="true"]'),
    await ctx.avaliar('window.__dialogosNativos'),
    'nenhum diálogo modal'
  );

  // Aceite inalterado.
  assert.equal(await ctx.avaliar('document.querySelector("#c-aceite").checked'), false);
  assert.equal(await ctx.visivel('#view-suporte'), true, 'continua na Tela_de_Chamado');
  ctx.semErros();
});

cenario('acionar pelo teclado (Enter e Space) mantém uma só mensagem e o foco no botão', async (ctx) => {
  await abrirComBotaoFocado(ctx);
  const hashAntes = await ctx.hash();

  await ctx.teclar('Enter');
  await ctx.esperar(function () {
    return !document.querySelector('#termos-msg').hidden;
  }, 1000, 'a mensagem de termos aparecer depois de Enter');
  await ctx.teclar('Space');
  await ctx.teclar('Enter');

  assert.equal(await ctx.lerTexto(MENSAGEM), TEXTO);
  assert.equal(await mensagensDeTermos(ctx), 1);
  assert.equal((await ctx.foco()).id, 'btn-ler-termos');
  assert.equal(await ctx.hash(), hashAntes);
  assert.equal(await ctx.avaliar('document.querySelector("#c-aceite").checked'), false);
  ctx.semErros();
});

cenario('com o aceite marcado, acionar os termos não o desmarca; desmarcado, não o marca', async (ctx) => {
  await ctx.abrir(ROTA);
  await ctx.marcar(ACEITE, true);
  assert.equal(await ctx.avaliar('document.querySelector("#c-aceite").checked'), true);

  await ctx.clicar(BOTAO, 3);
  assert.equal(await ctx.avaliar('document.querySelector("#c-aceite").checked'), true, 'aceite marcado deve continuar marcado');
  assert.equal(await mensagensDeTermos(ctx), 1);
  assert.equal(await ctx.hash(), ROTA);

  await ctx.marcar(ACEITE, false);
  await ctx.clicar(BOTAO, 1);
  assert.equal(await ctx.avaliar('document.querySelector("#c-aceite").checked'), false, 'aceite desmarcado deve continuar desmarcado');
  assert.equal(await mensagensDeTermos(ctx), 1);
  ctx.semErros();
});

cenario('acionar os termos não envia o formulário nem mostra erros de validação', async (ctx) => {
  await ctx.abrir(ROTA);
  await ctx.clicar(BOTAO, 3);

  assert.equal(await ctx.hash(), ROTA, 'continua na rota do formulário');
  assert.equal(
    await ctx.avaliar('document.querySelectorAll("#form-chamado [aria-invalid=\\"true\\"]").length'),
    0,
    'o botão de termos não dispara validação'
  );
  assert.deepEqual(await ctx.chamadosLocais(), [], 'nenhum chamado foi gravado');
  ctx.semErros();
});
