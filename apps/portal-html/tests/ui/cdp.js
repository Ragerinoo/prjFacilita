'use strict';
/**
 * Controle do Edge headless por DevTools Protocol (somente desenvolvimento).
 *
 * Sem dependências: usa child_process, fetch/WebSocket nativos do Node (22+).
 * - Inicia o Edge com perfil temporário próprio e porta de depuração própria
 *   (porta 0 -> o Edge escolhe e grava em DevToolsActivePort).
 * - Cada cenário usa um contexto de navegador novo (armazenamento isolado) e
 *   uma aba nova. Nada do Edge do usuário é tocado.
 * - Só encerra processos que este módulo iniciou.
 */
const { spawn, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const EDGE_CAMINHOS = [
  process.env.TRES_EDGE,
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  'C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe'
].filter(Boolean);

/** Prefixo dos perfis temporários; o runner usa para varrer sobras. */
const PREFIXO_PERFIL = 'tres-ui-edge-';

function achar() {
  const caminho = EDGE_CAMINHOS.find((c) => fs.existsSync(c));
  if (!caminho) throw new Error('Edge não encontrado. Procurei em: ' + EDGE_CAMINHOS.join(' | ') + ' (use TRES_EDGE para indicar o caminho).');
  return caminho;
}

const dormir = (ms) => new Promise((r) => setTimeout(r, ms));

function matarArvore(pid) {
  if (!pid) return;
  try {
    if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(pid), '/T', '/F'], { stdio: 'ignore', windowsHide: true });
    else process.kill(pid, 'SIGKILL');
  } catch (e) { /* já encerrado */ }
}

/** Conexão CDP única (navegador) com sessões "flatten" por aba. */
class Conexao {
  constructor(ws) {
    this.ws = ws;
    this.proximo = 1;
    this.pendentes = new Map();
    this.ouvintes = new Map(); // sessionId -> Set<fn(method, params)>
    this.fechada = false;
    ws.addEventListener('message', (ev) => {
      let msg;
      try { msg = JSON.parse(typeof ev.data === 'string' ? ev.data : Buffer.from(ev.data).toString('utf8')); } catch (e) { return; }
      if (msg.id && this.pendentes.has(msg.id)) {
        const p = this.pendentes.get(msg.id);
        this.pendentes.delete(msg.id);
        if (msg.error) p.reject(new Error('CDP ' + p.metodo + ': ' + msg.error.message));
        else p.resolve(msg.result || {});
      } else if (msg.method) {
        const set = this.ouvintes.get(msg.sessionId || '');
        if (set) for (const fn of set) { try { fn(msg.method, msg.params || {}); } catch (e) { /* ouvinte não derruba a conexão */ } }
      }
    });
    const aoFechar = () => {
      this.fechada = true;
      for (const p of this.pendentes.values()) p.reject(new Error('Conexão com o Edge fechada (' + p.metodo + ')'));
      this.pendentes.clear();
    };
    ws.addEventListener('close', aoFechar);
    ws.addEventListener('error', aoFechar);
  }

  enviar(metodo, params = {}, sessionId) {
    if (this.fechada) return Promise.reject(new Error('Conexão com o Edge fechada (' + metodo + ')'));
    const id = this.proximo++;
    const msg = { id, method: metodo, params };
    if (sessionId) msg.sessionId = sessionId;
    return new Promise((resolve, reject) => {
      this.pendentes.set(id, { resolve, reject, metodo });
      this.ws.send(JSON.stringify(msg));
    });
  }

  ouvir(sessionId, fn) {
    if (!this.ouvintes.has(sessionId)) this.ouvintes.set(sessionId, new Set());
    this.ouvintes.get(sessionId).add(fn);
  }

  fechar() { try { this.ws.close(); } catch (e) { /* ignora */ } }
}

/**
 * Inicia o Edge headless. Devolve { conexao, encerrar(), pid, perfil }.
 * Falha com mensagem clara se o Edge não abrir a porta em `limiteMs`.
 */
