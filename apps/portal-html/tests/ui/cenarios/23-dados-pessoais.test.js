'use strict';
// Tarefa 12.13 - dados pessoais fora de lugar indevido.
// Depois do fluxo (e também ao sair sem enviar), nome, e-mail, telefone e descrição NÃO podem
// aparecer em: métricas (tres-autoatendimento-eventos), URL/hash/histórico, console, sessionStorage,
// cookies, título, window.name, history.state, IndexedDB, CacheStorage nem em outras chaves do
// localStorage. Só podem existir (a) no Repositorio_de_Chamados em Modo_Prototipo e (b) no corpo do POST
// ao Back_end em Modo_API. Em Modo_Prototipo não pode haver requisição de rede para chamados.
// Tarefa 10.12 (resolved-feedback-comment): o mesmo vale para o texto do comentário da Tela_de_Resolvido.
// Ele só pode existir em tres-autoatendimento-feedbacks (Modo_Prototipo) ou no corpo do POST a api/feedbacks
// (Modo_API) e nunca junto de dados do chamado.
// Requisitos: 6.13, 6.14, 9.3, 12.7, 12.8, 2.4, 11.2, 11.3
const assert = require('node:assert/strict');
const { cenario } = require('../cenarios');

const DADOS = {
  nome: 'Zelinda Quaresmeira',
  email: 'Zelinda.Quaresmeira@Exemplo-Teste.com.br',
  telefone: '(11) 98765-4321',
  descricao: 'A cafeteira xyzzy-quokka derrama agua pela lateral',
  aceite: true
};
const CHAVE_EVENTOS = 'tres-autoatendimento-eventos';
const CHAVE_CHAMADOS = 'tres-autoatendimento-chamados';
const CHAVE_FEEDBACKS = 'tres-autoatendimento-feedbacks';
// Chaves do localStorage que o produto conhece; qualquer outra aparecendo é falha.
const CHAVES_CONHECIDAS = [CHAVE_EVENTOS, CHAVE_CHAMADOS, CHAVE_FEEDBACKS];
const ROTA = '#/suporte/1';
const ROTA_RESOLVIDO = '#/resolvido/1';

// Texto do comentário da Tela_de_Resolvido e os trechos que o identificam.
const COMENTARIO = 'Atendimento excelente: o guia flamingo-quokka-7391 resolveu tudo & rapido';
const AGULHAS_COMENTARIO = Array.from(new Set(
  [COMENTARIO, 'flamingo-quokka-7391', 'atendimento excelente'].flatMap((b) => [b, encodeURIComponent(b)]).map((s) => s.toLowerCase())
));

// Trechos que identificam cada dado pessoal (comparação sem diferenciar maiúsculas de minúsculas).
const BASES = [
  DADOS.nome, 'zelinda', 'quaresmeira',
  DADOS.email, 'zelinda.quaresmeira', '@exemplo-teste',
  DADOS.telefone, '11987654321', '98765-4321', '987654321',
  DADOS.descricao, 'xyzzy-quokka'
];
const AGULHAS = Array.from(new Set(BASES.flatMap((b) => [b, encodeURIComponent(b)]).map((s) => s.toLowerCase())));

/** Quais dados pessoais aparecem no texto (também olhando a forma decodificada de URL). */
function achados(texto, agulhas = AGULHAS) {
  const t = String(texto == null ? '' : texto).toLowerCase();
  let dec = t;
  try { dec = decodeURIComponent(t.replace(/\+/g, ' ')); } catch (e) { /* mantém o texto cru */ }
  return agulhas.filter((a) => t.includes(a) || dec.includes(a));
}

