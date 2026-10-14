'use strict';
// Tarefa 12.12: regressão das rotas existentes (Requisitos 11.9, 12.1, 12.2).
// `#/`, `#/problemas`, `#/solucao/ID`, `#/confirma/ID`, `#/resolvido/ID` e `#/contato` mantêm DOM e
// comportamento depois da nova tela; cabeçalho "Falar com a gente" e rodapé iguais; barra de etapas
// com 3 itens e etapa 3 atual nas telas novas (#/suporte/ID e #/chamado/ID).
// Tarefa 10.7 (resolved-feedback-comment): `#/resolvido/ID` ganha só o bloco de comentário opcional
// (estrelas, formulário, cuidados, links; sem identificação); `#/suporte/ID` e `#/chamado/ID` não o têm;
// o DOM das demais telas não muda e `resumo()` traz `comentarios: 0`.
// Os valores esperados vêm do conteúdo de js/data.js (lido só para leitura, fora do navegador) e dos
// textos que a versão anterior já tinha em index.html.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { cenario } = require('../cenarios');

// Lê js/data.js sem escrever nada: o arquivo só atribui window.TRES_DATA.
const D = (() => {
  const w = {};
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', '..', '..', 'js', 'data.js'), 'utf8'), { window: w });
  return JSON.parse(JSON.stringify(w.TRES_DATA)); // objetos do mesmo realm, para o deepEqual
})();

const PROBLEMA = D.PROBLEMAS.find((p) => p.id === 1); // "A máquina não liga", 3 passos
const ID = PROBLEMA.id;
const TOTAL = PROBLEMA.passos.length;
const C = D.CONTATO;
const DADOS = {
  nome: 'Maria da Silva',
  email: 'maria.silva@exemplo.com.br',
  telefone: '(11) 91234-5678',
  descricao: 'A máquina não liga mesmo depois de trocar a tomada.',
  aceite: true
};

const NOMES_ETAPAS = ['Sua máquina', 'O problema', 'A solução'];

/** Ids das telas (.view) visíveis. Deve ser sempre exatamente uma. */
const viewsVisiveis = (ctx) => ctx.avaliar(() => Array.from(document.querySelectorAll('.view:not([hidden])')).map((v) => v.id));

/** Estado da barra de etapas: itens, etapa atual (aria-current), feitas e se a barra está oculta. */
const etapas = (ctx) => ctx.avaliar(() => {
  const nav = document.querySelector('.etapas');
  const r = nav.getBoundingClientRect();
  return {
    oculta: nav.classList.contains('etapas--oculta') || r.height === 0,
    itens: Array.from(document.querySelectorAll('#etapas li')).map((li) => ({
      num: li.querySelector('.etapas__num').textContent.trim(),
      nome: li.querySelector('.etapas__nome').textContent.trim(),
      atual: li.getAttribute('aria-current'),
      feita: li.classList.contains('feita')
    }))
  };
});

/** Confere a barra: 3 itens com os nomes de sempre, `atual` como etapa corrente e as anteriores como feitas. */
async function conferirEtapas(ctx, atual) {
  const e = await etapas(ctx);
  assert.equal(e.itens.length, 3, 'a barra de etapas deve ter 3 itens');
  assert.deepEqual(e.itens.map((i) => i.nome), NOMES_ETAPAS);
  assert.deepEqual(e.itens.map((i) => i.num), ['1', '2', '3']);
  assert.equal(e.oculta, false, 'a barra de etapas deve estar visível');
  e.itens.forEach((i, k) => {
    const n = k + 1;
    assert.equal(i.atual, n === atual ? 'step' : null, 'aria-current da etapa ' + n);
    assert.equal(i.feita, n < atual, 'etapa ' + n + ' feita?');
  });
}

/** Muda o hash e espera a tela de destino. Vale para navegação dentro da mesma carga. */
async function ir(ctx, hash, view) {
  await ctx.avaliar('location.hash = ' + JSON.stringify(hash));
  await ctx.esperar('location.hash === ' + JSON.stringify(hash) + ' && !document.querySelector("#view-' + view + '").hidden', 1500, hash + ' (#view-' + view + ')');
}

/** Clica o botão do modelo pelo nome (como o consumidor). */
async function escolherModelo(ctx, nome) {
  await ctx.avaliar((n) => {
    const t = Array.from(document.querySelectorAll('#lista-modelos .modelo__nome')).find((x) => x.textContent.trim() === n);
    t.closest('button').click();
  }, nome);
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1500, 'tela de problemas');
}

/** Clica o cartão do problema pelo título. */
async function escolherProblema(ctx, titulo) {
  await ctx.avaliar((tit) => {
    const t = Array.from(document.querySelectorAll('.problema .problema__titulo')).find((x) => x.textContent.trim() === tit);
    t.closest('button').click();
  }, titulo);
  await ctx.esperar('location.hash === "#/solucao/' + ID + '" && !document.querySelector("#view-solucao").hidden', 1500, 'tela de solução');
}

const eventosDo = async (ctx, tipo) => (await ctx.eventos()).filter((e) => e && e.tipo === tipo);

// ---------------------------------------------------------------------------
// #/  (Sua máquina)
// ---------------------------------------------------------------------------

cenario('#/ mantém a tela "Sua máquina": só ela visível, textos, 5 modelos, etapa 1 atual', async (ctx) => {
  await ctx.abrir('#/');
  assert.deepEqual(await viewsVisiveis(ctx), ['view-modelo']);
  assert.equal(await ctx.lerTexto('#titulo-modelo'), 'Sua máquina deu um sinal estranho? Vamos resolver juntos.');
  assert.equal(await ctx.lerTexto('.hero__sobre'), 'Autoatendimento TRES');
  assert.equal(await ctx.lerTexto('.hero__texto'), 'Em geral, é só uma limpeza ou um ajuste simples. Em poucos passos você descobre o que fazer, sem precisar ligar.');
  assert.equal(await ctx.lerTexto('#view-modelo .secao-titulo'), 'Qual é a sua máquina?');

  const modelos = await ctx.avaliar(() => Array.from(document.querySelectorAll('#lista-modelos > li > button.modelo')).map((b) => ({
    nome: b.querySelector('.modelo__nome').textContent.trim(),
    dica: b.querySelector('.modelo__dica').textContent.trim()
  })));
  assert.deepEqual(modelos, D.MODELOS.map((m) => ({ nome: m.nome, dica: m.dica || 'Toque para escolher' })));
  assert.deepEqual(modelos.map((m) => m.nome), ['LOV', 'Modo', 'Passione', 'Luna', 'Touch']);

  await conferirEtapas(ctx, 1);
  // Nada de chamado nem de formulário na tela inicial.
  assert.equal(await ctx.visivel('#form-chamado'), false);
  ctx.semErros();
});

