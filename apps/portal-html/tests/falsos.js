'use strict';
// Dublês de teste para o "mundo externo" do núcleo (storage, fetch,
// AbortController, setTimeout, relógio e sorteio). Nada aqui depende de
// js/chamado.js nem de rede, disco ou tempo real.

/* ==========================================================
 * 1. Storage falso (como localStorage)
 * ========================================================== */

// opcoes:
//   inicial        objeto { chave: texto } com o conteúdo de partida
//   lancaEmGetItem getItem lança (armazenamento indisponível)
//   lancaEmSetItem setItem lança (cota cheia, modo privado)
// O espião registra toda chamada em `chamadas` ({ metodo, chave, valor? }).
function criarStorageFalso(opcoes) {
  const o = opcoes || {};
  const dados = new Map(Object.entries(o.inicial || {}));
  const chamadas = [];

  const storage = {
    lancaEmGetItem: Boolean(o.lancaEmGetItem),
    lancaEmSetItem: Boolean(o.lancaEmSetItem),
    chamadas,
    dados,

    getItem(chave) {
      chamadas.push({ metodo: 'getItem', chave });
      if (storage.lancaEmGetItem) throw new Error('getItem indisponível (falso)');
      return dados.has(chave) ? dados.get(chave) : null;
    },

    setItem(chave, valor) {
      chamadas.push({ metodo: 'setItem', chave, valor });
      if (storage.lancaEmSetItem) {
        const erro = new Error('cota excedida (falso)');
        erro.name = 'QuotaExceededError';
        throw erro;
      }
      dados.set(chave, String(valor));
    },

    removeItem(chave) {
      chamadas.push({ metodo: 'removeItem', chave });
      dados.delete(chave);
    },

    // Quantas vezes cada método foi chamado.
    contar(metodo) {
      return chamadas.filter((c) => c.metodo === metodo).length;
    },

    // Conteúdo atual como objeto simples.
    instantaneo() {
      return Object.fromEntries(dados);
    }
  };
  return storage;
}

/* ==========================================================
 * 2. AbortController e setTimeout falsos
 * ========================================================== */

// Sinal mínimo compatível com o que o fetch e o núcleo usam.
function criarSinalFalso() {
  const ouvintes = [];
  const sinal = {
    aborted: false,
    onabort: null,
    addEventListener(tipo, fn) {
      if (tipo === 'abort') ouvintes.push(fn);
    },
    removeEventListener(tipo, fn) {
      const i = ouvintes.indexOf(fn);
      if (tipo === 'abort' && i !== -1) ouvintes.splice(i, 1);
    },
    _disparar() {
      if (sinal.aborted) return;
      sinal.aborted = true;
      const evento = { type: 'abort', target: sinal };
      if (typeof sinal.onabort === 'function') sinal.onabort(evento);
      ouvintes.slice().forEach((fn) => fn(evento));
    }
  };
  return sinal;
}

// Classe AbortController falsa; `instancias` guarda cada uso para conferência.
function criarAbortControllerFalso() {
  class AbortControllerFalso {
    constructor() {
      this.signal = criarSinalFalso();
      AbortControllerFalso.instancias.push(this);
    }
    abort() {
      this.signal._disparar();
    }
  }
  AbortControllerFalso.instancias = [];
  return AbortControllerFalso;
}

// Temporizador falso: nada dispara até `avancar(ms)` ser chamado.
function criarTemporizadorFalso() {
  let agora = 0;
  let proximoId = 1;
  const pendentes = new Map(); // id -> { quando, fn }
  const limpos = [];

  function setTimeoutFalso(fn, ms) {
    const id = proximoId++;
    pendentes.set(id, { quando: agora + (Number(ms) || 0), fn });
    return id;
  }

  function clearTimeoutFalso(id) {
    limpos.push(id);
    pendentes.delete(id);
  }

  // Avança o tempo e dispara, em ordem, o que venceu.
  function avancar(ms) {
    const limite = agora + ms;
    for (;;) {
      let escolhido = null;
      for (const [id, t] of pendentes) {
        if (t.quando <= limite && (escolhido === null || t.quando < pendentes.get(escolhido).quando)) escolhido = id;
      }
      if (escolhido === null) break;
      const t = pendentes.get(escolhido);
      pendentes.delete(escolhido);
      agora = Math.max(agora, t.quando);
      t.fn();
    }
    agora = limite;
  }

  return {
    setTimeout: setTimeoutFalso,
    clearTimeout: clearTimeoutFalso,
    avancar,
    pendentes: () => pendentes.size,
    limpos: () => limpos.slice(),
    agora: () => agora
  };
}

