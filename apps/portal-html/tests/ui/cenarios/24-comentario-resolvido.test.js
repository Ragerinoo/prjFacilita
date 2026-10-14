'use strict';
// Tarefas 10.3 a 10.5 (resolved-feedback-comment): comentário opcional na Tela_de_Resolvido, Modo_Prototipo.
// 10.3 fluxos principais (só comentário, nota + comentário, só nota)
// 10.4 validação, contador e limite de 500 caracteres
// 10.5 falha de gravação, sem aviso de protótipo, conteúdo indisponível e estrutura da tela
// Requisitos: 1.1, 1.2, 1.7, 2.1, 3.1, 3.2, 3.3, 4.2, 4.3, 5.3 a 5.7, 7.4 a 7.6, 8.1 a 8.4, 9.1, 11.1, 11.5, 11.8, 13.4
const assert = require('node:assert/strict');
const { cenario } = require('../cenarios');

const ID = 1; // "A máquina não liga"
const CHAVE_FEEDBACKS = 'tres-autoatendimento-feedbacks';
const CAMPOS_PAYLOAD = ['chaveIdempotencia', 'comentario', 'enviadoEm', 'modelo', 'nota', 'problemaId', 'versaoContrato'];
const DESCRIBEDBY_REPOUSO = 'f-comentario-aviso f-comentario-contador';
const DESCRIBEDBY_ERRO = 'f-comentario-aviso f-comentario-contador f-comentario-erro';

const textos = (ctx) => ctx.avaliar('window.TRES_DATA.FEEDBACK.textos');
const eventosDo = async (ctx, tipo) => (await ctx.eventos()).filter((e) => e && e.tipo === tipo);

/** Clica o botão do modelo pelo nome (como o consumidor). */
async function escolherModelo(ctx, nome) {
  await ctx.avaliar((n) => {
    const t = Array.from(document.querySelectorAll('#lista-modelos .modelo__nome')).find((x) => x.textContent.trim() === n);
    t.closest('button').click();
  }, nome);
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1500, 'tela de problemas');
}

/** Chega a #/resolvido/ID respondendo "Sim, resolvi" (com ou sem modelo escolhido). */
async function irParaResolvido(ctx, modelo) {
  await ctx.abrir('#/');
  if (modelo) await escolherModelo(ctx, modelo);
  await ctx.avaliar('location.hash = "#/confirma/' + ID + '"');
  await ctx.esperar('!document.querySelector("#view-confirma").hidden', 1000, 'tela "O problema foi solucionado?"');
  await ctx.clicar('#btn-sim');
  await ctx.esperar('location.hash === "#/resolvido/' + ID + '" && !document.querySelector("#view-resolvido").hidden', 1000, 'tela de problema resolvido');
  await ctx.esperar('!document.querySelector("#form-feedback").hidden', 500, 'formulário de comentário visível');
}

const enviarComentario = (ctx) => ctx.clicar('#btn-enviar-comentario');

/** Estado de acessibilidade do campo de comentário. */
const estadoCampo = (ctx) => ctx.avaliar(() => {
  const c = document.querySelector('#f-comentario');
  return {
    invalido: c.getAttribute('aria-invalid'),
    descrito: c.getAttribute('aria-describedby'),
    desabilitado: c.disabled,
    somenteLeitura: c.readOnly,
    valor: c.value
  };
});

// ---------------------------------------------------------------------------
// 10.3 Fluxos principais
// ---------------------------------------------------------------------------