cenario('#/: "Não sei qual é a minha" abre e fecha a dica; "Continuar sem escolher" vai a #/problemas sem modelo', async (ctx) => {
  await ctx.abrir('#/');
  assert.equal(await ctx.lerTexto('#btn-nao-sei'), 'Não sei qual é a minha');
  assert.equal(await ctx.atributo('#btn-nao-sei', 'aria-expanded'), 'false');
  assert.equal(await ctx.visivel('#dica-modelo'), false);

  await ctx.clicar('#btn-nao-sei');
  assert.equal(await ctx.atributo('#btn-nao-sei', 'aria-expanded'), 'true');
  assert.ok(await ctx.visivel('#dica-modelo'));
  assert.equal(await ctx.lerTexto('#btn-pular-modelo'), 'Continuar sem escolher');
  await ctx.clicar('#btn-nao-sei');
  assert.equal(await ctx.atributo('#btn-nao-sei', 'aria-expanded'), 'false');
  assert.equal(await ctx.visivel('#dica-modelo'), false);

  await ctx.clicar('#btn-nao-sei');
  await ctx.clicar('#btn-pular-modelo');
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1500, 'tela de problemas');
  assert.equal(await ctx.lerTexto('#sub-problema'), 'Escolha o que mais se parece com o que você está vendo.');
  assert.equal(await ctx.visivel('#maquina-escolhida'), false);
  const modelo = await eventosDo(ctx, 'modelo');
  assert.equal(modelo.length, 1);
  assert.equal(modelo[0].modelo, 'nao-informado');
  ctx.semErros();
});

// ---------------------------------------------------------------------------
// #/problemas
// ---------------------------------------------------------------------------

cenario('#/problemas: escolher modelo grava o evento, mostra a máquina, os grupos, os filtros e a etapa 2', async (ctx) => {
  await ctx.abrir('#/');
  await escolherModelo(ctx, 'LOV');

  assert.deepEqual(await viewsVisiveis(ctx), ['view-problema']);
  assert.equal(await ctx.lerTexto('#titulo-problema'), 'O que está acontecendo?');
  assert.equal(await ctx.lerTexto('#sub-problema'), 'Máquina: LOV. Escolha o que mais se parece com o que você está vendo.');
  assert.ok(await ctx.visivel('#maquina-escolhida'));
  assert.ok((await ctx.lerTexto('#maquina-escolhida')).includes('LOV'));
  assert.equal(await ctx.lerTexto('.voltar[data-voltar="#/"]'), '← Trocar de máquina');
  assert.equal(await ctx.lerTexto('label.busca__rotulo'), 'Buscar pelo que você está vendo');
  assert.equal(await ctx.atributo('#campo-busca', 'placeholder'), 'Ex.: café não sai, luz vermelha, vazando');
  assert.equal(await ctx.lerTexto('#titulo-comuns'), 'Mais comuns');
  assert.equal(await ctx.lerTexto('#titulo-outros'), 'Outros problemas');

  const chips = await ctx.avaliar(() => Array.from(document.querySelectorAll('#filtros .chip')).map((b) => [b.dataset.cat, b.textContent.trim(), b.getAttribute('aria-pressed')]));
  assert.deepEqual(chips, D.CATEGORIAS.map((c) => [c.id, c.nome, String(c.id === 'todos')]));

  const topo = D.PROBLEMAS.filter((p) => p.topo).length;
  assert.equal(await ctx.contar('#lista-comuns > li'), topo);
  assert.equal(await ctx.contar('#lista-outros > li'), D.PROBLEMAS.length - topo);
  assert.equal(await ctx.contar('#lista-comuns .problema__selo'), topo);

  assert.deepEqual(await eventosDo(ctx, 'modelo').then((l) => l.map((e) => e.modelo)), ['lov']);
  await conferirEtapas(ctx, 2);

  // "← Trocar de máquina" volta à tela inicial.
  await ctx.clicar('.voltar[data-voltar="#/"]');
  await ctx.esperar('location.hash === "#/" && !document.querySelector("#view-modelo").hidden', 1500, 'voltar à tela inicial');
  await conferirEtapas(ctx, 1);
  ctx.semErros();
});

cenario('#/problemas: filtro por categoria, busca e "Limpar busca" continuam funcionando', async (ctx) => {
  await ctx.abrir('#/problemas');
  assert.deepEqual(await viewsVisiveis(ctx), ['view-problema']);
  // Aberta direto, sem modelo: sem faixa de máquina.
  assert.equal(await ctx.lerTexto('#sub-problema'), 'Escolha o que mais se parece com o que você está vendo.');

  const energia = D.PROBLEMAS.filter((p) => p.categoria === 'energia').length;
  await ctx.clicar('#filtros .chip[data-cat="energia"]');
  assert.equal(await ctx.atributo('#filtros .chip[data-cat="energia"]', 'aria-pressed'), 'true');
  assert.equal(await ctx.atributo('#filtros .chip[data-cat="todos"]', 'aria-pressed'), 'false');
  assert.equal(await ctx.lerTexto('#status-busca'), energia + (energia === 1 ? ' problema encontrado' : ' problemas encontrados'));
  assert.equal(await ctx.contar('#lista-comuns > li') + await ctx.contar('#lista-outros > li'), energia);

  // Busca sem resultado: mensagem de vazio e botão "Limpar busca".
  await ctx.digitar('#campo-busca', 'zzzzzz');
  await ctx.esperar('!document.querySelector("#vazio").hidden', 800, 'mensagem de busca vazia');
  assert.ok((await ctx.lerTexto('#vazio')).startsWith('Não encontramos esse problema.'));
  assert.equal(await ctx.lerTexto('#btn-limpar-busca'), 'Limpar busca');
  assert.equal(await ctx.contar('.problema'), 0);

  await ctx.clicar('#btn-limpar-busca');
  assert.equal(await ctx.valor('#campo-busca'), '');
  assert.equal(await ctx.visivel('#vazio'), false);
  assert.equal(await ctx.atributo('#filtros .chip[data-cat="todos"]', 'aria-pressed'), 'true');
  assert.equal(await ctx.contar('.problema'), D.PROBLEMAS.length);
  assert.equal((await ctx.foco()).id, 'campo-busca');
  ctx.semErros();
});