/** Espião instalado antes de qualquer script da página: rede, janelas e URLs visitadas. */
const ESPIAO = '(' + function () {
  var e = window.__espiao = { rede: [], urls: [] };
  function reg(tipo, url, metodo, corpo) {
    e.rede.push({ tipo: tipo, url: String(url), metodo: String(metodo || 'GET').toUpperCase(), corpo: typeof corpo === 'string' ? corpo : (corpo == null ? null : '[nao-texto]') });
  }
  function url() { e.urls.push(location.href); }
  url();
  window.addEventListener('hashchange', url);
  window.addEventListener('popstate', url);
  ['pushState', 'replaceState'].forEach(function (nome) {
    var o = history[nome];
    history[nome] = function (s, t, u) { e.urls.push('[' + nome + '] ' + String(u)); return o.apply(this, arguments); };
  });
  var f = window.fetch;
  if (f) window.fetch = function (u, i) { reg('fetch', (u && u.url) || u, (i && i.method) || (u && u.method), i && i.body); return f.apply(this, arguments); };
  var ab = XMLHttpRequest.prototype.open, en = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__e = { m: m, u: u }; return ab.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function (b) { reg('xhr', this.__e && this.__e.u, this.__e && this.__e.m, b); return en.apply(this, arguments); };
  if (navigator.sendBeacon) { var sb = navigator.sendBeacon.bind(navigator); navigator.sendBeacon = function (u, d) { reg('beacon', u, 'POST', d); return sb(u, d); }; }
  if (window.WebSocket) { var WS = window.WebSocket; window.WebSocket = function (u) { reg('websocket', u, 'GET'); return new (Function.prototype.bind.apply(WS, [null].concat([].slice.call(arguments))))(); }; }
  var wo = window.open; window.open = function (u) { reg('window.open', u, 'GET'); return wo.apply(this, arguments); };
} + ')()';

/** Lê todos os lugares onde um dado pessoal poderia vazar. */
async function instantaneo(ctx) {
  const pag = await ctx.avaliar(async () => {
    const r = { local: [], sessao: [], cookies: document.cookie, url: location.href, titulo: document.title, nomeJanela: window.name, estado: null, urls: [], rede: [], recursos: [], idb: [], caches: [] };
    try { for (let i = 0; i < localStorage.length; i++) { const k = localStorage.key(i); r.local.push({ k, v: localStorage.getItem(k) }); } } catch (e) { /* ignora */ }
    try { for (let i = 0; i < sessionStorage.length; i++) { const k = sessionStorage.key(i); r.sessao.push({ k, v: sessionStorage.getItem(k) }); } } catch (e) { /* ignora */ }
    try { r.estado = JSON.stringify(history.state); } catch (e) { r.estado = String(history.state); }
    if (window.__espiao) { r.urls = window.__espiao.urls.slice(); r.rede = window.__espiao.rede.slice(); }
    r.recursos = performance.getEntriesByType('resource').map((x) => ({ nome: x.name, tipo: x.initiatorType }));
    try { if (indexedDB.databases) r.idb = (await indexedDB.databases()).map((d) => d.name); } catch (e) { /* ignora */ }
    try { if (window.caches) r.caches = await caches.keys(); } catch (e) { /* ignora */ }
    return r;
  });
  return { ...pag, console: ctx.consoleCompleto().map((c) => c.tipo + ': ' + c.texto) };
}

/**
 * Nenhum dado pessoal fora dos lugares permitidos.
 * `permitirChamados`: o Repositorio_de_Chamados (só Modo_Prototipo) pode conter os dados.
 */
