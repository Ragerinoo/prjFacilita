'use strict';
// Verificações estáticas da funcionalidade ticket-opening-screen (tarefa 12.14).
//
// Lê os arquivos do projeto (somente leitura) e confere regras de código, conteúdo,
// CSS e integridade que os testes de comportamento não cobrem.
//
//   node tests/estatico.js          roda direto (node:test)
//   cd tests && npm test            rodado também por tests/estatico.test.js
//
// Só módulos nativos do Node; nenhuma dependência nova. Heurísticas (regex, leitura
// simples de HTML e CSS) têm limites; onde há exceção legítima ela vem descrita num
// comentário ao lado da regra.

const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const { spawnSync } = require('child_process');

const RAIZ = path.resolve(__dirname, '..');
const ler = (rel) => fs.readFileSync(path.join(RAIZ, rel), 'utf8');

/* ------------------------------------------------------------------ */
/* Utilidades                                                          */
/* ------------------------------------------------------------------ */

const PALAVRAS_ANTES_DE_REGEX = ['return', 'typeof', 'case', 'in', 'of', 'delete', 'void', 'throw', 'new', 'else', 'do'];

function decodificar(bruto) {
  return bruto.replace(/\\(u[0-9a-fA-F]{4}|x[0-9a-fA-F]{2}|[\s\S])/g, function (_, c) {
    if (c[0] === 'u' && c.length === 5) return String.fromCharCode(parseInt(c.slice(1), 16));
    if (c[0] === 'x' && c.length === 3) return String.fromCharCode(parseInt(c.slice(1), 16));
    if (c === 'n') return '\n';
    if (c === 't') return '\t';
    return c;
  });
}

/*
 * Leitor mínimo de JavaScript. Devolve:
 *   codigo   o fonte com comentários trocados por espaços e o conteúdo de strings,
 *            templates e regex trocado por espaços (aspas ficam). Mesmo tamanho e
 *            mesmas quebras de linha do original, então os números de linha batem.
 *   literais lista { valor, linha } com o texto de cada string/template.
 * Se o fonte terminar num estado estranho (string aberta etc.), lança erro: é um
 * limite do analisador, não um problema do site.
 */
function analisarJs(src, nome) {
  const saida = [];
  const literais = [];
  let i = 0;
  let linha = 1;
  let ultimoSig = '';
  let ultimaPalavra = '';
  const n = src.length;

  function emitir(c) { saida.push(c); if (c === '\n') linha++; }

  while (i < n) {
    const c = src[i];
    const d = src[i + 1];

    if (c === '/' && d === '/') {
      while (i < n && src[i] !== '\n') { saida.push(' '); i++; }
      continue;
    }
    if (c === '/' && d === '*') {
      saida.push(' ', ' '); i += 2;
      while (i < n && !(src[i] === '*' && src[i + 1] === '/')) {
        if (src[i] === '\n') { saida.push('\n'); linha++; } else saida.push(' ');
        i++;
      }
      if (i >= n) throw new Error('Limite do analisador em ' + nome + ': comentário de bloco sem fim');
      saida.push(' ', ' '); i += 2;
      continue;
    }
    if (c === '\'' || c === '"' || c === '`') {
      const aspa = c;
      const linhaInicio = linha;
      let bruto = '';
      emitir(aspa); i++;
      let fechou = false;
      while (i < n) {
        const x = src[i];
        if (x === '\\') { bruto += x + (src[i + 1] || ''); saida.push(' '); if (src[i + 1] === '\n') { saida.push('\n'); linha++; } else saida.push(' '); i += 2; continue; }
        if (x === aspa) { fechou = true; break; }
        if (x === '\n' && aspa !== '`') throw new Error('Limite do analisador em ' + nome + ': string sem fim na linha ' + linha);
        bruto += x;
        if (x === '\n') { saida.push('\n'); linha++; } else saida.push(' ');
        i++;
      }
      if (!fechou) throw new Error('Limite do analisador em ' + nome + ': string sem fim (linha ' + linhaInicio + ')');
      emitir(aspa); i++;
      literais.push({ valor: decodificar(bruto), linha: linhaInicio });
      ultimoSig = aspa; ultimaPalavra = '';
      continue;
    }
    if (c === '/') {
      // Divisão ou regex? Regex quando o último token não é um valor.
      const ehRegex = ultimoSig === '' || '(,=:[!&|?{};+-*%<>~^'.indexOf(ultimoSig) !== -1 ||
        PALAVRAS_ANTES_DE_REGEX.indexOf(ultimaPalavra) !== -1;
      if (ehRegex) {
        emitir('/'); i++;
        let emClasse = false;
        let fechou = false;
        while (i < n) {
          const x = src[i];
          if (x === '\n') throw new Error('Limite do analisador em ' + nome + ': regex sem fim na linha ' + linha);
          if (x === '\\') { saida.push(' ', ' '); i += 2; continue; }
          if (x === '[') emClasse = true;
          else if (x === ']') emClasse = false;
          else if (x === '/' && !emClasse) { fechou = true; break; }
          saida.push(' '); i++;
        }
        if (!fechou) throw new Error('Limite do analisador em ' + nome + ': regex sem fim');
        emitir('/'); i++;
        while (i < n && /[a-z]/i.test(src[i])) { emitir(src[i]); i++; } // flags
        ultimoSig = ')'; ultimaPalavra = '';
        continue;
      }
    }
    emitir(c);
    if (!/\s/.test(c)) {
      ultimoSig = c;
      if (/[A-Za-z_$]/.test(c)) {
        let j = i; let p = '';
        while (j < n && /[\w$]/.test(src[j])) { p += src[j]; j++; }
        // Emite o resto da palavra de uma vez.
        for (let k = i + 1; k < j; k++) emitir(src[k]);
        i = j; ultimaPalavra = p; ultimoSig = p[p.length - 1];
        continue;
      }
      ultimaPalavra = '';
    }
    i++;
  }
  return { codigo: saida.join(''), literais: literais };
}

function linhaDe(texto, indice) {
  return texto.slice(0, indice).split('\n').length;
}

