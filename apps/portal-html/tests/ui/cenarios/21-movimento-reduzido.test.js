'use strict';
// Tarefa 12.11: movimento reduzido (Requisito 11.7). Tarefa 10.11 (resolved-feedback-comment): Tela_de_Resolvido (Requisito 12.8).
// Com `prefers-reduced-motion: reduce` emulado (antes da carga), a Tela_de_Chamado e a
// Tela_de_Confirmacao não podem ter transição, animação nem rolagem suave: toda duração é 0 s,
// nenhuma animação está em curso e o fluxo continua funcionando.
// Um cenário de controle (sem a emulação) prova que a medição enxerga as transições do site.
const assert = require('node:assert/strict');
const { cenario } = require('../cenarios');

const PROBLEMA = 'A máquina não extrai bebida';
const DADOS = {
  nome: 'Maria da Silva',
  email: 'maria.silva@exemplo.com.br',
  telefone: '(11) 91234-5678',
  descricao: 'A máquina não extrai o café mesmo com água no reservatório.',
  aceite: true
};
// Viewport baixa de propósito: a página fica mais alta que a janela e dá para testar a rolagem.
const REDUZIDO = { movimentoReduzido: true, viewport: { largura: 360, altura: 480 } };

/** Chega à Tela_de_Chamado como o consumidor (mesmo caminho dos cenários 12 e 20). */
async function irParaChamado(ctx) {
  await ctx.abrir('#/');
  await ctx.avaliar(() => {
    const btn = Array.from(document.querySelectorAll('#lista-modelos .modelo__nome'))
      .find((n) => n.textContent.trim() === 'LOV');
    btn.closest('button').click();
  });
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1500, 'tela de problemas');
  await ctx.avaliar((titulo) => {
    const t = Array.from(document.querySelectorAll('.problema .problema__titulo'))
      .find((n) => n.textContent.trim() === titulo);
    t.closest('button').click();
  }, PROBLEMA);
  await ctx.esperar('/^#\\/solucao\\/\\d+$/.test(location.hash)', 1500, 'tela de solução');
  const id = await ctx.avaliar('Number(location.hash.split("/")[2])');
  await ctx.clicar('#btn-proximo');
  await ctx.avaliar('location.hash = "#/confirma/' + id + '"');
  await ctx.esperar('!document.querySelector("#view-confirma").hidden', 1000, 'tela "O problema foi solucionado?"');
  await ctx.clicar('#btn-nao');
  await ctx.esperar('location.hash === "#/suporte/' + id + '" && !document.querySelector("#view-suporte").hidden', 1000, 'Tela_de_Chamado');
  return id;
}

/**
 * Mede, na página, tudo que poderia se mover dentro da view indicada: duração e atraso de
 * transições e animações (elemento, ::before e ::after), nome da animação, animações em curso
 * (Web Animations) e o scroll-behavior do documento. Roda serializada na página.
 */
function medirMovimento(seletorView) {
  const view = document.querySelector(seletorView);
  const zero = (lista) => String(lista).split(',').every((v) => parseFloat(v) === 0);
  const problemas = [];
  let analisados = 0;
  const conferir = (el, pseudo) => {
    const cs = getComputedStyle(el, pseudo || null);
    analisados += 1;
    const nome = (el.id ? '#' + el.id : el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.split(/\s+/)[0] : '')) + (pseudo || '');
    if (!zero(cs.transitionDuration)) problemas.push(nome + ' transition-duration=' + cs.transitionDuration);
    if (!zero(cs.transitionDelay)) problemas.push(nome + ' transition-delay=' + cs.transitionDelay);
    if (!zero(cs.animationDuration)) problemas.push(nome + ' animation-duration=' + cs.animationDuration);
    if (!zero(cs.animationDelay)) problemas.push(nome + ' animation-delay=' + cs.animationDelay);
    if (!String(cs.animationName).split(',').every((v) => v.trim() === 'none')) problemas.push(nome + ' animation-name=' + cs.animationName);
  };
  [view].concat(Array.from(view.querySelectorAll('*'))).forEach((el) => {
    conferir(el);
    conferir(el, '::before');
    conferir(el, '::after');
  });
  return {
    analisados,
    problemas,
    animacoesEmCurso: view.getAnimations({ subtree: true }).length,
    rolagemSuave: getComputedStyle(document.documentElement).scrollBehavior,
    preferencia: window.matchMedia('(prefers-reduced-motion: reduce)').matches
  };
}

