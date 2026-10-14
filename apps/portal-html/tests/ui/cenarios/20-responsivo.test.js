'use strict';
// Tarefa 12.10: responsivo em 360, 480, 768 e 1024 px (Tela_de_Chamado e Tela_de_Confirmacao).
// Confere: sem rolagem horizontal (11.1), alvos de 44 px com 8 px de espaço (11.2), fonte dos
// campos de 16 px (11.3), lista de passos recolhida até 480 px e expandida acima (2.9, 2.11, 2.12).
// Capturas de tela de cada estado ficam na pasta temporária (ctx.capturar) para revisão visual.
// Tarefa 10.10 (resolved-feedback-comment): também a Tela_de_Resolvido com o formulário de comentário
// (antes e depois do envio), com os mesmos critérios (12.1, 12.2, 12.3) mais foco visível (12.5).
const assert = require('node:assert/strict');
const { cenario } = require('../cenarios');

const LARGURAS = [360, 480, 768, 1024];
const PROBLEMA = 'A máquina não extrai bebida';
const DADOS = {
  nome: 'Maria da Silva',
  email: 'maria.silva@exemplo.com.br',
  telefone: '(11) 91234-5678',
  descricao: 'A máquina não extrai o café mesmo com água no reservatório.',
  aceite: true
};

const viewport = (largura) => ({ largura, altura: largura >= 768 ? 900 : 780 });

/** Chega à Tela_de_Chamado como o consumidor: escolhe LOV e o problema, percorre um passo e diz "Não, ainda não". */
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
 * Mede, dentro da view indicada: rolagem horizontal, cortes laterais, alvos de toque e espaçamento.
 * Roda na página (serializada), por isso não usa nada de fora.
 */
function medirLayout(seletorView) {
  const view = document.querySelector(seletorView);
  const largura = window.innerWidth;
  const doc = document.documentElement;
  const visivel = (el) => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 || r.height === 0) return false;
    const cs = getComputedStyle(el);
    return cs.visibility !== 'hidden' && cs.display !== 'none';
  };
  const nome = (el) => (el.id ? '#' + el.id : el.tagName.toLowerCase() + (el.className ? '.' + String(el.className).split(/\s+/)[0] : '')) +
    ((el.textContent || '').trim() ? ' "' + el.textContent.trim().slice(0, 24) + '"' : '');

  // Elementos da view que escapam da largura da viewport (corte lateral).
  const cortados = [];
  view.querySelectorAll('*').forEach((el) => {
    if (!visivel(el) || el.closest('.sr-only')) return;
    const r = el.getBoundingClientRect();
    if (r.right > largura + 0.5 || r.left < -0.5) cortados.push(nome(el) + ' [' + Math.round(r.left) + ',' + Math.round(r.right) + ']');
  });

  // Alvos de toque: botões, links, campos e a caixa de aceite (o alvo dela é o rótulo inteiro).
  const alvos = [];
  view.querySelectorAll('button, a[href], input, textarea, select, summary').forEach((el) => {
    if (!visivel(el) || el.closest('.sr-only') || el.type === 'hidden') return;
    const dono = el.type === 'checkbox' ? (el.closest('label') || el) : el;
    if (alvos.some((a) => a.el === dono)) return;
    const r = dono.getBoundingClientRect();
    alvos.push({ el: dono, nome: nome(dono), l: r.left, t: r.top, r: r.right, b: r.bottom, w: r.width, h: r.height });
  });
  const pequenos = alvos.filter((a) => a.w < 44 - 0.01 || a.h < 44 - 0.01)
    .map((a) => a.nome + ' ' + a.w.toFixed(1) + 'x' + a.h.toFixed(1));

  const juntos = [];
  for (let i = 0; i < alvos.length; i++) {
    for (let j = i + 1; j < alvos.length; j++) {
      const a = alvos[i];
      const b = alvos[j];
      if (a.el.contains(b.el) || b.el.contains(a.el)) continue;
      const dx = Math.max(0, a.l - b.r, b.l - a.r);
      const dy = Math.max(0, a.t - b.b, b.t - a.b);
      const dist = Math.hypot(dx, dy);
      if (dist < 8 - 0.01) juntos.push(a.nome + ' / ' + b.nome + ' = ' + dist.toFixed(1) + ' px');
    }
  }

  return {
    innerWidth: largura,
    scrollWidthDoc: doc.scrollWidth,
    scrollWidthBody: document.body.scrollWidth,
    cortados,
    totalAlvos: alvos.length,
    pequenos,
    juntos
  };
}