function acharTodos(texto, regex) {
  const r = new RegExp(regex.source, regex.flags.indexOf('g') === -1 ? regex.flags + 'g' : regex.flags);
  const achados = [];
  let m;
  while ((m = r.exec(texto)) !== null) {
    achados.push({ texto: m[0], indice: m.index, linha: linhaDe(texto, m.index) });
    if (m[0].length === 0) r.lastIndex++;
  }
  return achados;
}

function formatar(achados, arquivo) {
  return achados.map(function (a) { return '  ' + arquivo + ':' + a.linha + '  ' + a.texto.trim(); }).join('\n');
}

const fonte = {};
['js/app.js', 'js/chamado.js', 'js/feedback.js', 'js/data.js'].forEach(function (rel) {
  const src = ler(rel);
  fonte[rel] = { src: src, linhas: src.split('\n'), analise: analisarJs(src, rel) };
});

// Núcleos sem DOM: carregados em Node pelos testes e, no navegador, por <script> clássico.
const NUCLEOS = ['js/chamado.js', 'js/feedback.js'];

// js/data.js carregado numa área isolada: só precisa de um `window` falso.
function carregarDados() {
  const janela = {};
  vm.runInNewContext(fonte['js/data.js'].src, { window: janela }, { filename: 'js/data.js' });
  return janela.TRES_DATA;
}

/* ------------------------------------------------------------------ */
/* Leitor mínimo de HTML (para index.html)                             */
/* ------------------------------------------------------------------ */

const VAZIOS = ['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr'];

function lerHtml(html) {
  const semComentarios = html.replace(/<!--[\s\S]*?-->/g, function (m) { return m.replace(/[^\n]/g, ' '); });
  const tokens = [];
  const pilha = [];
  const re = /<(\/?)([a-zA-Z][\w-]*)((?:"[^"]*"|'[^']*'|[^>"'])*)>|([^<]+)/g;
  let m;
  while ((m = re.exec(semComentarios)) !== null) {
    const linha = linhaDe(semComentarios, m.index);
    if (m[4] !== undefined) {
      tokens.push({ tipo: 'texto', texto: m[4], linha: linha, ancestrais: pilha.slice() });
      continue;
    }
    const fecha = m[1] === '/';
    const tag = m[2].toLowerCase();
    const attrsBrutos = m[3] || '';
    if (fecha) {
      for (let k = pilha.length - 1; k >= 0; k--) {
        if (pilha[k].tag === tag) { pilha.length = k; break; }
      }
      continue;
    }
    const attrs = {};
    attrsBrutos.replace(/([\w:-]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+)))?/g, function (_, nome, a, b, c) {
      attrs[nome.toLowerCase()] = a !== undefined ? a : (b !== undefined ? b : (c !== undefined ? c : ''));
      return '';
    });
    const el = { tag: tag, attrs: attrs, linha: linha, ancestrais: pilha.slice() };
    tokens.push(Object.assign({ tipo: 'abre' }, el));
    const autoFecha = VAZIOS.indexOf(tag) !== -1 || /\/\s*$/.test(attrsBrutos);
    if (!autoFecha) pilha.push(el);
    if (tag === 'script' || tag === 'style') {
      // Conteúdo bruto até o fechamento.
      const fim = semComentarios.toLowerCase().indexOf('</' + tag, re.lastIndex);
      if (fim !== -1) {
        tokens.push({ tipo: 'bruto', texto: semComentarios.slice(re.lastIndex, fim), linha: linha, ancestrais: pilha.slice() });
        re.lastIndex = fim;
      }
    }
  }
  return tokens;
}

const html = ler('index.html');
const tokensHtml = lerHtml(html);

/* ------------------------------------------------------------------ */
/* CSS                                                                 */
/* ------------------------------------------------------------------ */

const css = ler('css/styles.css');
const MARCADOR_CSS = 'Tela_de_Chamado (abertura de chamado)';