cenario('só comentário: agradece em role=status, trava campo e botão, foca o agradecimento, grava 1 registro com nota null e 1 evento comentario', async (ctx) => {
  await irParaResolvido(ctx, 'LOV');
  const T = await textos(ctx);
  const texto = 'O passo a passo resolveu em dois minutos. <b>Valeu</b> & "obrigado" \\o/ 👍';

  assert.deepEqual(await ctx.feedbacksLocais(), []);
  await ctx.digitar('#f-comentario', texto);
  await enviarComentario(ctx);

  // 7.4, 7.6: agradecimento em região role=status/aria-live, foco nele em até 300 ms.
  await ctx.esperar('document.activeElement && document.activeElement.id === "feedback-agradecimento"', 300, 'foco no agradecimento em até 300 ms');
  assert.equal(await ctx.lerTexto('#feedback-agradecimento'), T.agradecimento);
  assert.equal(await ctx.atributo('#feedback-agradecimento', 'role'), 'status');
  assert.equal(await ctx.atributo('#feedback-agradecimento', 'aria-live'), 'polite');

  // 7.6: campo e botão desabilitados, texto enviado continua visível.
  const campo = await estadoCampo(ctx);
  assert.equal(campo.desabilitado, true, 'o campo deve ficar desabilitado');
  assert.equal(campo.valor, texto, 'o texto enviado continua visível, sem alteração');
  assert.equal(await ctx.avaliar('document.querySelector("#btn-enviar-comentario").disabled'), true, 'o botão deve ficar desabilitado');
  assert.equal(await ctx.atributo('#form-feedback', 'aria-busy'), null);

  // 9.1: exatamente um registro, sem nota, com os 7 campos do contrato.
  const regs = await ctx.feedbacksLocais();
  assert.equal(regs.length, 1, 'exatamente um registro em ' + CHAVE_FEEDBACKS);
  assert.deepEqual(Object.keys(regs[0]).sort(), CAMPOS_PAYLOAD);
  assert.equal(regs[0].nota, null);
  assert.equal(regs[0].comentario, texto, 'texto puro: <, >, &, aspas, barra e emoji preservados');
  assert.equal(regs[0].problemaId, ID);
  assert.equal(regs[0].modelo, 'lov');
  assert.equal(regs[0].versaoContrato, '1');
  assert.match(regs[0].chaveIdempotencia, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  assert.ok(!Number.isNaN(Date.parse(regs[0].enviadoEm)));

  // 11.1, 11.5, 11.8: um evento comentario sem texto; nenhum avaliacao; resumo conta 1 comentário.
  const com = await eventosDo(ctx, 'comentario');
  assert.equal(com.length, 1);
  assert.deepEqual(Object.keys(com[0]).sort(), ['em', 'modelo', 'problema', 'tipo']);
  assert.equal(com[0].problema, ID);
  assert.equal(com[0].modelo, 'lov');
  assert.ok(!JSON.stringify(await ctx.eventos()).includes('Valeu'), 'o texto do comentário não pode ir para as métricas');
  assert.deepEqual(await eventosDo(ctx, 'avaliacao'), [], 'enviar só o comentário não gera avaliacao');
  const resumo = await ctx.avaliar('window.TRESMetricas.resumo()');
  assert.equal(resumo.comentarios, 1);
  assert.equal(resumo.resolvidos, 1, 'o comentário não altera os resolvidos');

  // O comentário não vai para as chaves de métricas nem de chamados.
  assert.equal(await ctx.avaliar('localStorage.getItem("tres-autoatendimento-chamados")'), null);
  ctx.semErros();
});

cenario('nota 4 + comentário: o registro leva nota 4 e há um único evento avaliacao', async (ctx) => {
  await irParaResolvido(ctx);
  await ctx.avaliar('document.querySelectorAll("#estrelas button")[3].click()');
  assert.equal((await eventosDo(ctx, 'avaliacao')).length, 1);

  await ctx.digitar('#f-comentario', 'Gostei do passo a passo.');
  await enviarComentario(ctx);
  await ctx.esperar('document.querySelector("#feedback-agradecimento").textContent.trim().length > 0', 500, 'agradecimento do comentário');

  const regs = await ctx.feedbacksLocais();
  assert.equal(regs.length, 1);
  assert.equal(regs[0].nota, 4);
  assert.equal(regs[0].comentario, 'Gostei do passo a passo.');
  assert.equal(regs[0].modelo, null, 'sem modelo escolhido, o payload leva null');

  const av = await eventosDo(ctx, 'avaliacao');
  assert.equal(av.length, 1, 'o envio do comentário não registra um novo avaliacao');
  assert.equal(av[0].nota, 4);
  assert.equal(av[0].desfecho, 'resolvido');
  assert.equal((await eventosDo(ctx, 'comentario')).length, 1);
  const resumo = await ctx.avaliar('window.TRESMetricas.resumo()');
  assert.equal(resumo.comentarios, 1);

  // 3.4: uma nota escolhida depois do envio grava avaliacao e não altera o feedback já enviado.
  await ctx.avaliar('document.querySelectorAll("#estrelas button")[0].click()');
  assert.equal((await eventosDo(ctx, 'avaliacao')).length, 2);
  const depois = await ctx.feedbacksLocais();
  assert.deepEqual(depois, regs, 'o feedback enviado não muda');
  ctx.semErros();
});

cenario('só nota: nenhum registro novo, comentarios === 0 e o formulário segue operável', async (ctx) => {
  await irParaResolvido(ctx);
  await ctx.avaliar('document.querySelectorAll("#estrelas button")[4].click()');

  const av = await eventosDo(ctx, 'avaliacao');
  assert.equal(av.length, 1);
  assert.equal(av[0].nota, 5);
  assert.equal(av[0].desfecho, 'resolvido');
  assert.equal(await ctx.lerTexto('#status-aval'), 'Obrigado pela sua avaliação!');

  assert.deepEqual(await ctx.feedbacksLocais(), [], 'avaliar só com estrelas não grava feedback');
  assert.equal(await ctx.avaliar('localStorage.getItem(' + JSON.stringify(CHAVE_FEEDBACKS) + ')'), null);
  assert.deepEqual(await eventosDo(ctx, 'comentario'), []);
  const resumo = await ctx.avaliar('window.TRESMetricas.resumo()');
  assert.equal(resumo.comentarios, 0);
  assert.equal(resumo.resolvidos, 1);

  const campo = await estadoCampo(ctx);
  assert.equal(campo.desabilitado, false);
  assert.equal(await ctx.lerTexto('#feedback-agradecimento'), '');
  ctx.semErros();
});

// ---------------------------------------------------------------------------
// 10.4 Validação, contador e limite
// ---------------------------------------------------------------------------

cenario('comentário vazio: mensagem, aria-invalid, aria-describedby, foco, anúncio e nada gravado', async (ctx) => {
  await irParaResolvido(ctx);
  const T = await textos(ctx);

  // Estado de repouso: sem erro, descrito por aviso e contador.
  let campo = await estadoCampo(ctx);
  assert.equal(campo.invalido, null);
  assert.equal(campo.descrito, DESCRIBEDBY_REPOUSO);
  assert.equal(await ctx.lerTexto('#f-comentario-contador'), '0 de 500 caracteres');
  assert.equal(await ctx.visivel('#f-comentario-erro'), false);

  await enviarComentario(ctx);

  assert.ok(await ctx.visivel('#f-comentario-erro'), 'a mensagem de erro deve ficar visível sob o campo');
  assert.equal(await ctx.lerTexto('#f-comentario-erro'), T.erroVazio);
  campo = await estadoCampo(ctx);
  assert.equal(campo.invalido, 'true');
  assert.equal(campo.descrito, DESCRIBEDBY_ERRO, 'aviso, contador e erro');
  assert.equal((await ctx.foco()).id, 'f-comentario', 'foco volta ao campo');
  await ctx.esperar('document.querySelector("#anuncio").textContent === ' + JSON.stringify(T.anuncioErroVazio), 1000, 'anúncio do erro em #anuncio');

  assert.deepEqual(await ctx.feedbacksLocais(), []);
  assert.deepEqual(await eventosDo(ctx, 'comentario'), []);
  assert.equal(await ctx.lerTexto('#feedback-agradecimento'), '');
  ctx.semErros();
});

cenario('só espaços e quebras de linha: erro, texto preservado; editar remove o erro e mantém aviso e contador; Enter não envia', async (ctx) => {
  await irParaResolvido(ctx);
  const T = await textos(ctx);
  const brancos = '   \n  ';

  await ctx.digitar('#f-comentario', brancos);
  assert.equal(await ctx.lerTexto('#f-comentario-contador'), brancos.length + ' de 500 caracteres');
  await enviarComentario(ctx);

  let campo = await estadoCampo(ctx);
  assert.equal(campo.invalido, 'true');
  assert.equal(campo.descrito, DESCRIBEDBY_ERRO);
  assert.equal(await ctx.lerTexto('#f-comentario-erro'), T.erroVazio);
  assert.equal(campo.valor, brancos, 'o texto digitado é preservado após a rejeição');
  assert.equal((await ctx.foco()).id, 'f-comentario');
  await ctx.esperar('document.querySelector("#anuncio").textContent === ' + JSON.stringify(T.anuncioErroVazio), 1000, 'anúncio do erro');
  assert.deepEqual(await ctx.feedbacksLocais(), []);

  // 5.5: editar remove erro, aria-invalid e a referência ao erro em até 200 ms; aviso e contador ficam.
  await ctx.digitar('#f-comentario', 'ok');
  await ctx.esperar('document.querySelector("#f-comentario").getAttribute("aria-invalid") === null', 200, 'aria-invalid removido em até 200 ms');
  campo = await estadoCampo(ctx);
  assert.equal(campo.descrito, DESCRIBEDBY_REPOUSO);
  assert.equal(await ctx.visivel('#f-comentario-erro'), false);
  assert.equal(await ctx.lerTexto('#f-comentario-erro'), '');
  assert.equal(await ctx.lerTexto('#f-comentario-contador'), '2 de 500 caracteres');
  assert.ok(await ctx.visivel('#f-comentario-aviso'), 'o aviso de não identificação segue visível');

  // 5.7: Enter no campo insere quebra de linha e não envia.
  await ctx.avaliar('(function(){var c=document.querySelector("#f-comentario");c.focus();c.setSelectionRange(c.value.length,c.value.length);})()');
  await ctx.teclar('Enter');
  await ctx.esperar('document.querySelector("#f-comentario").value === "ok\\n"', 500, 'quebra de linha inserida pelo Enter');
  assert.deepEqual(await ctx.feedbacksLocais(), [], 'Enter não envia');
  assert.equal(await ctx.lerTexto('#feedback-agradecimento'), '');
  assert.equal(await ctx.avaliar('document.querySelector("#btn-enviar-comentario").disabled'), false);
  assert.equal(await ctx.hash(), '#/resolvido/' + ID);
  ctx.semErros();
});

cenario('contador acompanha a digitação e o limite de 500 vale ao digitar e ao colar', async (ctx) => {
  await irParaResolvido(ctx);

  assert.equal(await ctx.lerTexto('#f-comentario-contador'), '0 de 500 caracteres');
  assert.equal(await ctx.atributo('#f-comentario-contador', 'aria-live'), null, 'o contador não é região viva');
  await ctx.digitar('#f-comentario', 'abc');
  assert.equal(await ctx.lerTexto('#f-comentario-contador'), '3 de 500 caracteres');

  // Digitar acima de 500.
  await ctx.digitar('#f-comentario', 'x'.repeat(600));
  assert.equal((await ctx.valor('#f-comentario')).length, 500);
  assert.equal(await ctx.lerTexto('#f-comentario-contador'), '500 de 500 caracteres');

  // Colar acima de 500 (valor atribuído por script burla o maxlength do navegador; o código trunca).
  await ctx.avaliar(() => {
    const c = document.querySelector('#f-comentario');
    c.value = 'y'.repeat(700);
    c.dispatchEvent(new Event('input', { bubbles: true }));
  });
  assert.equal(await ctx.valor('#f-comentario'), 'y'.repeat(500), 'texto colado truncado em 500, preservando o início');
  assert.equal(await ctx.lerTexto('#f-comentario-contador'), '500 de 500 caracteres');

  // 500 caracteres é um comentário válido e vai inteiro.
  await enviarComentario(ctx);
  await ctx.esperar('document.querySelector("#feedback-agradecimento").textContent.trim().length > 0', 500, 'agradecimento');
  const regs = await ctx.feedbacksLocais();
  assert.equal(regs.length, 1);
  assert.equal(regs[0].comentario, 'y'.repeat(500));
  ctx.semErros();
});

// ---------------------------------------------------------------------------
// 10.5 Falha, aviso de protótipo, conteúdo indisponível e estrutura
// ---------------------------------------------------------------------------

/**
 * Faz o setItem da chave de feedbacks lançar enquanto window.__falharFeedback for verdadeiro e registra
 * cada tentativa de gravação (a chave de idempotência do último item da lista). Outras chaves não são afetadas.
 */
const ANTES_FALHA_GRAVACAO = '(' + function () {
  window.__falharFeedback = true;
  window.__tentativas = [];
  var original = Storage.prototype.setItem;
  Storage.prototype.setItem = function (k, v) {
    if (k === 'tres-autoatendimento-feedbacks') {
      try { var l = JSON.parse(v); window.__tentativas.push(l[l.length - 1].chaveIdempotencia); } catch (e) { window.__tentativas.push('ilegivel'); }
      if (window.__falharFeedback) throw new DOMException('armazenamento cheio', 'QuotaExceededError');
    }
    return original.apply(this, arguments);
  };
} + ')()';

cenario('falha de gravação: bloco role=alert, texto preservado, botão reabilitado, sem métrica; reenviar usa a mesma chave', { antes: ANTES_FALHA_GRAVACAO }, async (ctx) => {
  await irParaResolvido(ctx);
  const T = await textos(ctx);
  const texto = 'Primeiro texto do comentário.';

  await ctx.digitar('#f-comentario', texto);
  await enviarComentario(ctx);
  await ctx.esperar('!!document.querySelector("#feedback-falha-area [role=alert]")', 500, 'bloco de falha');

  // 8.1 a 8.4
  assert.equal(await ctx.lerTexto('#feedback-falha-area [role=alert]'), T.falha);
  await ctx.esperar('document.activeElement && document.activeElement.getAttribute("role") === "alert"', 300, 'foco no bloco de falha');
  const campo = await estadoCampo(ctx);
  assert.equal(campo.valor, texto, 'o texto digitado é preservado');
  assert.equal(campo.desabilitado, false);
  assert.equal(campo.somenteLeitura, false);
  assert.equal(await ctx.avaliar('document.querySelector("#btn-enviar-comentario").disabled'), false, 'botão reabilitado');
  assert.equal(await ctx.lerTexto('#btn-enviar-comentario'), T.botaoEnviar);
  assert.equal(await ctx.atributo('#form-feedback', 'aria-busy'), null);
  assert.equal(await ctx.lerTexto('#feedback-agradecimento'), '', 'nada de agradecimento');
  assert.deepEqual(await eventosDo(ctx, 'comentario'), [], 'nenhuma métrica em caso de falha');
  assert.deepEqual(await eventosDo(ctx, 'avaliacao'), []);
  assert.equal((await ctx.avaliar('window.TRESMetricas.resumo()')).comentarios, 0);
  assert.deepEqual(await ctx.feedbacksLocais(), []);
  const tentativas1 = await ctx.avaliar('window.__tentativas');
  assert.equal(tentativas1.length, 1);

  // 8.7: estrelas e links seguem funcionando.
  await ctx.avaliar('document.querySelectorAll("#estrelas button")[1].click()');
  assert.equal((await eventosDo(ctx, 'avaliacao')).length, 1);

  // 8.5, 8.6: reenviar com o texto editado, agora com sucesso, reutiliza a mesma chave.
  await ctx.avaliar('window.__falharFeedback = false');
  const novo = texto + ' Depois de editar.';
  await ctx.digitar('#f-comentario', novo);
  await enviarComentario(ctx);
  await ctx.esperar('document.querySelector("#feedback-agradecimento").textContent.trim().length > 0', 500, 'agradecimento após reenviar');

  assert.equal(await ctx.contar('#feedback-falha-area [role=alert]'), 0, 'o bloco de falha sai');
  assert.equal(await ctx.lerTexto('#feedback-agradecimento'), T.agradecimento);
  const tentativas2 = await ctx.avaliar('window.__tentativas');
  assert.equal(tentativas2.length, 2);
  assert.equal(tentativas2[1], tentativas1[0], 'a segunda tentativa reutiliza a mesma Chave_de_Idempotencia');
  const regs = await ctx.feedbacksLocais();
  assert.equal(regs.length, 1);
  assert.equal(regs[0].chaveIdempotencia, tentativas1[0]);
  assert.equal(regs[0].comentario, novo, 'vai o texto atualizado');
  assert.equal((await eventosDo(ctx, 'comentario')).length, 1);
  assert.equal((await ctx.avaliar('window.TRESMetricas.resumo()')).comentarios, 1);
  ctx.semErros();
});

cenario('sem aviso de protótipo: o agradecimento é o texto de data.js e nada na tela cita protótipo', async (ctx) => {
  await irParaResolvido(ctx);
  const T = await textos(ctx);
  assert.ok(!/protótipo/i.test(Object.values(T).join(' ')), 'FEEDBACK.textos não tem texto de protótipo');

  await ctx.digitar('#f-comentario', 'Tudo certo por aqui.');
  await enviarComentario(ctx);
  await ctx.esperar('document.querySelector("#feedback-agradecimento").textContent.trim().length > 0', 500, 'agradecimento');

  assert.equal(await ctx.lerTexto('#feedback-agradecimento'), T.agradecimento);
  const restos = await ctx.avaliar(() => {
    const v = document.querySelector('#view-resolvido');
    return {
      texto: v.textContent,
      elementos: v.querySelectorAll('[id*="prototipo" i], [class*="prototipo" i], [data-texto-feedback*="prototipo" i]').length,
      avisos: v.querySelectorAll('.aviso, .aviso-prototipo, [role="note"]').length
    };
  });
  assert.ok(!/protótipo/i.test(restos.texto), 'nenhum texto de protótipo na Tela_de_Resolvido');
  assert.equal(restos.elementos, 0);
  assert.equal(restos.avisos, 0);
  ctx.semErros();
});

cenario('conteúdo indisponível: sem uma chave de FEEDBACK.textos o formulário é omitido; estrelas e links funcionam', { semTextosFeedback: ['agradecimento'] }, async (ctx) => {
  await ctx.abrir('#/confirma/' + ID);
  await ctx.esperar('!document.querySelector("#view-confirma").hidden', 1000, 'tela "O problema foi solucionado?"');
  await ctx.clicar('#btn-sim');
  await ctx.esperar('location.hash === "#/resolvido/' + ID + '" && !document.querySelector("#view-resolvido").hidden', 1000, 'tela de problema resolvido');

  assert.equal(await ctx.avaliar('window.TRES_DATA.FEEDBACK.textos.agradecimento'), undefined, 'a chave foi mesmo removida');
  assert.equal(await ctx.visivel('#form-feedback'), false, 'formulário omitido');
  assert.equal(await ctx.atributo('#form-feedback', 'hidden') !== null, true);
  assert.equal(await ctx.lerTexto('#f-comentario-contador'), '', 'nada foi montado');
  assert.equal(await ctx.lerTexto('#titulo-resolvido'), 'Que bom! Seu café está de volta.');
  assert.equal(await ctx.lerTexto('#titulo-aval'), 'Como foi a ajuda?');

  // Estrelas funcionam como antes.
  assert.equal(await ctx.contar('#estrelas button'), 5);
  await ctx.avaliar('document.querySelectorAll("#estrelas button")[2].click()');
  const av = await eventosDo(ctx, 'avaliacao');
  assert.equal(av.length, 1);
  assert.equal(av[0].nota, 3);
  assert.equal(await ctx.lerTexto('#status-aval'), 'Obrigado pela sua avaliação!');
  assert.ok(await ctx.visivel('#cuidados-resolvido'));

  // Links funcionam.
  assert.equal(await ctx.lerTexto('#view-resolvido .passo-acoes a[href="#/problemas"]'), 'Tenho outro problema');
  assert.equal(await ctx.lerTexto('#view-resolvido .passo-acoes a[href="#/"]'), 'Voltar ao início');
  await ctx.clicar('#view-resolvido .passo-acoes a[href="#/problemas"]');
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1000, '"Tenho outro problema"');

  assert.deepEqual(await ctx.feedbacksLocais(), []);
  ctx.semErros();
});