function afirmarLayout(m, rotulo) {
  assert.ok(m.scrollWidthDoc <= m.innerWidth, rotulo + ': rolagem horizontal no documento (scrollWidth ' + m.scrollWidthDoc + ' > innerWidth ' + m.innerWidth + ')');
  assert.ok(m.scrollWidthBody <= m.innerWidth, rotulo + ': rolagem horizontal no body (scrollWidth ' + m.scrollWidthBody + ' > innerWidth ' + m.innerWidth + ')');
  assert.deepEqual(m.cortados, [], rotulo + ': elementos cortados pela lateral da viewport');
  assert.ok(m.totalAlvos > 0, rotulo + ': nenhum alvo de toque encontrado (seletor errado?)');
  assert.deepEqual(m.pequenos, [], rotulo + ': alvos de toque menores que 44 x 44 px');
  assert.deepEqual(m.juntos, [], rotulo + ': alvos de toque com menos de 8 px de espaço entre si');
}

// ---------------------------------------------------------------------------
// Tarefa 10.10 (resolved-feedback-comment): Tela_de_Resolvido com o formulário de comentário
// (antes e depois do envio). Requisitos 12.1, 12.2, 12.3 (e 12.5 para o foco visível).
// ---------------------------------------------------------------------------
const ID_RESOLVIDO = 1; // "A máquina não liga"

/** Chega a #/resolvido/ID respondendo "Sim, resolvi", com o formulário de comentário visível. */
async function irParaResolvido(ctx) {
  await ctx.abrir('#/');
  await ctx.avaliar(() => {
    const btn = Array.from(document.querySelectorAll('#lista-modelos .modelo__nome'))
      .find((n) => n.textContent.trim() === 'LOV');
    btn.closest('button').click();
  });
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1500, 'tela de problemas');
  await ctx.avaliar('location.hash = "#/confirma/' + ID_RESOLVIDO + '"');
  await ctx.esperar('!document.querySelector("#view-confirma").hidden', 1000, 'tela "O problema foi solucionado?"');
  await ctx.clicar('#btn-sim');
  await ctx.esperar('location.hash === "#/resolvido/' + ID_RESOLVIDO + '" && !document.querySelector("#view-resolvido").hidden', 1000, 'Tela_de_Resolvido');
  await ctx.esperar('!document.querySelector("#form-feedback").hidden', 500, 'formulário de comentário visível');
}

/**
 * Mede o formulário de comentário: fonte do campo (digitado e orientação), largura do formulário
 * em relação ao bloco de avaliação e largura do campo/botão em relação ao formulário.
 * Roda na página (serializada).
 */
function medirFormulario() {
  const bloco = document.querySelector('#view-resolvido .avaliacao');
  const form = document.querySelector('#form-feedback');
  const campo = document.querySelector('#f-comentario');
  const botao = document.querySelector('#btn-enviar-comentario');
  const cb = getComputedStyle(bloco);
  const larguraBloco = bloco.getBoundingClientRect().width - parseFloat(cb.paddingLeft) - parseFloat(cb.paddingRight) -
    parseFloat(cb.borderLeftWidth) - parseFloat(cb.borderRightWidth);
  const rf = form.getBoundingClientRect();
  const rc = campo.getBoundingClientRect();
  const rb = botao.getBoundingClientRect();
  return {
    larguraBloco,
    larguraForm: rf.width,
    esquerdaForm: rf.left,
    larguraCampo: rc.width,
    esquerdaCampo: rc.left,
    direitaCampo: rc.right,
    direitaForm: rf.right,
    larguraBotao: rb.width,
    fonteCampo: parseFloat(getComputedStyle(campo).fontSize),
    fonteOrientacao: parseFloat(getComputedStyle(campo, '::placeholder').fontSize),
    alturaCampo: rc.height,
    alturaBotao: rb.height,
    maxWidthForm: getComputedStyle(form).maxWidth
  };
}