async function iniciarEdge({ limiteMs = 15000 } = {}) {
  const exe = achar();
  const perfil = fs.mkdtempSync(path.join(os.tmpdir(), PREFIXO_PERFIL));
  const args = [
    '--headless=new',
    '--remote-debugging-port=0',
    '--remote-allow-origins=*',
    '--user-data-dir=' + perfil,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    '--disable-sync',
    '--disable-background-networking',
    '--disable-component-update',
    '--disable-default-apps',
    '--disable-gpu',
    '--mute-audio',
    'about:blank'
  ];
  const filho = spawn(exe, args, { stdio: 'ignore', windowsHide: true });
  let saiu = false;
  filho.on('exit', () => { saiu = true; });
  filho.on('error', () => { saiu = true; });

  const aoSair = () => { if (!saiu) matarArvore(filho.pid); };
  process.on('exit', aoSair);

  let conexao = null;
  async function limpar() {
    process.removeListener('exit', aoSair);
    if (conexao) {
      try { await Promise.race([conexao.enviar('Browser.close'), dormir(1500)]); } catch (e) { /* fechando */ }
      conexao.fechar();
    }
    const t0 = Date.now();
    while (!saiu && Date.now() - t0 < 2500) await dormir(50);
    if (!saiu) matarArvore(filho.pid);
    // O Edge pode demorar a soltar o perfil: tenta apagar algumas vezes.
    for (let i = 0; i < 20; i++) {
      try { fs.rmSync(perfil, { recursive: true, force: true }); } catch (e) { /* tenta de novo */ }
      if (!fs.existsSync(perfil)) break;
      await dormir(200);
    }
  }

  try {
    const arquivoPorta = path.join(perfil, 'DevToolsActivePort');
    const t0 = Date.now();
    let linhas = null;
    while (Date.now() - t0 < limiteMs) {
      if (saiu) throw new Error('O Edge encerrou antes de abrir a porta de depuração.');
      if (fs.existsSync(arquivoPorta)) {
        const l = fs.readFileSync(arquivoPorta, 'utf8').split(/\r?\n/).filter(Boolean);
        if (l.length >= 2) { linhas = l; break; }
      }
      await dormir(50);
    }
    if (!linhas) throw new Error('O Edge não abriu a porta de depuração em ' + limiteMs + ' ms.');
    const ws = new WebSocket('ws://127.0.0.1:' + linhas[0] + linhas[1]);
    await new Promise((resolve, reject) => {
      const t = setTimeout(() => reject(new Error('Tempo esgotado conectando ao Edge (WebSocket).')), 8000);
      ws.addEventListener('open', () => { clearTimeout(t); resolve(); });
      ws.addEventListener('error', () => { clearTimeout(t); reject(new Error('Falha ao conectar ao Edge (WebSocket).')); });
    });
    conexao = new Conexao(ws);
    return { conexao, encerrar: limpar, pid: filho.pid, perfil, porta: Number(linhas[0]) };
  } catch (e) {
    await limpar();
    throw e;
  }
}

/** Texto legível de um RemoteObject do Runtime. */
function textoDe(obj) {
  if (!obj) return '';
  if ('value' in obj) return typeof obj.value === 'string' ? obj.value : JSON.stringify(obj.value);
  return obj.description || obj.unserializableValue || obj.type || '';
}

/**
 * Cria um contexto isolado + aba nova.
 * Devolve uma Aba com: navegar, avaliar, capturar, fechar e os registros de
 * erros/console/cargas.
 */