/* ==========================================================
 * 3. fetch falso
 * ========================================================== */

function erroDeAborto() {
  const e = new Error('The operation was aborted.');
  e.name = 'AbortError';
  return e;
}

// comportamento:
//   { status, corpo }      responde com esse status. `corpo` objeto → json()
//                          devolve o objeto; `corpo` texto → json() faz parse
//                          (texto inválido rejeita); sem `corpo` → json() rejeita.
//   { semResposta: true }  nunca responde; rejeita com AbortError se o sinal abortar.
//   { rejeita: erro }      rejeita (falha de rede). Padrão: TypeError('Failed to fetch').
// Devolve uma função fetch com `chamadas` (cada { url, init }) como espião.
function criarFetchFalso(comportamento) {
  const c = comportamento || {};

  function fetchFalso(url, init) {
    fetchFalso.chamadas.push({ url, init });
    const sinal = init && init.signal;

    if (c.semResposta) {
      return new Promise((resolve, reject) => {
        if (!sinal) return;
        if (sinal.aborted) return reject(erroDeAborto());
        sinal.addEventListener('abort', () => reject(erroDeAborto()));
      });
    }

    if (Object.prototype.hasOwnProperty.call(c, 'rejeita')) {
      const erro = c.rejeita instanceof Error ? c.rejeita : new TypeError('Failed to fetch');
      return Promise.reject(erro);
    }

    const status = c.status;
    const resposta = {
      status,
      ok: status >= 200 && status <= 299,
      json() {
        if (c.corpo === undefined) return Promise.reject(new SyntaxError('Unexpected end of JSON input'));
        if (typeof c.corpo === 'string') {
          try {
            return Promise.resolve(JSON.parse(c.corpo));
          } catch (e) {
            return Promise.reject(e);
          }
        }
        return Promise.resolve(c.corpo);
      },
      text() {
        if (c.corpo === undefined) return Promise.resolve('');
        return Promise.resolve(typeof c.corpo === 'string' ? c.corpo : JSON.stringify(c.corpo));
      }
    };
    return Promise.resolve(resposta);
  }

  fetchFalso.chamadas = [];
  return fetchFalso;
}

/* ==========================================================
 * 4. Relógio e sorteio determinísticos
 * ========================================================== */

// `agora()` devolve sempre um novo Date com o instante atual do relógio falso.
function criarRelogio(inicio) {
  let ms = inicio instanceof Date ? inicio.getTime() : typeof inicio === 'number' ? inicio : Date.UTC(2026, 9, 13, 17, 32, 10, 123);
  return {
    agora: () => new Date(ms),
    avancar(delta) {
      ms += delta;
    }
  };
}

// sorteio(max) → inteiro de 0 a max - 1, percorrendo a sequência em ciclo.
// Reproduz a mesma saída para a mesma sequência. `chamadas` conta os usos.
function criarSorteio(sequencia) {
  const lista = Array.isArray(sequencia) && sequencia.length > 0 ? sequencia : [0];
  let i = 0;
  function sorteio(max) {
    sorteio.chamadas += 1;
    const n = lista[i % lista.length];
    i += 1;
    return max > 0 ? Math.abs(Math.trunc(n)) % max : 0;
  }
  sorteio.chamadas = 0;
  return sorteio;
}

module.exports = {
  criarStorageFalso,
  criarSinalFalso,
  criarAbortControllerFalso,
  criarTemporizadorFalso,
  criarFetchFalso,
  criarRelogio,
  criarSorteio
};
