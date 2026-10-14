'use strict';
// Tarefa 12.8: estrelas de avaliação (Requisitos 9.8, 9.9, 9.10, 8.19).
// - Confirmação do chamado: nota grava `avaliacao` com desfecho 'chamado' e protocolo.
// - Tela_de_Chamado: sem estrelas e sem evento `avaliacao` antes do envio.
// - Problema resolvido: mesmo evento de antes (desfecho 'resolvido', sem protocolo).
const assert = require('node:assert/strict');
const { cenario } = require('../cenarios');

const DADOS = {
  nome: 'Maria da Silva',
  email: 'maria.silva@exemplo.com.br',
  telefone: '(11) 91234-5678',
  descricao: 'A máquina não extrai o café mesmo com água no reservatório.',
  aceite: true
};
const PROBLEMA = 'A máquina não extrai bebida';

/** Escolhe o modelo LOV e o problema pelos botões e devolve o id do problema. */
async function escolherModeloEProblema(ctx) {
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
  return ctx.avaliar((titulo) => window.TRES_DATA.PROBLEMAS.find((x) => x.titulo === titulo).id, PROBLEMA);
}

/** Vai direto à tela "O problema foi solucionado?" do problema escolhido. */
async function irParaConfirma(ctx, id) {
  await ctx.avaliar('location.hash = "#/confirma/' + id + '"');
  await ctx.esperar('!document.querySelector("#view-confirma").hidden', 1000, 'tela "O problema foi solucionado?"');
}

/** Responde "Não, ainda não", preenche o formulário e envia; espera a Tela_de_Confirmacao. */
async function abrirChamado(ctx, id) {
  await irParaConfirma(ctx, id);
  await ctx.clicar('#btn-nao');
  await ctx.esperar('location.hash === "#/suporte/' + id + '"', 1000, 'rota #/suporte/ID');
}

async function enviarEEsperarConfirmacao(ctx, id) {
  await ctx.preencherFormulario(DADOS);
  await ctx.enviar();
  await ctx.esperar('location.hash === "#/chamado/' + id + '" && !document.querySelector("#view-chamado").hidden', 1000, 'Tela_de_Confirmacao');
}

const avaliacoes = async (ctx) => (await ctx.eventos()).filter((e) => e.tipo === 'avaliacao');

cenario('confirmação: tocar a nota 4 grava avaliacao com desfecho chamado, protocolo e sem dados pessoais', async (ctx) => {
  const id = await escolherModeloEProblema(ctx);
  await abrirChamado(ctx, id);
  await enviarEEsperarConfirmacao(ctx, id);

  // 8.19 / 11.15: cinco botões "N estrela(s) de 5", sem nota marcada, status vazio.
  const rotulos = await ctx.avaliar(() => Array.from(document.querySelectorAll('#estrelas-chamado button')).map((b) => b.getAttribute('aria-label')));
  assert.deepEqual(rotulos, ['1 estrela de 5', '2 estrelas de 5', '3 estrelas de 5', '4 estrelas de 5', '5 estrelas de 5']);
  assert.equal(await ctx.lerTexto('#status-aval-chamado'), '');
  assert.deepEqual(await avaliacoes(ctx), [], 'nenhuma avaliação antes de tocar uma nota');

  const protocolo = await ctx.lerTexto('#chamado-protocolo');
  assert.match(protocolo, /^TRES-\d{8}-[A-Z0-9]{6}$/);

  await ctx.avaliar('document.querySelectorAll("#estrelas-chamado button")[3].click()');

  // 9.9: evento avaliacao com nota, desfecho, problema, modelo, protocolo e instante.
  const av = await avaliacoes(ctx);
  assert.equal(av.length, 1, 'exatamente um evento avaliacao');
  assert.equal(av[0].nota, 4);
  assert.equal(av[0].desfecho, 'chamado');
  assert.equal(av[0].protocolo, protocolo);
  assert.equal(av[0].problema, id);
  assert.equal(av[0].modelo, 'lov');
  assert.ok(!Number.isNaN(Date.parse(av[0].em)), 'o evento deve ter o instante do registro');

  // 9.3: sem dados pessoais no evento.
  const bruto = JSON.stringify(av[0]).toLowerCase();
  for (const v of [DADOS.nome, DADOS.email, '11912345678', DADOS.descricao]) {
    assert.ok(!bruto.includes(v.toLowerCase()), 'o evento avaliacao não deve conter dado pessoal: ' + v);
  }
  assert.deepEqual(Object.keys(av[0]).sort(), ['desfecho', 'em', 'modelo', 'nota', 'problema', 'protocolo', 'tipo']);

  // 9.9: agradecimento em região aria-live; estado das estrelas.
  assert.equal(await ctx.lerTexto('#status-aval-chamado'), 'Obrigado pela sua avaliação!');
  assert.equal(await ctx.atributo('#status-aval-chamado', 'aria-live'), 'polite');
  const pressionados = await ctx.avaliar(() => Array.from(document.querySelectorAll('#estrelas-chamado button')).map((b) => b.getAttribute('aria-pressed')));
  assert.deepEqual(pressionados, ['false', 'false', 'false', 'true', 'false']);

  // Avaliação não afeta os demais indicadores e não bloqueia a navegação.
  const resumo = await ctx.avaliar('window.TRESMetricas.resumo()');
  assert.equal(resumo.chamadosAbertos, 1);
  assert.equal(resumo.encaminhadosAoSuporte, 1);
  assert.equal(resumo.resolvidos, 0);

  ctx.semErros();
});