// ---------------------------------------------------------------------------
// #/solucao/ID
// ---------------------------------------------------------------------------

cenario('#/solucao/ID: passo a passo (contagem, barra, Anterior/Próximo) e "Escolher outro problema"', async (ctx) => {
  await ctx.abrir('#/');
  await escolherModelo(ctx, 'LOV');
  await escolherProblema(ctx, PROBLEMA.titulo);

  assert.deepEqual(await viewsVisiveis(ctx), ['view-solucao']);
  assert.deepEqual((await eventosDo(ctx, 'problema')).map((e) => [e.problema, e.modelo]), [[ID, 'lov']]);
  assert.equal(await ctx.lerTexto('#solucao-modelo'), 'Máquina: LOV');
  assert.equal(await ctx.lerTexto('#titulo-solucao'), PROBLEMA.titulo);
  assert.equal(await ctx.lerTexto('.voltar[data-voltar="#/problemas"]'), '← Escolher outro problema');
  assert.equal(await ctx.visivel('#visual3d'), false, 'a ilustração 3D é só da Touch');
  await conferirEtapas(ctx, 3);

  for (let i = 0; i < TOTAL; i++) {
    const passo = PROBLEMA.passos[i];
    assert.equal(await ctx.lerTexto('#contagem-passo'), 'Passo ' + (i + 1) + ' de ' + TOTAL);
    assert.equal(await ctx.lerTexto('#passo .passo__tipo'), passo.tipo === 'checar' ? 'Confira' : 'Faça');
    assert.equal(await ctx.lerTexto('#passo .passo__texto'), passo.texto);
    assert.equal(await ctx.avaliar('document.querySelector("#btn-anterior").disabled'), i === 0);
    assert.equal(await ctx.lerTexto('#btn-proximo'), i === TOTAL - 1 ? 'Terminei os passos' : 'Próximo passo');
    const largura = await ctx.avaliar('parseFloat(document.querySelector("#barra-passo").style.width)');
    assert.ok(Math.abs(largura - ((i + 1) / TOTAL) * 100) < 0.01, 'barra de progresso do passo ' + (i + 1));
    if (i < TOTAL - 1) await ctx.clicar('#btn-proximo');
  }

  // Anterior volta um passo.
  await ctx.clicar('#btn-anterior');
  assert.equal(await ctx.lerTexto('#contagem-passo'), 'Passo ' + (TOTAL - 1) + ' de ' + TOTAL);
  await ctx.clicar('#btn-proximo');

  // Observação do problema, quando existe.
  assert.equal(await ctx.visivel('#obs-solucao'), Boolean(PROBLEMA.obs));
  if (PROBLEMA.obs) assert.equal(await ctx.lerTexto('#obs-solucao'), 'Bom saber: ' + PROBLEMA.obs);

  // "Terminei os passos" leva a #/confirma/ID.
  await ctx.clicar('#btn-proximo');
  await ctx.esperar('location.hash === "#/confirma/' + ID + '" && !document.querySelector("#view-confirma").hidden', 1500, 'tela de confirmação do problema');

  // Volta pelo navegador e usa "← Escolher outro problema".
  await ir(ctx, '#/solucao/' + ID, 'solucao');
  await ctx.clicar('.voltar[data-voltar="#/problemas"]');
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1500, 'tela de problemas');
  ctx.semErros();
});

cenario('#/solucao/ID aberta direto, sem modelo: "qualquer modelo" e primeiro passo', async (ctx) => {
  await ctx.abrir('#/solucao/' + ID);
  assert.deepEqual(await viewsVisiveis(ctx), ['view-solucao']);
  assert.equal(await ctx.lerTexto('#solucao-modelo'), 'Máquina: qualquer modelo');
  assert.equal(await ctx.lerTexto('#titulo-solucao'), PROBLEMA.titulo);
  assert.equal(await ctx.lerTexto('#contagem-passo'), 'Passo 1 de ' + TOTAL);
  assert.equal(await ctx.lerTexto('#passo .passo__texto'), PROBLEMA.passos[0].texto);
  await conferirEtapas(ctx, 3);
  // A Tela_de_Chamado não aparece nem monta nada por aqui.
  assert.equal(await ctx.visivel('#view-suporte'), false);
  assert.deepEqual(await eventosDo(ctx, 'suporte'), []);
  ctx.semErros();
});

// ---------------------------------------------------------------------------
// #/confirma/ID
// ---------------------------------------------------------------------------

cenario('#/confirma/ID: pergunta, botões, "Rever os passos" e etapa 3 atual', async (ctx) => {
  await ctx.abrir('#/confirma/' + ID);
  assert.deepEqual(await viewsVisiveis(ctx), ['view-confirma']);
  assert.equal(await ctx.lerTexto('#view-confirma .etiqueta'), 'Última etapa');
  assert.equal(await ctx.lerTexto('#titulo-confirma'), 'O problema foi solucionado?');
  assert.equal(await ctx.lerTexto('#confirma-problema'), PROBLEMA.titulo);
  assert.equal(await ctx.lerTexto('#btn-sim'), 'Sim, resolvi');
  assert.equal(await ctx.lerTexto('#btn-nao'), 'Não, ainda não');
  assert.equal(await ctx.lerTexto('#btn-rever'), 'Rever os passos');
  await conferirEtapas(ctx, 3);

  await ctx.clicar('#btn-rever');
  await ctx.esperar('location.hash === "#/solucao/' + ID + '" && !document.querySelector("#view-solucao").hidden', 1500, 'rever os passos');
  assert.equal(await ctx.lerTexto('#contagem-passo'), 'Passo 1 de ' + TOTAL);
  assert.deepEqual(await eventosDo(ctx, 'resolvido'), []);
  assert.deepEqual(await eventosDo(ctx, 'suporte'), []);
  ctx.semErros();
});

