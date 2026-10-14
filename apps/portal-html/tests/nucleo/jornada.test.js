'use strict';
// Testes do núcleo (js/chamado.js) sobre a jornada: passos percorridos,
// resumo e sessão. Cada tarefa acrescenta testes independentes neste arquivo.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { fc } = require('../geradores.js');
const nucleo = require(path.join(__dirname, '..', '..', 'js', 'chamado.js'));

/* ==========================================================
 * Property 8: Passos percorridos
 * ========================================================== */

// Congela em profundidade para detectar qualquer mutação da entrada.
function congelar(x) {
  if (x && typeof x === 'object' && !Object.isFrozen(x)) {
    Object.freeze(x);
    Object.values(x).forEach(congelar);
  }
  return x;
}

// Cada problema tem um total de passos fixo (1 a 6), como em js/data.js.
// Uma exibição é (problemaId, posicao); a posição também pode cair fora de
// 1..total (0, negativa, acima do total), que deve ser descartada.
const exibicoes = fc
  .array(fc.integer({ min: 1, max: 6 }), { minLength: 4, maxLength: 4 })
  .chain((totais) =>
    fc.array(
      fc.integer({ min: 1, max: 4 }).chain((problemaId) =>
        fc.record({
          problemaId: fc.constant(problemaId),
          total: fc.constant(totais[problemaId - 1]),
          // dentro de 1..total na maior parte dos casos; fora dele de vez em quando
          posicao: fc.oneof(
            { weight: 4, arbitrary: fc.integer({ min: 1, max: totais[problemaId - 1] }) },
            { weight: 1, arbitrary: fc.integer({ min: -3, max: totais[problemaId - 1] + 4 }) }
          )
        })
      ),
      { maxLength: 40 }
    )
  );

// Feature: ticket-opening-screen, Property 8: Passos percorridos
test('Property 8: registrarPasso mantém posições únicas, em ordem de exibição, dentro de 1..total, e zera ao mudar de problema', () => {
  fc.assert(
    fc.property(exibicoes, (sequencia) => {
      let estado = { problemaId: null, posicoes: [] };
      // Modelo de referência independente da implementação.
      let refId = null;
      let refPosicoes = [];

      for (const { problemaId, posicao, total } of sequencia) {
        const antes = congelar(JSON.parse(JSON.stringify(estado)));
        const copiaAntes = JSON.parse(JSON.stringify(antes));

        const depois = nucleo.registrarPasso(antes, problemaId, posicao, total);

        // Não muta a entrada e devolve um objeto novo.
        assert.deepEqual(antes, copiaAntes);
        assert.notEqual(depois, antes);
        assert.notEqual(depois.posicoes, antes.posicoes);

        // Modelo: zera ao mudar de problema; só entra posição inédita em 1..total.
        if (refId !== problemaId) refPosicoes = [];
        refId = problemaId;
        if (Number.isInteger(posicao) && posicao >= 1 && posicao <= total && !refPosicoes.includes(posicao)) {
          refPosicoes = refPosicoes.concat([posicao]);
        }

        assert.equal(depois.problemaId, problemaId);
        assert.deepEqual(depois.posicoes, refPosicoes);

        // Invariantes explícitas (Property 8).
        assert.equal(new Set(depois.posicoes).size, depois.posicoes.length, 'sem duplicatas');
        assert.ok(depois.posicoes.length <= total, 'tamanho nunca passa do total');
        for (const p of depois.posicoes) {
          assert.ok(Number.isInteger(p) && p >= 1 && p <= total, 'posição dentro de 1..total');
        }

        if (antes.problemaId === problemaId) {
          // Mesmo problema (rever/voltar/repetir): mantém o que já havia, na mesma ordem.
          assert.deepEqual(depois.posicoes.slice(0, antes.posicoes.length), antes.posicoes);
          assert.ok(depois.posicoes.length - antes.posicoes.length <= 1);
        } else {
          // Outro problema: nada do anterior sobrevive; no máximo a nova posição.
          assert.ok(depois.posicoes.length <= 1);
          if (depois.posicoes.length === 1) assert.equal(depois.posicoes[0], posicao);
        }

        estado = depois;
      }
    }),
    { numRuns: 200 }
  );
});

/* ==========================================================
 * Property 9: Resumo da jornada
 * ========================================================== */