// Troca comentários por espaços (preserva posições).
const cssSemComentarios = css.replace(/\/\*[\s\S]*?\*\//g, function (m) { return m.replace(/[^\n]/g, ' '); });

function inicioBlocosNovos() {
  const idx = css.indexOf(MARCADOR_CSS);
  if (idx === -1) return -1;
  const banner = css.lastIndexOf('/* =====', idx);
  return banner === -1 ? idx : banner;
}
const INICIO_NOVO = inicioBlocosNovos();

// Lista as regras de estilo (com @media aninhado). Cada item: { seletor, corpo, contexto, indice }.
function listarRegras(texto) {
  const regras = [];
  function percorrer(inicio, fim, contexto) {
    let i = inicio;
    let preludioIni = i;
    while (i < fim) {
      const c = texto[i];
      if (c === ';') { preludioIni = i + 1; i++; continue; }
      if (c === '}') { preludioIni = i + 1; i++; continue; }
      if (c === '{') {
        const preludio = texto.slice(preludioIni, i).trim();
        let prof = 1; let j = i + 1;
        while (j < fim && prof > 0) { if (texto[j] === '{') prof++; else if (texto[j] === '}') prof--; j++; }
        const corpo = texto.slice(i + 1, j - 1);
        if (/^@(media|supports)/i.test(preludio)) {
          percorrer(i + 1, j - 1, contexto.concat(preludio));
        } else if (!/^@/.test(preludio)) {
          regras.push({ seletor: preludio, corpo: corpo, contexto: contexto, indice: preludioIni + (texto.slice(preludioIni, i).length - texto.slice(preludioIni, i).trimStart().length) });
        }
        i = j; preludioIni = j;
        continue;
      }
      i++;
    }
  }
  percorrer(0, texto.length, []);
  return regras;
}

function declaracoes(corpo) {
  const mapa = {};
  corpo.split(';').forEach(function (d) {
    const k = d.indexOf(':');
    if (k === -1) return;
    const nome = d.slice(0, k).trim().toLowerCase();
    const valor = d.slice(k + 1).trim();
    if (nome) { (mapa[nome] = mapa[nome] || []).push(valor); }
  });
  return mapa;
}

function emPx(valor) {
  const m = /^(-?\d*\.?\d+)(px|rem|em)$/.exec(String(valor).trim());
  if (!m) return NaN;
  return m[2] === 'px' ? parseFloat(m[1]) : parseFloat(m[1]) * 16;
}

const regrasCss = listarRegras(cssSemComentarios);
const regrasNovas = regrasCss.filter(function (r) { return INICIO_NOVO !== -1 && r.indice >= INICIO_NOVO; });

// Tokens do :root, com var() resolvido.
function tokensRaiz() {
  const raiz = regrasCss.find(function (r) { return r.seletor === ':root'; });
  const mapa = {};
  if (!raiz) return mapa;
  Object.keys(declaracoes(raiz.corpo)).forEach(function (k) {
    if (k.indexOf('--') === 0) mapa[k] = declaracoes(raiz.corpo)[k][0];
  });
  return mapa;
}
const TOKENS = tokensRaiz();
function resolverToken(valor, profundidade) {
  profundidade = profundidade || 0;
  if (profundidade > 10) throw new Error('Referência circular nos tokens do :root');
  const m = /^var\(\s*(--[\w-]+)\s*\)$/.exec(String(valor).trim());
  if (!m) return String(valor).trim();
  if (!(m[1] in TOKENS)) throw new Error('Token ausente no :root: ' + m[1]);
  return resolverToken(TOKENS[m[1]], profundidade + 1);
}
function corDoToken(nome) {
  const v = resolverToken('var(' + nome + ')');
  const m = /^#([0-9a-fA-F]{6})$/.exec(v);
  if (!m) throw new Error('O token ' + nome + ' não resolve para #RRGGBB (valor: ' + v + ')');
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function luminancia(rgb) {
  const [r, g, b] = rgb.map(function (v) {
    const s = v / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contraste(a, b) {
  const la = luminancia(a); const lb = luminancia(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}

/* ================================================================== */
/* Verificações                                                        */
/* ================================================================== */

test('1. Sem console.* em js/app.js, js/chamado.js e js/feedback.js (R6.14)', function () {
  const problemas = [];
  ['js/app.js', 'js/chamado.js', 'js/feedback.js'].forEach(function (rel) {
    const achados = acharTodos(fonte[rel].analise.codigo, /\bconsole\s*\./);
    achados.forEach(function (a) { problemas.push('  ' + rel + ':' + a.linha + '  ' + fonte[rel].linhas[a.linha - 1].trim()); });
  });
  assert.equal(problemas.length, 0, 'Dados do formulário podem vazar para o console. Remova:\n' + problemas.join('\n'));
});

test('2. Sem HTML dinâmico: o único innerHTML é o SVG fixo SVG_MAQUINA (R6.14, R12.3)', function () {
  const regexPerigosos = /\b(innerHTML|outerHTML|insertAdjacentHTML)\b|\bdocument\s*\.\s*write(ln)?\b/;
  const nao = [];
  const permitidos = [];
  ['js/app.js', 'js/chamado.js', 'js/feedback.js', 'js/data.js'].forEach(function (rel) {
    acharTodos(fonte[rel].analise.codigo, new RegExp(regexPerigosos.source, 'g')).forEach(function (a) {
      permitidos.push({ rel: rel, a: a });
    });
  });

  // Exceção única e conhecida: `caixa.innerHTML = SVG_MAQUINA;` em fotoModelo (js/app.js),
  // com comentário na mesma linha dizendo que a marcação é fixa.
  const legitimos = permitidos.filter(function (p) {
    if (p.rel !== 'js/app.js') return false;
    const original = fonte[p.rel].linhas[p.a.linha - 1];
    return /\.innerHTML\s*=\s*SVG_MAQUINA\s*;/.test(original) && /\/\/.*(fixa|fixo)/i.test(original);
  });
  permitidos.forEach(function (p) {
    if (legitimos.indexOf(p) === -1) nao.push('  ' + p.rel + ':' + p.a.linha + '  ' + fonte[p.rel].linhas[p.a.linha - 1].trim());
  });
  assert.equal(nao.length, 0, 'Uso de HTML dinâmico fora da exceção permitida (SVG_MAQUINA, marcado com comentário). Use textContent/createElement:\n' + nao.join('\n'));
  assert.ok(legitimos.length <= 1, 'Esperado no máximo um innerHTML (SVG_MAQUINA), achados: ' + legitimos.length);

  // SVG_MAQUINA tem de ser só strings literais concatenadas (sem variável nem ${}).
  const src = fonte['js/app.js'].src;
  const decl = /const\s+SVG_MAQUINA\s*=([\s\S]*?);/.exec(src);
  assert.ok(decl, 'Declaração de SVG_MAQUINA não encontrada em js/app.js');
  const resto = decl[1].replace(/'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"/g, '').replace(/[\s+]/g, '');
  assert.equal(resto, '', 'SVG_MAQUINA deve ser feita só de strings literais; sobrou: ' + resto);
  assert.ok(!/\$\{/.test(decl[1]), 'SVG_MAQUINA não pode usar ${} (interpolação)');
});

test('3. index.html: #view-suporte e #view-chamado só têm texto via data-texto (R12.3)', function () {
  const problemas = [];
  const dentro = function (t) {
    return t.ancestrais.some(function (a) { return a.attrs.id === 'view-suporte' || a.attrs.id === 'view-chamado'; });
  };
  const atributosDeTexto = ['placeholder', 'title', 'alt', 'aria-label', 'value'];
  tokensHtml.forEach(function (t) {
    if (t.tipo === 'texto' && dentro(t) && /\S/.test(t.texto)) {
      // Exceção: emoji decorativo dentro de elemento aria-hidden="true" (sem letras nem números).
      const decorativo = t.ancestrais.some(function (a) { return a.attrs['aria-hidden'] === 'true'; }) &&
        !/[\p{L}\p{N}]/u.test(t.texto);
      if (!decorativo) problemas.push('  index.html:' + t.linha + '  texto escrito direto: "' + t.texto.trim() + '"');
    }
    if (t.tipo === 'abre' && (dentro(t) || t.attrs.id === 'view-suporte' || t.attrs.id === 'view-chamado')) {
      atributosDeTexto.forEach(function (nome) {
        // value em checkbox/radio/botão não é texto de interface; só vale para textos escritos à mão.
        if (nome in t.attrs && t.attrs[nome] !== '') problemas.push('  index.html:' + t.linha + '  <' + t.tag + '> com ' + nome + '="' + t.attrs[nome] + '" (texto fora de data.js)');
      });
    }
  });
  assert.equal(problemas.length, 0, 'Texto novo escrito em index.html. Mova para D.CHAMADO.textos e use data-texto:\n' + problemas.join('\n'));
});

test('3b. index.html: todo data-texto aponta para uma chave existente em D.CHAMADO.textos', function () {
  const textos = carregarDados().CHAMADO.textos;
  const problemas = [];
  tokensHtml.forEach(function (t) {
    if (t.tipo === 'abre' && 'data-texto' in t.attrs) {
      const v = textos[t.attrs['data-texto']];
      if (typeof v !== 'string' || v.trim() === '') problemas.push('  index.html:' + t.linha + '  data-texto="' + t.attrs['data-texto'] + '" sem texto em data.js');
    }
  });
  assert.equal(problemas.length, 0, 'Chaves data-texto sem texto correspondente:\n' + problemas.join('\n'));
});

test('4. Frases de D.CHAMADO.textos não aparecem escritas em js/app.js nem js/chamado.js (R12.3)', function () {
  const textos = carregarDados().CHAMADO.textos;
  const problemas = [];
  ['js/app.js', 'js/chamado.js'].forEach(function (rel) {
    const literais = fonte[rel].analise.literais;
    Object.keys(textos).forEach(function (chave) {
      const valor = textos[chave];
      if (typeof valor !== 'string') return;
      // Marcadores {x} são trocados em código; compara só os pedaços de texto fixo.
      const comMarcador = /\{[A-Za-z]+\}/.test(valor);
      valor.split(/\{[A-Za-z]+\}/).map(function (s) { return s.trim(); }).filter(Boolean).forEach(function (trecho) {
        // Sobras curtas de textos com marcador (", ", " de ", ".") não identificam frase nenhuma.
        if (comMarcador && trecho.length < 12) return;
        literais.forEach(function (lit) {
          // Pedaços longos (>= 12 caracteres) são procurados dentro de qualquer literal;
          // textos curtos inteiros ("Nome", "E-mail") só contam se o literal inteiro for igual,
          // para não acusar palavras comuns dentro de outras frases.
          const achou = trecho.length >= 12 ? lit.valor.indexOf(trecho) !== -1 : lit.valor.trim() === trecho;
          if (!achou) return;
          // Exceção legítima: js/chamado.js guarda FRASE_CONTEUDO_INDISPONIVEL como último
          // recurso para o caso de js/data.js não carregar (R12.6). É a mesma frase de
          // textos.conteudoIndisponivel, por isso não pode vir de data.js.
          if (rel === 'js/chamado.js' && chave === 'conteudoIndisponivel') return;
          problemas.push('  ' + rel + ':' + lit.linha + '  repete textos.' + chave + ': "' + lit.valor.slice(0, 70) + '"');
        });
      });
    });
  });
  assert.equal(problemas.length, 0, 'Texto de interface das telas novas escrito fora de js/data.js:\n' + problemas.join('\n'));

  // A exceção só vale para a constante nomeada.
  const decl = /var\s+FRASE_CONTEUDO_INDISPONIVEL\s*=\s*'/.exec(fonte['js/chamado.js'].src);
  assert.ok(decl, 'FRASE_CONTEUDO_INDISPONIVEL deveria estar declarada em js/chamado.js');
});

test('5. js/chamado.js e js/feedback.js são núcleos puros: sem DOM, window, storage, fetch direto nem relógio (R12.x, design)', function () {
  const problemas = [];
  NUCLEOS.forEach(function (rel) {
  const codigo = fonte[rel].analise.codigo;
  const linhas = fonte[rel].linhas;
  const registrar = function (a, motivo) { problemas.push('  ' + rel + ':' + a.linha + '  ' + motivo + '  >> ' + linhas[a.linha - 1].trim()); };

  // Exceção 1: wrapper UMD `(typeof window !== 'undefined' ? window : globalThis, ...)`.
  // Ele escolhe onde pendurar window.TRESChamado no navegador; não lê estado nenhum.
  const semWrapper = codigo.replace(/typeof\s+window\s*!==\s*'\s*'\s*\?\s*window\s*:\s*globalThis/, function (m) { return m.replace(/[^\n]/g, ' '); });
  acharTodos(semWrapper, /\bdocument\b/).forEach(function (a) { registrar(a, 'referência a document'); });
  acharTodos(semWrapper, /\bwindow\b/).forEach(function (a) { registrar(a, 'referência a window fora do wrapper UMD'); });
  acharTodos(codigo, /\b(localStorage|sessionStorage)\b/).forEach(function (a) { registrar(a, 'acesso direto a storage (use a porta storage)'); });
  // `fetch(` direto proibido; `fnFetch(` (porta injetada) tem F maiúsculo e não casa.
  acharTodos(codigo, /(^|[^\w$.])fetch\s*\(/).forEach(function (a) { registrar(a, 'fetch direto (use a porta fetch)'); });
  acharTodos(codigo, /\bXMLHttpRequest\b/).forEach(function (a) { registrar(a, 'XMLHttpRequest'); });
  acharTodos(codigo, /\bDate\s*\.\s*now\b/).forEach(function (a) { registrar(a, 'Date.now (use a porta agora)'); });

  // Exceção 2: `new Date()` sem argumentos só como valor padrão quando a porta `agora`/data
  // não foi injetada: `x ? y : new Date()` ou `return new Date()...`. Qualquer outra forma falha.
  acharTodos(codigo, /\bnew\s+Date\s*\(\s*\)/).forEach(function (a) {
    const antes = codigo.slice(Math.max(0, a.indice - 40), a.indice);
    if (!/(:\s*|\breturn\s+)$/.test(antes)) registrar(a, 'new Date() fora de um valor padrão de porta');
  });
  });
  assert.equal(problemas.length, 0, 'js/chamado.js e js/feedback.js devem receber DOM, tempo, rede e storage por injeção:\n' + problemas.join('\n'));
});

test('6. Sem dependências de terceiros novas (R12.4)', function () {
  const problemas = [];
  const scripts = tokensHtml.filter(function (t) { return t.tipo === 'abre' && t.tag === 'script'; });
  const srcs = scripts.map(function (t) { return t.attrs.src; });
  assert.deepEqual(srcs, ['js/data.js', 'js/chamado.js', 'js/feedback.js', 'js/app.js'], 'index.html deve carregar só js/data.js, js/chamado.js, js/feedback.js e js/app.js, nessa ordem. Achado: ' + JSON.stringify(srcs));

  tokensHtml.filter(function (t) { return t.tipo === 'abre' && t.tag === 'link'; }).forEach(function (t) {
    if (t.attrs.href !== 'css/styles.css') problemas.push('  index.html:' + t.linha + '  <link href="' + t.attrs.href + '"> (só css/styles.css é permitido)');
  });
  tokensHtml.filter(function (t) { return t.tipo === 'abre' && /^(img|iframe|source|video|audio|embed|object)$/.test(t.tag); }).forEach(function (t) {
    const url = t.attrs.src || '';
    if (/^(https?:)?\/\//i.test(url)) problemas.push('  index.html:' + t.linha + '  <' + t.tag + ' src="' + url + '"> externo');
  });
  // Nenhuma regra de CSS importa recurso externo ou fonte.
  acharTodos(cssSemComentarios, /@import|@font-face|url\(\s*['"]?(https?:)?\/\//i).forEach(function (a) {
    problemas.push('  css/styles.css:' + a.linha + '  ' + a.texto + ' (recurso externo ou fonte)');
  });
  // JS novo não carrega scripts externos nem usa import/require dinâmico.
  ['js/app.js', 'js/chamado.js', 'js/feedback.js'].forEach(function (rel) {
    acharTodos(fonte[rel].analise.codigo, /\b(importScripts|require)\s*\(|\bimport\s*\(|^\s*import\s/m).forEach(function (a) { problemas.push('  ' + rel + ':' + a.linha + '  ' + a.texto.trim()); });
    fonte[rel].analise.literais.forEach(function (lit) {
      if (/^(https?:)?\/\//i.test(lit.valor)) problemas.push('  ' + rel + ':' + lit.linha + '  URL externa escrita no código: ' + lit.valor);
    });
  });
  // js/vendor: só o que já existia (model-viewer carregado sob demanda e a licença).
  const vendor = fs.readdirSync(path.join(RAIZ, 'js', 'vendor')).sort();
  assert.deepEqual(vendor, ['model-viewer-umd.min.js', 'model-viewer.LICENSE.txt'], 'js/vendor mudou: ' + JSON.stringify(vendor));
  assert.equal(fonte['js/data.js'].src.indexOf("biblioteca: 'js/vendor/model-viewer-umd.min.js'") !== -1, true, 'MODELO_3D.biblioteca deve continuar apontando para js/vendor/model-viewer-umd.min.js');

  assert.ok(!fs.existsSync(path.join(RAIZ, 'package.json')), 'Não pode haver package.json na raiz (o site não tem etapa de instalação)');
  assert.ok(!fs.existsSync(path.join(RAIZ, 'node_modules')), 'Não pode haver node_modules na raiz');
  assert.equal(problemas.length, 0, 'Dependências ou recursos de terceiros:\n' + problemas.join('\n'));
});

test('7. Cabeçalho, rodapé, etapas e views existentes preservados (R12.1, R12.2)', function () {
  assert.match(html, /<a\b[^>]*\bhref="#\/contato"[^>]*>\s*Falar com a gente\s*<\/a>/, 'Link "Falar com a gente" (href="#/contato") ausente do cabeçalho');
  const rodape = /<footer\b[\s\S]*?<\/footer>/.exec(html);
  assert.ok(rodape, '<footer> ausente');
  assert.match(rodape[0], /<a\b[^>]*\bhref="#\/contato"[^>]*>\s*Veja os canais de atendimento\s*<\/a>/, 'Rodapé sem o link "Veja os canais de atendimento" (href="#/contato")');
  assert.match(rodape[0], /id="link-central"/, 'Rodapé sem o link da Central de Ajuda');

  ['modelo', 'problema', 'solucao', 'confirma', 'resolvido', 'contato'].forEach(function (v) {
    assert.match(html, new RegExp('<section\\b[^>]*\\bid="view-' + v + '"'), 'View existente #view-' + v + ' sumiu do index.html');
  });
  const itens = tokensHtml.filter(function (t) { return t.tipo === 'abre' && t.tag === 'li' && 'data-etapa' in t.attrs; });
  assert.deepEqual(itens.map(function (t) { return t.attrs['data-etapa']; }), ['1', '2', '3'], 'A barra de etapas deve ter exatamente 3 itens (1, 2, 3)');
  // As duas views novas existem.
  ['suporte', 'chamado'].forEach(function (v) {
    assert.match(html, new RegExp('<section\\b[^>]*\\bid="view-' + v + '"'), 'View nova #view-' + v + ' ausente');
  });
});

test('8. Nenhum ID órfão removido é referenciado em js/ ou css/', function () {
  const ids = ['cartao-contato', 'lista-em-maos', 'estrelas-suporte', 'status-aval-suporte', 'btn-rever-suporte'];
  const problemas = [];
  const arquivos = ['js/app.js', 'js/chamado.js', 'js/data.js', 'css/styles.css'];
  arquivos.forEach(function (rel) {
    const texto = rel.indexOf('.css') !== -1 ? cssSemComentarios : fonte[rel].src;
    ids.forEach(function (id) {
      // `(?![\w-])` evita falso positivo com `cartao-contato-geral` (ID vivo) e com a classe
      // `.cartao-contato` do CSS (classe existente, não é o ID); aqui só importa uso como ID.
      const comoId = new RegExp('(#|getElementById\\(\\s*[\'"]|id\\s*[:=]\\s*[\'"]|\\[id=[\'"]?)' + id + '(?![\\w-])');
      const solto = new RegExp('[\'"]' + id + '[\'"]');
      acharTodos(texto, comoId).concat(acharTodos(texto, solto)).forEach(function (a) {
        problemas.push('  ' + rel + ':' + a.linha + '  ' + a.texto);
      });
    });
  });
  // Também não podem voltar ao HTML.
  ids.forEach(function (id) {
    if (new RegExp('\\bid="' + id + '"').test(html)) problemas.push('  index.html  id="' + id + '" voltou');
  });
  assert.equal(problemas.length, 0, 'IDs removidos ainda referenciados:\n' + problemas.join('\n'));
});

test('9a. CSS: blocos novos sem transition/animation e redução de movimento global (R11.7)', function () {
  assert.ok(INICIO_NOVO !== -1, 'Marcador dos blocos novos não encontrado em css/styles.css: "' + MARCADOR_CSS + '"');
  assert.ok(regrasNovas.length > 10, 'Poucas regras encontradas nos blocos novos (' + regrasNovas.length + '); o analisador de CSS pode ter falhado');
  const problemas = [];
  regrasNovas.forEach(function (r) {
    Object.keys(declaracoes(r.corpo)).forEach(function (nome) {
      if (/^(transition|animation)(-|$)/.test(nome) || nome === 'scroll-behavior') {
        problemas.push('  css/styles.css:' + linhaDe(css, r.indice) + '  ' + r.seletor + ' { ' + nome + ' }');
      }
    });
  });
  assert.equal(problemas.length, 0, 'Blocos novos não podem criar transição nem animação:\n' + problemas.join('\n'));

  const reduzido = regrasCss.filter(function (r) { return r.contexto.some(function (c) { return /prefers-reduced-motion\s*:\s*reduce/.test(c); }); });
  assert.ok(reduzido.length > 0, 'Falta @media (prefers-reduced-motion: reduce) em css/styles.css');
  const global = reduzido.find(function (r) { return /\*/.test(r.seletor); });
  assert.ok(global, 'A regra de movimento reduzido deve ser global (seletor com *)');
  const d = declaracoes(global.corpo);
  assert.match((d.transition || [''])[0], /^none\b/, 'Movimento reduzido deve zerar transition');
  assert.match((d.animation || [''])[0], /^none\b/, 'Movimento reduzido deve zerar animation');
});

test('9b. CSS: campos novos com fonte >= 1rem (16 px) (R11.x)', function () {
  const ehCampo = function (seletor) {
    return seletor.split(',').some(function (s) { return /(^|[\s>+~])(input|textarea|select)(?![\w-])/.test(s.trim()); });
  };
  const problemas = [];
  const cobertos = { input: false, textarea: false };
  regrasNovas.filter(function (r) { return ehCampo(r.seletor); }).forEach(function (r) {
    const fs_ = declaracoes(r.corpo)['font-size'];
    if (!fs_) return;
    const px = emPx(fs_[0]);
    if (isNaN(px) || px < 16) {
      problemas.push('  css/styles.css:' + linhaDe(css, r.indice) + '  ' + r.seletor + ' { font-size: ' + fs_[0] + ' } (precisa ser >= 1rem / 16px)');
    } else {
      if (/input/.test(r.seletor)) cobertos.input = true;
      if (/textarea/.test(r.seletor)) cobertos.textarea = true;
    }
  });
  assert.equal(problemas.length, 0, 'Fonte de campo abaixo de 16 px (iOS dá zoom ao focar):\n' + problemas.join('\n'));
  assert.ok(cobertos.input, 'Nenhuma regra nova define font-size >= 1rem para input');
  assert.ok(cobertos.textarea, 'Nenhuma regra nova define font-size >= 1rem para textarea');
});

test('9c. CSS: alvos de toque novos com min-height de 44 px ou var(--alvo-minimo) (R11.x, heurística)', function () {
  const alvo = emPx(resolverToken('var(--alvo-minimo)'));
  assert.ok(alvo >= 44, '--alvo-minimo deve ser >= 44px (valor: ' + TOKENS['--alvo-minimo'] + ')');

  const minAltura = function (valor) {
    if (/^var\(\s*--alvo-minimo\s*\)$/.test(valor.trim())) return alvo;
    return emPx(valor);
  };
  // Classe de base com min-height suficiente (ex.: .btn 48px, .link-btn 44px) já cobre o elemento.
  const baseOk = function (classe) {
    return regrasCss.some(function (r) {
      return r.seletor === '.' + classe && r.contexto.length === 0 &&
        (declaracoes(r.corpo)['min-height'] || []).some(function (v) { return minAltura(v) >= 44; });
    });
  };
  const problemas = [];
  regrasNovas.forEach(function (r) {
    r.seletor.split(',').map(function (s) { return s.trim(); }).forEach(function (sel) {
      if (/[:\[]/.test(sel.split(/\s+/).pop())) return; // estados, atributos e pseudo-elementos
      const ultimo = sel.split(/[\s>+~]+/).pop();
      const tag = (/^[a-z]+/.exec(ultimo) || [''])[0];
      const classes = (ultimo.match(/\.[\w-]+/g) || []).map(function (c) { return c.slice(1); });
      const interativo = ['input', 'textarea', 'select', 'button', 'a'].indexOf(tag) !== -1 ||
        classes.some(function (c) { return /^(btn|link-btn)/.test(c) || /toggle$/.test(c); });
      if (!interativo) return;
      // Exceção: .aceite__rotulo input é a caixa de marcar (24 px) dentro de .aceite__rotulo,
      // cujo rótulo inteiro é clicável e tem min-height var(--alvo-minimo) (verificado abaixo).
      if (sel === '.aceite__rotulo input') return;
      // Modificadores de .btn (ex.: .btn--grande) herdam o min-height do .btn de base.
      if (classes.some(baseOk)) return;
      const mh = declaracoes(r.corpo)['min-height'];
      if (!mh || !(minAltura(mh[0]) >= 44)) {
        problemas.push('  css/styles.css:' + linhaDe(css, r.indice) + '  ' + sel + ' sem min-height >= 44px (valor: ' + (mh ? mh[0] : 'ausente') + ')');
      }
    });
  });
  const rotulo = regrasNovas.find(function (r) { return r.seletor === '.aceite__rotulo'; });
  assert.ok(rotulo && minAltura((declaracoes(rotulo.corpo)['min-height'] || [''])[0]) >= 44, '.aceite__rotulo deve ter min-height >= 44px (área de toque do aceite)');
  assert.equal(problemas.length, 0, 'Alvos de toque menores que 44 px:\n' + problemas.join('\n'));
});

test('9d. CSS: contraste dos pares de tokens (texto >= 4,5:1; borda e foco >= 3:1) (R11.5)', function () {
  const pares = [
    // [primeiro plano, fundo, mínimo, onde é usado]
    ['--texto', '--superficie', 4.5, 'texto em cartões'],
    ['--texto', '--campo-fundo', 4.5, 'texto digitado nos campos'],
    ['--texto', '--info-fundo', 4.5, 'faixa de abertura'],
    ['--texto', '--aviso-fundo', 4.5, 'aviso de protótipo'],
    ['--texto', '--erro-fundo', 4.5, 'mensagem de falha'],
    ['--texto', '--creme', 4.5, 'texto sobre a página'],
    ['--texto', '--campo-fundo-desabilitado', 4.5, 'comentário e botão travados (Enviando e já enviado)'],
    ['--texto', '--sucesso-fundo', 4.5, 'agradecimento do comentário'],
    ['--texto-suave', '--superficie', 4.5, 'ajuda e legendas em cartões'],
    ['--texto-suave', '--creme', 4.5, 'ajuda e legendas sobre a página'],
    ['--texto-suave', '--campo-fundo', 4.5, 'placeholder'],
    ['--erro', '--erro-fundo', 4.5, 'texto de erro do campo'],
    ['--erro', '--superficie', 4.5, 'erro sobre cartão'],
    ['--link', '--superficie', 4.5, 'links e botões de texto em cartões'],
    ['--link', '--creme', 4.5, 'links e botões de texto sobre a página'],
    ['--link', '--erro-fundo', 4.5, 'links na mensagem de falha'],
    ['--campo-borda', '--campo-fundo', 3, 'borda do campo'],
    ['--campo-borda', '--creme', 3, 'borda do campo sobre a página'],
    ['--campo-borda-foco', '--campo-fundo', 3, 'borda do campo em foco'],
    ['--foco', '--superficie', 3, 'anel de foco sobre cartão'],
    ['--foco', '--creme', 3, 'anel de foco sobre a página'],
    ['--erro', '--campo-fundo', 3, 'borda do campo com erro']
  ];
  const falhas = [];
  pares.forEach(function (p) {
    // --creme e --branco são tokens de marca; os semânticos apontam para eles.
    const r = contraste(corDoToken(p[0]), corDoToken(p[1]));
    if (r < p[2]) falhas.push('  ' + p[0] + ' sobre ' + p[1] + ' = ' + r.toFixed(2) + ':1 (mínimo ' + p[2] + ':1) em ' + p[3]);
  });
  assert.equal(falhas.length, 0, 'Contraste abaixo do mínimo WCAG:\n' + falhas.join('\n'));
});

/* ------------------------------------------------------------------ */
/* Comentário opcional (resolved-feedback-comment)                     */
/* ------------------------------------------------------------------ */

// Pedaços de texto fixo de cada frase de FEEDBACK.textos, na mesma regra do teste 4:
// pedaços longos (>= 12) valem em qualquer lugar; textos curtos só valem se forem o texto inteiro.
function trechosDeFeedback() {
  const textos = carregarDados().FEEDBACK.textos;
  const lista = [];
  Object.keys(textos).forEach(function (chave) {
    const valor = textos[chave];
    if (typeof valor !== 'string') return;
    const comMarcador = /\{[A-Za-z]+\}/.test(valor);
    valor.split(/\{[A-Za-z]+\}/).map(function (s) { return s.trim(); }).filter(Boolean).forEach(function (trecho) {
      if (comMarcador && trecho.length < 12) return;
      lista.push({ chave: chave, trecho: trecho, longo: trecho.length >= 12 });
    });
  });
  return lista;
}

test('11. #form-feedback: todo texto vem de data-texto-feedback e toda chave existe em FEEDBACK.textos (R13.1)', function () {
  const textos = carregarDados().FEEDBACK.textos;
  const problemas = [];
  const dentro = function (t) { return t.ancestrais.some(function (a) { return a.attrs.id === 'form-feedback'; }); };
  const atributosDeTexto = ['placeholder', 'title', 'alt', 'aria-label', 'value'];
  let formEncontrado = false;
  tokensHtml.forEach(function (t) {
    if (t.tipo === 'abre' && t.attrs.id === 'form-feedback') formEncontrado = true;
    if (t.tipo === 'texto' && dentro(t) && /\S/.test(t.texto)) {
      problemas.push('  index.html:' + t.linha + '  texto escrito direto: "' + t.texto.trim() + '"');
    }
    if (t.tipo === 'abre' && (dentro(t) || t.attrs.id === 'form-feedback')) {
      atributosDeTexto.forEach(function (nome) {
        if (nome in t.attrs && t.attrs[nome] !== '') problemas.push('  index.html:' + t.linha + '  <' + t.tag + '> com ' + nome + '="' + t.attrs[nome] + '" (texto fora de data.js)');
      });
    }
    if (t.tipo === 'abre' && 'data-texto-feedback' in t.attrs) {
      const v = textos[t.attrs['data-texto-feedback']];
      if (typeof v !== 'string' || v.trim() === '') problemas.push('  index.html:' + t.linha + '  data-texto-feedback="' + t.attrs['data-texto-feedback'] + '" sem texto em FEEDBACK.textos');
      if (!dentro(t)) problemas.push('  index.html:' + t.linha + '  data-texto-feedback fora de #form-feedback');
    }
  });
  assert.ok(formEncontrado, '#form-feedback não encontrado em index.html');
  assert.equal(problemas.length, 0, 'Texto do feedback escrito em index.html. Use FEEDBACK.textos e data-texto-feedback:\n' + problemas.join('\n'));
});

test('11b. Nenhuma frase de FEEDBACK.textos escrita em index.html, js/app.js, js/chamado.js nem js/feedback.js (R13.1)', function () {
  const trechos = trechosDeFeedback();
  assert.ok(trechos.length > 0, 'FEEDBACK.textos sem texto algum para comparar');
  const problemas = [];
  const casa = function (valor, t) { return t.longo ? valor.indexOf(t.trecho) !== -1 : valor.trim() === t.trecho; };

  ['js/app.js', 'js/chamado.js', 'js/feedback.js'].forEach(function (rel) {
    fonte[rel].analise.literais.forEach(function (lit) {
      trechos.forEach(function (t) {
        if (casa(lit.valor, t)) problemas.push('  ' + rel + ':' + lit.linha + '  repete FEEDBACK.textos.' + t.chave + ': "' + lit.valor.slice(0, 70) + '"');
      });
    });
  });
  tokensHtml.forEach(function (t) {
    const valores = [];
    if (t.tipo === 'texto') valores.push(t.texto);
    if (t.tipo === 'abre') Object.keys(t.attrs).forEach(function (k) { if (k !== 'data-texto-feedback') valores.push(t.attrs[k]); });
    valores.forEach(function (v) {
      trechos.forEach(function (tr) {
        if (casa(v, tr)) problemas.push('  index.html:' + t.linha + '  repete FEEDBACK.textos.' + tr.chave + ': "' + v.trim().slice(0, 70) + '"');
      });
    });
  });
  assert.equal(problemas.length, 0, 'Frase do feedback escrita fora de js/data.js:\n' + problemas.join('\n'));
});

test('11c. Tela_de_Resolvido mantém h1, h2 "Como foi a ajuda?" e links finais (R1, R14.2)', function () {
  const secao = /<section\b[^>]*\bid="view-resolvido"[\s\S]*?<\/section>/.exec(html);
  assert.ok(secao, '#view-resolvido ausente');
  const s = secao[0];
  assert.match(s, /<h1\b[^>]*\bid="titulo-resolvido"[^>]*>\s*Que bom! Seu café está de volta\.\s*<\/h1>/, 'h1 da Tela_de_Resolvido mudou');
  assert.match(s, /<h2\b[^>]*\bid="titulo-aval"[^>]*>\s*Como foi a ajuda\?\s*<\/h2>/, 'h2 "Como foi a ajuda?" mudou');
  assert.match(s, /<a\b[^>]*\bhref="#\/problemas"[^>]*>\s*Tenho outro problema\s*<\/a>/, 'Link "Tenho outro problema" mudou');
  assert.match(s, /<a\b[^>]*\bhref="#\/"[^>]*>\s*Voltar ao início\s*<\/a>/, 'Link "Voltar ao início" mudou');
  // O h2 fica fora do formulário (o formulário vem depois das estrelas).
  assert.ok(s.indexOf('id="titulo-aval"') < s.indexOf('id="form-feedback"'), 'O formulário deve vir depois do h2 e das estrelas');
});

test('11d. CSS do feedback: bloco novo depois do marcador, sem transição, fonte do campo 16 px e alvos de 44 px (R12)', function () {
  assert.ok(INICIO_NOVO !== -1, 'Marcador dos blocos novos não encontrado em css/styles.css');
  // O :root só declara o token e fica fora do bloco novo, por definição.
  const doFeedback = function (r) {
    return r.seletor !== ':root' && (/feedback|campo-fundo-desabilitado/.test(r.seletor + r.corpo) || /textarea:disabled|textarea\[readonly\]/.test(r.seletor));
  };
  const todas = regrasCss.filter(doFeedback);
  const novas = regrasNovas.filter(doFeedback);
  ['.feedback', '.feedback__agradecimento', '.feedback .btn[disabled]'].forEach(function (sel) {
    assert.ok(todas.some(function (r) { return r.seletor === sel; }), 'Regra ' + sel + ' ausente de css/styles.css');
    assert.ok(novas.some(function (r) { return r.seletor === sel; }), 'Regra ' + sel + ' deve ficar depois do marcador dos blocos novos');
  });
  assert.equal(todas.length, novas.length, 'Há regra do feedback antes do marcador dos blocos novos: ' +
    todas.filter(function (r) { return novas.indexOf(r) === -1; }).map(function (r) { return r.seletor; }).join(' | '));

  const problemas = [];
  novas.forEach(function (r) {
    Object.keys(declaracoes(r.corpo)).forEach(function (nome) {
      if (/^(transition|animation)(-|$)/.test(nome) || nome === 'scroll-behavior') problemas.push('  ' + r.seletor + ' { ' + nome + ' }');
    });
  });
  assert.equal(problemas.length, 0, 'Bloco do feedback não pode ter transição nem animação:\n' + problemas.join('\n'));

  // Fonte do campo: alguma regra nova de textarea define font-size >= 1rem, e nenhuma define menos.
  const regrasTextarea = regrasNovas.filter(function (r) { return /(^|[\s>+~,])textarea(?![\w-])/.test(r.seletor) && declaracoes(r.corpo)['font-size']; });
  assert.ok(regrasTextarea.length > 0, 'Nenhuma regra nova define font-size para textarea');
  regrasTextarea.forEach(function (r) {
    assert.ok(emPx(declaracoes(r.corpo)['font-size'][0]) >= 16, r.seletor + ': font-size do campo abaixo de 16 px');
  });

  // Alvos de 44 px: o botão do formulário usa .btn (min-height >= 44) e o token mínimo é >= 44 px.
  const btn = regrasCss.find(function (r) { return r.seletor === '.btn' && r.contexto.length === 0; });
  assert.ok(btn && emPx((declaracoes(btn.corpo)['min-height'] || [''])[0]) >= 44, '.btn deve ter min-height >= 44px');
  assert.ok(emPx(resolverToken('var(--alvo-minimo)')) >= 44, '--alvo-minimo deve ser >= 44px');
  assert.match(html, /<button\b[^>]*\bid="btn-enviar-comentario"[^>]*\bclass="btn"|<button\b[^>]*\bclass="btn"[^>]*\bid="btn-enviar-comentario"/, 'O botão de enviar o comentário deve usar a classe .btn');
  assert.ok('--campo-fundo-desabilitado' in TOKENS, 'Token --campo-fundo-desabilitado ausente do :root');
});

test('10. node tests/verificar-protegidos.js --conferir retorna 0 (R12.5)', function () {
  const r = spawnSync(process.execPath, [path.join(__dirname, 'verificar-protegidos.js'), '--conferir'], { cwd: RAIZ, encoding: 'utf8' });
  assert.equal(r.status, 0, 'Arquivos protegidos alterados (material/, imagens originais ou .glb):\n' + (r.stderr || '') + (r.stdout || ''));
});
