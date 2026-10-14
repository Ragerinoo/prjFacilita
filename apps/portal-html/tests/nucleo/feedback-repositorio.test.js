'use strict';
// Testes de propriedade do Repositorio_de_Feedbacks (Modo_Prototipo) em js/feedback.js.
// Cobrem as propriedades 6, 7, 8, 9, 11 e 14 do design (resolved-feedback-comment).
// O storage e o fetch são falsos (tests/falsos.js); em Modo_Prototipo o fetch nunca é chamado.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { fc, payloadFeedback: payloadGerado, listaDeFeedbacks: listaGerada } = require('../geradores.js');
const {
  criarFetchFalso,
  criarStorageFalso,
  criarAbortControllerFalso,
  criarTemporizadorFalso
} = require('../falsos.js');

const base = require(path.join(__dirname, '..', '..', 'js', 'chamado.js'));
const feedback = require(path.join(__dirname, '..', '..', 'js', 'feedback.js')).criar(base);

/* ==========================================================
 * Apoio comum
 * ========================================================== */

const CHAVE_FEEDBACKS = 'tres-autoatendimento-feedbacks';
const CHAVE_EVENTOS = 'tres-autoatendimento-eventos';
const CHAVE_CHAMADOS = 'tres-autoatendimento-chamados';
const URL_API = 'https://exemplo.com.br/api/feedbacks';
const NUM_RUNS = 100;

// Ponto de integração com todos os dublês. `url` vazia = Modo_Prototipo.
function montarAmbiente(storage, url, comportamentoFetch) {
  const fetchFalso = criarFetchFalso(comportamentoFetch || { status: 201 });
  const temporizador = criarTemporizadorFalso();
  const ponto = feedback.criarPontoDeIntegracao({
    config: { API_FEEDBACK_URL: url, TIMEOUT_FEEDBACK_MS: 10000 },
    fetch: fetchFalso,
    AbortController: criarAbortControllerFalso(),
    setTimeout: temporizador.setTimeout,
    clearTimeout: temporizador.clearTimeout,
    storage
  });
  return { ponto, fetchFalso };
}

function storageCom(inicial) {
  return criarStorageFalso({ inicial: inicial || {} });
}

function lerGravado(storage) {
  return JSON.parse(storage.getItem(CHAVE_FEEDBACKS));
}

function ehObjetoSimples(x) {
  return x !== null && typeof x === 'object' && !Array.isArray(x);
}

// fast-check pode gerar objetos sem protótipo; o oráculo compara com o que volta do JSON.parse (protótipo comum).
const plano = (p) => Object.assign({}, p);
const payloadFeedback = payloadGerado.map(plano);
const listaDeFeedbacks = listaGerada.map((l) => l.map(plano));

// Payload cuja chave de idempotência não aparece na lista prévia.
const listaEPayload = fc
  .tuple(listaDeFeedbacks, payloadFeedback)
  .filter(([lista, p]) => lista.every((q) => q.chaveIdempotencia !== p.chaveIdempotencia));

/* ==========================================================
 * Property 6
 * ========================================================== */

test('Property 6: Ida e volta pelo Repositorio_de_Feedbacks', async () => {
  // Feature: resolved-feedback-comment, Property 6: Ida e volta pelo Repositorio_de_Feedbacks
  // **Validates: Requirements 9.1, 9.4, 9.5**
  await fc.assert(
    fc.asyncProperty(listaEPayload, async ([previa, payload]) => {
      const inicial = previa.length > 0 ? { [CHAVE_FEEDBACKS]: JSON.stringify(previa) } : {};
      const storage = storageCom(inicial);
      const { ponto, fetchFalso } = montarAmbiente(storage, '');

      const resultado = await ponto.enviar(payload);

      assert.deepEqual(resultado, { ok: true, modo: 'prototipo' });
      assert.equal(fetchFalso.chamadas.length, 0);

      const lista = lerGravado(storage);
      assert.ok(Array.isArray(lista));
      const ultimo = lista[lista.length - 1];
      assert.deepEqual(ultimo, payload);
      assert.deepEqual(Object.keys(ultimo).sort(), Object.keys(payload).sort());
      for (const campo of Object.keys(payload)) {
        assert.strictEqual(ultimo[campo], payload[campo], 'campo ' + campo);
      }
    }),
    { numRuns: NUM_RUNS }
  );
});

/* ==========================================================
 * Property 7
 * ========================================================== */