const { textoUnicodeCompleto } = require('../geradores.js');

// Nome do modelo: texto Unicode livre não vazio, ou ausente (null/undefined).
const modeloNomeOuAusente = fc.oneof(
  { weight: 3, arbitrary: textoUnicodeCompleto.filter((s) => s.length > 0) },
  { weight: 1, arbitrary: fc.constant(null) },
  { weight: 1, arbitrary: fc.constant(undefined) }
);

// Problema com N passos (0 a 8), título e textos Unicode livres.
const problemaComPosicoes = fc.integer({ min: 0, max: 8 }).chain((n) =>
  fc.record({
    modeloNome: modeloNomeOuAusente,
    titulo: textoUnicodeCompleto.filter((s) => s.length > 0),
    textos: fc.array(textoUnicodeCompleto, { minLength: n, maxLength: n }),
    // Posições vistas: repetidas, fora de 1..N e não inteiras entram de vez em quando.
    posicoes: fc.array(
      fc.oneof(
        { weight: 5, arbitrary: fc.integer({ min: 1, max: Math.max(n, 1) }) },
        { weight: 2, arbitrary: fc.integer({ min: -3, max: n + 4 }) },
        { weight: 1, arbitrary: fc.constantFrom(1.5, 0.5, NaN, Infinity, -Infinity) }
      ),
      { maxLength: 24 }
    )
  })
);

// Sem problema: null, ausente ou valor que não é problema.
const semProblema = fc.constantFrom(null, undefined);

