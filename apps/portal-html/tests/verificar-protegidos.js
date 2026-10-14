'use strict';
// Verifica a integridade dos arquivos protegidos do projeto (somente leitura).
//
//   node tests/verificar-protegidos.js --gerar     grava tests/baseline-protegidos.json
//   node tests/verificar-protegidos.js --conferir  compara o estado atual com a linha de base
//
// Protegidos: tudo em material/ (recursivo), as cinco imagens originais em img/
// e o modelo 3D original em modelos3d/. Só módulos nativos do Node.

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const RAIZ = path.resolve(__dirname, '..');
const BASELINE = path.join(__dirname, 'baseline-protegidos.json');

const PASTAS_RECURSIVAS = ['material'];
const ARQUIVOS_FIXOS = [
  'img/LOV.png',
  'img/Luna.png',
  'img/Modo.png',
  'img/Passione.png',
  'img/TOUCH.png',
  'modelos3d/c0adab67d5fc6db5e82670d1271e4559.glb'
];

function relativo(abs) {
  return path.relative(RAIZ, abs).split(path.sep).join('/');
}

function listarRecursivo(dirAbs) {
  const saida = [];
  if (!fs.existsSync(dirAbs)) return saida;
  for (const entrada of fs.readdirSync(dirAbs, { withFileTypes: true })) {
    const abs = path.join(dirAbs, entrada.name);
    if (entrada.isDirectory()) saida.push(...listarRecursivo(abs));
    else if (entrada.isFile()) saida.push(abs);
  }
  return saida;
}

function hashArquivo(abs) {
  return crypto.createHash('sha256').update(fs.readFileSync(abs)).digest('hex');
}

// Lê o estado atual: { caminhoRelativo: sha256 } e a lista de fixos ausentes.
function lerEstadoAtual() {
  const arquivos = {};
  const ausentes = [];
  for (const pasta of PASTAS_RECURSIVAS) {
    for (const abs of listarRecursivo(path.join(RAIZ, pasta))) {
      arquivos[relativo(abs)] = hashArquivo(abs);
    }
  }
  for (const rel of ARQUIVOS_FIXOS) {
    const abs = path.join(RAIZ, rel);
    if (fs.existsSync(abs) && fs.statSync(abs).isFile()) arquivos[rel] = hashArquivo(abs);
    else ausentes.push(rel);
  }
  return { arquivos, ausentes };
}

function ordenar(obj) {
  const saida = {};
  Object.keys(obj).sort().forEach(function (k) { saida[k] = obj[k]; });
  return saida;
}

function gerar() {
  const { arquivos, ausentes } = lerEstadoAtual();
  if (ausentes.length) {
    process.stderr.write('Arquivos protegidos ausentes, linha de base não gravada:\n  ' + ausentes.join('\n  ') + '\n');
    return 1;
  }
  const conteudo = { algoritmo: 'sha256', arquivos: ordenar(arquivos) };
  fs.writeFileSync(BASELINE, JSON.stringify(conteudo, null, 2) + '\n', 'utf8');
  process.stdout.write('Linha de base gravada com ' + Object.keys(arquivos).length + ' arquivos em tests/baseline-protegidos.json\n');
  return 0;
}

function conferir() {
  if (!fs.existsSync(BASELINE)) {
    process.stderr.write('Linha de base não encontrada. Rode com --gerar primeiro.\n');
    return 1;
  }
  let base;
  try {
    base = JSON.parse(fs.readFileSync(BASELINE, 'utf8')).arquivos;
  } catch (e) {
    process.stderr.write('Linha de base ilegível.\n');
    return 1;
  }
  if (!base || typeof base !== 'object') {
    process.stderr.write('Linha de base inválida.\n');
    return 1;
  }

  const { arquivos: atual } = lerEstadoAtual();
  const alterados = [];
  const sumiram = [];
  const novos = [];

  Object.keys(base).forEach(function (rel) {
    if (!(rel in atual)) sumiram.push(rel);
    else if (atual[rel] !== base[rel]) alterados.push(rel);
  });
  // Arquivo novo só é problema dentro de material/.
  Object.keys(atual).forEach(function (rel) {
    if (!(rel in base) && rel.indexOf('material/') === 0) novos.push(rel);
  });

  if (!alterados.length && !sumiram.length && !novos.length) {
    process.stdout.write('OK: ' + Object.keys(base).length + ' arquivos protegidos intactos.\n');
    return 0;
  }
  if (alterados.length) process.stderr.write('Hash alterado:\n  ' + alterados.join('\n  ') + '\n');
  if (sumiram.length) process.stderr.write('Arquivo ausente:\n  ' + sumiram.join('\n  ') + '\n');
  if (novos.length) process.stderr.write('Arquivo novo em material/:\n  ' + novos.join('\n  ') + '\n');
  return 1;
}

function main() {
  const modo = process.argv[2];
  if (modo === '--gerar') return gerar();
  if (modo === '--conferir') return conferir();
  process.stderr.write('Uso: node tests/verificar-protegidos.js --gerar | --conferir\n');
  return 2;
}

process.exitCode = main();