function afirmarFormulario(f, largura, rotulo) {
  // 12.1: o formulário ocupa a largura do bloco (limitada ao máximo de 640 px do CSS) e o campo, a do formulário.
  const esperada = Math.min(f.larguraBloco, 640);
  assert.ok(Math.abs(f.larguraForm - esperada) <= 1, rotulo + ': formulário com ' + f.larguraForm.toFixed(1) + ' px, esperado ' + esperada.toFixed(1) + ' px (bloco ' + f.larguraBloco.toFixed(1) + ' px)');
  assert.ok(Math.abs(f.larguraCampo - f.larguraForm) <= 1, rotulo + ': campo com ' + f.larguraCampo.toFixed(1) + ' px, formulário com ' + f.larguraForm.toFixed(1) + ' px');
  assert.ok(f.esquerdaCampo >= f.esquerdaForm - 0.5 && f.direitaCampo <= f.direitaForm + 0.5, rotulo + ': campo escapa do formulário');
  assert.ok(f.larguraForm <= largura, rotulo + ': formulário mais largo que a viewport');
  // 12.2: alvos de 44 px (o botão e o campo; as demais medidas vêm de medirLayout).
  assert.ok(f.alturaCampo >= 44 && f.larguraCampo >= 44, rotulo + ': campo ' + f.larguraCampo.toFixed(1) + 'x' + f.alturaCampo.toFixed(1));
  assert.ok(f.alturaBotao >= 44 && f.larguraBotao >= 44, rotulo + ': botão ' + f.larguraBotao.toFixed(1) + 'x' + f.alturaBotao.toFixed(1));
  // 12.3: fonte de pelo menos 16 px, no texto digitado e na orientação.
  assert.ok(f.fonteCampo >= 16, rotulo + ': fonte do campo ' + f.fonteCampo + ' px < 16 px');
  assert.ok(f.fonteOrientacao >= 16, rotulo + ': fonte da orientação ' + f.fonteOrientacao + ' px < 16 px');
}

/** Foco do teclado no controle indicado: contorno de 2 px ou mais, visível e dentro da viewport (não cortado). */
function medirFoco() {
  const el = document.activeElement;
  const cs = getComputedStyle(el);
  const r = el.getBoundingClientRect();
  const espessura = parseFloat(cs.outlineWidth) || 0;
  const desloc = parseFloat(cs.outlineOffset) || 0;
  const borda = espessura + Math.max(0, desloc);
  return {
    id: el.id || null,
    focoVisivel: el.matches(':focus-visible'),
    estilo: cs.outlineStyle,
    espessura,
    corContorno: cs.outlineColor,
    corFundo: getComputedStyle(el.parentElement).backgroundColor,
    esquerda: r.left - borda,
    direita: r.right + borda,
    largura: window.innerWidth
  };
}

function afirmarFoco(m, idEsperado, rotulo) {
  assert.equal(m.id, idEsperado, rotulo + ': o foco deveria estar em #' + idEsperado);
  assert.equal(m.focoVisivel, true, rotulo + ': #' + idEsperado + ' deveria casar :focus-visible com o teclado');
  assert.notEqual(m.estilo, 'none', rotulo + ': #' + idEsperado + ' sem contorno de foco');
  assert.ok(m.espessura >= 2, rotulo + ': contorno de foco de ' + m.espessura + ' px (< 2 px) em #' + idEsperado);
  assert.ok(m.esquerda >= 0 && m.direita <= m.largura, rotulo + ': contorno de foco de #' + idEsperado + ' cortado pela lateral [' + Math.round(m.esquerda) + ',' + Math.round(m.direita) + ']');
}

