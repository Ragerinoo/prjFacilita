'use strict';
/**
 * Runner dos testes de interface (Edge headless). Somente desenvolvimento.
 *
 *   node tests/ui/rodar.js                       roda todos os tests/ui/cenarios/*.js
 *   node tests/ui/rodar.js 00-fumaca             roda um arquivo (nome, nome.test.js ou caminho)
 *   node tests/ui/rodar.js --relatorio=C:\x.txt  grava o relatório em outro caminho
 *
 * Cada arquivo roda em processo próprio, um por vez (--test-concurrency=1), com
 * o node:test. O relatório legível vai para o stdout e para o arquivo
 * <pasta temporária>/tres-ui-relatorio.txt (o caminho é impresso no fim).
 * O código de saída é 0 só se todos passarem.
 *
 * Ao final varre e encerra qualquer Edge que ESTE conjunto de testes tenha deixado
 * (identificado pelo perfil temporário "tres-ui-edge-"); não toca nos outros Edge.
 */
const { spawn, spawnSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { PREFIXO_PERFIL } = require('./cdp');

const PASTA_CENARIOS = path.join(__dirname, 'cenarios');
const SEM_ANSI = /\u001b\[[0-9;]*[A-Za-z]/g;

function resolverArquivos(pedidos) {
  const todos = fs.existsSync(PASTA_CENARIOS)
    ? fs.readdirSync(PASTA_CENARIOS).filter((f) => f.endsWith('.js')).sort()
    : [];
  if (!pedidos.length) return todos.map((f) => path.join(PASTA_CENARIOS, f));
  return pedidos.map((p) => {
    const candidatos = [
      p,
      path.join(PASTA_CENARIOS, p),
      path.join(PASTA_CENARIOS, p + '.js'),
      path.join(PASTA_CENARIOS, p + '.test.js')
    ];
    const achado = candidatos.find((c) => fs.existsSync(c) && fs.statSync(c).isFile());
    if (!achado) {
      throw new Error('Cenário não encontrado: "' + p + '". Disponíveis: ' + (todos.join(', ') || '(nenhum)'));
    }
    return path.resolve(achado);
  });
}

/** Encerra só os Edge cujo perfil começa com o prefixo de teste. Devolve quantos matou. */
function varrerEdgesOrfaos() {
  if (process.platform !== 'win32') return 0;
  const cmd =
    "$p = Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | Where-Object { $_.CommandLine -like '*" +
    PREFIXO_PERFIL + "*' }; " +
    "$n = 0; foreach ($x in $p) { Stop-Process -Id $x.ProcessId -Force -ErrorAction SilentlyContinue; $n++ }; Write-Output $n";
  const r = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', cmd], { encoding: 'utf8', windowsHide: true, timeout: 20000 });
  const n = parseInt(String(r.stdout || '').trim(), 10);
  return Number.isFinite(n) ? n : 0;
}

function limparPerfis() {
  let removidos = 0;
  for (const nome of fs.readdirSync(os.tmpdir())) {
    if (!nome.startsWith(PREFIXO_PERFIL)) continue;
    try { fs.rmSync(path.join(os.tmpdir(), nome), { recursive: true, force: true, maxRetries: 5, retryDelay: 200 }); removidos++; } catch (e) { /* em uso */ }
  }
  return removidos;
}

async function principal() {
  const args = process.argv.slice(2);
  const opcaoRelatorio = args.find((a) => a.startsWith('--relatorio='));
  const relatorio = opcaoRelatorio ? opcaoRelatorio.slice('--relatorio='.length) : path.join(os.tmpdir(), 'tres-ui-relatorio.txt');
  const pedidos = args.filter((a) => !a.startsWith('--'));

  let arquivos;
  try { arquivos = resolverArquivos(pedidos); } catch (e) { console.error(e.message); return 2; }
  if (!arquivos.length) { console.error('Nenhum cenário em ' + PASTA_CENARIOS); return 2; }

  const inicio = Date.now();
  const linhas = [];
  const registrar = (texto) => {
    const limpo = String(texto).replace(SEM_ANSI, '');
    linhas.push(limpo);
    process.stdout.write(limpo);
  };
  registrar('Testes de interface (Edge headless) - ' + new Date().toISOString() + '\n');
  registrar('Arquivos: ' + arquivos.map((a) => path.basename(a)).join(', ') + '\n\n');

  const codigo = await new Promise((resolve) => {
    const filho = spawn(
      process.execPath,
      ['--test', '--test-concurrency=1', '--test-reporter=spec', ...arquivos],
      { stdio: ['ignore', 'pipe', 'pipe'], env: { ...process.env, NO_COLOR: '1', FORCE_COLOR: '0' }, windowsHide: true }
    );
    filho.stdout.on('data', registrar);
    filho.stderr.on('data', registrar);
    filho.on('error', (e) => { registrar('Falha ao iniciar o node --test: ' + e.message + '\n'); resolve(1); });
    filho.on('close', (c) => resolve(c === null ? 1 : c));
  });

  const orfaos = varrerEdgesOrfaos();
  const perfis = limparPerfis();
  registrar('\nLimpeza: ' + orfaos + ' Edge de teste órfão(s) encerrado(s), ' + perfis + ' perfil(is) temporário(s) removido(s).\n');
  registrar('Resultado: ' + (codigo === 0 ? 'OK' : 'FALHOU (código ' + codigo + ')') + ' em ' + ((Date.now() - inicio) / 1000).toFixed(1) + ' s\n');
  try {
    fs.writeFileSync(relatorio, linhas.join(''), 'utf8');
    process.stdout.write('Relatório gravado em: ' + relatorio + '\n');
  } catch (e) {
    process.stdout.write('Não consegui gravar o relatório em ' + relatorio + ': ' + e.message + '\n');
  }
  return codigo;
}

principal().then((c) => { process.exitCode = c; }, (e) => { console.error(e); process.exitCode = 1; });