cenario('#/confirma/ID: "Não, ainda não" grava o evento suporte de sempre e abre #/suporte/ID', async (ctx) => {
  await ctx.abrir('#/');
  await escolherModelo(ctx, 'LOV');
  await ir(ctx, '#/confirma/' + ID, 'confirma');
  await ctx.clicar('#btn-nao');
  await ctx.esperar('location.hash === "#/suporte/' + ID + '" && !document.querySelector("#view-suporte").hidden', 1500, 'Tela_de_Chamado');

  const eventos = await eventosDo(ctx, 'suporte');
  assert.equal(eventos.length, 1);
  assert.deepEqual(Object.keys(eventos[0]).sort(), ['em', 'modelo', 'problema', 'tipo']);
  assert.equal(eventos[0].problema, ID);
  assert.equal(eventos[0].modelo, 'lov');
  assert.deepEqual(await eventosDo(ctx, 'chamado'), [], 'nenhum chamado é registrado só por abrir a tela');
  await conferirEtapas(ctx, 3);
  const resumo = await ctx.avaliar('window.TRESMetricas.resumo()');
  assert.equal(resumo.encaminhadosAoSuporte, 1);
  assert.equal(resumo.resolvidos, 0);
  assert.equal(resumo.chamadosAbertos, 0);
  assert.equal(resumo.comentarios, 0);
  ctx.semErros();
});

// ---------------------------------------------------------------------------
// #/resolvido/ID
// ---------------------------------------------------------------------------

cenario('#/resolvido/ID: "Sim, resolvi" grava resolvido e mostra a tela de sempre, com links e etapa 3', async (ctx) => {
  await ctx.abrir('#/');
  await escolherModelo(ctx, 'LOV');
  await ir(ctx, '#/confirma/' + ID, 'confirma');
  await ctx.clicar('#btn-sim');
  await ctx.esperar('location.hash === "#/resolvido/' + ID + '" && !document.querySelector("#view-resolvido").hidden', 1500, 'tela de resolvido');

  assert.deepEqual(await viewsVisiveis(ctx), ['view-resolvido']);
  assert.equal(await ctx.lerTexto('#titulo-resolvido'), 'Que bom! Seu café está de volta.');
  assert.equal(await ctx.lerTexto('#view-resolvido .desfecho p:not(.desfecho__icone):not(:empty)'), 'Você resolveu sem precisar ligar. Obrigado por usar o autoatendimento TRES.');
  assert.equal(await ctx.lerTexto('#titulo-aval'), 'Como foi a ajuda?');
  assert.equal(await ctx.contar('#estrelas button'), 5);
  assert.equal(await ctx.lerTexto('#view-resolvido .passo-acoes a[href="#/problemas"]'), 'Tenho outro problema');
  assert.equal(await ctx.lerTexto('#view-resolvido .passo-acoes a[href="#/"]'), 'Voltar ao início');
  await conferirEtapas(ctx, 3);

  // Foco no título (h1) ao chegar pela resposta "Sim", nunca no campo de comentário.
  await ctx.esperar('document.activeElement && document.activeElement.id === "titulo-resolvido"', 1000, 'foco no h1 da tela de resolvido');

  const eventos = await eventosDo(ctx, 'resolvido');
  assert.equal(eventos.length, 1);
  assert.deepEqual(Object.keys(eventos[0]).sort(), ['em', 'modelo', 'problema', 'tipo']);
  assert.equal(eventos[0].problema, ID);
  assert.equal(eventos[0].modelo, 'lov');
  const resumo = await ctx.avaliar('window.TRESMetricas.resumo()');
  assert.equal(resumo.resolvidos, 1);
  assert.equal(resumo.encaminhadosAoSuporte, 0);
  assert.equal(resumo.chamadosAbertos, 0);
  assert.equal(resumo.comentarios, 0);

  // Só mostrar a tela não grava avaliação, comentário nem feedback.
  assert.deepEqual(await eventosDo(ctx, 'avaliacao'), []);
  assert.deepEqual(await eventosDo(ctx, 'comentario'), []);
  assert.deepEqual(await ctx.feedbacksLocais(), []);

  // Nada da nova tela por aqui.
  assert.equal(await ctx.visivel('#view-suporte'), false);
  assert.equal(await ctx.visivel('#view-chamado'), false);

  await ctx.clicar('#view-resolvido .passo-acoes a[href="#/problemas"]');
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1500, '"Tenho outro problema"');
  ctx.semErros();
});

