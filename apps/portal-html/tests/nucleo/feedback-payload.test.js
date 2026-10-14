'use strict';
// Testes de propriedade do núcleo do feedback (js/feedback.js) sobre o
// Payload_do_Feedback: conteúdo (Propriedade 4), ida e volta em JSON
// (Propriedade 5) e chave de idempotência (Propriedade 15).
const test = require('node:test');
const assert = require('node:assert/strict');

const {
  fc,
  IDS_MODELO,
  comentarioBruto,
  comentarioValido,
  payloadFeedback,
  textoUnicodeCompleto,
  uuidV4,
  sequenciaDeSorteio
} = require('../geradores.js');
const { criarSorteio } = require('../falsos.js');

const feedback = require('../../js/feedback.js').criar(require('../../js/chamado.js'));

const CAMPOS_DO_CONTRATO = [
  'versaoContrato', 'chaveIdempotencia', 'enviadoEm', 'comentario', 'nota',
  'problemaId', 'modelo'
];

const ISO_COM_FUSO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$/;
const UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/* ==========================================================
 * Propriedade 4: Conteúdo do Payload_do_Feedback
 * ========================================================== */

// Nota recebida: valores válidos (1 a 5) e qualquer outra coisa.
const notaQualquer = fc.oneof(
  { weight: 4, arbitrary: fc.integer({ min: 1, max: 5 }) },
  { weight: 1, arbitrary: fc.constantFrom(null, undefined, 0, 6, -1, 2.5, NaN, Infinity, '3', '', true, {}, []) },
  { weight: 1, arbitrary: fc.integer({ min: -1000, max: 1000 }) },
  { weight: 1, arbitrary: fc.double({ noNaN: false }) }
);

// Comentário válido com espaços e quebras de linha nas pontas (como digitado).
const comentarioValidoComPontas = fc
  .tuple(fc.constantFrom('', ' ', '\n', '\t', '  \r\n '), comentarioValido, fc.constantFrom('', ' ', '\n', '\t', ' \u00A0'))
  .map(([ini, c, fim]) => ini + c + fim);

// Campos de identificação que nunca podem aparecer no payload.
const camposExtras = fc.record(
  {
    nome: textoUnicodeCompleto,
    email: textoUnicodeCompleto,
    telefone: textoUnicodeCompleto,
    protocolo: textoUnicodeCompleto,
    problemaTitulo: textoUnicodeCompleto,
    aceiteTermos: fc.boolean(),
    descricao: textoUnicodeCompleto
  },
  { requiredKeys: [] }
);

const entradaDoPayload = fc.record({
  chave: uuidV4,
  texto: comentarioValidoComPontas,
  nota: notaQualquer,
  problemaId: fc.integer({ min: 1, max: 13 }),
  modelo: fc.option(fc.constantFrom(...IDS_MODELO), { nil: null }),
  instante: fc.date({ min: new Date('2000-01-01T00:00:00Z'), max: new Date('2100-12-31T23:59:59Z'), noInvalidDate: true }),
  extras: camposExtras
});

test('Propriedade 4: conteúdo do Payload_do_Feedback', () => {
  // Feature: resolved-feedback-comment, Property 4: Conteúdo do Payload_do_Feedback
  // **Validates: Requirements 2.4, 3.2, 3.3, 10.11, 10.12, 10.13**
  fc.assert(
    fc.property(entradaDoPayload, ({ chave, texto, nota, problemaId, modelo, instante, extras }) => {
      const entrada = Object.assign({}, extras, {
        chave,
        texto,
        nota,
        problemaId,
        modelo,
        agora: () => instante
      });
      const p = feedback.montarPayload(entrada);

      // Exatamente os 7 campos do contrato, sem nenhum valor extra da entrada.
      assert.deepEqual(Object.keys(p).sort(), CAMPOS_DO_CONTRATO.slice().sort());
      for (const proibido of ['nome', 'email', 'telefone', 'protocolo', 'problemaTitulo', 'aceiteTermos', 'descricao']) {
        assert.equal(Object.prototype.hasOwnProperty.call(p, proibido), false, 'campo extra: ' + proibido);
      }

      assert.equal(p.versaoContrato, '1');
      assert.equal(p.chaveIdempotencia, chave);

      // ISO 8601 com fuso (nunca 'Z') que representa o mesmo instante.
      assert.match(p.enviadoEm, ISO_COM_FUSO);
      assert.equal(Date.parse(p.enviadoEm), instante.getTime());

      // Comentário normalizado, de 1 a 500 caracteres.
      assert.equal(p.comentario, texto.trim());
      assert.ok(p.comentario.length >= 1 && p.comentario.length <= 500);

      // Nota: a recebida se for inteiro de 1 a 5, senão null.
      const notaValida = typeof nota === 'number' && Number.isInteger(nota) && nota >= 1 && nota <= 5;
      assert.equal(p.nota, notaValida ? nota : null);

      assert.equal(p.problemaId, problemaId);
      assert.equal(p.modelo, modelo === null ? null : modelo);
    }),
    { numRuns: 200 }
  );
});

