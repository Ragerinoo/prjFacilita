'use strict';
// Cenário de fumaça: prova que a infraestrutura de interface (servidor de teste,
// Edge headless, DevTools Protocol) funciona. Não cobre requisitos da tela de chamado.
const assert = require('node:assert/strict');
const { cenario } = require('../cenarios');

cenario('abre #/ e mostra a tela de modelo sem erro de script', async (ctx) => {
  await ctx.abrir('#/');

  assert.equal(await ctx.hash(), '#/');
  assert.ok(await ctx.existe('#view-modelo'), '#view-modelo deve existir');
  assert.ok(await ctx.visivel('#view-modelo'), 'a tela de modelo deve estar visível em #/');
  assert.ok(await ctx.lerTexto('#titulo-modelo'), 'o título da tela de modelo não pode estar vazio');
  assert.equal(await ctx.visivel('#view-suporte'), false, 'a tela de chamado não deve aparecer em #/');

  ctx.semErros();
  assert.deepEqual(ctx.erros(), []);
});