cenario('#/resolvido/ID: bloco de comentário na ordem estrelas, formulário, cuidados e links, sem nenhum campo de identificação', async (ctx) => {
  await ctx.abrir('#/');
  await escolherModelo(ctx, 'LOV');
  await ir(ctx, '#/resolvido/' + ID, 'resolvido');

  assert.ok(await ctx.visivel('#form-feedback'), 'o formulário de comentário deve aparecer na tela de resolvido');

  // Ordem visual e de leitura: estrelas, formulário, cuidados, links finais.
  const ordem = await ctx.avaliar(() => {
    const ordemDe = (...sels) => {
      const els = sels.map((s) => document.querySelector(s));
      return els.every((e, i) => i === 0 || Boolean(els[i - 1].compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING));
    };
    const topo = (s) => document.querySelector(s).getBoundingClientRect().top;
    return {
      ordemDom: ordemDe('#estrelas', '#status-aval', '#form-feedback', '#cuidados-resolvido', '#view-resolvido .passo-acoes'),
      ordemVisual: topo('#estrelas') < topo('#form-feedback') && topo('#form-feedback') < topo('#view-resolvido .passo-acoes'),
      formDentroDaAvaliacao: Boolean(document.querySelector('.avaliacao #form-feedback')),
      cuidadosForaDoFormulario: !document.querySelector('#form-feedback').contains(document.querySelector('#cuidados-resolvido'))
    };
  });
  assert.equal(ordem.ordemDom, true, 'ordem no DOM: estrelas, status, formulário, cuidados, links');
  assert.equal(ordem.ordemVisual, true, 'ordem visual: estrelas acima do formulário, formulário acima dos links');
  assert.equal(ordem.formDentroDaAvaliacao, true);
  assert.equal(ordem.cuidadosForaDoFormulario, true);

  // Textos de sempre continuam: h1, título da avaliação, 5 estrelas e links finais.
  assert.equal(await ctx.lerTexto('#titulo-resolvido'), 'Que bom! Seu café está de volta.');
  assert.equal(await ctx.lerTexto('#titulo-aval'), 'Como foi a ajuda?');
  assert.equal(await ctx.contar('#estrelas button'), 5);
  assert.equal(await ctx.avaliar('Array.from(document.querySelectorAll("#view-resolvido .passo-acoes a")).map((a) => a.getAttribute("href")).join(",")'), '#/problemas,#/');

  // O formulário: um único campo editável, textos vindos de data.js e nada de identificação.
  const T = D.FEEDBACK.textos;
  const form = await ctx.avaliar(() => {
    const f = document.querySelector('#form-feedback');
    const norm = (t) => t.replace(/\s+/g, ' ').trim();
    return {
      campos: Array.from(f.querySelectorAll('input, textarea, select')).map((c) => c.tagName.toLowerCase() + '#' + c.id),
      botoes: Array.from(f.querySelectorAll('button')).map((b) => b.id + ':' + b.type + ':' + b.textContent.trim()),
      links: f.querySelectorAll('a').length,
      rotulo: norm(f.querySelector('label[for="f-comentario"]').textContent),
      aviso: norm(document.querySelector('#f-comentario-aviso').textContent),
      contador: norm(document.querySelector('#f-comentario-contador').textContent),
      describedby: document.querySelector('#f-comentario').getAttribute('aria-describedby'),
      valor: document.querySelector('#f-comentario').value,
      maxlength: document.querySelector('#f-comentario').getAttribute('maxlength'),
      identificacao: document.querySelectorAll('#view-resolvido input, #view-resolvido [type="email"], #view-resolvido [type="tel"], #view-resolvido [type="checkbox"], #view-resolvido #c-nome, #view-resolvido #c-email, #view-resolvido #c-telefone, #view-resolvido #c-aceite').length,
      termos: Array.from(document.querySelectorAll('#view-resolvido button, #view-resolvido a')).filter((n) => /termos/i.test(n.textContent)).length
    };
  });
  assert.deepEqual(form.campos, ['textarea#f-comentario'], 'um único campo editável');
  assert.deepEqual(form.botoes, ['btn-enviar-comentario:submit:' + T.botaoEnviar]);
  assert.equal(form.links, 0);
  assert.equal(form.rotulo, T.rotulo + ' ' + T.opcional);
  assert.equal(form.aviso, T.avisoNaoIdentificacao);
  assert.equal(form.contador, '0 de 500 caracteres');
  assert.equal(form.describedby, 'f-comentario-aviso f-comentario-contador');
  assert.equal(form.valor, '');
  assert.equal(form.maxlength, '500');
  assert.equal(form.identificacao, 0, 'nenhum campo de nome, e-mail, telefone nem aceite na tela de resolvido');
  assert.equal(form.termos, 0, 'sem botão nem link de termos na tela de resolvido');
  assert.equal(await ctx.avaliar('document.querySelector("#feedback-agradecimento").textContent.trim()'), '', 'agradecimento só depois do envio');
  assert.equal(await ctx.contar('#feedback-falha-area > *'), 0);

  // Abrir a tela não envia nada.
  assert.deepEqual(await ctx.feedbacksLocais(), []);
  assert.deepEqual(await eventosDo(ctx, 'comentario'), []);
  assert.equal((await ctx.avaliar('window.TRESMetricas.resumo()')).comentarios, 0);
  await conferirEtapas(ctx, 3);
  ctx.semErros();
});

cenario('#/resolvido/ID aberta direto: mostra o bloco de comentário e o foco vai ao h1, não ao campo', async (ctx) => {
  await ctx.abrir('#/resolvido/' + ID);
  assert.deepEqual(await viewsVisiveis(ctx), ['view-resolvido']);
  await ctx.esperar('document.activeElement && document.activeElement.id === "titulo-resolvido"', 1000, 'foco no h1 ao abrir a URL direto');
  assert.equal((await ctx.foco()).id, 'titulo-resolvido');
  assert.ok(await ctx.visivel('#form-feedback'));
  assert.equal(await ctx.contar('#view-resolvido textarea'), 1);
  assert.equal(await ctx.valor('#f-comentario'), '');
  assert.equal(await ctx.contar('#estrelas button'), 5);
  await conferirEtapas(ctx, 3);
  ctx.semErros();
});

// ---------------------------------------------------------------------------
// O formulário de feedback é só da Tela_de_Resolvido
// ---------------------------------------------------------------------------

cenario('#/suporte/ID e #/chamado/ID não têm o formulário de feedback e não gravam feedback nem comentário', async (ctx) => {
  const semFeedback = (viewId) => ctx.avaliar((id) => {
    const v = document.getElementById(id);
    const f = document.getElementById('form-feedback');
    return {
      formDentro: Boolean(v.querySelector('#form-feedback, #f-comentario, #btn-enviar-comentario, #feedback-agradecimento, #feedback-falha-area')),
      textosDentro: v.querySelectorAll('[data-texto-feedback]').length,
      textareas: v.querySelectorAll('textarea').length,
      formVisivel: Boolean(f && !f.hidden && f.getClientRects().length > 0),
      formNaView: f ? f.closest('.view').id : null
    };
  }, viewId);

  await ctx.abrir('#/suporte/' + ID);
  await ctx.esperar('!document.querySelector("#view-suporte").hidden', 1500, 'Tela_de_Chamado');
  assert.deepEqual(await viewsVisiveis(ctx), ['view-suporte']);
  assert.deepEqual(await semFeedback('view-suporte'), { formDentro: false, textosDentro: 0, textareas: 1, formVisivel: false, formNaView: 'view-resolvido' });
  assert.equal(await ctx.visivel('#form-feedback'), false);
  assert.equal(await ctx.existe('#view-suporte #c-descricao'), true, 'a única caixa de texto do chamado é a Descricao');

  await ctx.preencherFormulario(DADOS);
  await ctx.enviar();
  await ctx.esperar('location.hash === "#/chamado/' + ID + '" && !document.querySelector("#view-chamado").hidden', 1500, 'Tela_de_Confirmacao');
  assert.deepEqual(await viewsVisiveis(ctx), ['view-chamado']);
  assert.deepEqual(await semFeedback('view-chamado'), { formDentro: false, textosDentro: 0, textareas: 0, formVisivel: false, formNaView: 'view-resolvido' });
  assert.equal(await ctx.visivel('#form-feedback'), false);

  // O chamado não grava feedback nem comentário, e o resumo conta zero comentários.
  assert.deepEqual(await ctx.feedbacksLocais(), []);
  assert.deepEqual(await eventosDo(ctx, 'comentario'), []);
  const resumo = await ctx.avaliar('window.TRESMetricas.resumo()');
  assert.equal(resumo.chamadosAbertos, 1);
  assert.equal(resumo.comentarios, 0);
  ctx.semErros();
});