// Texto prévio da chave: ausente, vazio, JSON inválido, JSON que não é lista,
// lista só com itens que não são objetos e lista mista.
const JSON_INVALIDO = fc
  .string({ unit: 'binary', maxLength: 40 })
  .filter((s) => {
    try {
      JSON.parse(s);
      return false;
    } catch (e) {
      return true;
    }
  });
const itemQueNaoEhObjeto = fc.oneof(
  fc.constant(null),
  fc.integer(),
  fc.boolean(),
  fc.string({ maxLength: 10 }),
  fc.array(fc.integer(), { maxLength: 3 })
);
const textoPrevioDoRepositorio = fc.oneof(
  fc.constant(undefined),
  fc.constant(''),
  JSON_INVALIDO,
  fc.constantFrom('{}', 'null', '42', '"texto"', 'true', '{"a":1}'),
  fc.jsonValue().filter((v) => !Array.isArray(v)).map((v) => JSON.stringify(v)),
  fc.array(itemQueNaoEhObjeto, { maxLength: 6 }).map((l) => JSON.stringify(l)),
  fc.array(fc.oneof(itemQueNaoEhObjeto, payloadFeedback), { maxLength: 6 }).map((l) => JSON.stringify(l))
);

test('Property 7: Leitura tolerante do repositório', async () => {
  // Feature: resolved-feedback-comment, Property 7: Leitura tolerante do repositório
  // **Validates: Requirements 9.6**
  await fc.assert(
    fc.asyncProperty(textoPrevioDoRepositorio, payloadFeedback, async (texto, payload) => {
      const storage = storageCom(texto === undefined ? {} : { [CHAVE_FEEDBACKS]: texto });
      const { ponto, fetchFalso } = montarAmbiente(storage, '');

      // Oráculo: objetos simples de uma lista JSON válida; o resto é descartado.
      let mantidos = [];
      if (texto !== undefined) {
        try {
          const valor = JSON.parse(texto);
          if (Array.isArray(valor)) mantidos = valor.filter(ehObjetoSimples);
        } catch (e) {
          mantidos = [];
        }
      }

      const resultado = await ponto.enviar(payload);

      assert.deepEqual(resultado, { ok: true, modo: 'prototipo' });
      assert.equal(fetchFalso.chamadas.length, 0);
      const lista = lerGravado(storage);
      assert.deepEqual(lista, mantidos.concat([payload]));
      if (mantidos.length === 0) assert.deepEqual(lista, [payload]);
    }),
    { numRuns: NUM_RUNS }
  );
});

/* ==========================================================
 * Property 8
 * ========================================================== */

test('Property 8: Limite de 50 registros', async () => {
  // Feature: resolved-feedback-comment, Property 8: Limite de 50 registros
  // **Validates: Requirements 9.2**
  await fc.assert(
    fc.asyncProperty(listaEPayload, async ([previa, payload]) => {
      const inicial = previa.length > 0 ? { [CHAVE_FEEDBACKS]: JSON.stringify(previa) } : {};
      const storage = storageCom(inicial);
      const { ponto } = montarAmbiente(storage, '');

      const resultado = await ponto.enviar(payload);

      assert.deepEqual(resultado, { ok: true, modo: 'prototipo' });
      const lista = lerGravado(storage);
      assert.ok(lista.length <= 50);
      assert.deepEqual(lista[lista.length - 1], payload);
      // Os mais antigos saem; os demais mantêm a ordem.
      const esperado = previa.concat([payload]).slice(-50);
      assert.deepEqual(lista, esperado);
      if (previa.length >= 50) assert.equal(lista.length, 50);
    }),
    { numRuns: NUM_RUNS }
  );
});

/* ==========================================================
 * Property 9
 * ========================================================== */

test('Property 9: Idempotência por chave no repositório', async () => {
  // Feature: resolved-feedback-comment, Property 9: Idempotência por chave no repositório
  // **Validates: Requirements 9.8**
  await fc.assert(
    fc.asyncProperty(listaEPayload, fc.integer({ min: 1, max: 5 }), async ([previa, payload], vezes) => {
      const inicial = previa.length > 0 ? { [CHAVE_FEEDBACKS]: JSON.stringify(previa) } : {};
      const storage = storageCom(inicial);
      const { ponto, fetchFalso } = montarAmbiente(storage, '');

      for (let i = 0; i < vezes; i++) {
        const resultado = await ponto.enviar(payload);
        assert.deepEqual(resultado, { ok: true, modo: 'prototipo' });
      }

      const lista = lerGravado(storage);
      const comAChave = lista.filter((q) => q.chaveIdempotencia === payload.chaveIdempotencia);
      assert.equal(comAChave.length, 1);
      assert.deepEqual(comAChave[0], payload);
      // Uma única gravação, igual à de um envio só.
      assert.deepEqual(lista, previa.concat([payload]).slice(-50));
      assert.equal(storage.contar('setItem'), 1);
      assert.equal(fetchFalso.chamadas.length, 0);
    }),
    { numRuns: NUM_RUNS }
  );
});

