'use strict';
// Cenário 12.3: validação do formulário de chamado (Requisito 5, critérios 6 a 12, 16 e 17).
// Cada cenário é curto e independente: abre #/suporte/6 em carga nova.
const assert = require('node:assert/strict');
const { cenario } = require('../cenarios');

const ROTA = '#/suporte/6';
const CAMPOS = ['nome', 'email', 'telefone', 'descricao', 'aceite'];
const CONTROLE = (c) => '#c-' + c;
const ERRO = (c) => '#c-' + c + '-erro';

const VALIDOS = {
  nome: 'Maria da Silva',
  email: 'maria@exemplo.com',
  telefone: '(11) 91234-5678',
  descricao: 'A máquina não extrai a bebida.'
};

/** Estado de acessibilidade de um campo, lido direto no DOM. */
function estado(ctx, campo) {
  return ctx.avaliar(function (sel, selErro, id) {
    var c = document.querySelector(sel);
    var e = document.querySelector(selErro);
    return {
      invalido: c.getAttribute('aria-invalid'),
      descrito: (c.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean),
      erroVisivel: !!e && !e.hidden && e.textContent.trim() !== '',
      erroTexto: e ? e.textContent.trim() : null,
      erroId: e ? e.id : null,
      ref: id
    };
  }, CONTROLE(campo), ERRO(campo), 'c-' + campo + '-erro');
}

async function abrirFormulario(ctx) {
  await ctx.abrir(ROTA);
  await ctx.esperar('!!document.querySelector("#form-chamado") && !document.querySelector("#form-chamado").hidden', 2000, 'formulário de chamado visível');
}

cenario('enviar vazio mostra 5 erros com aria, foco no primeiro e anúncio "5 itens"', async (ctx) => {
  await abrirFormulario(ctx);

  // Antes de enviar: nenhum erro visível nem aria-invalid.
  for (const c of CAMPOS) {
    const e = await estado(ctx, c);
    assert.equal(e.erroVisivel, false, 'sem erro visível antes de enviar: ' + c);
    assert.equal(e.invalido, null, 'sem aria-invalid antes de enviar: ' + c);
  }

  await ctx.enviar();

  const textos = {};
  for (const c of CAMPOS) {
    const e = await estado(ctx, c);
    assert.equal(e.erroVisivel, true, 'erro visível em ' + c);
    assert.equal(e.invalido, 'true', 'aria-invalid="true" em ' + c);
    assert.ok(e.descrito.includes(e.ref), 'aria-describedby de ' + c + ' deve referenciar ' + e.ref + ' (tem: ' + e.descrito.join(' ') + ')');
    textos[c] = e.erroTexto;
  }

  // Mensagens em português com o motivo (5.7): campo vazio usa o texto "Preencha este campo."
  // (design.md, chave erroVazio); os limites de Nome e Descrição aparecem no cenário de formato inválido.
  for (const c of ['nome', 'email', 'telefone', 'descricao']) {
    assert.match(textos[c], /^Preencha este campo\.$/, 'mensagem de campo vazio em ' + c);
  }
  assert.match(textos.aceite, /marque que você leu e concorda com os termos/i);
  assert.ok(!/\{(min|max|n)\}/.test(Object.values(textos).join(' ')), 'nenhum marcador {min}/{max} sem substituir');

  // Telefone mantém também o texto de ajuda em aria-describedby (5.10).
  const tel = await estado(ctx, 'telefone');
  assert.ok(tel.descrito.includes('c-telefone-ajuda'), 'telefone mantém a ajuda em aria-describedby');
  const desc = await estado(ctx, 'descricao');
  assert.ok(desc.descrito.includes('c-descricao-contador'), 'descrição mantém o contador em aria-describedby');

  // Foco no primeiro controle inválido: Nome (5.8).
  const foco = await ctx.foco();
  assert.equal(foco.id, 'c-nome', 'foco deve ir para o Nome');

  // Anúncio em região aria-live em até 1 s com "5 itens" (5.9).
  await ctx.esperar('/5 itens/.test(document.querySelector("#anuncio").textContent)', 1000, 'anúncio com "5 itens" em #anuncio');
  assert.equal(await ctx.atributo('#anuncio', 'aria-live'), 'polite');

  // Nada gravado, mesma tela (5.6).
  assert.deepEqual(await ctx.chamadosLocais(), []);
  assert.equal(await ctx.hash(), ROTA);
  assert.ok(await ctx.visivel('#form-chamado'));
  assert.equal(await ctx.contar('#view-chamado:not([hidden])'), 0);
  assert.deepEqual(ctx.api.requisicoes(), []);

  ctx.semErros();
});