test('Propriedade 4: modelo ausente (undefined) vira null', () => {
  // Feature: resolved-feedback-comment, Property 4: Conteúdo do Payload_do_Feedback
  // **Validates: Requirements 10.11, 10.13**
  fc.assert(
    fc.property(uuidV4, comentarioValido, fc.integer({ min: 1, max: 13 }), (chave, texto, problemaId) => {
      const p = feedback.montarPayload({ chave, texto, nota: null, problemaId, agora: () => new Date(0) });
      assert.equal(p.modelo, null);
      assert.equal(p.nota, null);
    }),
    { numRuns: 100 }
  );
});

/* ==========================================================
 * Propriedade 5: Ida e volta do Payload em JSON
 * ========================================================== */

// Payload com comentário em Unicode completo (emojis, aspas, barras, <, >, &,
// quebras de linha e surrogates soltos), mais o gerador padrão do payload.
const payloadUnicode = fc.oneof(
  { weight: 2, arbitrary: payloadFeedback },
  {
    weight: 2,
    arbitrary: fc
      .tuple(payloadFeedback, comentarioBruto.filter((s) => s.trim().length > 0).map((s) => s.trim().slice(0, 500)))
      .map(([p, comentario]) => Object.assign({}, p, { comentario }))
  },
  {
    weight: 1,
    arbitrary: fc
      .tuple(payloadFeedback, fc.string({ unit: 'binary', minLength: 1, maxLength: 500 }))
      .map(([p, comentario]) => Object.assign({}, p, { comentario }))
  }
);

test('Propriedade 5: ida e volta do Payload em JSON', () => {
  // Feature: resolved-feedback-comment, Property 5: Ida e volta do Payload em JSON
  // **Validates: Requirements 10.14**
  fc.assert(
    fc.property(payloadUnicode, (gerado) => {
      // fc.record pode devolver objetos sem protótipo; JSON.parse devolve objeto comum.
      const payload = Object.assign({}, gerado);
      const texto = feedback.serializar(payload);
      assert.equal(typeof texto, 'string');
      const volta = feedback.desserializar(texto);
      assert.deepStrictEqual(volta, payload);
      assert.equal(volta.comentario, payload.comentario);
      // Segunda volta: o texto serializado é estável.
      assert.equal(feedback.serializar(volta), texto);
    }),
    { numRuns: 500 }
  );
});

/* ==========================================================
 * Propriedade 15: Chave de idempotência
 * ========================================================== */

test('Propriedade 15: chave de idempotência no formato UUID v4 (sorteio injetado)', () => {
  // Feature: resolved-feedback-comment, Property 15: Chave de idempotência
  // **Validates: Requirements 7.1, 10.15**
  fc.assert(
    fc.property(comentarioValido, sequenciaDeSorteio, (texto, sequencia) => {
      const r = feedback.prepararEnvio(feedback.novoEstado(3), {
        texto,
        nota: null,
        problemaId: 3,
        modelo: null,
        agora: () => new Date(0),
        sorteio: criarSorteio(sequencia)
      });
      assert.equal(r.ok, true);
      const chave = r.payload.chaveIdempotencia;
      assert.equal(chave.length, 36);
      assert.match(chave, UUID_V4);
      assert.equal(r.estado.chave, chave);
    }),
    { numRuns: 200 }
  );
});

test('Propriedade 15: chave de idempotência no formato UUID v4 e sem repetição (sorteio aleatório)', () => {
  // Feature: resolved-feedback-comment, Property 15: Chave de idempotência
  // **Validates: Requirements 7.1, 10.15**
  fc.assert(
    fc.property(comentarioValido, fc.integer({ min: 2, max: 40 }), (texto, quantas) => {
      const chaves = [];
      for (let i = 0; i < quantas; i++) {
        const r = feedback.prepararEnvio(feedback.novoEstado(1), {
          texto,
          nota: null,
          problemaId: 1,
          modelo: null,
          agora: () => new Date(0)
        });
        assert.equal(r.ok, true);
        assert.equal(r.payload.chaveIdempotencia.length, 36);
        assert.match(r.payload.chaveIdempotencia, UUID_V4);
        chaves.push(r.payload.chaveIdempotencia);
      }
      assert.equal(new Set(chaves).size, chaves.length, 'chaves repetidas');
    }),
    { numRuns: 100 }
  );
});