cenario('confirmação: a nota é operável por teclado (Enter/Espaço) e uma nova nota grava novo evento com o mesmo protocolo', async (ctx) => {
  const id = await escolherModeloEProblema(ctx);
  await abrirChamado(ctx, id);
  await enviarEEsperarConfirmacao(ctx, id);
  const protocolo = await ctx.lerTexto('#chamado-protocolo');

  // Botões nativos: foco + Enter aciona o clique.
  await ctx.avaliar('document.querySelectorAll("#estrelas-chamado button")[1].focus()');
  await ctx.teclar('Enter');
  await ctx.esperar('document.querySelector("#status-aval-chamado").textContent.length > 0', 500, 'agradecimento após Enter');

  let av = await avaliacoes(ctx);
  assert.equal(av.length, 1);
  assert.equal(av[0].nota, 2);
  assert.equal(av[0].desfecho, 'chamado');
  assert.equal(av[0].protocolo, protocolo);

  await ctx.avaliar('document.querySelectorAll("#estrelas-chamado button")[4].focus()');
  await ctx.teclar('Space');
  await ctx.esperar('document.querySelectorAll("#estrelas-chamado button")[4].getAttribute("aria-pressed") === "true"', 500, 'quinta estrela marcada');

  av = await avaliacoes(ctx);
  assert.equal(av.length, 2);
  assert.equal(av[1].nota, 5);
  assert.equal(av[1].protocolo, protocolo);
  ctx.semErros();
});

cenario('Tela_de_Chamado: não tem estrelas e nenhum evento avaliacao é gravado antes do envio', async (ctx) => {
  const id = await escolherModeloEProblema(ctx);
  await abrirChamado(ctx, id);

  // 9.10: nada de Componente_de_Avaliacao dentro da Tela_de_Chamado.
  assert.ok(await ctx.visivel('#view-suporte'));
  const estrelasNaTela = await ctx.avaliar(() => {
    const v = document.querySelector('#view-suporte');
    return {
      botoes: v.querySelectorAll('.estrela, .estrelas, .avaliacao, [aria-label$=" de 5"]').length,
      glifos: Array.from(v.querySelectorAll('button')).filter((b) => b.textContent.includes('★')).length
    };
  });
  assert.deepEqual(estrelasNaTela, { botoes: 0, glifos: 0 });

  // Preenche mas ainda não envia: segue sem avaliação.
  await ctx.preencherFormulario(DADOS);
  assert.deepEqual(await avaliacoes(ctx), []);
  assert.equal((await ctx.eventos()).filter((e) => e.desfecho === 'suporte' || e.desfecho === 'chamado').length, 0);

  // A confirmação só aparece depois do envio; mesmo então, sem nota tocada, nada é gravado.
  await ctx.enviar();
  await ctx.esperar('location.hash === "#/chamado/' + id + '" && !document.querySelector("#view-chamado").hidden', 1000, 'Tela_de_Confirmacao');
  assert.deepEqual(await avaliacoes(ctx), []);
  ctx.semErros();
});

cenario('problema resolvido: tocar a nota 5 grava o mesmo evento de antes (desfecho resolvido, sem protocolo)', async (ctx) => {
  const id = await escolherModeloEProblema(ctx);
  await irParaConfirma(ctx, id);
  await ctx.clicar('#btn-sim');
  await ctx.esperar('location.hash === "#/resolvido/' + id + '" && !document.querySelector("#view-resolvido").hidden', 1000, 'tela de problema resolvido');

  assert.equal(await ctx.contar('#estrelas button'), 5);
  assert.equal(await ctx.lerTexto('#status-aval'), '');
  assert.deepEqual(await avaliacoes(ctx), []);

  await ctx.avaliar('document.querySelectorAll("#estrelas button")[4].click()');

  const av = await avaliacoes(ctx);
  assert.equal(av.length, 1);
  assert.deepEqual(Object.keys(av[0]).sort(), ['desfecho', 'em', 'modelo', 'nota', 'problema', 'tipo']);
  assert.equal(av[0].nota, 5);
  assert.equal(av[0].desfecho, 'resolvido');
  assert.equal(av[0].problema, id);
  assert.equal(av[0].modelo, 'lov');
  assert.ok('protocolo' in av[0] === false, 'a avaliação de problema resolvido não leva protocolo');
  assert.ok(!Number.isNaN(Date.parse(av[0].em)));

  assert.equal(await ctx.lerTexto('#status-aval'), 'Obrigado pela sua avaliação!');
  assert.equal(await ctx.atributo('#status-aval', 'aria-live'), 'polite');

  const resumo = await ctx.avaliar('window.TRESMetricas.resumo()');
  assert.equal(resumo.resolvidos, 1);
  assert.equal(resumo.encaminhadosAoSuporte, 0);
  assert.equal(resumo.chamadosAbertos, 0);

  // resolved-feedback-comment 3.1: tocar a nota não cria feedback nem evento `comentario`.
  assert.deepEqual(await ctx.feedbacksLocais(), [], 'só a nota: nenhum registro em tres-autoatendimento-feedbacks');
  assert.deepEqual((await ctx.eventos()).filter((e) => e.tipo === 'comentario'), [], 'só a nota: nenhum evento comentario');
  assert.equal(resumo.comentarios, 0);
  ctx.semErros();
});

