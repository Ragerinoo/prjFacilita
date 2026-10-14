'use strict';
/**
 * Servidor de teste (somente desenvolvimento; não faz parte do site).
 *
 * - Serve a raiz do projeto como arquivos estáticos (módulos nativos http/fs),
 *   em 127.0.0.1 e porta livre escolhida pelo sistema.
 * - Cada cenário recebe uma "sessão" com prefixo próprio (/__t/<id>/), o que
 *   isola a configuração da API falsa e o registro das requisições. Os
 *   caminhos relativos do site (css/, js/, img/) continuam funcionando.
 * - API falsa opcional: POST <sessão>/api/chamados com respostas configuráveis
 *   (sucesso 201, erro 500, 2xx sem protocolo, corpo inválido, lenta, sem
 *   resposta) e registro de todas as requisições recebidas.
 * - Override de configuração SEM tocar nos arquivos do projeto: quando a sessão
 *   é criada com { modoApi: true }, a rota js/data.js da sessão é entregue
 *   por esta camada, em memória, com API_CHAMADOS_URL: '' trocado pela URL da
 *   API falsa. O arquivo js/data.js em disco nunca é lido para escrita.
 *   Sem modoApi, a sessão entrega o arquivo real, e o site fica em
 *   Modo_Prototipo (URL vazia).
 * - Feedback (comentário na tela de problema resolvido): mesma técnica, de forma
 *   independente do chamado. Com { modoApiFeedback: true }, API_FEEDBACK_URL: ''
 *   é trocado, em memória, pela URL da API falsa de feedback
 *   (<sessão>/api/feedbacks). Com { semTextosFeedback: ['rotulo', ...] }, as chaves
 *   indicadas de FEEDBACK.textos são removidas do js/data.js entregue (simula
 *   conteúdo indisponível). configNumerica vale para qualquer chave numérica
 *   (ex.: TIMEOUT_ENVIO_MS, TIMEOUT_FEEDBACK_MS) sempre que a sessão sobrescreve data.js.
 */
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');

const RAIZ = path.resolve(__dirname, '..', '..');

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.gif': 'image/gif',
  '.ico': 'image/x-icon',
  '.glb': 'model/gltf-binary',
  '.pdf': 'application/pdf',
  '.woff2': 'font/woff2',
  '.mjs': 'text/javascript; charset=utf-8'
};

const LIMITE_CORPO = 64 * 1024;

/**
 * Modos da API falsa:
 *   'sucesso'       201 { protocolo } (mesma chave de idempotência = mesmo protocolo)
 *   'erro500'       500 { erro }
 *   'sem-protocolo' 200 { ok: true } (2xx sem protocolo)
 *   'invalida'      201 com corpo que não é JSON
 *   'lenta'         responde 201 depois de `atraso` ms (padrão 6000)
 *   'sem-resposta'  aceita a conexão e nunca responde
 * `sequencia` (lista de modos) é consumida uma por requisição; o último se repete.
 *
 * Modos da API falsa de feedback (POST <sessão>/api/feedbacks, opção `apiFeedback`):
 *   'sucesso'       201 com corpo VAZIO
 *   'erro500'       500 { erro }
 *   'lento'         responde 201 (corpo vazio) depois de `atraso` ms (padrão 6000)
 *   'sem-resposta'  aceita a conexão e nunca responde
 * `sequencia` funciona como na API do chamado.
 */
