'use strict';
// Testes de propriedade do texto do comentário e do conteúdo do feedback
// (js/feedback.js): normalização, validação, limite/contador e conteúdo
// indisponível. Outros arquivos tests/nucleo/feedback-*.test.js cobrem as
// demais propriedades.

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const base = require(path.join(__dirname, '..', '..', 'js', 'chamado.js'));
const feedback = require(path.join(__dirname, '..', '..', 'js', 'feedback.js')).criar(base);
const {
  fc,
  textoUnicodeCompleto,
  comentarioBruto,
  comentarioValido,
  comentarioLongo
} = require('../geradores.js');

const NUM_RUNS = 200;

// Texto qualquer: comentário como digitado/colado ou Unicode completo.
const textoQualquer = fc.oneof(comentarioBruto, textoUnicodeCompleto, comentarioValido, comentarioLongo);

test('Property 1: Normalização do comentário', () => {
  // Feature: resolved-feedback-comment, Property 1: Normalização do comentário
  // **Validates: Requirements 2.5, 6.1, 6.2, 6.5**
  fc.assert(
    fc.property(textoQualquer, (s) => {
      const n = feedback.normalizarComentario(s);

      // igual a s.trim()
      assert.equal(n, s.trim());
      // trecho contíguo de s, com todos os caracteres internos preservados
      assert.ok(s.includes(n));
      assert.equal(s.slice(s.indexOf(n), s.indexOf(n) + n.length), n);
      // nada de espaço ou quebra de linha nas pontas
      assert.equal(n, n.trim());
      // só as pontas mudam: o que sobra de s são apenas espaços em branco
      const resto = s.replace(n, '');
      assert.equal(resto.trim(), '');
      if (n.length > 0) {
        const i = s.indexOf(n);
        assert.equal(s.slice(0, i).trim(), '');
        assert.equal(s.slice(i + n.length).trim(), '');
      }
      // idempotente
      assert.equal(feedback.normalizarComentario(n), n);
    }),
    { numRuns: NUM_RUNS }
  );
});

test('Property 1: normalização não escapa nem remove caracteres internos', () => {
  // Feature: resolved-feedback-comment, Property 1: Normalização do comentário
  // **Validates: Requirements 2.5, 6.1, 6.2, 6.5**
  const miolo = fc.oneof(comentarioValido, textoUnicodeCompleto).filter((m) => m.trim() === m);
  const pontas = fc.constantFrom('', ' ', '\n', '\t', '\r\n', ' \u00A0 ', '\u2028');
  fc.assert(
    fc.property(pontas, miolo, pontas, (ini, m, fim) => {
      assert.equal(feedback.normalizarComentario(ini + m + fim), m);
    }),
    { numRuns: NUM_RUNS }
  );
});

test('Property 1: null e undefined normalizam para texto vazio', () => {
  // Feature: resolved-feedback-comment, Property 1: Normalização do comentário
  // **Validates: Requirements 6.1**
  assert.equal(feedback.normalizarComentario(null), '');
  assert.equal(feedback.normalizarComentario(undefined), '');
});

test('Property 2: Validação do comentário', () => {
  // Feature: resolved-feedback-comment, Property 2: Validação do comentário
  // **Validates: Requirements 5.2, 5.3**
  fc.assert(
    fc.property(textoQualquer, (s) => {
      const n = feedback.normalizarComentario(s);
      const codigo = feedback.validarComentario(s);

      if (n.length >= 1 && n.length <= 500) {
        assert.equal(codigo, null);
      } else {
        assert.notEqual(codigo, null);
      }
      if (n.length === 0) assert.equal(codigo, 'vazio');
      if (n.length > 500) assert.equal(codigo, 'tamanho');
      if (s === '' || s.trim() === '') assert.equal(codigo, 'vazio');
    }),
    { numRuns: NUM_RUNS }
  );
});