function afirmarSemMovimento(m, rotulo) {
  assert.equal(m.preferencia, true, rotulo + ': a emulação de prefers-reduced-motion: reduce deve valer na página');
  assert.ok(m.analisados > 20, rotulo + ': poucos elementos analisados (' + m.analisados + '); seletor errado?');
  assert.deepEqual(m.problemas, [], rotulo + ': transições ou animações com duração/atraso diferente de 0 s');
  assert.equal(m.animacoesEmCurso, 0, rotulo + ': há animações em curso');
  assert.notEqual(m.rolagemSuave, 'smooth', rotulo + ': scroll-behavior suave com movimento reduzido');
}

/** A rolagem programática precisa ser imediata (sem animação), lida na mesma volta do JS. */
async function afirmarRolagemImediata(ctx, rotulo) {
  const r = await ctx.avaliar(() => {
    const alturaExtra = document.documentElement.scrollHeight - window.innerHeight;
    window.scrollTo(0, 300);
    const depoisDeDescer = Math.round(window.scrollY);
    window.scrollTo(0, 0);
    const depoisDeSubir = Math.round(window.scrollY);
    return { alturaExtra, depoisDeDescer, depoisDeSubir };
  });
  assert.ok(r.alturaExtra >= 300, rotulo + ': a página precisa rolar pelo menos 300 px para este teste (rola ' + r.alturaExtra + ' px)');
  assert.equal(r.depoisDeDescer, 300, rotulo + ': scrollTo(0, 300) deve ser imediato');
  assert.equal(r.depoisDeSubir, 0, rotulo + ': scrollTo(0, 0) deve ser imediato');
}

cenario('Movimento reduzido: Tela_de_Chamado sem transição, animação nem rolagem suave, e o formulário funciona', REDUZIDO, async (ctx) => {
  await irParaChamado(ctx);

  afirmarSemMovimento(await ctx.avaliar(medirMovimento, '#view-suporte'), 'Tela_de_Chamado');
  await afirmarRolagemImediata(ctx, 'Tela_de_Chamado');

  // O fluxo segue funcionando: foco no h1 e envio sem erro de validação.
  await ctx.esperar('document.activeElement && document.activeElement.id === "titulo-suporte"', 300, 'foco no h1 da Tela_de_Chamado');
  await ctx.preencherFormulario(DADOS);
  assert.equal(await ctx.valor('#c-nome'), DADOS.nome);
  assert.equal(await ctx.avaliar('document.querySelector("#c-aceite").checked'), true);

  // Estado de erro (mudança de estado imediata, sem animar): envia vazio e confere o 0 ms.
  await ctx.preencherFormulario({ nome: '' });
  await ctx.enviar();
  await ctx.esperar('document.querySelector("#c-nome").getAttribute("aria-invalid") === "true"', 500, 'erro de validação no nome');
  afirmarSemMovimento(await ctx.avaliar(medirMovimento, '#view-suporte'), 'Tela_de_Chamado com erro');
  ctx.semErros();
});

cenario('Movimento reduzido: Tela_de_Confirmacao sem transição, animação nem rolagem suave, e o envio conclui', REDUZIDO, async (ctx) => {
  const id = await irParaChamado(ctx);
  await ctx.preencherFormulario(DADOS);
  await ctx.enviar();
  await ctx.esperar('location.hash === "#/chamado/' + id + '" && !document.querySelector("#view-chamado").hidden', 1000, 'Tela_de_Confirmacao');

  // A mudança de tela é imediata: protocolo já está escrito e o foco já está no h1.
  assert.match(await ctx.lerTexto('#chamado-protocolo'), /^TRES-\d{8}-[A-Z0-9]{6}$/);
  await ctx.esperar('document.activeElement && document.activeElement.id === "titulo-chamado"', 500, 'foco no h1 da confirmação');
  assert.equal(await ctx.visivel('#view-suporte'), false, 'a Tela_de_Chamado deve ficar oculta');

  afirmarSemMovimento(await ctx.avaliar(medirMovimento, '#view-chamado'), 'Tela_de_Confirmacao');
  await afirmarRolagemImediata(ctx, 'Tela_de_Confirmacao');
  ctx.semErros();
});

/** Chega à Tela_de_Resolvido respondendo "Sim, resolvi" (mesmo caminho do cenário 24). */
async function irParaResolvido(ctx) {
  await ctx.abrir('#/');
  await ctx.avaliar('location.hash = "#/confirma/1"');
  await ctx.esperar('!document.querySelector("#view-confirma").hidden', 1000, 'tela "O problema foi solucionado?"');
  await ctx.clicar('#btn-sim');
  await ctx.esperar('location.hash === "#/resolvido/1" && !document.querySelector("#view-resolvido").hidden', 1000, 'Tela_de_Resolvido');
  await ctx.esperar('!document.querySelector("#form-feedback").hidden', 500, 'formulário de comentário visível');
}