// ---------------------------------------------------------------------------
// #/contato
// ---------------------------------------------------------------------------

cenario('#/contato: canais de atendimento iguais, voltar e "Tentar resolver sozinho"; barra de etapas oculta', async (ctx) => {
  await ctx.abrir('#/contato');
  assert.deepEqual(await viewsVisiveis(ctx), ['view-contato']);
  assert.equal(await ctx.lerTexto('#titulo-contato'), 'Falar com a gente');
  assert.equal(await ctx.lerTexto('#view-contato .sub'), 'Antes de ligar, vale tentar o passo a passo: a maioria dos casos se resolve em poucos minutos.');
  assert.equal(await ctx.lerTexto('#view-contato a.btn--grande[href="#/problemas"]'), 'Tentar resolver sozinho');

  const cartao = await ctx.avaliar(() => {
    const c = document.querySelector('#cartao-contato-geral');
    const a = (n) => ({ texto: n.textContent.trim(), href: n.getAttribute('href'), alvo: n.getAttribute('target'), rel: n.getAttribute('rel') });
    return {
      titulo: c.querySelector('h2').textContent.trim(),
      tel: a(c.querySelector('a.tel')),
      horarios: Array.from(c.querySelectorAll('ul li')).map((li) => li.textContent.trim()),
      email: a(c.querySelector('a[href^="mailto:"]')),
      central: a(c.querySelector('a[target="_blank"]')),
      textoEmail: c.querySelector('p').textContent.trim()
    };
  });
  assert.equal(cartao.titulo, 'Canais de atendimento');
  assert.deepEqual(cartao.tel, { texto: C.telefone, href: C.telefoneLink, alvo: null, rel: null });
  assert.deepEqual(cartao.tel.texto, '0800 979 2021');
  assert.equal(cartao.tel.href, 'tel:08009792021');
  assert.deepEqual(cartao.horarios, ['Segunda à sexta, das 08h às 18h', 'Sábado, das 08h às 12h']);
  assert.deepEqual(cartao.email, { texto: 'atendimento@3coracoes.com.br', href: 'mailto:atendimento@3coracoes.com.br', alvo: null, rel: null });
  assert.deepEqual(cartao.central, {
    texto: 'Ver vídeos e perguntas frequentes (abre em nova aba)',
    href: 'https://www.escolhatres.com.br/central-de-ajuda/', alvo: '_blank', rel: 'noopener noreferrer'
  });
  assert.ok(cartao.textoEmail.startsWith('Se preferir, envie um e-mail:'));

  // Nesta tela a barra de etapas some, como antes.
  const e = await etapas(ctx);
  assert.equal(e.oculta, true);
  assert.equal(e.itens.length, 3);
  assert.deepEqual(e.itens.map((i) => i.atual), [null, null, null]);

  // "← Voltar" vai à tela inicial.
  assert.equal(await ctx.lerTexto('#view-contato .voltar'), '← Voltar');
  await ctx.clicar('#view-contato .voltar');
  await ctx.esperar('location.hash === "#/" && !document.querySelector("#view-modelo").hidden', 1500, 'voltar à tela inicial');
  ctx.semErros();
});

// ---------------------------------------------------------------------------
// Cabeçalho e rodapé
// ---------------------------------------------------------------------------

cenario('cabeçalho "Falar com a gente" e rodapé iguais em todas as rotas, inclusive nas novas', async (ctx) => {
  await ctx.abrir('#/');
  const instantaneo = () => ctx.avaliar(() => {
    const norm = (t) => t.replace(/\s+/g, ' ').trim();
    const a = (n) => ({ texto: norm(n.textContent), href: n.getAttribute('href'), alvo: n.getAttribute('target'), rel: n.getAttribute('rel') });
    const rodape = document.querySelector('.rodape');
    return {
      skip: a(document.querySelector('.skip-link')),
      marca: Object.assign(a(document.querySelector('.topo .marca')), { rotulo: document.querySelector('.topo .marca').getAttribute('aria-label') }),
      contato: a(document.querySelector('.topo__contato')),
      rodape: norm(rodape.textContent),
      rodapeLinks: Array.from(rodape.querySelectorAll('a')).map(a),
      visiveis: ['.topo__contato', '.rodape'].map((s) => {
        const r = document.querySelector(s).getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      })
    };
  });
  const esperado = {
    skip: { texto: 'Pular para o conteúdo', href: '#conteudo', alvo: null, rel: null },
    marca: { texto: 'TRES Central de Ajuda', href: '#/', alvo: null, rel: null, rotulo: 'TRES Central de Ajuda, voltar ao início' },
    contato: { texto: 'Falar com a gente', href: '#/contato', alvo: null, rel: null },
    rodape: 'Ainda precisa falar com alguém? Veja os canais de atendimento. Mais vídeos e perguntas frequentes na Central de Ajuda (abre em nova aba).',
    rodapeLinks: [
      { texto: 'Veja os canais de atendimento', href: '#/contato', alvo: null, rel: null },
      { texto: 'Central de Ajuda (abre em nova aba)', href: 'https://www.escolhatres.com.br/central-de-ajuda/', alvo: '_blank', rel: 'noopener noreferrer' }
    ],
    visiveis: [true, true]
  };

  const rotas = [
    ['#/', 'modelo'], ['#/problemas', 'problema'], ['#/solucao/' + ID, 'solucao'], ['#/confirma/' + ID, 'confirma'],
    ['#/resolvido/' + ID, 'resolvido'], ['#/contato', 'contato'], ['#/suporte/' + ID, 'suporte']
  ];
  for (const [hash, view] of rotas) {
    if (hash !== '#/') await ir(ctx, hash, view);
    assert.deepEqual(await instantaneo(), esperado, 'cabeçalho/rodapé em ' + hash);
  }
  ctx.semErros();
});