function exigirSemVazamento(s, onde, { permitirChamados = false, permitirFeedbacks = false, agulhas = AGULHAS } = {}) {
  const falhas = [];
  const olhar = (lugar, texto) => { const a = achados(texto, agulhas); if (a.length) falhas.push(lugar + ' contém ' + JSON.stringify(a)); };

  for (const { k, v } of s.local) {
    olhar('localStorage (nome da chave) "' + k + '"', k);
    if (!CHAVES_CONHECIDAS.includes(k)) falhas.push('localStorage tem a chave desconhecida "' + k + '"');
    if (k === CHAVE_CHAMADOS && permitirChamados) continue;
    if (k === CHAVE_FEEDBACKS && permitirFeedbacks) continue;
    olhar('localStorage["' + k + '"]', v);
  }
  for (const { k, v } of s.sessao) { olhar('sessionStorage (nome da chave)', k); olhar('sessionStorage["' + k + '"]', v); }
  olhar('document.cookie', s.cookies);
  olhar('URL', s.url);
  s.urls.forEach((u) => olhar('URL visitada ' + u, u));
  olhar('document.title', s.titulo);
  olhar('window.name', s.nomeJanela);
  olhar('history.state', s.estado);
  s.recursos.forEach((x) => olhar('URL de recurso carregado ' + x.nome, x.nome));
  s.idb.forEach((n) => olhar('IndexedDB (nome)', n));
  s.caches.forEach((n) => olhar('CacheStorage (nome)', n));
  s.console.forEach((c) => olhar('console', c));
  s.rede.forEach((r) => { olhar('URL de requisição ' + r.url, r.url); });
  assert.deepEqual(falhas, [], onde + ': dados pessoais em lugar indevido:\n  ' + falhas.join('\n  '));
}

/** Os eventos de métricas não têm campos nem valores pessoais (9.3, 6.13). */
async function exigirMetricasLimpas(ctx, onde) {
  const bruto = await ctx.avaliar('localStorage.getItem(' + JSON.stringify(CHAVE_EVENTOS) + ')');
  assert.deepEqual(achados(bruto), [], onde + ': a chave ' + CHAVE_EVENTOS + ' não pode conter dado pessoal');
  assert.deepEqual(achados(bruto, AGULHAS_COMENTARIO), [], onde + ': a chave ' + CHAVE_EVENTOS + ' não pode conter o texto do comentário');
  const proibidos = ['nome', 'email', 'telefone', 'descricao', 'aceite', 'chaveIdempotencia', 'comentario', 'texto', 'feedback'];
  for (const ev of await ctx.eventos()) {
    for (const campo of proibidos) {
      assert.ok(!(campo in ev), onde + ': evento "' + ev.tipo + '" não pode ter o campo "' + campo + '"');
    }
  }
}