// Feature: ticket-opening-screen, Property 9: Resumo da jornada
// **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.13**
test('Property 9: montarResumo devolve modelo, título, textos dos passos vistos na ordem da solução e "X de Y" coerente', () => {
  fc.assert(
    fc.property(problemaComPosicoes, ({ modeloNome, titulo, textos, posicoes }) => {
      const total = textos.length;
      const entrada = congelar({
        modeloNome,
        problema: { id: 1, titulo, passos: textos.map((texto) => ({ texto })) },
        posicoes
      });
      const copiaAntes = JSON.stringify(entrada, (k, v) => (typeof v === 'number' && !isFinite(v) ? String(v) : v));

      const r = nucleo.montarResumo(entrada);

      // Modelo de referência independente: posições válidas únicas, em ordem da solução.
      const validas = new Set(posicoes.filter((p) => Number.isInteger(p) && p >= 1 && p <= total));
      const esperados = [];
      for (let pos = 1; pos <= total; pos++) if (validas.has(pos)) esperados.push(textos[pos - 1]);

      assert.equal(r.modelo, modeloNome === undefined ? null : modeloNome);
      assert.equal(r.problemaTitulo, titulo);
      assert.deepEqual(r.passos, esperados, 'textos sem alteração, na ordem da solução');
      assert.equal(r.vistos, validas.size);
      assert.equal(r.vistos, r.passos.length);
      assert.equal(r.total, total);
      assert.ok(r.vistos >= 0 && r.vistos <= r.total, '0 <= X <= Y');

      // Não muta a entrada.
      assert.equal(
        JSON.stringify(entrada, (k, v) => (typeof v === 'number' && !isFinite(v) ? String(v) : v)),
        copiaAntes
      );
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 9: Resumo da jornada
test('Property 9: sem problema, o resumo mantém o modelo e devolve título nulo, passos vazios e "0 de 0"', () => {
  fc.assert(
    fc.property(
      modeloNomeOuAusente,
      semProblema,
      fc.array(fc.oneof(fc.integer({ min: -3, max: 12 }), fc.constant(NaN)), { maxLength: 12 }),
      (modeloNome, problema, posicoes) => {
        const r = nucleo.montarResumo({ modeloNome, problema, posicoes });
        assert.deepEqual(r, {
          modelo: modeloNome === undefined ? null : modeloNome,
          problemaTitulo: null,
          passos: [],
          vistos: 0,
          total: 0
        });
      }
    ),
    { numRuns: 100 }
  );
});

/* ==========================================================
 * Property 29: Nova sessão para outro problema
 * ========================================================== */

const { chamado: chamadoGerado, uuidV4 } = require('../geradores.js');

const problemaIdSessao = fc.integer({ min: 1, max: 13 });

// Dois identificadores de problema diferentes.
const doisProblemasDiferentes = fc
  .tuple(problemaIdSessao, problemaIdSessao)
  .filter(([a, b]) => a !== b);

// Sessão do primeiro problema, possivelmente toda preenchida.
const sessaoPreenchida = (problemaId) =>
  fc.record({
    problemaId: fc.constant(problemaId),
    valores: fc.record({
      nome: textoUnicodeCompleto,
      email: textoUnicodeCompleto,
      telefone: textoUnicodeCompleto,
      descricao: textoUnicodeCompleto
    }),
    aceite: fc.boolean(),
    chave: fc.oneof(fc.constant(null), uuidV4),
    estado: fc.constantFrom('ocioso', 'enviando', 'erro', 'enviado'),
    aberto: fc.oneof(fc.constant(null), chamadoGerado)
  });

const SESSAO_VAZIA = (problemaId) => ({
  problemaId,
  valores: { nome: '', email: '', telefone: '', descricao: '' },
  aceite: false,
  chave: null,
  estado: 'ocioso',
  aberto: null
});

// Feature: ticket-opening-screen, Property 29: Nova sessão para outro problema
// **Validates: Requirements 4.14, 8.15**
test('Property 29: garantirSessao para outro problema devolve sessão nova e vazia, sem alterar a sessão recebida', () => {
  fc.assert(
    fc.property(
      doisProblemasDiferentes.chain(([a, b]) => fc.tuple(fc.constant(a), fc.constant(b), sessaoPreenchida(a))),
      ([primeiro, segundo, sessao]) => {
        congelar(sessao);
        const copiaAntes = JSON.parse(JSON.stringify(sessao));
        const referenciaValores = sessao.valores;

        const nova = nucleo.garantirSessao(sessao, segundo);

        // Sessão nova, com o formato esperado e identificador do novo problema.
        assert.notEqual(nova, sessao);
        assert.notEqual(nova.valores, sessao.valores);
        assert.deepEqual(nova, SESSAO_VAZIA(segundo));
        assert.equal(nova.problemaId, segundo);
        assert.deepEqual(nova.valores, { nome: '', email: '', telefone: '', descricao: '' });
        assert.equal(nova.aceite, false);
        assert.equal(nova.chave, null);
        assert.equal(nova.estado, 'ocioso');
        assert.equal(nova.aberto, null);

        // A sessão do primeiro problema não foi alterada.
        assert.equal(sessao.problemaId, primeiro);
        assert.equal(sessao.valores, referenciaValores);
        assert.deepEqual(JSON.parse(JSON.stringify(sessao)), copiaAntes);
      }
    ),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 29: Nova sessão para outro problema
// **Validates: Requirements 4.14, 8.15**
test('Property 29: garantirSessao para o mesmo problema devolve a mesma referência, sem alterá-la', () => {
  fc.assert(
    fc.property(
      problemaIdSessao.chain((id) => fc.tuple(fc.constant(id), sessaoPreenchida(id))),
      ([id, sessao]) => {
        congelar(sessao);
        const copiaAntes = JSON.parse(JSON.stringify(sessao));

        const resultado = nucleo.garantirSessao(sessao, id);

        assert.equal(resultado, sessao, 'mesma referência');
        assert.deepEqual(JSON.parse(JSON.stringify(sessao)), copiaAntes);
      }
    ),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 29: Nova sessão para outro problema
// **Validates: Requirements 4.14, 8.15**
test('Property 29: novaSessao devolve o formato vazio esperado, com objetos independentes a cada chamada', () => {
  fc.assert(
    fc.property(problemaIdSessao, (id) => {
      const a = nucleo.novaSessao(id);
      const b = nucleo.novaSessao(id);

      assert.deepEqual(a, SESSAO_VAZIA(id));
      assert.notEqual(a, b);
      assert.notEqual(a.valores, b.valores);
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 29: Nova sessão para outro problema
// **Validates: Requirements 4.14, 8.15**
test('Property 29: garantirSessao sem sessão anterior cria uma sessão nova para o problema', () => {
  fc.assert(
    fc.property(problemaIdSessao, fc.constantFrom(null, undefined), (id, anterior) => {
      assert.deepEqual(nucleo.garantirSessao(anterior, id), SESSAO_VAZIA(id));
    }),
    { numRuns: 100 }
  );
});