cenario('"Falar com a gente" (cabeçalho) e "Veja os canais de atendimento" (rodapé) abrem #/contato', async (ctx) => {
  await ctx.abrir('#/problemas');
  await ctx.clicar('.topo__contato');
  await ctx.esperar('location.hash === "#/contato" && !document.querySelector("#view-contato").hidden', 1500, 'contato pelo cabeçalho');
  assert.deepEqual(await viewsVisiveis(ctx), ['view-contato']);

  await ctx.clicar('.topo .marca');
  await ctx.esperar('(location.hash === "#/" || location.hash === "") && !document.querySelector("#view-modelo").hidden', 1500, 'logo volta ao início');

  await ctx.clicar('.rodape a[href="#/contato"]');
  await ctx.esperar('location.hash === "#/contato" && !document.querySelector("#view-contato").hidden', 1500, 'contato pelo rodapé');
  ctx.semErros();
});

// ---------------------------------------------------------------------------
// Barra de etapas
// ---------------------------------------------------------------------------

cenario('barra de etapas: 3 itens, etapa atual certa em cada rota e etapa 3 em #/suporte/ID', async (ctx) => {
  await ctx.abrir('#/');
  await conferirEtapas(ctx, 1);
  const casos = [
    ['#/problemas', 'problema', 2], ['#/solucao/' + ID, 'solucao', 3], ['#/confirma/' + ID, 'confirma', 3],
    ['#/resolvido/' + ID, 'resolvido', 3], ['#/suporte/' + ID, 'suporte', 3]
  ];
  for (const [hash, view, etapa] of casos) {
    await ir(ctx, hash, view);
    await conferirEtapas(ctx, etapa);
  }
  // Contato esconde a barra; ao sair dela, a barra volta.
  await ir(ctx, '#/contato', 'contato');
  assert.equal((await etapas(ctx)).oculta, true);
  await ir(ctx, '#/', 'modelo');
  await conferirEtapas(ctx, 1);
  assert.equal(await ctx.contar('#etapas li'), 3);
  ctx.semErros();
});

cenario('barra de etapas na Tela_de_Confirmacao (#/chamado/ID): etapa 3 atual por texto e forma, em 360 px', { viewport: { largura: 360, altura: 640 } }, async (ctx) => {
  await ctx.abrir('#/suporte/' + ID);
  await ctx.esperar('!document.querySelector("#view-suporte").hidden', 1500, 'Tela_de_Chamado');
  await ctx.preencherFormulario(DADOS);
  await ctx.enviar();
  await ctx.esperar('location.hash === "#/chamado/' + ID + '" && !document.querySelector("#view-chamado").hidden', 1500, 'Tela_de_Confirmacao');

  assert.deepEqual(await viewsVisiveis(ctx), ['view-chamado']);
  await conferirEtapas(ctx, 3);

  // Indicação perceptível sem depender de cor: aria-current, número e nome visíveis na etapa atual.
  const atual = await ctx.avaliar(() => {
    const li = document.querySelector('#etapas li[aria-current="step"]');
    const nome = li.querySelector('.etapas__nome');
    const n = nome.getBoundingClientRect();
    const num = li.querySelector('.etapas__num');
    return {
      etapa: li.dataset.etapa,
      nomeVisivel: getComputedStyle(nome).display !== 'none' && n.width > 0,
      nome: nome.textContent.trim(),
      numero: num.textContent.trim(),
      pesoNome: getComputedStyle(li).fontWeight,
      pesoOutra: getComputedStyle(document.querySelector('#etapas li[data-etapa="1"]')).fontWeight
    };
  });
  assert.equal(atual.etapa, '3');
  assert.equal(atual.nome, 'A solução');
  assert.equal(atual.numero, '3');
  assert.ok(atual.nomeVisivel, 'o nome da etapa atual deve aparecer também em tela estreita');
  assert.ok(Number(atual.pesoNome) > Number(atual.pesoOutra), 'a etapa atual deve ter peso de fonte maior (não só cor)');

  // Rota existente continua igual depois de abrir o chamado: o resolvido não é afetado.
  await ir(ctx, '#/resolvido/' + ID, 'resolvido');
  assert.equal(await ctx.visivel('#view-chamado'), false);
  await conferirEtapas(ctx, 3);
  ctx.semErros();
});

// ---------------------------------------------------------------------------
// Rotas inválidas e botão voltar
// ---------------------------------------------------------------------------

cenario('rotas inválidas continuam redirecionando: desconhecida a #/, ID inexistente a #/problemas', async (ctx) => {
  await ctx.abrir('#/rota-que-nao-existe');
  await ctx.esperar('(location.hash === "#/") && !document.querySelector("#view-modelo").hidden', 1500, 'rota desconhecida vai a #/');
  assert.deepEqual(await viewsVisiveis(ctx), ['view-modelo']);

  for (const rota of ['solucao', 'confirma', 'resolvido']) {
    await ctx.avaliar('location.hash = "#/' + rota + '/999"');
    await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1500, '#/' + rota + '/999 vai a #/problemas');
    assert.deepEqual(await viewsVisiveis(ctx), ['view-problema']);
    await ir(ctx, '#/', 'modelo');
  }
  // Sem ID também.
  await ctx.avaliar('location.hash = "#/solucao"');
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1500, '#/solucao sem ID');
  ctx.semErros();
});

