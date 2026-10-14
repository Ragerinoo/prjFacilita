'use strict';
// Testes de propriedade do núcleo (js/feedback.js e js/chamado.js) sobre as
// métricas do comentário da Tela_de_Resolvido (spec resolved-feedback-comment).
const test = require('node:test');
const assert = require('node:assert/strict');

const {
  fc,
  payloadFeedback,
  instanteIso,
  listaDeEventosComComentarios,
  eventoMetricaComComentario,
  eventoComentario
} = require('../geradores.js');

const chamado = require('../../js/chamado.js');
const feedback = require('../../js/feedback.js').criar(chamado);

const EXECUCOES = { numRuns: 200 };

const MARCADOR_INICIO = 'ZQX-COMENTARIO-INICIO-7f3a';
const MARCADOR_FIM = 'ZQX-COMENTARIO-FIM-7f3a';

/* ==========================================================
 * Property 18: Evento de métrica sem texto
 * ========================================================== */

// Feature: resolved-feedback-comment, Property 18: Evento de métrica sem texto
// **Validates: Requirements 11.1, 11.2**
test('Property 18: eventoComentario tem só tipo, em, problema e modelo, sem texto, nota, tamanho nem chave', () => {
  fc.assert(
    fc.property(payloadFeedback, instanteIso, (base, em) => {
      // O comentário recebe marcadores únicos para detectar qualquer vazamento do texto.
      const payload = Object.assign({}, base, {
        comentario: MARCADOR_INICIO + base.comentario + MARCADOR_FIM
      });
      const ev = feedback.eventoComentario(payload, em);

      // Exatamente os quatro campos.
      assert.deepEqual(Object.keys(ev).sort(), ['em', 'modelo', 'problema', 'tipo']);
      assert.equal(ev.tipo, 'comentario');
      assert.equal(ev.em, em);
      assert.equal(ev.problema, payload.problemaId);
      assert.equal(ev.modelo, payload.modelo === null ? 'nao-informado' : payload.modelo);

      // Nenhum dos campos proibidos.
      for (const proibido of ['comentario', 'nota', 'tamanho', 'chave', 'chaveIdempotencia', 'texto']) {
        assert.equal(Object.prototype.hasOwnProperty.call(ev, proibido), false, proibido);
      }

      // Nada do texto, da chave nem do instante de envio aparece em qualquer valor.
      const json = JSON.stringify(ev);
      assert.equal(json.includes(MARCADOR_INICIO), false);
      assert.equal(json.includes(MARCADOR_FIM), false);
      assert.equal(json.includes(payload.chaveIdempotencia), false);
    }),
    EXECUCOES
  );
});

// Feature: resolved-feedback-comment, Property 18: Evento de métrica sem texto
// **Validates: Requirements 11.1, 11.2**
test('Property 18: eventoComentario com Date grava o instante em ISO 8601 UTC e não altera o payload', () => {
  fc.assert(
    fc.property(
      payloadFeedback,
      fc.date({ min: new Date('2000-01-01T00:00:00Z'), max: new Date('2100-12-31T23:59:59Z'), noInvalidDate: true }),
      (payload, data) => {
        const antes = JSON.stringify(payload);
        const ev = feedback.eventoComentario(payload, data);
        assert.equal(ev.em, data.toISOString());
        assert.deepEqual(Object.keys(ev).sort(), ['em', 'modelo', 'problema', 'tipo']);
        assert.equal(JSON.stringify(payload), antes);
      }
    ),
    EXECUCOES
  );
});

/* ==========================================================
 * Property 19: Resumo de métricas com comentários
 * ========================================================== */

// Feature: resolved-feedback-comment, Property 19: Resumo de métricas com comentários
// **Validates: Requirements 11.5, 11.6**
test('Property 19: resumirEventos soma comentarios e os demais valores ignoram eventos comentario', () => {
  fc.assert(
    fc.property(listaDeEventosComComentarios, (eventos) => {
      const semComentarios = eventos.filter((e) => e.tipo !== 'comentario');
      const esperado = eventos.length - semComentarios.length;

      const resumo = chamado.resumirEventos(eventos);
      const base = chamado.resumirEventos(semComentarios);

      assert.equal(resumo.comentarios, esperado);
      assert.equal(base.comentarios, 0);
      assert.equal(resumo.resolvidos, base.resolvidos);
      assert.equal(resumo.encaminhadosAoSuporte, base.encaminhadosAoSuporte);
      assert.equal(resumo.deflexaoPercentual, base.deflexaoPercentual);
      assert.deepEqual(resumo.porProblema, base.porProblema);
      assert.equal(resumo.chamadosAbertos, base.chamadosAbertos);
    }),
    EXECUCOES
  );
});

// Itens que não são objetos e tipos desconhecidos também ficam fora das contas.
const itemEstranho = fc.oneof(
  fc.constantFrom(null, undefined, 0, 1, '', 'comentario', true, false, NaN, []),
  fc.record({ tipo: fc.constantFrom('desconhecido', 'Comentario', 'COMENTARIO', ''), problema: fc.integer({ min: 1, max: 13 }) })
);

// Feature: resolved-feedback-comment, Property 19: Resumo de métricas com comentários
// **Validates: Requirements 11.5, 11.6**
test('Property 19: com itens que não são objetos e tipos desconhecidos, comentarios continua igual à contagem de eventos comentario', () => {
  fc.assert(
    fc.property(
      fc.array(fc.oneof({ weight: 4, arbitrary: eventoMetricaComComentario }, { weight: 1, arbitrary: itemEstranho }), {
        maxLength: 60
      }),
      (itens) => {
        const comentarios = itens.filter((e) => e !== null && typeof e === 'object' && e.tipo === 'comentario');
        const semComentarios = itens.filter((e) => !(e !== null && typeof e === 'object' && e.tipo === 'comentario'));

        const resumo = chamado.resumirEventos(itens);
        const base = chamado.resumirEventos(semComentarios);

        assert.equal(resumo.comentarios, comentarios.length);
        assert.equal(resumo.resolvidos, base.resolvidos);
        assert.equal(resumo.encaminhadosAoSuporte, base.encaminhadosAoSuporte);
        assert.equal(resumo.deflexaoPercentual, base.deflexaoPercentual);
        assert.deepEqual(resumo.porProblema, base.porProblema);
        assert.equal(resumo.chamadosAbertos, base.chamadosAbertos);
      }
    ),
    EXECUCOES
  );
});

// Feature: resolved-feedback-comment, Property 19: Resumo de métricas com comentários
// **Validates: Requirements 11.5, 11.6**
test('Property 19: lista só de eventos comentario dá comentarios = tamanho e o resto zerado', () => {
  fc.assert(
    fc.property(fc.array(eventoComentario, { maxLength: 40 }), (eventos) => {
      const resumo = chamado.resumirEventos(eventos);
      assert.deepEqual(resumo, {
        resolvidos: 0,
        encaminhadosAoSuporte: 0,
        deflexaoPercentual: null,
        porProblema: {},
        chamadosAbertos: 0,
        comentarios: eventos.length
      });
    }),
    EXECUCOES
  );
});
