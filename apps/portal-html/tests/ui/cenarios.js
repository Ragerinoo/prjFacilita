'use strict';
/**
 * Infraestrutura de cenários de interface (somente desenvolvimento).
 *
 * Uso num arquivo tests/ui/cenarios/NN-nome.test.js:
 *
 *   const assert = require('node:assert/strict');
 *   const { cenario } = require('../cenarios');
 *
 *   cenario('abre a tela inicial', async (ctx) => {
 *     await ctx.abrir('#/');
 *     assert.ok(await ctx.existe('#view-modelo'));
 *   });
 *
 *   cenario('Modo_API com falha 500', { modoApi: true, api: { modo: 'erro500' } },
 *     async (ctx) => { ... ctx.api.requisicoes() ... });
 *
 * O que `cenario` garante:
 *  - Um servidor estático de teste e um Edge headless por ARQUIVO (hooks
 *    before/after do node:test, sempre encerrados, mesmo em falha).
 *  - Cada cenário roda em CARGA NOVA: contexto de navegador isolado (sem
 *    localStorage, sessionStorage nem cookies herdados) e aba nova, fechados ao final.
 *  - Limite de 4 s por cenário (`limiteMs`, só para baixo, por segurança): o Edge
 *    headless costuma recarregar a aba depois de ~5 s (ver CONTEXTO-PROJETO.md,
 *    seção 8). Se a aba navegar mais vezes do que o cenário pediu, o cenário
 *    falha com mensagem explicando isso.
 *
 * COMO API_CHAMADOS_URL É CONFIGURADA SEM ALTERAR js/data.js EM DISCO:
 *  - Sem `modoApi`, o site recebe o js/data.js real (URL vazia = Modo_Prototipo).
 *  - Com `{ modoApi: true }`, o servidor de teste entrega, em memória, o conteúdo
 *    de js/data.js com `API_CHAMADOS_URL: ''` trocado pela URL da API falsa da
 *    sessão (http://127.0.0.1:<porta>/__t/<id>/api/chamados). O arquivo no disco
 *    nunca é escrito. O comportamento da API falsa vem de `api` (ver
 *    servidor-teste.js) e pode mudar durante o cenário com ctx.api.definirApi().
 *
 *  - Opção `configNumerica` (com modoApi, modoApiFeedback ou semTextosFeedback): troca,
 *    em memória, valores numéricos de js/data.js, ex.: { configNumerica: { TIMEOUT_ENVIO_MS: 800 } }
 *    ou { TIMEOUT_FEEDBACK_MS: 800 } para cobrir o tempo limite do envio dentro dos 4 s do cenário.
 *
 *  - FEEDBACK (comentário na tela de problema resolvido), mesma técnica e independente do chamado:
 *      modoApiFeedback: true      troca API_FEEDBACK_URL por http://127.0.0.1:<porta>/__t/<id>/api/feedbacks
 *      apiFeedback: { modo }      comportamento da API falsa de feedback: 'sucesso' (201, corpo vazio),
 *                                 'erro500', 'lento' (atraso em ms, padrão 6000), 'sem-resposta';
 *                                 também `sequencia` (lista de modos), como em `api`
 *      semTextosFeedback: [...]   remove essas chaves de FEEDBACK.textos do data.js entregue
 *                                 (conteúdo indisponível); aceita também uma string
 *    Modo_API do chamado e do feedback são independentes: modoApi não liga o feedback e vice-versa.
 *
 * O `ctx` entregue ao cenário (todas as funções devolvem Promise, salvo indicação):
 *   abrir(destino='#/', { nova })   navega (carga nova na 1ª vez; depois, só o hash)
 *   recarregar()                    recarrega a página (nova carga, mesmo contexto)
 *   avaliar(js | fn, ...args)       executa JS na página (awaitPromise, valor por JSON)
 *   esperar(cond, ms=1500, texto)   espera condição (string JS ou função) com tempo limite
 *   preencherFormulario(valores)    { nome, email, telefone, descricao, aceite } digitando
 *   digitar(sel, texto)             foca, seleciona e insere o texto (vazio limpa o campo)
 *   marcar(sel, marcado=true)       liga/desliga checkbox por clique
 *   enviar()                        clica em #btn-abrir-chamado
 *   clicar(sel, vezes=1)            clique(s) rápido(s) via DOM
 *   teclar(tecla)                   'Tab' | 'Shift+Tab' | 'Enter' | 'Space' | 'Escape'
 *   lerTexto(sel)  existe(sel)  visivel(sel)  contar(sel)  valor(sel)  atributo(sel, nome)
 *   foco()                          { id, tag, tipo, texto } do elemento focado
 *   erros()                         erros de script/console/log capturados (strings)
 *   semErros()                      lança se houver algum erro de script/console
 *   consoleCompleto()               todo o console { tipo, texto }
 *   eventos()                       lista gravada em 'tres-autoatendimento-eventos'
 *   chamadosLocais()                lista de 'tres-autoatendimento-chamados' (Modo_Prototipo)
 *   feedbacksLocais()               lista de 'tres-autoatendimento-feedbacks' (Modo_Prototipo)
 *   armazenamento()                 { local, sessao, cookies } como texto
 *   hash()  url()                   hash e URL atuais
 *   viewport(l, a)  movimentoReduzido(bool)   emulação (valem para as próximas cargas também)
 *   janelas()                       abas abertas no contexto (detecta window.open)
 *   capturar(nome)                  PNG em pasta temporária; devolve o caminho
 *   api                             { requisicoes(), chaves(), outras(), definirApi(cfg), apiUrl }  (chamado)
 *   apiFeedback                     { requisicoes(), chaves(), outras(), definirApi(cfg), apiUrl }  (feedback)
 *   restante()                      ms restantes do orçamento do cenário
 */