test('Property 2: validação nos geradores válido, longo e só com espaços', () => {
  // Feature: resolved-feedback-comment, Property 2: Validação do comentário
  // **Validates: Requirements 5.2, 5.3**
  fc.assert(
    fc.property(
      comentarioValido,
      comentarioLongo,
      fc.array(fc.constantFrom(' ', '\n', '\t', '\r\n', '\u00A0', '\u2028'), { maxLength: 20 }),
      (valido, longo, brancos) => {
        assert.equal(feedback.validarComentario(valido), null);
        assert.equal(feedback.validarComentario(longo), 'tamanho');
        assert.equal(feedback.validarComentario(brancos.join('')), 'vazio');
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

test('Property 3: Limite e contador de caracteres', () => {
  // Feature: resolved-feedback-comment, Property 3: Limite e contador de caracteres
  // **Validates: Requirements 4.1, 4.2, 4.3**
  const MODELO = '{n} de {max} caracteres';
  fc.assert(
    fc.property(textoQualquer, (s) => {
      const lim = feedback.limitarComentario(s);
      assert.ok(lim.length <= 500);
      assert.ok(s.startsWith(lim));
      if (s.length <= 500) assert.equal(lim, s);
      else assert.equal(lim.length, 500);
      // limitar é idempotente
      assert.equal(feedback.limitarComentario(lim), lim);

      // contador para qualquer texto de até 500 caracteres (o próprio limitado)
      assert.equal(feedback.formatarContador(MODELO, lim), lim.length + ' de 500 caracteres');
      if (s.length <= 500) {
        assert.equal(feedback.formatarContador(MODELO, s), s.length + ' de 500 caracteres');
      }
    }),
    { numRuns: NUM_RUNS }
  );
});

test('Property 3: limite e contador nas bordas de 0, 500 e 501 caracteres', () => {
  // Feature: resolved-feedback-comment, Property 3: Limite e contador de caracteres
  // **Validates: Requirements 4.1, 4.2, 4.3**
  const MODELO = '{n} de {max} caracteres';
  fc.assert(
    fc.property(fc.constantFrom(0, 1, 499, 500, 501, 700), fc.constantFrom('a', 'é', '😀', '\n'), (n, u) => {
      const s = u.repeat(n);
      const lim = feedback.limitarComentario(s);
      assert.equal(lim.length, Math.min(s.length, 500));
      assert.ok(s.startsWith(lim));
      assert.equal(feedback.formatarContador(MODELO, lim), lim.length + ' de 500 caracteres');
    }),
    { numRuns: 100 }
  );
});

// ---------------------------------------------------------------
// Property 20: Conteúdo indisponível
// ---------------------------------------------------------------

function dadosCompletos() {
  const textos = {};
  feedback.CHAVES_TEXTOS_OBRIGATORIOS.forEach((chave) => {
    textos[chave] = 'texto de ' + chave;
  });
  return {
    config: { API_FEEDBACK_URL: '', TIMEOUT_FEEDBACK_MS: 10000, VERSAO_CONTRATO_FEEDBACK: '1' },
    textos
  };
}

// Valor que deve ser rejeitado como texto obrigatório: ausente, não texto
// ou texto vazio/só com espaços após trim.
const valorInvalido = fc.oneof(
  fc.constant(undefined),
  fc.constant(null),
  fc.constantFrom('', ' ', '  ', '\n', '\t', ' \u00A0 ', '\u2028'),
  fc.array(fc.constantFrom(' ', '\n', '\t', '\r', '\u00A0'), { maxLength: 8 }).map((a) => a.join('')),
  fc.integer(),
  fc.boolean(),
  fc.constant({}),
  fc.constant(['texto'])
);

test('Property 20: Conteúdo indisponível', () => {
  // Feature: resolved-feedback-comment, Property 20: Conteúdo indisponível
  // **Validates: Requirements 13.4**
  assert.equal(feedback.textosValidos(dadosCompletos()), true);

  fc.assert(
    fc.property(
      fc.constantFrom(...feedback.CHAVES_TEXTOS_OBRIGATORIOS),
      valorInvalido,
      fc.boolean(),
      (chave, invalido, remover) => {
        const dados = dadosCompletos();
        if (remover) delete dados.textos[chave];
        else dados.textos[chave] = invalido;
        const antes = JSON.stringify(dados);
        assert.equal(feedback.textosValidos(dados), false);
        // não altera a entrada
        assert.equal(JSON.stringify(dados), antes);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

test('Property 20: configuração ou textos ausentes ou inválidos', () => {
  // Feature: resolved-feedback-comment, Property 20: Conteúdo indisponível
  // **Validates: Requirements 13.4**
  const naoObjeto = fc.oneof(
    fc.constant(undefined),
    fc.constant(null),
    fc.string(),
    fc.integer(),
    fc.boolean(),
    fc.constant([])
  );
  fc.assert(
    fc.property(fc.constantFrom('config', 'textos'), fc.boolean(), naoObjeto, (campo, remover, invalido) => {
      const dados = dadosCompletos();
      if (remover) delete dados[campo];
      else dados[campo] = invalido;
      assert.equal(feedback.textosValidos(dados), false);
    }),
    { numRuns: NUM_RUNS }
  );

  // o próprio objeto de dados ausente ou inválido
  fc.assert(
    fc.property(naoObjeto, (dados) => {
      assert.equal(feedback.textosValidos(dados), false);
    }),
    { numRuns: NUM_RUNS }
  );
});

test('Property 20: textos válidos continuam válidos com texto qualquer e chaves extras', () => {
  // Feature: resolved-feedback-comment, Property 20: Conteúdo indisponível
  // **Validates: Requirements 13.4**
  const textoNaoVazio = fc.string({ minLength: 1, maxLength: 60 }).filter((t) => t.trim() !== '');
  fc.assert(
    fc.property(
      fc.array(textoNaoVazio, {
        minLength: feedback.CHAVES_TEXTOS_OBRIGATORIOS.length,
        maxLength: feedback.CHAVES_TEXTOS_OBRIGATORIOS.length
      }),
      textoNaoVazio,
      (valores, extra) => {
        const dados = dadosCompletos();
        feedback.CHAVES_TEXTOS_OBRIGATORIOS.forEach((chave, i) => {
          dados.textos[chave] = valores[i];
        });
        dados.textos.chaveExtra = extra;
        assert.equal(feedback.textosValidos(dados), true);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});