/** Vai a "O problema foi solucionado?" → "Sim" e espera a tela de problema resolvido com o formulário. */
async function irParaResolvido(ctx, id) {
  await irParaConfirma(ctx, id);
  await ctx.clicar('#btn-sim');
  await ctx.esperar('location.hash === "#/resolvido/' + id + '" && !document.querySelector("#view-resolvido").hidden', 1000, 'tela de problema resolvido');
  await ctx.esperar('!document.querySelector("#form-feedback").hidden', 500, 'formulário de comentário visível');
}

cenario('problema resolvido: a nota escolhida acompanha o comentário e não cria segundo avaliacao; estrela tocada depois do envio não altera o feedback gravado', async (ctx) => {
  const id = await escolherModeloEProblema(ctx);
  await irParaResolvido(ctx, id);

  // Nota 4 antes de comentar: um único avaliacao, exatamente como antes.
  await ctx.avaliar('document.querySelectorAll("#estrelas button")[3].click()');
  assert.equal((await avaliacoes(ctx)).length, 1);

  await ctx.digitar('#f-comentario', 'O passo a passo resolveu rápido.');
  await ctx.clicar('#btn-enviar-comentario');
  await ctx.esperar('document.querySelector("#feedback-agradecimento").textContent.trim().length > 0', 500, 'agradecimento do comentário');

  // 3.1 / 3.3: a nota 4 vai no feedback; o envio não cria segundo avaliacao.
  let regs = await ctx.feedbacksLocais();
  assert.equal(regs.length, 1);
  assert.equal(regs[0].nota, 4);
  assert.equal(regs[0].comentario, 'O passo a passo resolveu rápido.');
  assert.equal(regs[0].problemaId, id);
  assert.equal(regs[0].modelo, 'lov');
  let av = await avaliacoes(ctx);
  assert.equal(av.length, 1, 'o envio do comentário não registra um novo avaliacao');
  assert.equal(av[0].nota, 4);
  assert.equal(av[0].desfecho, 'resolvido');
  assert.equal((await ctx.eventos()).filter((e) => e.tipo === 'comentario').length, 1);
  const gravado = JSON.stringify(regs);

  // 3.4: estrela tocada depois do envio segue gravando avaliacao como antes, sem tocar no feedback gravado.
  await ctx.avaliar('document.querySelectorAll("#estrelas button")[1].click()');
  av = await avaliacoes(ctx);
  assert.equal(av.length, 2, 'a estrela depois do envio grava avaliacao como sempre');
  assert.equal(av[1].nota, 2);
  assert.equal(av[1].desfecho, 'resolvido');
  assert.deepEqual(Object.keys(av[1]).sort(), ['desfecho', 'em', 'modelo', 'nota', 'problema', 'tipo']);
  assert.equal(JSON.stringify(await ctx.feedbacksLocais()), gravado, 'o feedback gravado não muda com a estrela tocada depois');
  assert.equal((await ctx.eventos()).filter((e) => e.tipo === 'comentario').length, 1, 'nenhum novo evento comentario');
  assert.equal(await ctx.lerTexto('#status-aval'), 'Obrigado pela sua avaliação!');
  ctx.semErros();
});

cenario('problema resolvido: o espaçamento de 0,5rem entre as estrelas continua (ajuste gap: 0.5rem)', async (ctx) => {
  const id = await escolherModeloEProblema(ctx);
  await irParaResolvido(ctx, id);
  const m = await ctx.avaliar(() => {
    const cont = document.querySelector('#estrelas');
    const bs = Array.from(cont.querySelectorAll('button')).map((b) => b.getBoundingClientRect());
    const raiz = parseFloat(getComputedStyle(document.documentElement).fontSize);
    return {
      colunaPx: parseFloat(getComputedStyle(cont).columnGap),
      meioRem: 0.5 * raiz,
      vaos: bs.slice(1).map((r, i) => Math.round((r.left - bs[i].right) * 100) / 100),
      larguras: bs.map((r) => Math.round(r.width))
    };
  });
  assert.equal(m.colunaPx, m.meioRem, 'gap das estrelas deve ser 0,5rem');
  assert.deepEqual(m.vaos, [m.meioRem, m.meioRem, m.meioRem, m.meioRem], 'vão visual de 0,5rem entre as cinco estrelas');
  assert.ok(m.larguras.every((w) => w >= 44), 'alvos das estrelas com pelo menos 44 px');
  ctx.semErros();
});
