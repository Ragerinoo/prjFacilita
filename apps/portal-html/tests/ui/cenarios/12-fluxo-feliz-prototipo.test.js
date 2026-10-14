'use strict';
// Tarefa 12.2: fluxo feliz em Modo_Prototipo (sem API_CHAMADOS_URL).
// Percorre a jornada real clicando nos botões do site, abre o chamado e confere a confirmação.
const assert = require('node:assert/strict');
const { cenario } = require('../cenarios');

const DADOS = {
  nome: '  Maria   da Silva ',
  email: 'Maria.Silva@Exemplo.com.br',
  telefone: '(11) 91234-5678',
  descricao: 'A máquina não extrai o café mesmo com água no reservatório.',
  aceite: true
};

/** Escolhe o modelo LOV (botão da lista) e o problema "não extrai bebida", como o consumidor faria. */
async function escolherModeloEProblema(ctx, tituloProblema) {
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
  }, tituloProblema);
  await ctx.esperar('/^#\\/solucao\\/\\d+$/.test(location.hash)', 1500, 'tela de solução');
}

/** Dados do problema em js/data.js (só leitura). */
function dadosProblema(ctx, titulo) {
  return ctx.avaliar((t) => {
    const p = window.TRES_DATA.PROBLEMAS.find((x) => x.titulo === t);
    return { id: p.id, total: p.passos.length, passos: p.passos.map((s) => s.texto) };
  }, titulo);
}

const PROBLEMA = 'A máquina não extrai bebida';

cenario('Modo_Prototipo: jornada "Não, ainda não" mostra o resumo (modelo, problema, X de Y passos)', async (ctx) => {
  await ctx.abrir('#/');
  const p = await dadosProblema(ctx, PROBLEMA);
  assert.ok(p.total >= 2, 'o problema escolhido precisa ter ao menos 2 passos para o teste');

  await escolherModeloEProblema(ctx, PROBLEMA);
  assert.equal(await ctx.hash(), '#/solucao/' + p.id);

  // Percorre apenas o primeiro e o segundo passo (X < Y), depois pula para a confirmação.
  await ctx.clicar('#btn-proximo');
  await ctx.esperar('document.querySelector("#contagem-passo").textContent.trim() === "Passo 2 de ' + p.total + '"', 1000, 'passo 2');
  await ctx.avaliar('location.hash = "#/confirma/' + p.id + '"');
  await ctx.esperar('!document.querySelector("#view-confirma").hidden', 1000, 'tela "O problema foi solucionado?"');

  await ctx.clicar('#btn-nao');
  await ctx.esperar('location.hash === "#/suporte/' + p.id + '"', 1000, 'rota #/suporte/ID');

  // 1.1: tela de chamado visível e confirmação oculta.
  assert.ok(await ctx.visivel('#view-suporte'), 'a Tela_de_Chamado deve estar visível');
  assert.equal(await ctx.visivel('#view-confirma'), false, 'a tela "O problema foi solucionado?" deve ficar oculta');

  // 1.6: foco no h1 em até 300 ms.
  await ctx.esperar('document.activeElement && document.activeElement.id === "titulo-suporte"', 300, 'foco no h1 da Tela_de_Chamado em até 300 ms');

  // 2.2, 2.4, 2.7: resumo.
  assert.equal(await ctx.lerTexto('#resumo-modelo'), 'LOV');
  assert.equal(await ctx.lerTexto('#resumo-problema'), PROBLEMA);
  assert.equal(await ctx.lerTexto('#resumo-contagem'), '2 de ' + p.total + ' passos');
  const itens = await ctx.avaliar(() => Array.from(document.querySelectorAll('#resumo-lista li')).map((li) => li.textContent));
  assert.deepEqual(itens, p.passos.slice(0, 2), 'os passos exibidos devem ser os dois primeiros, na ordem, sem alteração');

  // 9.1: exatamente um evento "suporte" com problema e modelo.
  const eventos = await ctx.eventos();
  const suporte = eventos.filter((e) => e.tipo === 'suporte');
  assert.equal(suporte.length, 1, 'deve haver exatamente um evento suporte');
  assert.equal(suporte[0].problema, p.id);
  assert.equal(suporte[0].modelo, 'lov');
  assert.ok(!Number.isNaN(Date.parse(suporte[0].em)), 'o evento deve ter o instante do registro');

  ctx.semErros();
});