async function criarAba(conexao, opcoes = {}) {
  const { browserContextId } = await conexao.enviar('Target.createBrowserContext', { disposeOnDetach: false });
  const { targetId } = await conexao.enviar('Target.createTarget', { url: 'about:blank', browserContextId });
  const { sessionId } = await conexao.enviar('Target.attachToTarget', { targetId, flatten: true });
  const cmd = (m, p) => conexao.enviar(m, p, sessionId);

  const aba = {
    sessionId,
    targetId,
    browserContextId,
    erros: [], // { tipo, texto }
    console: [], // { tipo, texto }
    navegacoes: 0 // navegações do quadro principal (exceto about:blank); recarga espontânea soma aqui
  };

  conexao.ouvir(sessionId, (metodo, p) => {
    if (metodo === 'Runtime.exceptionThrown') {
      const d = p.exceptionDetails || {};
      const texto = (d.exception && (d.exception.description || textoDe(d.exception))) || d.text || 'exceção sem detalhe';
      aba.erros.push({ tipo: 'excecao', texto: texto + (d.url ? ' (' + d.url + ':' + d.lineNumber + ')' : '') });
    } else if (metodo === 'Runtime.consoleAPICalled') {
      const texto = (p.args || []).map(textoDe).join(' ');
      aba.console.push({ tipo: p.type, texto });
      if (p.type === 'error' || p.type === 'assert') aba.erros.push({ tipo: 'console.' + p.type, texto });
    } else if (metodo === 'Log.entryAdded') {
      const e = p.entry || {};
      aba.console.push({ tipo: 'log.' + e.level, texto: e.text + (e.url ? ' (' + e.url + ')' : '') });
      if (e.level === 'error') aba.erros.push({ tipo: 'log', texto: e.text + (e.url ? ' (' + e.url + ')' : '') });
    } else if (metodo === 'Page.frameNavigated') {
      const f = p.frame || {};
      if (!f.parentId && f.url !== 'about:blank') aba.navegacoes += 1;
    }
  });

  await Promise.all([cmd('Page.enable'), cmd('Runtime.enable'), cmd('Log.enable')]);

  aba.viewport = (largura, altura, mobile = false) =>
    cmd('Emulation.setDeviceMetricsOverride', { width: largura, height: altura, deviceScaleFactor: 1, mobile });
  aba.movimentoReduzido = (ativo) =>
    cmd('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: ativo ? 'reduce' : 'no-preference' }] });
  aba.injetarAntes = (js) => cmd('Page.addScriptToEvaluateOnNewDocument', { source: js });

  aba.navegar = async (url) => {
    const r = await cmd('Page.navigate', { url });
    if (r.errorText) throw new Error('Falha ao navegar para ' + url + ': ' + r.errorText);
  };

  aba.avaliar = async (expressao) => {
    const r = await cmd('Runtime.evaluate', { expression: expressao, returnByValue: true, awaitPromise: true });
    if (r.exceptionDetails) {
      const d = r.exceptionDetails;
      const msg = (d.exception && (d.exception.description || textoDe(d.exception))) || d.text;
      throw new Error('Erro ao executar JS na página: ' + msg);
    }
    return r.result ? r.result.value : undefined;
  };

  aba.enviarComando = cmd;

  aba.capturar = async (arquivo) => {
    const r = await cmd('Page.captureScreenshot', { format: 'png' });
    fs.mkdirSync(path.dirname(arquivo), { recursive: true });
    fs.writeFileSync(arquivo, Buffer.from(r.data, 'base64'));
    return arquivo;
  };

  /** Quantidade de abas/janelas no contexto isolado (para detectar window.open). */
  aba.alvosDoContexto = async () => {
    const { targetInfos } = await conexao.enviar('Target.getTargets');
    return targetInfos.filter((t) => t.browserContextId === browserContextId && t.type === 'page').length;
  };

  aba.fechar = async () => {
    try { await conexao.enviar('Target.closeTarget', { targetId }); } catch (e) { /* já fechada */ }
    try { await conexao.enviar('Target.disposeBrowserContext', { browserContextId }); } catch (e) { /* ignora */ }
  };

  if (opcoes.viewport) await aba.viewport(opcoes.viewport.largura, opcoes.viewport.altura, Boolean(opcoes.viewport.mobile));
  if (opcoes.movimentoReduzido) await aba.movimentoReduzido(true);
  return aba;
}

module.exports = { iniciarEdge, criarAba, achar, matarArvore, PREFIXO_PERFIL };