cenario('valores com formato inválido mostram mensagens por campo com os limites (5.7)', async (ctx) => {
  await abrirFormulario(ctx);
  await ctx.preencherFormulario({ nome: 'ab', email: 'sem-arroba', telefone: '123', descricao: 'curta', aceite: true });
  await ctx.enviar();

  const e = {};
  for (const c of CAMPOS.slice(0, 4)) {
    e[c] = await estado(ctx, c);
    assert.equal(e[c].erroVisivel, true, 'erro visível em ' + c);
    assert.equal(e[c].invalido, 'true');
    assert.ok(e[c].descrito.includes(e[c].ref));
  }
  assert.match(e.nome.erroTexto, /3 a 100/, 'nome traz mínimo e máximo');
  assert.match(e.email.erroTexto, /e-mail válido/i);
  assert.match(e.telefone.erroTexto, /telefone com DDD/i);
  assert.match(e.descricao.erroTexto, /10 a 500/, 'descrição traz mínimo e máximo');
  assert.equal((await estado(ctx, 'aceite')).erroVisivel, false, 'aceite marcado: sem erro');

  assert.equal((await ctx.foco()).id, 'c-nome');
  await ctx.esperar('/4 itens/.test(document.querySelector("#anuncio").textContent)', 1000, 'anúncio com "4 itens"');
  // Valores mantidos como digitados (5.14).
  assert.equal(await ctx.valor('#c-email'), 'sem-arroba');
  assert.equal(await ctx.valor('#c-telefone'), '123');
  assert.deepEqual(await ctx.chamadosLocais(), []);

  ctx.semErros();
});

cenario('corrigir um campo remove só o erro dele, em até 200 ms', async (ctx) => {
  await abrirFormulario(ctx);
  await ctx.enviar();
  await ctx.esperar('/5 itens/.test(document.querySelector("#anuncio").textContent)', 1000, 'anúncio com "5 itens"');

  // Telefone: ao corrigir, o erro sai mas a ajuda continua em aria-describedby (5.12).
  await ctx.digitar(CONTROLE('telefone'), VALIDOS.telefone);
  const t0 = Date.now();
  await ctx.esperar('document.querySelector("#c-telefone-erro").hidden === true', 200, 'erro do telefone removido');
  assert.ok(Date.now() - t0 <= 400, 'remoção do erro do telefone levou ' + (Date.now() - t0) + ' ms (margem do protocolo incluída)');
  const tel = await estado(ctx, 'telefone');
  assert.equal(tel.erroVisivel, false);
  assert.equal(tel.erroTexto, '', 'texto do erro limpo');
  assert.equal(tel.invalido, null, 'aria-invalid removido');
  assert.ok(!tel.descrito.includes('c-telefone-erro'), 'aria-describedby não referencia mais o erro');
  assert.ok(tel.descrito.includes('c-telefone-ajuda'), 'a ajuda continua em aria-describedby');

  // Nome: sem ajuda, aria-describedby fica sem a referência ao erro.
  await ctx.digitar(CONTROLE('nome'), VALIDOS.nome);
  await ctx.esperar('document.querySelector("#c-nome-erro").hidden === true', 200, 'erro do nome removido');
  const nome = await estado(ctx, 'nome');
  assert.equal(nome.invalido, null);
  assert.ok(!nome.descrito.includes('c-nome-erro'));

  // Os outros três seguem com erro.
  for (const c of ['email', 'descricao', 'aceite']) {
    const e = await estado(ctx, c);
    assert.equal(e.erroVisivel, true, 'erro de ' + c + ' continua visível');
    assert.equal(e.invalido, 'true', 'aria-invalid de ' + c + ' continua');
  }

  // Valor ainda inválido: o erro permanece (a mensagem acompanha o código atual).
  await ctx.digitar(CONTROLE('email'), 'sem-arroba');
  const email = await estado(ctx, 'email');
  assert.equal(email.erroVisivel, true, 'e-mail ainda inválido mantém o erro');
  assert.equal(email.invalido, 'true');

  ctx.semErros();
});