cenario('estrutura: ordem estrelas, formulário, cuidados, links; um único campo editável; sem identificação nem "Ler os termos"', async (ctx) => {
  await irParaResolvido(ctx);
  const T = await textos(ctx);

  const e = await ctx.avaliar(() => {
    const q = (s) => document.querySelector(s);
    const antes = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
    const topo = (s) => q(s).getBoundingClientRect().top;
    const view = q('#view-resolvido');
    const editaveis = Array.from(view.querySelectorAll('input, textarea, select, [contenteditable]:not([contenteditable="false"])'));
    const campo = q('#f-comentario');
    const rotulo = q('label[for="f-comentario"]');
    const citados = (campo.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
    return {
      ordemDom: [antes(q('#estrelas'), q('#form-feedback')), antes(q('#form-feedback'), q('#cuidados-resolvido')), antes(q('#cuidados-resolvido'), q('#view-resolvido .passo-acoes'))],
      ordemVisual: [topo('#estrelas') < topo('#form-feedback'), topo('#form-feedback') < topo('#cuidados-resolvido'), topo('#cuidados-resolvido') < topo('#view-resolvido .passo-acoes')],
      dentroDoBlocoDeAvaliacao: !!q('#form-feedback').closest('.avaliacao'),
      editaveis: editaveis.map((n) => n.tagName.toLowerCase() + '#' + n.id),
      botoesNoForm: Array.from(q('#form-feedback').querySelectorAll('button')).map((b) => b.id),
      identificacao: view.querySelectorAll('#c-nome, #c-email, #c-telefone, #c-aceite, input[type="checkbox"], input[type="email"], input[type="tel"], [name="nome"], [name="email"], [name="telefone"]').length,
      textoTermos: /ler os termos/i.test(view.textContent) || !!view.querySelector('#btn-ler-termos, [id*="termos" i]'),
      rotulo: rotulo ? rotulo.textContent.replace(/\s+/g, ' ').trim() : null,
      rotuloVisivel: rotulo ? rotulo.getBoundingClientRect().height > 0 : false,
      atributos: { rows: campo.getAttribute('rows'), maxlength: campo.getAttribute('maxlength'), autocomplete: campo.getAttribute('autocomplete'), tag: campo.tagName.toLowerCase() },
      describedby: campo.getAttribute('aria-describedby'),
      citadosExistem: citados.every((id) => !!document.getElementById(id)),
      aviso: q('#f-comentario-aviso').textContent.trim(),
      ariaLiveNoContador: q('#f-comentario-contador').hasAttribute('aria-live'),
      campoEmFocoNaAbertura: document.activeElement === campo
    };
  });

  assert.deepEqual(e.ordemDom, [true, true, true], 'ordem no DOM: estrelas, formulário, cuidados, links');
  assert.deepEqual(e.ordemVisual, [true, true, true], 'ordem visual: estrelas, formulário, cuidados, links');
  assert.equal(e.dentroDoBlocoDeAvaliacao, true);
  assert.deepEqual(e.editaveis, ['textarea#f-comentario'], 'um único campo editável na tela');
  assert.deepEqual(e.botoesNoForm, ['btn-enviar-comentario']);
  assert.equal(e.identificacao, 0, 'sem campos de nome, e-mail, telefone nem aceite');
  assert.equal(e.textoTermos, false, 'sem "Ler os termos"');
  assert.match(e.rotulo, new RegExp(T.rotulo.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
  assert.match(e.rotulo, /opcional/i);
  assert.equal(e.rotuloVisivel, true);
  assert.deepEqual(e.atributos, { rows: '4', maxlength: '500', autocomplete: 'off', tag: 'textarea' });
  assert.equal(e.describedby, DESCRIBEDBY_REPOUSO);
  assert.equal(e.citadosExistem, true);
  assert.equal(e.aviso, T.avisoNaoIdentificacao);
  assert.ok(e.aviso.length >= 1 && e.aviso.length <= 200);
  assert.equal(e.ariaLiveNoContador, false);
  assert.equal(e.campoEmFocoNaAbertura, false, 'o foco não vai para o campo');
  assert.equal((await ctx.foco()).id, 'titulo-resolvido');
  assert.equal(await ctx.lerTexto('#f-comentario-contador'), '0 de 500 caracteres');
  assert.equal(await ctx.valor('#f-comentario'), '');
  ctx.semErros();
});

cenario('foco no h1 ao abrir #/resolvido/ID direto pela URL (carga nova)', async (ctx) => {
  await ctx.abrir('#/resolvido/' + ID);
  await ctx.esperar('document.activeElement && document.activeElement.id === "titulo-resolvido"', 300, 'foco no h1 em até 300 ms');
  assert.notEqual((await ctx.foco()).id, 'f-comentario');
  assert.ok(await ctx.visivel('#form-feedback'));
  ctx.semErros();
});

cenario('foco no h1 ao chegar por "Sim", pelo botão voltar e pelo botão avançar do navegador', async (ctx) => {
  const foco = (descricao) => ctx.esperar('document.activeElement && document.activeElement.id === "titulo-resolvido"', 300, 'foco no h1 ' + descricao);
  const emResolvido = () => ctx.esperar('location.hash === "#/resolvido/' + ID + '" && !document.querySelector("#view-resolvido").hidden', 1000, 'tela de problema resolvido');

  // Resposta "Sim".
  await ctx.abrir('#/confirma/' + ID);
  await ctx.esperar('!document.querySelector("#view-confirma").hidden', 1000, 'tela "O problema foi solucionado?"');
  await ctx.clicar('#btn-sim');
  await emResolvido();
  await foco('depois de "Sim"');

  // Voltar: resolvido -> problemas (link) -> voltar.
  await ctx.clicar('#view-resolvido .passo-acoes a[href="#/problemas"]');
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1000, 'tela de problemas');
  await ctx.avaliar('history.back()');
  await emResolvido();
  await foco('depois de voltar');
  assert.ok(await ctx.visivel('#form-feedback'));

  // Avançar: resolvido -> confirma (voltar) -> avançar.
  await ctx.avaliar('history.back()');
  await ctx.esperar('location.hash === "#/confirma/' + ID + '" && !document.querySelector("#view-confirma").hidden', 1000, 'voltar à confirmação');
  await ctx.avaliar('history.forward()');
  await emResolvido();
  await foco('depois de avançar');
  assert.notEqual((await ctx.foco()).id, 'f-comentario');
  ctx.semErros();
});