for (const largura of LARGURAS) {
  cenario('Responsivo ' + largura + ' px: Tela_de_Resolvido com o formulário sem rolagem horizontal, alvos de 44 px, campo de 16 px, foco visível e largura do bloco',
    { viewport: viewport(largura) }, async (ctx) => {
      await irParaResolvido(ctx);
      assert.equal(await ctx.avaliar('window.innerWidth'), largura, 'a emulação de viewport deve valer na página');

      // 12.1, 12.2: layout, alvos (estrelas, campo, botão, links) e espaçamento em #view-resolvido.
      const medidas = await ctx.avaliar(medirLayout, '#view-resolvido');
      await ctx.capturar('responsivo-' + largura + '-resolvido-formulario');
      afirmarLayout(medidas, largura + ' px, Tela_de_Resolvido com o formulário');
      // Estrelas (5) + campo + botão + 2 links = pelo menos 9 alvos.
      assert.ok(medidas.totalAlvos >= 9, largura + ' px: esperava ao menos 9 alvos (5 estrelas, campo, botão, 2 links), achei ' + medidas.totalAlvos);

      // 12.3 e largura do formulário.
      afirmarFormulario(await ctx.avaliar(medirFormulario), largura, largura + ' px, Tela_de_Resolvido');

      // 12.5: foco do teclado no campo e no botão (Tab), contorno visível e sem corte.
      await ctx.avaliar('document.querySelector("#f-comentario").focus()');
      afirmarFoco(await ctx.avaliar(medirFoco), 'f-comentario', largura + ' px');
      await ctx.teclar('Tab');
      afirmarFoco(await ctx.avaliar(medirFoco), 'btn-enviar-comentario', largura + ' px');

      ctx.semErros();
    });

  cenario('Responsivo ' + largura + ' px: Tela_de_Resolvido depois do envio sem rolagem horizontal, alvos de 44 px e sem cortes',
    { viewport: viewport(largura) }, async (ctx) => {
      await irParaResolvido(ctx);
      // Texto longo, sem espaços, para provar que não estoura a largura do campo nem da tela.
      const texto = 'Muito obrigado pela ajuda, funcionou! ' + 'x'.repeat(80) + ' ' + 'Passo a passo claro e fácil de seguir. '.repeat(3);
      await ctx.digitar('#f-comentario', texto);
      await ctx.clicar('#btn-enviar-comentario');
      await ctx.esperar('document.querySelector("#feedback-agradecimento").textContent.trim().length > 0', 500, 'agradecimento do comentário');
      assert.equal(await ctx.avaliar('window.innerWidth'), largura);

      const medidas = await ctx.avaliar(medirLayout, '#view-resolvido');
      await ctx.capturar('responsivo-' + largura + '-resolvido-enviado');
      afirmarLayout(medidas, largura + ' px, Tela_de_Resolvido depois do envio');
      assert.ok(await ctx.visivel('#feedback-agradecimento'), 'o agradecimento deve ficar visível');
      afirmarFormulario(await ctx.avaliar(medirFormulario), largura, largura + ' px, Tela_de_Resolvido depois do envio');
      ctx.semErros();
    });
}