cenario('botão voltar do navegador percorre as telas na ordem inversa da jornada', async (ctx) => {
  await ctx.abrir('#/');
  await escolherModelo(ctx, 'LOV');
  await escolherProblema(ctx, PROBLEMA.titulo);
  await ctx.clicar('#btn-proximo');
  assert.equal(await ctx.lerTexto('#contagem-passo'), 'Passo 2 de ' + TOTAL);

  await ctx.avaliar('history.back()');
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1500, 'voltar a #/problemas');
  await conferirEtapas(ctx, 2);
  await ctx.avaliar('history.back()');
  await ctx.esperar('location.hash === "#/" && !document.querySelector("#view-modelo").hidden', 1500, 'voltar a #/');
  await conferirEtapas(ctx, 1);
  // Avançar de novo retoma a tela de problemas.
  await ctx.avaliar('history.forward()');
  await ctx.esperar('location.hash === "#/problemas" && !document.querySelector("#view-problema").hidden', 1500, 'avançar a #/problemas');
  ctx.semErros();
});

// ---------------------------------------------------------------------------
// DOM das telas existentes
// ---------------------------------------------------------------------------

cenario('DOM das telas existentes: mesma ordem de elementos, mesmos destinos e nenhum texto novo (data-texto)', async (ctx) => {
  await ctx.abrir('#/');
  const dom = await ctx.avaliar(() => {
    const desc = (c) => c.tagName.toLowerCase() + (c.id ? '#' + c.id : '') + (c.className ? '.' + String(c.className).trim().split(/\s+/).join('.') : '');
    const ids = ['view-modelo', 'view-problema', 'view-solucao', 'view-confirma', 'view-resolvido', 'view-contato'];
    const saida = {};
    ids.forEach((id) => {
      const v = document.getElementById(id);
      saida[id] = {
        filhos: Array.from(v.children).map(desc),
        classe: v.className,
        rotulo: v.getAttribute('aria-labelledby'),
        textoNovo: v.querySelectorAll('[data-texto]').length,
        textoFeedback: v.querySelectorAll('[data-texto-feedback]').length,
        formsFeedback: v.querySelectorAll('#form-feedback').length,
        voltar: Array.from(v.querySelectorAll('[data-voltar]')).map((b) => b.dataset.voltar),
        links: Array.from(v.querySelectorAll('a')).map((a) => a.getAttribute('href'))
      };
    });
    // Bloco de avaliação da Tela_de_Resolvido: o formulário de comentário entra depois do status das estrelas.
    saida.avaliacaoResolvido = Array.from(document.querySelector('#view-resolvido .avaliacao').children).map(desc);
    saida.ordemViews = Array.from(document.querySelectorAll('main > .view')).map((v) => v.id);
    return saida;
  });

  assert.deepEqual(dom['view-modelo'].filhos, ['div.hero', 'h2.secao-titulo', 'ul#lista-modelos.modelos', 'div.ajuda-modelo']);
  assert.deepEqual(dom['view-problema'].filhos, [
    'button.voltar', 'h1#titulo-problema', 'p#sub-problema.sub', 'div#maquina-escolhida.maquina-escolhida', 'div.busca',
    'div#filtros.filtros', 'p#status-busca.status', 'section#bloco-comuns', 'section#bloco-outros', 'p#vazio.vazio', 'div#cuidados-problema'
  ]);
  assert.deepEqual(dom['view-solucao'].filhos, [
    'button.voltar', 'p#solucao-modelo.etiqueta', 'h1#titulo-solucao', 'div.passo-progresso', 'p#contagem-passo.passo-contagem',
    'div#passo.passo', 'figure#visual3d.visual3d', 'div.passo-acoes', 'p#obs-solucao.obs'
  ]);
  assert.deepEqual(dom['view-confirma'].filhos, ['p.etiqueta', 'h1#titulo-confirma', 'p#confirma-problema.sub', 'div.confirma', 'button#btn-rever.link-btn']);
  assert.deepEqual(dom['view-resolvido'].filhos, ['div.desfecho.desfecho--ok', 'div.avaliacao', 'div#cuidados-resolvido', 'div.passo-acoes']);
  assert.deepEqual(dom.avaliacaoResolvido, ['h2#titulo-aval.secao-titulo', 'div#estrelas.estrelas', 'p#status-aval.status', 'form#form-feedback.feedback']);
  assert.deepEqual(dom['view-contato'].filhos, ['button.voltar', 'h1#titulo-contato', 'p.sub', 'a.btn.btn--grande', 'div#cartao-contato-geral.cartao-contato']);

  // Destinos de botões e links.
  assert.deepEqual(dom['view-problema'].voltar, ['#/']);
  assert.deepEqual(dom['view-solucao'].voltar, ['#/problemas']);
  assert.deepEqual(dom['view-contato'].voltar, ['#/']);
  assert.deepEqual(dom['view-resolvido'].links, ['#/problemas', '#/']);
  assert.deepEqual(dom['view-contato'].links, ['#/problemas']);

  // Nenhum texto das telas antigas virou [data-texto]: só as duas telas novas usam o mecanismo.
  for (const id of ['view-modelo', 'view-problema', 'view-solucao', 'view-confirma', 'view-resolvido', 'view-contato']) {
    assert.equal(dom[id].textoNovo, 0, id + ' não deve usar [data-texto]');
  }
  for (const id of Object.keys(dom).filter((k) => k.startsWith('view-'))) assert.equal(dom[id].classe, 'view');

  // O mecanismo de textos do feedback e o formulário existem só na Tela_de_Resolvido; as demais telas não mudaram.
  for (const id of ['view-modelo', 'view-problema', 'view-solucao', 'view-confirma', 'view-contato']) {
    assert.equal(dom[id].textoFeedback, 0, id + ' não deve usar [data-texto-feedback]');
    assert.equal(dom[id].formsFeedback, 0, id + ' não deve ter #form-feedback');
  }
  assert.equal(dom['view-resolvido'].formsFeedback, 1);
  assert.ok(dom['view-resolvido'].textoFeedback > 0);

  // Ordem das telas dentro de <main>: as antigas na ordem de sempre, as novas depois de "resolvido".
  assert.deepEqual(dom.ordemViews, ['view-modelo', 'view-problema', 'view-solucao', 'view-confirma', 'view-resolvido', 'view-suporte', 'view-chamado', 'view-contato']);
  ctx.semErros();
});
