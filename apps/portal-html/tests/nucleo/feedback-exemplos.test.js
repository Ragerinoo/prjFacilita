'use strict';
// Testes de exemplo e de borda do núcleo do feedback (js/feedback.js), sem fast-check.
// Cobrem: códigos de validação, normalização, limite de 500 caracteres,
// tempo limite (com e sem AbortController), leitura tolerante do repositório
// e a independência entre API_FEEDBACK_URL e API_CHAMADOS_URL.
const test = require('node:test');
const assert = require('node:assert/strict');

const {
  criarFetchFalso,
  criarStorageFalso,
  criarAbortControllerFalso,
  criarTemporizadorFalso
} = require('../falsos.js');
const base = require('../../js/chamado.js');
const nucleo = require('../../js/feedback.js').criar(base);

/* ==========================================================
 * Apoio comum
 * ========================================================== */

const URL_FEEDBACK = 'https://api.exemplo.com/feedbacks';
const URL_CHAMADOS = 'https://api.exemplo.com/chamados';
const CHAVE = 'tres-autoatendimento-feedbacks';

const PAYLOAD = {
  versaoContrato: '1',
  chaveIdempotencia: 'chave-exemplo-1',
  enviadoEm: '2026-10-13T14:32:10.123-03:00',
  comentario: 'ótimo',
  nota: 5,
  problemaId: 1,
  modelo: 'Luna'
};

/* ==========================================================
 * 1. Validação e normalização do comentário (Req. 4.1, 5.2, 5.3)
 * ========================================================== */

test('validarComentario: vazio, só espaços e ausentes dão "vazio"', () => {
  assert.equal(nucleo.validarComentario(''), 'vazio');
  assert.equal(nucleo.validarComentario('   \n\t  '), 'vazio');
  assert.equal(nucleo.validarComentario(null), 'vazio');
  assert.equal(nucleo.validarComentario(undefined), 'vazio');
});

test('validarComentario: mais de 500 caracteres dá "tamanho"', () => {
  assert.equal(nucleo.validarComentario('a'.repeat(501)), 'tamanho');
  assert.equal(nucleo.validarComentario('a'.repeat(5000)), 'tamanho');
});

test('validarComentario: texto comum é válido (null)', () => {
  assert.equal(nucleo.validarComentario('ótimo'), null);
  assert.equal(nucleo.validarComentario('a'), null);
});

test('normalizarComentario: "  ótimo \\n" vira "ótimo"', () => {
  assert.equal(nucleo.normalizarComentario('  ótimo \n'), 'ótimo');
});

test('normalizarComentario: preserva espaços e quebras internas', () => {
  assert.equal(nucleo.normalizarComentario('  a  b\nc \n'), 'a  b\nc');
});

test('limite: 500 caracteres é aceito e 501 é recusado', () => {
  assert.equal(nucleo.LIMITES.comentario.max, 500);
  assert.equal(nucleo.validarComentario('x'.repeat(500)), null);
  assert.equal(nucleo.validarComentario('x'.repeat(501)), 'tamanho');
});

test('limite: o limite vale depois do trim (500 com espaços nas pontas é aceito)', () => {
  assert.equal(nucleo.validarComentario('  ' + 'x'.repeat(500) + ' \n'), null);
});

test('limitarComentario: mantém só os primeiros 500 caracteres', () => {
  assert.equal(nucleo.limitarComentario('y'.repeat(501)).length, 500);
  assert.equal(nucleo.limitarComentario('y'.repeat(500)).length, 500);
});

/* ==========================================================
 * 2. Tempo limite em Modo_API (Req. 10.10)
 * ========================================================== */

test('tempo limite: fetch que nunca responde com temporizador falso → "timeout"', async () => {
  const fetch = criarFetchFalso({ semResposta: true });
  const temporizador = criarTemporizadorFalso();
  const AbortController = criarAbortControllerFalso();
  const ponto = nucleo.criarPontoDeIntegracao({
    config: { API_FEEDBACK_URL: URL_FEEDBACK, TIMEOUT_FEEDBACK_MS: 5000 },
    fetch,
    AbortController,
    setTimeout: temporizador.setTimeout,
    clearTimeout: temporizador.clearTimeout,
    storage: criarStorageFalso()
  });

  let resultado = null;
  const promessa = ponto.enviar(PAYLOAD).then((r) => {
    resultado = r;
    return r;
  });

  temporizador.avancar(4999);
  await Promise.resolve();
  assert.equal(resultado, null, 'antes do limite ainda não há resultado');
  assert.equal(fetch.chamadas.length, 1);
  assert.equal(AbortController.instancias[0].signal.aborted, false);

  temporizador.avancar(1);
  assert.deepEqual(await promessa, { ok: false, categoria: 'timeout' });
  assert.equal(AbortController.instancias[0].signal.aborted, true);
});

test('tempo limite: sem TIMEOUT_FEEDBACK_MS válido usa o padrão de 10000 ms', async () => {
  const fetch = criarFetchFalso({ semResposta: true });
  const temporizador = criarTemporizadorFalso();
  const ponto = nucleo.criarPontoDeIntegracao({
    config: { API_FEEDBACK_URL: URL_FEEDBACK },
    fetch,
    AbortController: criarAbortControllerFalso(),
    setTimeout: temporizador.setTimeout,
    clearTimeout: temporizador.clearTimeout,
    storage: criarStorageFalso()
  });

  const promessa = ponto.enviar(PAYLOAD);
  temporizador.avancar(10000);
  assert.deepEqual(await promessa, { ok: false, categoria: 'timeout' });
});