const { test, before, after } = require('node:test');
const os = require('node:os');
const path = require('node:path');
const { criarServidor } = require('./servidor-teste');
const { iniciarEdge, criarAba } = require('./cdp');

const LIMITE_PADRAO_MS = 4000;
const PASTA_CAPTURAS = path.join(os.tmpdir(), 'tres-ui-capturas');

const SELETORES_FORM = {
  nome: '#c-nome',
  email: '#c-email',
  telefone: '#c-telefone',
  descricao: '#c-descricao'
};
const SELETOR_ACEITE = '#c-aceite';
const SELETOR_ENVIAR = '#btn-abrir-chamado';

const TECLAS = {
  Tab: { key: 'Tab', code: 'Tab', vk: 9 },
  Enter: { key: 'Enter', code: 'Enter', vk: 13, text: '\r' },
  Space: { key: ' ', code: 'Space', vk: 32, text: ' ' },
  Escape: { key: 'Escape', code: 'Escape', vk: 27 }
};

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
const js = (v) => JSON.stringify(v);

function montarContexto(aba, sessao, base, limiteMs) {
  const prazoFinal = Date.now() + limiteMs;
  let pedidas = 0; // navegações pedidas pelo cenário
  let pagina = false;

  const restante = () => Math.max(0, prazoFinal - Date.now());

  function expressao(fn, args) {
    if (typeof fn === 'function') return '(' + fn.toString() + ')(...' + js(args) + ')';
    return String(fn);
  }

  const ctx = {
    api: {
      apiUrl: sessao.apiUrl,
      requisicoes: sessao.requisicoes,
      chaves: sessao.chaves,
      outras: sessao.outras,
      definirApi: sessao.definirApi
    },
    apiFeedback: {
      apiUrl: sessao.apiFeedbackUrl,
      requisicoes: sessao.requisicoesFeedback,
      chaves: sessao.chavesFeedback,
      outras: sessao.outrasFeedback,
      definirApi: sessao.definirApiFeedback
    },
    restante,

    avaliar: (fn, ...args) => aba.avaliar(expressao(fn, args)),

    async esperar(cond, ms = 1500, descricao) {
      const limite = Math.min(ms, restante());
      const inicio = Date.now();
      let ultimoErro = null;
      const quando = typeof cond === 'function' ? '(' + cond.toString() + ')()' : '(' + cond + ')';
      while (true) {
        try {
          if (await aba.avaliar('Promise.resolve(' + quando + ').then(Boolean)')) return true;
          ultimoErro = null;
        } catch (e) { ultimoErro = e; }
        if (Date.now() - inicio >= limite) break;
        await dormir(25);
      }
      const orcamento = restante() === 0 ? ' (orçamento do cenário esgotado)' : '';
      throw new Error(
        'Tempo esgotado (' + limite + ' ms)' + orcamento + ' esperando: ' +
          (descricao || (typeof cond === 'function' ? cond.toString().replace(/\s+/g, ' ').slice(0, 120) : String(cond).slice(0, 120))) +
          (ultimoErro ? ' | último erro: ' + ultimoErro.message : '')
      );
    },

    async abrir(destino = '#/', opcoes = {}) {
      const absoluta = /^https?:/.test(destino);
      const hashApenas = destino.startsWith('#');
      if (hashApenas && pagina && !opcoes.nova) {
        await aba.avaliar('location.hash = ' + js(destino));
      } else {
        const alvo = absoluta ? destino : base + (hashApenas ? 'index.html' + destino : destino.replace(/^\//, ''));
        if (opcoes.nova && pagina) await aba.navegar('about:blank');
        pedidas += 1;
        await aba.navegar(alvo);
        pagina = true;
        await ctx.esperar('document.readyState === "complete" && location.href.indexOf(' + js(base) + ') === 0', 3000, 'carregar a página ' + alvo);
      }
      if (!absoluta && (hashApenas || destino.indexOf('index.html') >= 0 || destino === '' || destino === '/')) {
        await ctx.esperar('!!document.querySelector(".view:not([hidden])")', 2500, 'alguma tela (.view) visível depois de abrir ' + destino);
      }
    },

    async recarregar() {
      pedidas += 1;
      await aba.avaliar('location.reload()').catch(() => {});
      await ctx.esperar('document.readyState === "complete"', 3000, 'recarregar a página');
      await ctx.esperar('!!document.querySelector(".view:not([hidden])")', 2500, 'tela visível depois de recarregar');
    },

    async existe(sel) { return aba.avaliar('!!document.querySelector(' + js(sel) + ')'); },
    async contar(sel) { return aba.avaliar('document.querySelectorAll(' + js(sel) + ').length'); },
    async visivel(sel) {
      return aba.avaliar(
        '(function(){var e=document.querySelector(' + js(sel) + ');if(!e||e.hidden)return false;' +
          'var r=e.getBoundingClientRect(),s=getComputedStyle(e);' +
          'return r.width>0&&r.height>0&&s.visibility!=="hidden"&&s.display!=="none";})()'
      );
    },
    async lerTexto(sel) {
      return aba.avaliar('(function(){var e=document.querySelector(' + js(sel) + ');return e?e.textContent.trim():null;})()');
    },
    async valor(sel) {
      return aba.avaliar('(function(){var e=document.querySelector(' + js(sel) + ');return e?e.value:null;})()');
    },
    async atributo(sel, nome) {
      return aba.avaliar('(function(){var e=document.querySelector(' + js(sel) + ');return e?e.getAttribute(' + js(nome) + '):null;})()');
    },
    async foco() {
      return aba.avaliar(
        '(function(){var e=document.activeElement;if(!e)return null;' +
          'return {id:e.id||null,tag:e.tagName.toLowerCase(),tipo:e.getAttribute("type"),texto:(e.textContent||"").trim().slice(0,80)};})()'
      );
    },
    hash: () => aba.avaliar('location.hash'),
    url: () => aba.avaliar('location.href'),

    async digitar(sel, texto) {
      const ok = await aba.avaliar(
        '(function(){var e=document.querySelector(' + js(sel) + ');if(!e)return false;e.focus();' +
          'if(e.select)e.select();return document.activeElement===e;})()'
      );
      if (!ok) throw new Error('Não consegui focar o campo ' + sel);
      if (texto === '' || texto == null) {
        await aba.avaliar(
          '(function(){var e=document.querySelector(' + js(sel) + ');e.value="";' +
            'e.dispatchEvent(new Event("input",{bubbles:true}));})()'
        );
      } else {
        await aba.enviarComando('Input.insertText', { text: String(texto) });
      }
    },
    async marcar(sel, marcado = true) {
      const atual = await aba.avaliar('!!document.querySelector(' + js(sel) + ').checked');
      if (atual !== marcado) await aba.avaliar('document.querySelector(' + js(sel) + ').click()');
    },
    async preencherFormulario(valores = {}) {
      for (const campo of Object.keys(SELETORES_FORM)) {
        if (valores[campo] !== undefined) await ctx.digitar(SELETORES_FORM[campo], valores[campo]);
      }
      if (valores.aceite !== undefined) await ctx.marcar(SELETOR_ACEITE, Boolean(valores.aceite));
    },
    async clicar(sel, vezes = 1) {
      for (let i = 0; i < vezes; i++) {
        const achou = await aba.avaliar(
          '(function(){var e=document.querySelector(' + js(sel) + ');if(!e)return false;e.click();return true;})()'
        );
        if (!achou) throw new Error('Elemento não encontrado para clicar: ' + sel);
      }
    },
    enviar: () => ctx.clicar(SELETOR_ENVIAR),

    async teclar(tecla) {
      const shift = /^Shift\+/.test(tecla);
      const nome = tecla.replace(/^Shift\+/, '');
      const t = TECLAS[nome];
      if (!t) throw new Error('Tecla não suportada: ' + tecla);
      const base = { key: t.key, code: t.code, windowsVirtualKeyCode: t.vk, modifiers: shift ? 8 : 0 };
      await aba.enviarComando('Input.dispatchKeyEvent', { type: t.text ? 'keyDown' : 'rawKeyDown', ...base, ...(t.text ? { text: t.text } : {}) });
      await aba.enviarComando('Input.dispatchKeyEvent', { type: 'keyUp', ...base });
    },

    erros: () => aba.erros.map((e) => '[' + e.tipo + '] ' + e.texto),
    semErros() {
      if (aba.erros.length) throw new Error('Erros de script/console na página:\n  ' + ctx.erros().join('\n  '));
    },
    consoleCompleto: () => aba.console.slice(),

    async eventos() {
      return aba.avaliar('(function(){try{return JSON.parse(localStorage.getItem("tres-autoatendimento-eventos"))||[];}catch(e){return [];}})()');
    },
    async chamadosLocais() {
      return aba.avaliar('(function(){try{return JSON.parse(localStorage.getItem("tres-autoatendimento-chamados"))||[];}catch(e){return [];}})()');
    },
    async feedbacksLocais() {
      return aba.avaliar('(function(){try{return JSON.parse(localStorage.getItem("tres-autoatendimento-feedbacks"))||[];}catch(e){return [];}})()');
    },
    async armazenamento() {
      return aba.avaliar(
        '(function(){var l=[],s=[],i,k;try{for(i=0;i<localStorage.length;i++){k=localStorage.key(i);l.push(k+"="+localStorage.getItem(k));}}catch(e){}' +
          'try{for(i=0;i<sessionStorage.length;i++){k=sessionStorage.key(i);s.push(k+"="+sessionStorage.getItem(k));}}catch(e){}' +
          'return {local:l.join("\\n"),sessao:s.join("\\n"),cookies:document.cookie};})()'
      );
    },

    viewport: (largura, altura, mobile) => aba.viewport(largura, altura, mobile),
    movimentoReduzido: (ativo) => aba.movimentoReduzido(ativo),
    janelas: () => aba.alvosDoContexto(),
    async capturar(nome) {
      const seguro = String(nome).replace(/[^\w.-]+/g, '_');
      return aba.capturar(path.join(PASTA_CAPTURAS, seguro + '.png'));
    },

    _navegacoesPedidas: () => pedidas
  };
  return ctx;
}

/**
 * Registra os hooks do arquivo e devolve { cenario }.
 * Chamado uma vez por arquivo de teste (já feito na importação deste módulo,
 * porque cada arquivo roda em processo próprio sob `node --test`).
 */
function usarAmbiente() {
  let servidor = null;
  let info = null;
  let edge = null;
  let falhaInicial = null;

  before(async () => {
    try {
      servidor = criarServidor();
      info = await servidor.iniciar();
      edge = await iniciarEdge();
    } catch (e) {
      falhaInicial = e;
      // Libera o que subiu antes de falhar: nada fica órfão.
      if (edge) await edge.encerrar().catch(() => {});
      if (servidor) await servidor.fechar().catch(() => {});
      servidor = null; edge = null;
      throw new Error('Não foi possível preparar o ambiente de interface: ' + e.message);
    }
  }, { timeout: 30000 });

  after(async () => {
    if (edge) await edge.encerrar().catch(() => {});
    if (servidor) await servidor.fechar().catch(() => {});
    edge = null; servidor = null;
  }, { timeout: 30000 });

  /** cenario(nome, [opcoes], fn(ctx)) */
  function cenario(nome, a, b) {
    const opcoes = typeof a === 'function' ? {} : a || {};
    const fn = typeof a === 'function' ? a : b;
    const limiteMs = Math.min(opcoes.limiteMs || LIMITE_PADRAO_MS, LIMITE_PADRAO_MS);
    test(nome, { timeout: limiteMs + 8000 }, async () => {
      if (falhaInicial || !edge) throw new Error('Ambiente de interface indisponível: ' + (falhaInicial ? falhaInicial.message : 'não iniciado'));
      const sessao = servidor.criarSessao({
        modoApi: Boolean(opcoes.modoApi),
        api: opcoes.api,
        configNumerica: opcoes.configNumerica,
        modoApiFeedback: Boolean(opcoes.modoApiFeedback),
        apiFeedback: opcoes.apiFeedback,
        semTextosFeedback: opcoes.semTextosFeedback
      });
      const aba = await criarAba(edge.conexao, {
        viewport: opcoes.viewport,
        movimentoReduzido: opcoes.movimentoReduzido
      });
      const ctx = montarContexto(aba, sessao, sessao.base, limiteMs);
      let temporizador = null;
      try {
        if (opcoes.antes) await aba.injetarAntes(opcoes.antes);
        const limite = new Promise((_, rej) => {
          temporizador = setTimeout(
            () => rej(new Error('Cenário passou de ' + limiteMs + ' ms. O Edge headless recarrega a aba por volta de 5 s; encurte o cenário.')),
            limiteMs
          );
        });
        const execucao = Promise.resolve().then(() => fn(ctx));
        execucao.catch(() => {}); // evita rejeição solta se o limite vencer primeiro
        await Promise.race([execucao, limite]);
        if (aba.navegacoes > ctx._navegacoesPedidas()) {
          throw new Error(
            'A aba navegou ' + aba.navegacoes + ' vez(es), mas o cenário pediu ' + ctx._navegacoesPedidas() +
              '. Provável recarga espontânea do Edge headless (~5 s): encurte o cenário.'
          );
        }
      } catch (e) {
        const extra = ctx.erros().length ? '\n  Erros capturados na página:\n    ' + ctx.erros().join('\n    ') : '';
        e.message = '[cenário "' + nome + '"] ' + e.message + extra;
        throw e;
      } finally {
        if (temporizador) clearTimeout(temporizador);
        await aba.fechar();
      }
    });
  }

  return { cenario };
}

const ambiente = usarAmbiente();

module.exports = { cenario: ambiente.cenario, LIMITE_PADRAO_MS, PASTA_CAPTURAS };