/* ==========================================================
 * Property 11
 * ========================================================== */

// Conteúdo prévio das outras chaves: ausente ou qualquer texto.
const conteudoPrevio = fc.option(fc.string({ unit: 'binary', maxLength: 80 }), { nil: undefined });

test('Property 11: Armazenamento isolado', async () => {
  // Feature: resolved-feedback-comment, Property 11: Armazenamento isolado
  // **Validates: Requirements 9.3, 10.8**
  await fc.assert(
    fc.asyncProperty(payloadFeedback, conteudoPrevio, conteudoPrevio, async (payload, eventos, chamados) => {
      const inicial = {};
      if (eventos !== undefined) inicial[CHAVE_EVENTOS] = eventos;
      if (chamados !== undefined) inicial[CHAVE_CHAMADOS] = chamados;

      // Modo_Prototipo: escreve só na chave de feedbacks; sem rede.
      const storageP = storageCom(inicial);
      const protoAmb = montarAmbiente(storageP, '');
      const resP = await protoAmb.ponto.enviar(payload);
      assert.deepEqual(resP, { ok: true, modo: 'prototipo' });
      assert.equal(protoAmb.fetchFalso.chamadas.length, 0);
      assert.equal(storageP.getItem(CHAVE_EVENTOS), eventos === undefined ? null : eventos);
      assert.equal(storageP.getItem(CHAVE_CHAMADOS), chamados === undefined ? null : chamados);
      const escritas = storageP.chamadas.filter((c) => c.metodo !== 'getItem');
      assert.ok(escritas.length > 0);
      for (const c of escritas) {
        assert.equal(c.metodo, 'setItem');
        assert.equal(c.chave, CHAVE_FEEDBACKS);
      }
      assert.deepEqual(
        Object.keys(storageP.instantaneo()).sort(),
        Object.keys(inicial).concat([CHAVE_FEEDBACKS]).sort()
      );

      // Modo_API: não escreve em nenhuma chave.
      const storageA = storageCom(inicial);
      const antes = storageA.instantaneo();
      const apiAmb = montarAmbiente(storageA, URL_API);
      const resA = await apiAmb.ponto.enviar(payload);
      assert.deepEqual(resA, { ok: true, modo: 'api' });
      assert.equal(apiAmb.fetchFalso.chamadas.length, 1);
      assert.equal(storageA.contar('setItem'), 0);
      assert.equal(storageA.contar('removeItem'), 0);
      assert.deepEqual(storageA.instantaneo(), antes);
    }),
    { numRuns: NUM_RUNS }
  );
});

/* ==========================================================
 * Property 14
 * ========================================================== */

test('Property 14: Falha de armazenamento não deixa rastro', async () => {
  // Feature: resolved-feedback-comment, Property 14: Falha de armazenamento não deixa rastro
  // **Validates: Requirements 8.1, 9.7**
  await fc.assert(
    fc.asyncProperty(
      listaEPayload,
      fc.constantFrom('getItem', 'setItem'),
      async ([previa, payload], metodoQueFalha) => {
        const inicial = previa.length > 0 ? { [CHAVE_FEEDBACKS]: JSON.stringify(previa) } : {};
        const storage = criarStorageFalso({
          inicial,
          lancaEmGetItem: metodoQueFalha === 'getItem',
          lancaEmSetItem: metodoQueFalha === 'setItem'
        });
        const antes = storage.instantaneo();
        const { ponto, fetchFalso } = montarAmbiente(storage, '');

        const resultado = await ponto.enviar(payload);

        assert.deepEqual(resultado, { ok: false, categoria: 'armazenamento' });
        assert.deepEqual(storage.instantaneo(), antes);
        assert.equal(fetchFalso.chamadas.length, 0);
        if (metodoQueFalha === 'getItem') assert.equal(storage.contar('setItem'), 0);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});