cenario('Movimento reduzido: Tela_de_Resolvido com o bloco de comentário sem transição, animação nem rolagem suave, e o envio conclui', REDUZIDO, async (ctx) => {
  await irParaResolvido(ctx);

  // Em repouso: o bloco de comentário (formulário, contador, aviso, botão) e o resto da tela.
  afirmarSemMovimento(await ctx.avaliar(medirMovimento, '#view-resolvido'), 'Tela_de_Resolvido');
  afirmarSemMovimento(await ctx.avaliar(medirMovimento, '#form-feedback'), 'Formulario_de_Feedback');
  await afirmarRolagemImediata(ctx, 'Tela_de_Resolvido');

  // Estado de erro: envio vazio muda o estado na hora, sem animar.
  await ctx.clicar('#btn-enviar-comentario');
  await ctx.esperar('document.querySelector("#f-comentario").getAttribute("aria-invalid") === "true"', 500, 'erro de validação no comentário');
  afirmarSemMovimento(await ctx.avaliar(medirMovimento, '#view-resolvido'), 'Tela_de_Resolvido com erro');

  // Envio válido: agradecimento imediato, foco nele e campo/botão travados.
  const texto = 'Funcionou com movimento reduzido.';
  await ctx.digitar('#f-comentario', texto);
  await ctx.clicar('#btn-enviar-comentario');
  await ctx.esperar('document.activeElement && document.activeElement.id === "feedback-agradecimento"', 300, 'foco no agradecimento');
  assert.ok((await ctx.lerTexto('#feedback-agradecimento')).length > 0, 'o agradecimento deve estar escrito');
  assert.equal(await ctx.avaliar('document.querySelector("#f-comentario").disabled'), true, 'o campo fica desabilitado após o envio');
  assert.equal(await ctx.avaliar('document.querySelector("#btn-enviar-comentario").disabled'), true, 'o botão fica desabilitado após o envio');
  const regs = await ctx.feedbacksLocais();
  assert.equal(regs.length, 1, 'exatamente um feedback gravado');
  assert.equal(regs[0].comentario, texto);

  afirmarSemMovimento(await ctx.avaliar(medirMovimento, '#view-resolvido'), 'Tela_de_Resolvido após o envio');
  afirmarSemMovimento(await ctx.avaliar(medirMovimento, '#form-feedback'), 'Formulario_de_Feedback após o envio');
  await afirmarRolagemImediata(ctx, 'Tela_de_Resolvido após o envio');
  ctx.semErros();
});

cenario('Movimento reduzido: o site inteiro fica sem transição (controle: sem a emulação o botão anima)', {
  viewport: REDUZIDO.viewport
}, async (ctx) => {
  // Controle: sem prefers-reduced-motion, a medição enxerga as transições do .btn e a rolagem suave.
  // A preferência é fixada em "no-preference" porque o sistema do computador de teste pode já pedir movimento reduzido.
  await ctx.movimentoReduzido(false);
  await irParaChamado(ctx);
  const sem = await ctx.avaliar(() => ({
    preferencia: window.matchMedia('(prefers-reduced-motion: reduce)').matches,
    btn: getComputedStyle(document.querySelector('.btn')).transitionDuration,
    rolagem: getComputedStyle(document.documentElement).scrollBehavior
  }));
  assert.equal(sem.preferencia, false, 'o controle roda sem a preferência de movimento reduzido');
  assert.ok(parseFloat(sem.btn) > 0, 'sem a emulação o .btn deve ter transição (a medição precisa distinguir): ' + sem.btn);
  assert.equal(sem.rolagem, 'smooth', 'sem a emulação a rolagem é suave');

  // Liga a emulação na mesma aba: a regra global passa a zerar tudo na hora.
  await ctx.movimentoReduzido(true);
  const nova = await ctx.avaliar(() => ({
    btn: getComputedStyle(document.querySelector('.btn')).transitionDuration,
    rolagem: getComputedStyle(document.documentElement).scrollBehavior,
    barra: getComputedStyle(document.querySelector('.passo-progresso__barra span')).transitionDuration
  }));
  assert.ok(parseFloat(nova.btn) === 0, 'com movimento reduzido o .btn não tem transição: ' + nova.btn);
  assert.notEqual(nova.rolagem, 'smooth', 'com movimento reduzido a rolagem não é suave');
  assert.ok(parseFloat(nova.barra) === 0, 'com movimento reduzido a barra de progresso não anima: ' + nova.barra);
  ctx.semErros();
});