cenario('enviar sem aceite aponta só o aceite; marcar o aceite remove o erro, mantendo os valores', async (ctx) => {
  await abrirFormulario(ctx);
  await ctx.preencherFormulario(VALIDOS);
  assert.equal(await ctx.avaliar('document.querySelector("#c-aceite").checked'), false, 'aceite começa desmarcado');

  await ctx.enviar();

  // Só o aceite com erro (5.16).
  for (const c of ['nome', 'email', 'telefone', 'descricao']) {
    const e = await estado(ctx, c);
    assert.equal(e.erroVisivel, false, 'sem erro em ' + c);
    assert.equal(e.invalido, null, 'sem aria-invalid em ' + c);
  }
  const aceite = await estado(ctx, 'aceite');
  assert.equal(aceite.erroVisivel, true, 'erro do aceite visível');
  assert.match(aceite.erroTexto, /termos/i);
  assert.equal(aceite.invalido, 'true');
  assert.ok(aceite.descrito.includes('c-aceite-erro'), 'aria-describedby do aceite referencia a mensagem');

  // Foco no aceite e anúncio singular (5.8, 5.9).
  assert.equal((await ctx.foco()).id, 'c-aceite');
  await ctx.esperar('/1 item\\b/.test(document.querySelector("#anuncio").textContent)', 1000, 'anúncio com "1 item"');

  // Valores mantidos exatamente como digitados; nada gravado (5.6, 5.14).
  for (const c of Object.keys(VALIDOS)) {
    assert.equal(await ctx.valor(CONTROLE(c)), VALIDOS[c], 'valor mantido em ' + c);
  }
  assert.deepEqual(await ctx.chamadosLocais(), []);
  assert.equal(await ctx.hash(), ROTA);

  // Marcar o aceite remove o erro em até 200 ms (5.17).
  await ctx.marcar(CONTROLE('aceite'), true);
  const t0 = Date.now();
  await ctx.esperar('document.querySelector("#c-aceite-erro").hidden === true', 200, 'erro do aceite removido');
  assert.ok(Date.now() - t0 <= 400, 'remoção do erro do aceite levou ' + (Date.now() - t0) + ' ms (margem do protocolo incluída)');
  const depois = await estado(ctx, 'aceite');
  assert.equal(depois.erroVisivel, false);
  assert.equal(depois.erroTexto, '');
  assert.equal(depois.invalido, null, 'aria-invalid removido do aceite');
  assert.ok(!depois.descrito.includes('c-aceite-erro'), 'aria-describedby não referencia mais o erro do aceite');
  assert.equal(await ctx.avaliar('document.querySelector("#c-aceite").checked'), true, 'aceite continua marcado');

  ctx.semErros();
});

cenario('perder o foco de um campo vazio mostra o erro dele (5.11)', async (ctx) => {
  await abrirFormulario(ctx);

  // Foca o nome e sai com Tab sem digitar.
  await ctx.avaliar('document.querySelector("#c-nome").focus()');
  await ctx.teclar('Tab');
  await ctx.esperar('document.querySelector("#c-nome-erro").hidden === false', 500, 'erro do nome ao perder o foco');
  const nome = await estado(ctx, 'nome');
  assert.equal(nome.invalido, 'true');
  assert.ok(nome.descrito.includes('c-nome-erro'));
  assert.equal(await ctx.visivel('#c-email-erro'), false, 'o e-mail ainda não foi visitado: sem erro');

  ctx.semErros();
});