function criarServidor() {
  const sessoes = new Map();
  const timers = new Set();
  const sockets = new Set();
  let contadorSessao = 0;
  let porta = 0;

  function novaSessao(opcoes = {}) {
    contadorSessao += 1;
    const id = 's' + contadorSessao;
    const prefixo = '/__t/' + id + '/';
    const sessao = {
      id,
      prefixo,
      modoApi: Boolean(opcoes.modoApi),
      // Valores numéricos de CHAMADO.config ou FEEDBACK.config trocados em memória
      // (ex.: { TIMEOUT_ENVIO_MS: 800, TIMEOUT_FEEDBACK_MS: 800 }). Valem quando a sessão
      // sobrescreve js/data.js (modoApi, modoApiFeedback ou semTextosFeedback). Padrão: nenhum.
      configNumerica: { ...(opcoes.configNumerica || {}) },
      api: { modo: 'sucesso', atraso: 6000, sequencia: null, ...(opcoes.api || {}) },
      // Feedback: independente do chamado.
      modoApiFeedback: Boolean(opcoes.modoApiFeedback),
      semTextosFeedback: [].concat(opcoes.semTextosFeedback || []).map(String),
      apiFeedback: { modo: 'sucesso', atraso: 6000, sequencia: null, ...(opcoes.apiFeedback || {}) },
      requisicoesFeedback: [],
      outrasFeedback: [],
      consumidasFeedback: 0,
      requisicoes: [],
      outras: [],
      protocolosPorChave: new Map(),
      seq: 0,
      consumidas: 0
    };
    sessoes.set(id, sessao);
    const base = 'http://127.0.0.1:' + porta + prefixo;
    return {
      id,
      base,
      apiUrl: base + 'api/chamados',
      /** Requisições POST recebidas em /api/chamados, com corpo e chave. */
      requisicoes: () => sessao.requisicoes.slice(),
      /** Chaves de idempotência recebidas, na ordem. */
      chaves: () => sessao.requisicoes.map((r) => r.chaveIdempotencia),
      /** Outras requisições à API (métodos diferentes de POST, etc.). */
      outras: () => sessao.outras.slice(),
      /** Troca o comportamento da API falsa durante o cenário. */
      definirApi(config) {
        sessao.api = { ...sessao.api, ...config };
        sessao.consumidas = 0;
      },
      apiFeedbackUrl: base + 'api/feedbacks',
      /** Requisições POST recebidas em /api/feedbacks, com corpo e chave. */
      requisicoesFeedback: () => sessao.requisicoesFeedback.slice(),
      /** Chaves de idempotência recebidas pela API de feedback, na ordem. */
      chavesFeedback: () => sessao.requisicoesFeedback.map((r) => r.chaveIdempotencia),
      /** Outras requisições à API de feedback (métodos diferentes de POST). */
      outrasFeedback: () => sessao.outrasFeedback.slice(),
      /** Troca o comportamento da API falsa de feedback durante o cenário. */
      definirApiFeedback(config) {
        sessao.apiFeedback = { ...sessao.apiFeedback, ...config };
        sessao.consumidasFeedback = 0;
      }
    };
  }

  function modoDaVez(sessao) {
    const seq = sessao.api.sequencia;
    if (Array.isArray(seq) && seq.length) {
      const modo = seq[Math.min(sessao.consumidas, seq.length - 1)];
      sessao.consumidas += 1;
      return modo;
    }
    return sessao.api.modo;
  }

  function modoDaVezFeedback(sessao) {
    const seq = sessao.apiFeedback.sequencia;
    if (Array.isArray(seq) && seq.length) {
      const modo = seq[Math.min(sessao.consumidasFeedback, seq.length - 1)];
      sessao.consumidasFeedback += 1;
      return modo;
    }
    return sessao.apiFeedback.modo;
  }

  function modoDaVezFeedback(sessao) {
    const seq = sessao.apiFeedback.sequencia;
    if (Array.isArray(seq) && seq.length) {
      const modo = seq[Math.min(sessao.consumidasFeedback, seq.length - 1)];
      sessao.consumidasFeedback += 1;
      return modo;
    }
    return sessao.apiFeedback.modo;
  }

  function lerCorpo(req) {
    return new Promise((resolve) => {
      const partes = [];
      let total = 0;
      req.on('data', (c) => {
        total += c.length;
        if (total <= LIMITE_CORPO) partes.push(c);
      });
      req.on('end', () => resolve(Buffer.concat(partes).toString('utf8')));
      req.on('error', () => resolve(''));
    });
  }

  function responder(res, status, corpo, tipo) {
    const buf = Buffer.isBuffer(corpo) ? corpo : Buffer.from(String(corpo), 'utf8');
    res.writeHead(status, {
      'Content-Type': tipo || 'text/plain; charset=utf-8',
      'Content-Length': buf.length,
      'Cache-Control': 'no-store'
    });
    res.end(buf);
  }

  async function tratarApi(sessao, req, res) {
    const corpoTexto = await lerCorpo(req);
    if (req.method !== 'POST') {
      sessao.outras.push({ metodo: req.method, caminho: req.url });
      res.setHeader('Allow', 'POST');
      return responder(res, req.method === 'OPTIONS' ? 204 : 405, '');
    }
    let json = null;
    try { json = JSON.parse(corpoTexto); } catch (e) { json = null; }
    const chave =
      (json && typeof json === 'object' && json.chaveIdempotencia) ||
      req.headers['idempotency-key'] ||
      null;
    sessao.requisicoes.push({
      metodo: req.method,
      caminho: req.url,
      cabecalhos: { ...req.headers },
      corpoTexto,
      json,
      chaveIdempotencia: chave,
      recebidaEm: Date.now()
    });

    const modo = modoDaVez(sessao);
    const jsonTipo = 'application/json; charset=utf-8';
    switch (modo) {
      case 'sucesso': {
        let protocolo = chave && sessao.protocolosPorChave.get(chave);
        if (!protocolo) {
          sessao.seq += 1;
          protocolo = 'API-' + String(sessao.seq).padStart(5, '0');
          if (chave) sessao.protocolosPorChave.set(chave, protocolo);
        }
        return responder(res, 201, JSON.stringify({ protocolo }), jsonTipo);
      }
      case 'erro500':
        return responder(res, 500, JSON.stringify({ erro: 'falha simulada' }), jsonTipo);
      case 'sem-protocolo':
        return responder(res, 200, JSON.stringify({ ok: true }), jsonTipo);
      case 'invalida':
        return responder(res, 201, '<html>isto nao e json', jsonTipo);
      case 'lenta': {
        const t = setTimeout(() => {
          timers.delete(t);
          if (!res.writableEnded && !res.destroyed) {
            sessao.seq += 1;
            responder(res, 201, JSON.stringify({ protocolo: 'API-LENTA-' + sessao.seq }), jsonTipo);
          }
        }, Number(sessao.api.atraso) || 6000);
        timers.add(t);
        return undefined;
      }
      case 'sem-resposta':
        return undefined; // nunca responde; o socket é derrubado em fechar()
      default:
        return responder(res, 500, 'modo de API falsa desconhecido: ' + modo);
    }
  }

  async function tratarApiFeedback(sessao, req, res) {
    const corpoTexto = await lerCorpo(req);
    if (req.method !== 'POST') {
      sessao.outrasFeedback.push({ metodo: req.method, caminho: req.url });
      res.setHeader('Allow', 'POST');
      return responder(res, req.method === 'OPTIONS' ? 204 : 405, '');
    }
    let json = null;
    try { json = JSON.parse(corpoTexto); } catch (e) { json = null; }
    const chave =
      (json && typeof json === 'object' && json.chaveIdempotencia) ||
      req.headers['idempotency-key'] ||
      null;
    sessao.requisicoesFeedback.push({
      metodo: req.method,
      caminho: req.url,
      cabecalhos: { ...req.headers },
      corpoTexto,
      json,
      chaveIdempotencia: chave,
      recebidaEm: Date.now()
    });

    const modo = modoDaVezFeedback(sessao);
    const jsonTipo = 'application/json; charset=utf-8';
    switch (modo) {
      case 'sucesso':
        return responder(res, 201, '', jsonTipo);
      case 'erro500':
        return responder(res, 500, JSON.stringify({ erro: 'falha simulada' }), jsonTipo);
      case 'lento': {
        const t = setTimeout(() => {
          timers.delete(t);
          if (!res.writableEnded && !res.destroyed) responder(res, 201, '', jsonTipo);
        }, Number(sessao.apiFeedback.atraso) || 6000);
        timers.add(t);
        return undefined;
      }
      case 'sem-resposta':
        return undefined; // nunca responde; o socket é derrubado em fechar()
      default:
        return responder(res, 500, 'modo de API falsa de feedback desconhecido: ' + modo);
    }
  }

  function servirArquivo(sessao, caminhoRel, res) {
    let rel = caminhoRel;
    if (rel === '' || rel.endsWith('/')) rel += 'index.html';
    let decodificado;
    try { decodificado = decodeURIComponent(rel); } catch (e) { return responder(res, 400, 'URL inválida'); }
    const absoluto = path.resolve(RAIZ, '.' + path.sep + decodificado.replace(/\//g, path.sep));
    if (absoluto !== RAIZ && !absoluto.startsWith(RAIZ + path.sep)) return responder(res, 403, 'Fora da raiz');
    if (decodificado === 'favicon.ico') return responder(res, 204, '');
    fs.readFile(absoluto, (erro, dados) => {
      if (erro) return responder(res, 404, 'Não encontrado: ' + decodificado);
      const tipo = MIME[path.extname(absoluto).toLowerCase()] || 'application/octet-stream';
      const sobrescreve = sessao && decodificado === 'js/data.js' &&
        (sessao.modoApi || sessao.modoApiFeedback || sessao.semTextosFeedback.length > 0);
      if (sobrescreve) {
        let trocado = dados.toString('utf8');
        if (sessao.modoApi) {
          const apiUrl = 'http://127.0.0.1:' + porta + sessao.prefixo + 'api/chamados';
          const padrao = /API_CHAMADOS_URL\s*:\s*(['"])\1/;
          if (!padrao.test(trocado)) {
            return responder(res, 500, 'servidor-teste: não achei API_CHAMADOS_URL vazia em js/data.js para sobrescrever');
          }
          trocado = trocado.replace(padrao, () => "API_CHAMADOS_URL: '" + apiUrl + "'");
        }
        if (sessao.modoApiFeedback) {
          const apiFeedbackUrl = 'http://127.0.0.1:' + porta + sessao.prefixo + 'api/feedbacks';
          const padraoFb = /API_FEEDBACK_URL\s*:\s*(['"])\1/;
          if (!padraoFb.test(trocado)) {
            return responder(res, 500, 'servidor-teste: não achei API_FEEDBACK_URL vazia em js/data.js para sobrescrever');
          }
          trocado = trocado.replace(padraoFb, () => "API_FEEDBACK_URL: '" + apiFeedbackUrl + "'");
        }
        for (const [chave, valor] of Object.entries(sessao.configNumerica)) {
          if (!/^[A-Z_]+$/.test(chave) || !Number.isFinite(valor)) {
            return responder(res, 500, 'servidor-teste: configNumerica inválida: ' + chave);
          }
          const alvo = new RegExp('(\\b' + chave + '\\s*:\\s*)-?\\d+(\\.\\d+)?');
          if (!alvo.test(trocado)) {
            return responder(res, 500, 'servidor-teste: não achei ' + chave + ' numérica em js/data.js para sobrescrever');
          }
          trocado = trocado.replace(alvo, (_, prefixo) => prefixo + String(valor));
        }
        if (sessao.semTextosFeedback.length) {
          // Remove, só dentro de FEEDBACK.textos, a linha de cada chave pedida.
          const inicioFb = trocado.indexOf('const FEEDBACK');
          if (inicioFb < 0) return responder(res, 500, 'servidor-teste: não achei FEEDBACK em js/data.js');
          let cabeca = trocado.slice(0, inicioFb);
          let cauda = trocado.slice(inicioFb);
          for (const chave of sessao.semTextosFeedback) {
            if (!/^[A-Za-z_]+$/.test(chave)) {
              return responder(res, 500, 'servidor-teste: semTextosFeedback inválida: ' + chave);
            }
            const linha = new RegExp('^[ \\t]*' + chave + '\\s*:\\s*(["\\x27]).*\\1\\s*,?[ \\t]*\\r?\\n', 'm');
            if (!linha.test(cauda)) {
              return responder(res, 500, 'servidor-teste: não achei a chave de texto ' + chave + ' em FEEDBACK.textos para remover');
            }
            cauda = cauda.replace(linha, '');
          }
          trocado = cabeca + cauda;
        }
        return responder(res, 200, trocado, tipo);
      }
      return responder(res, 200, dados, tipo);
    });
  }

  const servidor = http.createServer((req, res) => {
    let caminho;
    try { caminho = new URL(req.url, 'http://127.0.0.1').pathname; } catch (e) { return responder(res, 400, 'URL inválida'); }
    let sessao = null;
    let resto = caminho;
    const m = /^\/__t\/(s\d+)\/(.*)$/.exec(caminho);
    if (m) {
      sessao = sessoes.get(m[1]);
      if (!sessao) return responder(res, 404, 'Sessão de teste desconhecida');
      resto = '/' + m[2];
    }
    if (sessao && resto === '/api/chamados') {
      tratarApi(sessao, req, res).catch(() => { if (!res.headersSent) responder(res, 500, 'erro interno'); });
      return;
    }
    if (sessao && resto === '/api/feedbacks') {
      tratarApiFeedback(sessao, req, res).catch(() => { if (!res.headersSent) responder(res, 500, 'erro interno'); });
      return;
    }
    if (req.method !== 'GET' && req.method !== 'HEAD') return responder(res, 405, 'Método não permitido');
    servirArquivo(sessao, resto.slice(1), res);
  });

  servidor.on('connection', (s) => {
    sockets.add(s);
    s.on('close', () => sockets.delete(s));
  });

  return {
    /** Inicia em 127.0.0.1 na porta livre escolhida pelo sistema. */
    iniciar() {
      return new Promise((resolve, reject) => {
        servidor.once('error', reject);
        servidor.listen(0, '127.0.0.1', () => {
          porta = servidor.address().port;
          resolve({ porta, base: 'http://127.0.0.1:' + porta + '/' });
        });
      });
    },
    criarSessao: novaSessao,
    /** Encerra o servidor, derruba conexões pendentes e cancela temporizadores. */
    fechar() {
      return new Promise((resolve) => {
        for (const t of timers) clearTimeout(t);
        timers.clear();
        for (const s of sockets) s.destroy();
        if (!servidor.listening) return resolve();
        servidor.close(() => resolve());
      });
    }
  };
}

module.exports = { criarServidor, RAIZ };