test('tempo limite: sem AbortController no ambiente usa a corrida com temporizador', async () => {
  const fetch = criarFetchFalso({ semResposta: true });
  const temporizador = criarTemporizadorFalso();
  const ponto = nucleo.criarPontoDeIntegracao({
    config: { API_FEEDBACK_URL: URL_FEEDBACK, TIMEOUT_FEEDBACK_MS: 3000 },
    fetch,
    AbortController: undefined,
    setTimeout: temporizador.setTimeout,
    clearTimeout: temporizador.clearTimeout,
    storage: criarStorageFalso()
  });

  const promessa = ponto.enviar(PAYLOAD);
  assert.equal(fetch.chamadas.length, 1);
  assert.equal(fetch.chamadas[0].init.signal, undefined, 'sem AbortController não há sinal');
  assert.equal(temporizador.pendentes(), 1);

  temporizador.avancar(3000);
  assert.deepEqual(await promessa, { ok: false, categoria: 'timeout' });
});

/* ==========================================================
 * 3. Leitura tolerante do repositório (Req. 9.6)
 * ========================================================== */

const FORMATOS_DE_LIXO = [
  ['texto que não é JSON', 'isto não é json {'],
  ['JSON que é objeto, não lista', '{"comentario":"x"}'],
  ['JSON que é texto simples', '"só um texto"'],
  ['lista com itens que não são objetos', '[1, "a", null, true, [1, 2]]'],
  ['texto vazio', '']
];

for (const [descricao, lixo] of FORMATOS_DE_LIXO) {
  test('repositório tolerante: ' + descricao + ' na chave vira lista vazia e o envio funciona', async () => {
    const storage = criarStorageFalso({ inicial: { [CHAVE]: lixo } });
    const fetch = criarFetchFalso({ status: 200 });
    const ponto = nucleo.criarPontoDeIntegracao({ config: {}, fetch, storage });

    assert.deepEqual(base.lerLista(storage.getItem(CHAVE)), []);

    const resultado = await ponto.enviar(PAYLOAD);
    assert.deepEqual(resultado, { ok: true, modo: 'prototipo' });
    assert.equal(fetch.chamadas.length, 0);

    const gravado = JSON.parse(storage.instantaneo()[CHAVE]);
    assert.deepEqual(gravado, [PAYLOAD]);
  });
}

test('repositório tolerante: descarta itens que não são objetos e mantém os registros bons', async () => {
  const anterior = Object.assign({}, PAYLOAD, { chaveIdempotencia: 'chave-antiga' });
  const storage = criarStorageFalso({ inicial: { [CHAVE]: JSON.stringify([1, anterior, null, 'x']) } });
  const ponto = nucleo.criarPontoDeIntegracao({ config: {}, fetch: criarFetchFalso({ status: 200 }), storage });

  const resultado = await ponto.enviar(PAYLOAD);
  assert.deepEqual(resultado, { ok: true, modo: 'prototipo' });
  assert.deepEqual(JSON.parse(storage.instantaneo()[CHAVE]), [anterior, PAYLOAD]);
});

/* ==========================================================
 * 4. Seleção do modo só por API_FEEDBACK_URL (Req. 10.5, 10.6)
 * ========================================================== */

test('sem API_FEEDBACK_URL mas com API_CHAMADOS_URL válida: fetch nunca é chamado', async () => {
  const fetch = criarFetchFalso({ status: 200 });
  const storage = criarStorageFalso();
  const config = { API_CHAMADOS_URL: URL_CHAMADOS };
  const ponto = nucleo.criarPontoDeIntegracao({
    config,
    fetch,
    AbortController: criarAbortControllerFalso(),
    storage
  });

  assert.equal(nucleo.modoDoFeedback(config), 'prototipo');
  const resultado = await ponto.enviar(PAYLOAD);

  assert.deepEqual(resultado, { ok: true, modo: 'prototipo' });
  assert.equal(fetch.chamadas.length, 0, 'fetch não pode ser chamado em Modo_Prototipo');
  assert.deepEqual(JSON.parse(storage.instantaneo()[CHAVE]), [PAYLOAD]);
});

test('API_FEEDBACK_URL vazia ou inválida com API_CHAMADOS_URL válida segue em Modo_Prototipo', () => {
  assert.equal(nucleo.modoDoFeedback({ API_FEEDBACK_URL: '', API_CHAMADOS_URL: URL_CHAMADOS }), 'prototipo');
  assert.equal(nucleo.modoDoFeedback({ API_FEEDBACK_URL: 'ftp://x/y', API_CHAMADOS_URL: URL_CHAMADOS }), 'prototipo');
});

test('API_FEEDBACK_URL https válida seleciona Modo_API mesmo sem API_CHAMADOS_URL', async () => {
  const fetch = criarFetchFalso({ status: 201 });
  const ponto = nucleo.criarPontoDeIntegracao({
    config: { API_FEEDBACK_URL: URL_FEEDBACK },
    fetch,
    AbortController: criarAbortControllerFalso(),
    setTimeout: criarTemporizadorFalso().setTimeout,
    clearTimeout: criarTemporizadorFalso().clearTimeout,
    storage: criarStorageFalso()
  });

  assert.deepEqual(await ponto.enviar(PAYLOAD), { ok: true, modo: 'api' });
  assert.equal(fetch.chamadas.length, 1);
  assert.equal(fetch.chamadas[0].url, URL_FEEDBACK);
});
