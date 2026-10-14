#!/usr/bin/env node
// Verificação pós-build (não é teste do Vitest e não entra no bundle).
//
// Prova que a biblioteca de gráficos (Recharts) fica fora do que o site carrega
// de forma estática (Req 15.5 e 25.17 da spec insights-gestor, decisão D11):
//   1. nenhum chunk com a marca `recharts` está no fecho dos `imports` estáticos
//      de `index.html` (entrada do site, rotas públicas do Consumidor);
//   2. nenhum chunk com a marca está no fecho dos `imports` estáticos de
//      `src/cs/Dashboard.tsx` (rota índice `/cs`, inclui a aba "Chamados em foco");
//   3. a biblioteca existe, e está no fecho de `src/cs/insights/ConteudoInsights.tsx`
//      (carregado por `import()` no Dashboard e de forma estática em `/cs/insights`).
//
// Uso (em apps/web):
//   npm run build -- --manifest
//   node scripts/verificar-chunks.mjs [pasta-do-dist]
//
// Sai com código 0 se tudo certo e 1 se alguma regra falhar ou se não der para verificar.

import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const MARCA = "recharts";
const ENTRADA_SITE = "index.html";
const ENTRADA_DASHBOARD = "src/cs/Dashboard.tsx";
const ENTRADA_INSIGHTS = "src/cs/insights/ConteudoInsights.tsx";

const raiz = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const dist = resolve(process.argv[2] ?? join(raiz, "dist"));
const caminhoManifest = join(dist, ".vite", "manifest.json");

function falhar(mensagem) {
  process.stderr.write(`verificar-chunks: ${mensagem}\n`);
  process.exit(1);
}

if (!existsSync(caminhoManifest)) {
  falhar(
    `manifest não encontrado em ${caminhoManifest}. Rode antes: npm run build -- --manifest`,
  );
}

let manifest;
try {
  manifest = JSON.parse(readFileSync(caminhoManifest, "utf8"));
} catch (erro) {
  falhar(`manifest inválido (${erro instanceof Error ? erro.message : erro})`);
}

/** Chaves do manifest cujo `file` contém a marca da biblioteca. */
function chavesComMarca() {
  const chaves = new Set();
  for (const [chave, chunk] of Object.entries(manifest)) {
    if (!chunk.file || !chunk.file.endsWith(".js")) continue;
    const arquivo = join(dist, chunk.file);
    if (!existsSync(arquivo)) {
      falhar(`arquivo do chunk ausente em dist: ${chunk.file} (chave ${chave})`);
    }
    if (readFileSync(arquivo, "utf8").includes(MARCA)) chaves.add(chave);
  }
  return chaves;
}

/** Fecho dos `imports` estáticos (inclui a própria chave); `import()` não entra. */
function fechoEstatico(inicio) {
  const visitadas = new Set();
  const pilha = [inicio];
  while (pilha.length > 0) {
    const chave = pilha.pop();
    if (visitadas.has(chave)) continue;
    const chunk = manifest[chave];
    if (!chunk) falhar(`o manifest referencia a chave inexistente "${chave}"`);
    visitadas.add(chave);
    for (const dependencia of chunk.imports ?? []) pilha.push(dependencia);
  }
  return visitadas;
}

function exigirEntrada(chave) {
  if (!manifest[chave]) {
    falhar(
      `a entrada "${chave}" não está no manifest; não dá para verificar o isolamento. ` +
        `Chaves disponíveis: ${Object.keys(manifest).join(", ")}`,
    );
  }
}

for (const chave of [ENTRADA_SITE, ENTRADA_DASHBOARD, ENTRADA_INSIGHTS]) exigirEntrada(chave);

const comMarca = chavesComMarca();
if (comMarca.size === 0) {
  falhar(
    `nenhum chunk contém "${MARCA}"; a marca pode ter mudado ou o gráfico saiu do build, ` +
      "então a verificação não prova nada.",
  );
}

const erros = [];

for (const entrada of [ENTRADA_SITE, ENTRADA_DASHBOARD]) {
  const vazados = [...fechoEstatico(entrada)].filter((chave) => comMarca.has(chave));
  for (const chave of vazados) {
    erros.push(
      `"${MARCA}" está no chunk ${manifest[chave].file} (${chave}), que é carregado de forma ` +
        `estática por ${entrada}`,
    );
  }
}

const fechoInsights = fechoEstatico(ENTRADA_INSIGHTS);
if (![...comMarca].some((chave) => fechoInsights.has(chave))) {
  erros.push(
    `"${MARCA}" existe em ${[...comMarca].map((c) => manifest[c].file).join(", ")}, ` +
      `mas não no fecho estático de ${ENTRADA_INSIGHTS}`,
  );
}

if (erros.length > 0) {
  for (const erro of erros) process.stderr.write(`verificar-chunks: ${erro}\n`);
  process.exit(1);
}

process.stdout.write(
  `verificar-chunks: ok. "${MARCA}" só em ${[...comMarca].map((c) => manifest[c].file).join(", ")}; ` +
    `fora de ${ENTRADA_SITE} e de ${ENTRADA_DASHBOARD}, dentro de ${ENTRADA_INSIGHTS}.\n`,
);