cenario('Modo_Prototipo: envia o chamado e a confirmação mostra protocolo, aviso, prazo, canais, foco, #anuncio e métricas', async (ctx) => {
  await ctx.abrir('#/');
  const p = await dadosProblema(ctx, PROBLEMA);

  await escolherModeloEProblema(ctx, PROBLEMA);
  // Percorre todos os passos até "Terminei os passos" e responde "Não, ainda não".
  for (let i = 1; i < p.total; i++) await ctx.clicar('#btn-proximo');
  await ctx.esperar('document.querySelector("#btn-proximo").textContent.trim() === "Terminei os passos"', 1000, 'último passo');
  await ctx.clicar('#btn-proximo');
  await ctx.esperar('location.hash === "#/confirma/' + p.id + '"', 1000, 'tela de confirmação da solução');
  await ctx.clicar('#btn-nao');
  await ctx.esperar('location.hash === "#/suporte/' + p.id + '"', 1000, 'rota #/suporte/ID');

  // Resumo com todos os passos (Y de Y).
  assert.equal(await ctx.lerTexto('#resumo-contagem'), p.total + ' de ' + p.total + ' passos');

  await ctx.preencherFormulario(DADOS);
  const aceite = await ctx.avaliar('document.querySelector("#c-aceite").checked');
  assert.equal(aceite, true, 'o aceite deve estar marcado antes do envio');
  await ctx.enviar();

  // 8.1: confirmação em até 1 s; rota #/chamado/ID.
  await ctx.esperar('location.hash === "#/chamado/' + p.id + '" && !document.querySelector("#view-chamado").hidden', 1000, 'Tela_de_Confirmacao em até 1 s');
  assert.equal(await ctx.visivel('#view-suporte'), false, 'a Tela_de_Chamado deve ficar oculta');

  // 8.12: foco no h1 da confirmação em até 500 ms.
  await ctx.esperar('document.activeElement && document.activeElement.id === "titulo-chamado"', 500, 'foco no h1 da confirmação');

  // 8.2: protocolo TRES-AAAAMMDD-XXXXXX com a data local do dispositivo.
  const protocolo = await ctx.lerTexto('#chamado-protocolo');
  assert.match(protocolo, /^TRES-\d{8}-[A-Z0-9]{6}$/);
  const hoje = await ctx.avaliar(() => {
    const d = new Date();
    return d.getFullYear() + String(d.getMonth() + 1).padStart(2, '0') + String(d.getDate()).padStart(2, '0');
  });
  assert.equal(protocolo.slice(5, 13), hoje, 'a data do protocolo deve ser a data local');

  // 8.10: aviso de protótipo visível.
  assert.ok(await ctx.visivel('#chamado-aviso-prototipo'), 'o Aviso_de_Prototipo deve estar visível em Modo_Prototipo');
  assert.match(await ctx.lerTexto('#chamado-aviso-prototipo'), /protótipo/i);

  // 8.7: prazo "N dias úteis" (PRAZO_RETORNO_DIAS_UTEIS = 2).
  assert.match(await ctx.lerTexto('#chamado-prazo'), /2 dias úteis/);
  // 8.8: canais com o telefone e o e-mail do chamado.
  const canais = await ctx.lerTexto('#chamado-canais');
  assert.match(canais, /WhatsApp/);
  assert.ok(canais.includes('11912345678'), 'os canais devem citar o telefone do chamado: ' + canais);
  assert.ok(canais.includes('maria.silva@exemplo.com.br'), 'os canais devem citar o e-mail do chamado: ' + canais);
  assert.equal(await ctx.lerTexto('#chamado-telefone'), '11912345678');
  assert.equal(await ctx.lerTexto('#chamado-email'), 'maria.silva@exemplo.com.br');

  // 11.6: anúncio da conclusão em #anuncio em até 1 s, com o protocolo.
  await ctx.esperar('document.querySelector("#anuncio").textContent.indexOf(' + JSON.stringify(protocolo) + ') >= 0', 1000, '#anuncio com o protocolo');

  // 7.5: o chamado foi gravado no Repositorio_de_Chamados, com o mesmo protocolo.
  const chamados = await ctx.chamadosLocais();
  assert.equal(chamados.length, 1);
  assert.equal(chamados[0].protocolo, protocolo);

  // 9.1, 9.2, 9.6: eventos e chamadosAbertos.
  const eventos = await ctx.eventos();
  assert.equal(eventos.filter((e) => e.tipo === 'suporte').length, 1, 'um único evento suporte');
  const evChamado = eventos.filter((e) => e.tipo === 'chamado');
  assert.equal(evChamado.length, 1, 'um único evento chamado');
  assert.equal(evChamado[0].problema, p.id);
  assert.equal(evChamado[0].modelo, 'lov');
  assert.equal(evChamado[0].protocolo, protocolo);
  assert.equal(evChamado[0].modo, 'prototipo');
  assert.equal(evChamado[0].passos, p.total);
  assert.ok(!Number.isNaN(Date.parse(evChamado[0].em)));
  const resumo = await ctx.avaliar('window.TRESMetricas.resumo()');
  assert.equal(resumo.chamadosAbertos, 1);
  assert.equal(resumo.encaminhadosAoSuporte, 1);

  ctx.semErros();
});