for (const largura of LARGURAS) {
  cenario('Responsivo ' + largura + ' px: Tela_de_Chamado sem rolagem horizontal, alvos de 44 px, campos de 16 px e resumo ' +
    (largura <= 480 ? 'recolhido' : 'expandido'), { viewport: viewport(largura) }, async (ctx) => {
    await irParaChamado(ctx);
    assert.equal(await ctx.avaliar('window.innerWidth'), largura, 'a emulação de viewport deve valer na página');

    // 11.1, 11.2: layout, alvos e espaçamento.
    afirmarLayout(await ctx.avaliar(medirLayout, '#view-suporte'), largura + ' px, Tela_de_Chamado');

    // 11.3: fonte de pelo menos 16 px nos campos (texto digitado e texto de orientação).
    const fontes = await ctx.avaliar(() => Array.from(document.querySelectorAll('#form-chamado input:not([type=checkbox]), #form-chamado textarea')).map((el) => ({
      id: el.id,
      campo: parseFloat(getComputedStyle(el).fontSize),
      orientacao: parseFloat(getComputedStyle(el, '::placeholder').fontSize)
    })));
    assert.equal(fontes.length, 4, 'nome, e-mail, telefone e descrição');
    for (const f of fontes) {
      assert.ok(f.campo >= 16, '#' + f.id + ': fonte do campo ' + f.campo + ' px < 16 px');
      assert.ok(f.orientacao >= 16, '#' + f.id + ': fonte da orientação ' + f.orientacao + ' px < 16 px');
    }

    // 2.9, 2.12: resumo recolhido até 480 px; expandido e sem controle acima.
    assert.ok(await ctx.visivel('#resumo-modelo'), 'o modelo deve ficar visível');
    assert.ok(await ctx.visivel('#resumo-problema'), 'o título do problema deve ficar visível');
    assert.match(await ctx.lerTexto('#resumo-contagem'), /^\d+ de \d+ passos$/);
    if (largura <= 480) {
      assert.equal(await ctx.visivel('#resumo-passos'), false, 'até 480 px a lista nasce recolhida');
      assert.ok(await ctx.visivel('#resumo-toggle'), 'até 480 px o controle de expandir aparece');
      assert.equal(await ctx.atributo('#resumo-toggle', 'aria-expanded'), 'false');
      await ctx.capturar('responsivo-' + largura + '-chamado-recolhido');

      // 2.11: alterna em até 300 ms (por toque/clique) e fica expandido.
      await ctx.clicar('#resumo-toggle');
      await ctx.esperar('document.querySelector("#resumo-toggle").getAttribute("aria-expanded") === "true"', 300, 'expandir em até 300 ms');
      await ctx.esperar('getComputedStyle(document.querySelector("#resumo-passos")).display !== "none"', 300, 'lista visível em até 300 ms');
      assert.ok(await ctx.visivel('#resumo-lista'), 'a lista de passos deve aparecer expandida');
      afirmarLayout(await ctx.avaliar(medirLayout, '#view-suporte'), largura + ' px, Tela_de_Chamado expandida');
      await ctx.capturar('responsivo-' + largura + '-chamado-expandido');
    } else {
      assert.ok(await ctx.visivel('#resumo-passos'), 'acima de 480 px a lista fica sempre expandida');
      assert.ok(await ctx.visivel('#resumo-lista'), 'a lista de passos deve estar visível');
      assert.equal(await ctx.visivel('#resumo-toggle'), false, 'acima de 480 px não há controle de expandir/recolher');
      await ctx.capturar('responsivo-' + largura + '-chamado-expandido');
    }
    ctx.semErros();
  });

  cenario('Responsivo ' + largura + ' px: Tela_de_Confirmacao sem rolagem horizontal, alvos de 44 px e 8 px de espaço',
    { viewport: viewport(largura) }, async (ctx) => {
      const id = await irParaChamado(ctx);
      await ctx.preencherFormulario(DADOS);
      await ctx.enviar();
      await ctx.esperar('location.hash === "#/chamado/' + id + '" && !document.querySelector("#view-chamado").hidden', 1000, 'Tela_de_Confirmacao');
      assert.equal(await ctx.avaliar('window.innerWidth'), largura);

      const medidas = await ctx.avaliar(medirLayout, '#view-chamado');
      await ctx.capturar('responsivo-' + largura + '-confirmacao');
      afirmarLayout(medidas, largura + ' px, Tela_de_Confirmacao');
      ctx.semErros();
    });
}