/** Nenhuma requisição de chamado: nem pelo espião da página, nem pelo desempenho, nem no servidor (12.8). */
async function exigirSemRedeDeChamados(ctx, onde) {
  const s = await instantaneo(ctx);
  const suspeitas = s.rede.filter((r) => r.metodo !== 'GET' || /chamado|\/api\//i.test(r.url));
  assert.deepEqual(suspeitas, [], onde + ': nenhuma requisição de chamado em Modo_Prototipo (fetch/XHR/beacon/WebSocket)');
  const dados = s.recursos.filter((x) => /^(fetch|xmlhttprequest|beacon)$/.test(x.tipo) && /chamado|\/api\//i.test(x.nome));
  assert.deepEqual(dados, [], onde + ': nenhum recurso de rede de chamados na linha do tempo de desempenho');
  assert.deepEqual(ctx.api.requisicoes(), [], onde + ': o servidor não recebeu POST de chamado');
  assert.deepEqual(ctx.api.outras(), [], onde + ': o servidor não recebeu outra requisição à API');
}

/** Vai a "O problema foi solucionado?" e responde "Não, ainda não" (gera o evento suporte). */
async function irParaOFormulario(ctx) {
  await ctx.abrir('#/confirma/1');
  await ctx.esperar('!document.querySelector("#view-confirma").hidden', 1000, 'tela "O problema foi solucionado?"');
  await ctx.clicar('#btn-nao');
  await ctx.esperar('location.hash === "' + ROTA + '" && !!document.querySelector("#view-suporte:not([hidden]) #c-nome")', 1000, 'Tela_de_Chamado');
}

const OPCOES = { antes: ESPIAO };
const OPCOES_API = { antes: ESPIAO, modoApi: true, api: { modo: 'sucesso' } };

cenario('Modo_Prototipo: depois do fluxo e da avaliação, só o Repositorio_de_Chamados guarda os dados pessoais', OPCOES, async (ctx) => {
  await irParaOFormulario(ctx);
  await ctx.preencherFormulario(DADOS);

  // Enquanto digita (sem enviar) nada vaza: o rascunho não é guardado em lugar nenhum.
  exigirSemVazamento(await instantaneo(ctx), 'durante o preenchimento');

  await ctx.enviar();
  await ctx.esperar('location.hash === "#/chamado/1" && !document.querySelector("#view-chamado").hidden', 1000, 'Tela_de_Confirmacao');
  await ctx.esperar('document.querySelectorAll("#estrelas-chamado button").length === 5', 500, 'estrelas da confirmação');
  await ctx.avaliar('document.querySelectorAll("#estrelas-chamado button")[3].click()');
  await ctx.esperar('document.querySelector("#status-aval-chamado").textContent.trim() !== ""', 500, 'agradecimento da avaliação');

  // Sanidade: o chamado foi mesmo gravado, com os dados, no repositório permitido.
  const chamados = await ctx.chamadosLocais();
  assert.equal(chamados.length, 1);
  assert.equal(chamados[0].nome, DADOS.nome);
  assert.equal(chamados[0].descricao, DADOS.descricao);

  exigirSemVazamento(await instantaneo(ctx), 'na confirmação', { permitirChamados: true });
  await exigirMetricasLimpas(ctx, 'na confirmação');

  // As métricas têm os eventos esperados, mas sem dados pessoais.
  const tipos = (await ctx.eventos()).map((e) => e.tipo);
  assert.ok(tipos.includes('suporte') && tipos.includes('chamado') && tipos.includes('avaliacao'), 'eventos suporte, chamado e avaliacao: ' + tipos.join(','));

  // Navegando depois do envio (outro problema, início) a URL continua limpa.
  await ctx.clicar('#view-chamado a[href="#/problemas"]');
  await ctx.esperar('location.hash === "#/problemas"', 1000, '"Tenho outro problema"');
  exigirSemVazamento(await instantaneo(ctx), 'depois de "Tenho outro problema"', { permitirChamados: true });
  await exigirMetricasLimpas(ctx, 'depois de "Tenho outro problema"');

  await exigirSemRedeDeChamados(ctx, 'fluxo completo');
  ctx.semErros();
});

cenario('Modo_Prototipo: sair da Tela_de_Chamado sem enviar não deixa dados pessoais em lugar nenhum', OPCOES, async (ctx) => {
  await irParaOFormulario(ctx);
  await ctx.preencherFormulario(DADOS);

  await ctx.abrir('#/problemas');
  await ctx.esperar('!document.querySelector("#view-problema").hidden', 1000, 'tela de problemas');
  exigirSemVazamento(await instantaneo(ctx), 'depois de sair para #/problemas');

  await ctx.abrir('#/');
  await ctx.avaliar('history.back()');
  await ctx.esperar('location.hash === "#/problemas"', 1000, 'voltar do navegador');
  exigirSemVazamento(await instantaneo(ctx), 'depois de voltar pelo navegador');

  // Carga nova (sem enviar): nada foi persistido, nem mesmo como rascunho.
  await ctx.recarregar();
  const s = await instantaneo(ctx);
  exigirSemVazamento(s, 'depois de recarregar');
  assert.equal(s.local.some((x) => x.k === CHAVE_CHAMADOS && achados(x.v).length), false, 'sem chamado gravado');
  await exigirMetricasLimpas(ctx, 'depois de recarregar');
  assert.equal((await ctx.eventos()).filter((e) => e.tipo === 'chamado').length, 0, 'sem evento chamado quando não se envia');

  await exigirSemRedeDeChamados(ctx, 'saída sem enviar');
  ctx.semErros();
});

cenario('Modo_Prototipo: envio recusado pela validação não vaza os valores digitados', OPCOES, async (ctx) => {
  await irParaOFormulario(ctx);
  // E-mail inválido e sem aceite: o envio é recusado e as mensagens de erro aparecem.
  await ctx.preencherFormulario({ nome: DADOS.nome, email: 'sem-arroba-zelinda', telefone: DADOS.telefone, descricao: DADOS.descricao, aceite: false });
  await ctx.enviar();
  await ctx.esperar('!document.querySelector("#c-email-erro").hidden', 1000, 'erro do e-mail');

  assert.notEqual(await ctx.hash(), '#/chamado/1');
  exigirSemVazamento(await instantaneo(ctx), 'depois da validação recusada');
  assert.deepEqual(await ctx.chamadosLocais(), [], 'nada é gravado com dados inválidos');
  await exigirMetricasLimpas(ctx, 'depois da validação recusada');
  await exigirSemRedeDeChamados(ctx, 'validação recusada');
  ctx.semErros();
});

cenario('Modo_API: os dados pessoais só existem no corpo do POST; armazenamento, URL, métricas e console ficam limpos', OPCOES_API, async (ctx) => {
  await irParaOFormulario(ctx);
  await ctx.preencherFormulario(DADOS);
  exigirSemVazamento(await instantaneo(ctx), 'durante o preenchimento (Modo_API)');

  await ctx.enviar();
  await ctx.esperar('location.hash === "#/chamado/1" && !document.querySelector("#view-chamado").hidden', 2000, 'Tela_de_Confirmacao');
  await ctx.esperar('document.querySelectorAll("#estrelas-chamado button").length === 5', 500, 'estrelas da confirmação');
  await ctx.avaliar('document.querySelectorAll("#estrelas-chamado button")[1].click()');
  await ctx.esperar('document.querySelector("#status-aval-chamado").textContent.trim() !== ""', 500, 'agradecimento da avaliação');

  // Único lugar permitido: o corpo do POST.
  const reqs = ctx.api.requisicoes();
  assert.equal(reqs.length, 1, 'um único POST');
  assert.equal(reqs[0].json.nome, DADOS.nome.trim(), 'o corpo do POST traz o nome');
  assert.equal(reqs[0].json.descricao, DADOS.descricao, 'o corpo do POST traz a descrição');
  assert.equal(reqs[0].json.email, DADOS.email.toLowerCase(), 'o corpo do POST traz o e-mail');
  assert.equal(reqs[0].json.telefone, '11987654321', 'o corpo do POST traz o telefone');
  // ...e não a URL nem os cabeçalhos da requisição.
  assert.deepEqual(achados(reqs[0].caminho), [], 'o caminho/consulta do POST não leva dados pessoais');
  assert.deepEqual(achados(JSON.stringify(reqs[0].cabecalhos)), [], 'os cabeçalhos do POST não levam dados pessoais');

  // Em Modo_API não há Repositorio_de_Chamados: nenhuma chave do localStorage pode ter os dados.
  assert.deepEqual(await ctx.chamadosLocais(), [], 'Modo_API não grava chamado local');
  const s = await instantaneo(ctx);
  exigirSemVazamento(s, 'na confirmação (Modo_API)');
  // A URL de requisição vista pelo espião também é limpa; o corpo é o único lugar permitido.
  const posts = s.rede.filter((r) => r.metodo === 'POST');
  assert.equal(posts.length, 1, 'o espião viu um único POST');
  assert.ok(achados(posts[0].corpo).length > 0, 'sanidade: o espião enxerga os dados no corpo do POST');
  await exigirMetricasLimpas(ctx, 'na confirmação (Modo_API)');
  assert.equal((await ctx.eventos()).filter((e) => e.tipo === 'chamado').length, 1);

  assert.deepEqual(ctx.api.outras(), [], 'sem outras requisições à API');
  ctx.semErros();
});

cenario('Modo_API: falha do envio e retentativa não vazam dados pessoais para console, URL nem armazenamento',
  { antes: ESPIAO, modoApi: true, api: { sequencia: ['erro500', 'sucesso'] } },
  async (ctx) => {
    await irParaOFormulario(ctx);
    await ctx.preencherFormulario(DADOS);
    await ctx.enviar();
    await ctx.esperar('!!document.querySelector("#chamado-falha-area .msg-falha") && !document.querySelector("#btn-abrir-chamado").disabled', 2500, 'bloco de falha');

    // Depois da falha: os valores seguem só nos campos; nada foi guardado.
    assert.equal(await ctx.valor('#c-nome'), DADOS.nome);
    const apos = await instantaneo(ctx);
    exigirSemVazamento(apos, 'depois da falha 500');
    await exigirMetricasLimpas(ctx, 'depois da falha 500');
    assert.deepEqual(await ctx.chamadosLocais(), [], 'sem chamado parcial');
    assert.equal((await ctx.eventos()).filter((e) => e.tipo === 'chamado').length, 0, 'sem evento chamado na falha');

    // Retentativa manual com sucesso.
    await ctx.enviar();
    await ctx.esperar('location.hash === "#/chamado/1"', 2500, 'confirmação após retentativa');
    exigirSemVazamento(await instantaneo(ctx), 'depois da retentativa');
    await exigirMetricasLimpas(ctx, 'depois da retentativa');
    assert.deepEqual(await ctx.chamadosLocais(), []);
    for (const r of ctx.api.requisicoes()) {
      assert.deepEqual(achados(r.caminho), [], 'o caminho do POST não leva dados pessoais');
    }

    // O log de rede do 500 simulado é do navegador e não traz dado pessoal (conferido acima);
    // qualquer outro erro de script é falha.
    const inesperados = ctx.erros().filter((e) => !/Failed to load resource.*status of 500/.test(e));
    assert.deepEqual(inesperados, [], 'sem erros de script além do log de rede do 500 simulado');
  });

// ---------------------------------------------------------------------------
// Tarefa 10.12: comentário da Tela_de_Resolvido x dados do chamado
// ---------------------------------------------------------------------------

/** Preenche o formulário do chamado (sem enviar) e vai a #/resolvido/1 na mesma carga. */
async function preencherChamadoEIrParaResolvido(ctx) {
  await irParaOFormulario(ctx);
  await ctx.preencherFormulario(DADOS);
  await ctx.abrir(ROTA_RESOLVIDO);
  await ctx.esperar('location.hash === "' + ROTA_RESOLVIDO + '" && !!document.querySelector("#form-feedback:not([hidden]) #f-comentario")', 1500, 'formulário do comentário');
}

async function enviarComentario(ctx) {
  await ctx.digitar('#f-comentario', COMENTARIO);
  await ctx.clicar('#btn-enviar-comentario');
  await ctx.esperar('document.querySelector("#feedback-agradecimento").textContent.trim().length > 0', 2000, 'agradecimento do comentário');
}

/** Opções de leitura: o comentário pode estar só no Repositorio_de_Feedbacks; os dados pessoais, em nenhum. */
const SO_COMENTARIO_EM_FEEDBACKS = { agulhas: AGULHAS_COMENTARIO, permitirFeedbacks: true };

cenario('Modo_Prototipo: dados do chamado (sem enviar) não vão ao feedback; o comentário só existe em tres-autoatendimento-feedbacks', OPCOES, async (ctx) => {
  await preencherChamadoEIrParaResolvido(ctx);
  await enviarComentario(ctx);

  // Sanidade: o comentário foi gravado no repositório de feedbacks, e nenhum chamado foi aberto.
  const feedbacks = await ctx.feedbacksLocais();
  assert.equal(feedbacks.length, 1, 'um registro em ' + CHAVE_FEEDBACKS);
  assert.equal(feedbacks[0].comentario, COMENTARIO);
  assert.deepEqual(await ctx.chamadosLocais(), [], 'nenhum chamado foi aberto');

  // Dados pessoais do chamado: nem no feedback gravado (nem no que seria o payload), nem no evento comentario.
  assert.deepEqual(achados(JSON.stringify(feedbacks)), [], 'o feedback gravado não pode conter dados do chamado');
  const comentarios = (await ctx.eventos()).filter((e) => e.tipo === 'comentario');
  assert.equal(comentarios.length, 1, 'um evento comentario');
  assert.deepEqual(achados(JSON.stringify(comentarios)), [], 'o evento comentario não pode conter dados do chamado');
  assert.deepEqual(achados(JSON.stringify(comentarios), AGULHAS_COMENTARIO), [], 'o evento comentario não pode conter o texto do comentário');
  assert.deepEqual(Object.keys(comentarios[0]).sort(), ['em', 'modelo', 'problema', 'tipo'], 'o evento comentario só tem tipo, instante, problema e modelo');

  // Texto do comentário: só em tres-autoatendimento-feedbacks (não em sessionStorage, cookies, URL, console,
  // eventos nem chamados). Dados do chamado: em lugar nenhum.
  const s = await instantaneo(ctx);
  exigirSemVazamento(s, 'comentário enviado (texto do comentário)', SO_COMENTARIO_EM_FEEDBACKS);
  exigirSemVazamento(s, 'comentário enviado (dados do chamado)');
  assert.ok(achados(s.local.find((x) => x.k === CHAVE_FEEDBACKS).v, AGULHAS_COMENTARIO).length > 0, 'sanidade: o texto está em ' + CHAVE_FEEDBACKS);
  await exigirMetricasLimpas(ctx, 'comentário enviado');

  // Sem rede: nem de chamados, nem de feedback.
  await exigirSemRedeDeChamados(ctx, 'comentário em Modo_Prototipo');
  assert.deepEqual(ctx.apiFeedback.requisicoes(), [], 'sem requisição de feedback em Modo_Prototipo');
  assert.deepEqual(ctx.apiFeedback.outras(), []);
  ctx.semErros();
});

cenario('Modo_API (feedback): o texto do comentário só existe no corpo do POST; dados do chamado não vão junto',
  { antes: ESPIAO, modoApiFeedback: true, apiFeedback: { modo: 'sucesso' } },
  async (ctx) => {
    await preencherChamadoEIrParaResolvido(ctx);
    await enviarComentario(ctx);

    // Único lugar permitido para o texto: o corpo do POST a api/feedbacks, sem dados do chamado.
    const reqs = ctx.apiFeedback.requisicoes();
    assert.equal(reqs.length, 1, 'uma requisição a api/feedbacks');
    assert.equal(reqs[0].json.comentario, COMENTARIO, 'o corpo do POST traz o comentário');
    assert.deepEqual(achados(reqs[0].corpoTexto), [], 'o corpo do POST não traz dados do chamado');
    assert.deepEqual(achados(reqs[0].caminho, AGULHAS_COMENTARIO), [], 'o caminho/consulta do POST não leva o comentário');
    assert.deepEqual(achados(reqs[0].caminho), [], 'o caminho/consulta do POST não leva dados do chamado');
    assert.deepEqual(achados(JSON.stringify(reqs[0].cabecalhos), AGULHAS_COMENTARIO), [], 'os cabeçalhos do POST não levam o comentário');
    assert.deepEqual(achados(JSON.stringify(reqs[0].cabecalhos)), [], 'os cabeçalhos do POST não levam dados do chamado');
    assert.equal(ctx.api.requisicoes().length, 0, 'nada vai a api/chamados');

    // Em Modo_API o comentário não fica em armazenamento nenhum.
    assert.deepEqual(await ctx.feedbacksLocais(), [], 'Modo_API não grava feedback local');
    assert.deepEqual(await ctx.chamadosLocais(), [], 'nenhum chamado foi aberto');
    const s = await instantaneo(ctx);
    exigirSemVazamento(s, 'comentário enviado (texto do comentário, Modo_API)', { agulhas: AGULHAS_COMENTARIO });
    exigirSemVazamento(s, 'comentário enviado (dados do chamado, Modo_API)');
    const posts = s.rede.filter((r) => r.metodo === 'POST');
    assert.equal(posts.length, 1, 'o espião viu um único POST');
    assert.ok(achados(posts[0].corpo, AGULHAS_COMENTARIO).length > 0, 'sanidade: o espião enxerga o comentário no corpo do POST');
    await exigirMetricasLimpas(ctx, 'comentário enviado (Modo_API)');
    assert.equal((await ctx.eventos()).filter((e) => e.tipo === 'comentario').length, 1, 'um evento comentario');
    ctx.semErros();
  });
