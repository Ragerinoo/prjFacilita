'use strict';
// Testes de propriedade do estado do formulário de comentário (js/feedback.js):
//   Property 16: Máquina de estados do envio (teste baseado em modelo)
//   Property 17: Reinício por jornada
//
// O núcleo é carregado como no design: criar(base) com o módulo do chamado.
// O modelo usado como oráculo na Property 16 é escrito aqui, sem chamar
// nenhuma função do feedback.js (nem normalizar, nem validar, nem montar payload).
const test = require('node:test');
const assert = require('node:assert/strict');

const { fc, acaoDoFormulario, IDS_MODELO } = require('../geradores.js');
const feedback = require('../../js/feedback.js').criar(require('../../js/chamado.js'));

const EXECUCOES = 200;

/* ==========================================================
 * Auxiliares
 * ========================================================== */

// Congela em profundidade para detectar qualquer mutação da entrada.
function congelar(x) {
  if (x && typeof x === 'object' && !Object.isFrozen(x)) {
    Object.freeze(x);
    Object.values(x).forEach(congelar);
  }
  return x;
}

function clonar(x) {
  return JSON.parse(JSON.stringify(x));
}

const REGEX_UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const REGEX_ISO_COM_FUSO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$/;

// Oráculo independente de trim(): \s em JavaScript cobre exatamente os
// espaços e terminadores de linha que String.prototype.trim remove.
function aparar(s) {
  return s.replace(/^\s+/, '').replace(/\s+$/, '');
}

const AGORA_FIXO = new Date(2026, 9, 13, 14, 32, 10, 123);
const agora = () => AGORA_FIXO;

/* ==========================================================
 * Property 16: Máquina de estados do envio
 * ========================================================== */

// Feature: resolved-feedback-comment, Property 16: Máquina de estados do envio
// **Validates: Requirements 4.5, 5.1, 5.6, 7.2, 7.3, 7.8, 7.10, 8.2, 8.4, 8.5, 8.6**
test('Property 16: máquina de estados do envio acompanha um modelo simples', () => {
  fc.assert(
    fc.property(fc.array(acaoDoFormulario, { minLength: 1, maxLength: 40 }), (acoes) => {
      // ---- Modelo (oráculo): estado esperado, sem usar o código sob teste ----
      let modelo = { problemaId: null, texto: '', chave: null, estado: 'ocioso', enviado: null, nota: null };
      // Payload da tentativa em andamento (para o "concluir com sucesso").
      let pendente = null;
      // Chave de cada tentativa já aceita, para conferir que não muda até o sucesso.
      let chaveDaJornada = null;

      // ---- Sistema real ----
      let real = congelar(feedback.novoEstado(null));
      assert.deepEqual(real, modelo, 'estado inicial');

      for (const acao of acoes) {
        const antes = clonar(real);

        if (acao.tipo === 'editar') {
          real = congelar(feedback.editarTexto(real, acao.texto));
          if (modelo.estado === 'ocioso') modelo = Object.assign({}, modelo, { texto: acao.texto.slice(0, 500) });
        } else if (acao.tipo === 'enviar') {
          const entrada = { texto: acao.texto, nota: acao.nota, problemaId: modelo.problemaId === null ? 1 : modelo.problemaId, modelo: acao.modelo, agora };
          const r = feedback.prepararEnvio(real, entrada);
          const apar = aparar(acao.texto);

          if (modelo.estado !== 'ocioso') {
            // Duplo envio / já enviado: recusado, sem payload e sem mexer no estado.
            assert.deepEqual(r, { ok: false, codigo: 'ocupado' });
            assert.deepEqual(real, antes, 'ocupado não altera o estado');
          } else if (apar.length === 0) {
            assert.deepEqual(r, { ok: false, codigo: 'vazio' });
            assert.deepEqual(real, antes, 'vazio deixa o estado como estava');
          } else if (apar.length > 500) {
            assert.deepEqual(r, { ok: false, codigo: 'tamanho' });
            assert.deepEqual(real, antes, 'tamanho deixa o estado como estava');
          } else {
            assert.equal(r.ok, true, 'envio válido em ocioso é aceito');
            const p = r.payload;

            // Chave: criada uma vez (UUID v4) e reutilizada em toda retentativa.
            assert.match(p.chaveIdempotencia, REGEX_UUID_V4);
            if (modelo.chave !== null) assert.equal(p.chaveIdempotencia, modelo.chave, 'retentativa reutiliza a chave');
            if (chaveDaJornada !== null) assert.equal(p.chaveIdempotencia, chaveDaJornada, 'chave estável até o sucesso');
            chaveDaJornada = p.chaveIdempotencia;

            // Payload reflete o texto atual, normalizado.
            assert.deepEqual(Object.keys(p).sort(), [
              'chaveIdempotencia', 'comentario', 'enviadoEm', 'modelo', 'nota', 'problemaId', 'versaoContrato'
            ]);
            assert.equal(p.versaoContrato, '1');
            assert.equal(p.comentario, apar);
            assert.equal(p.nota, acao.nota);
            assert.equal(p.problemaId, entrada.problemaId);
            assert.equal(p.modelo, acao.modelo);
            assert.match(p.enviadoEm, REGEX_ISO_COM_FUSO);

            modelo = Object.assign({}, modelo, { texto: acao.texto, chave: p.chaveIdempotencia, estado: 'enviando' });
            pendente = p;
            real = congelar(r.estado);
          }
        } else if (acao.tipo === 'concluirSucesso') {
          const retorno = feedback.concluirEnvio(real, { ok: true, modo: 'prototipo' }, pendente);
          if (modelo.estado === 'enviando') {
            modelo = Object.assign({}, modelo, { estado: 'enviado', enviado: { comentario: pendente.comentario } });
            pendente = null;
          } else {
            assert.deepEqual(retorno, antes, 'concluir fora de enviando não altera o estado');
          }
          real = congelar(retorno);
        } else if (acao.tipo === 'concluirFalha') {
          const retorno = feedback.concluirEnvio(real, { ok: false, categoria: acao.categoria }, pendente);
          if (modelo.estado === 'enviando') {
            // Falha: volta a ocioso, com o mesmo texto e a mesma chave.
            modelo = Object.assign({}, modelo, { estado: 'ocioso' });
            pendente = null;
            assert.equal(retorno.texto, antes.texto, 'falha preserva o texto');
            assert.equal(retorno.chave, antes.chave, 'falha preserva a chave');
          } else {
            assert.deepEqual(retorno, antes, 'concluir fora de enviando não altera o estado');
          }
          real = congelar(retorno);
        } else if (acao.tipo === 'reexibir') {
          real = congelar(feedback.aoExibir(real, acao.problemaId));
          if (modelo.problemaId !== acao.problemaId) {
            // Outra jornada: estado novo; qualquer envio em andamento deixa de valer.
            modelo = { problemaId: acao.problemaId, texto: '', chave: null, estado: 'ocioso', enviado: null, nota: null };
            pendente = null;
            chaveDaJornada = null;
          } else if (modelo.estado === 'ocioso') {
            modelo = Object.assign({}, modelo, { texto: '', chave: null, nota: null });
            chaveDaJornada = null;
          } else {
            modelo = Object.assign({}, modelo, { nota: null });
          }
        }

        assert.deepEqual(real, modelo, 'estado real igual ao do modelo depois de ' + acao.tipo);
        // Depois de um sucesso, o texto enviado é guardado (nunca vazio).
        if (modelo.estado === 'enviado') assert.equal(modelo.enviado.comentario.length > 0, true);
      }
    }),
    { numRuns: EXECUCOES }
  );
});

// Feature: resolved-feedback-comment, Property 16: Máquina de estados do envio
// **Validates: Requirements 7.2, 7.3, 7.10, 8.2, 8.5**
test('Property 16: duplo envio ocupado, falha preserva texto e chave, retentativa usa a mesma chave, sucesso trava', () => {
  const entradaValida = fc.record({
    texto: fc.stringMatching(/^[a-zA-Z]{1,20}$/),
    nota: fc.option(fc.integer({ min: 1, max: 5 }), { nil: null }),
    modelo: fc.option(fc.constantFrom(...IDS_MODELO), { nil: null }),
    novoTexto: fc.stringMatching(/^[a-zA-Z]{1,20}$/),
    falhas: fc.integer({ min: 1, max: 4 })
  });

  fc.assert(
    fc.property(entradaValida, fc.integer({ min: 1, max: 13 }), (e, problemaId) => {
      const mk = (texto) => ({ texto, nota: e.nota, problemaId, modelo: e.modelo, agora });
      let estado = congelar(feedback.novoEstado(problemaId));

      const primeiro = feedback.prepararEnvio(estado, mk(e.texto));
      assert.equal(primeiro.ok, true);
      assert.equal(primeiro.estado.estado, 'enviando');
      const chave = primeiro.payload.chaveIdempotencia;
      assert.match(chave, REGEX_UUID_V4);
      estado = congelar(primeiro.estado);

      // Segundo toque durante o envio: recusado e sem segundo payload.
      assert.deepEqual(feedback.prepararEnvio(estado, mk(e.texto)), { ok: false, codigo: 'ocupado' });

      let atual = e.texto;
      for (let i = 0; i < e.falhas; i++) {
        estado = congelar(feedback.concluirEnvio(estado, { ok: false, categoria: 'rede' }, null));
        assert.equal(estado.estado, 'ocioso');
        assert.equal(estado.texto, atual);
        assert.equal(estado.chave, chave);

        // Edição entre tentativas muda o texto, não a chave.
        atual = i % 2 === 0 ? e.novoTexto : atual;
        estado = congelar(feedback.editarTexto(estado, atual));
        const retentativa = feedback.prepararEnvio(estado, mk(atual));
        assert.equal(retentativa.ok, true);
        assert.equal(retentativa.payload.chaveIdempotencia, chave);
        assert.equal(retentativa.payload.comentario, atual);
        estado = congelar(retentativa.estado);
      }

      estado = congelar(feedback.concluirEnvio(estado, { ok: true, modo: 'api' }, { comentario: atual }));
      assert.equal(estado.estado, 'enviado');
      assert.deepEqual(estado.enviado, { comentario: atual });

      // Travado: nem novo envio nem edição mudam o estado.
      assert.deepEqual(feedback.prepararEnvio(estado, mk('outro texto')), { ok: false, codigo: 'ocupado' });
      assert.equal(feedback.editarTexto(estado, 'x'), estado);
      // Reexibir o mesmo problema mantém o "enviado".
      assert.deepEqual(feedback.aoExibir(estado, problemaId), Object.assign({}, estado, { nota: null }));
    }),
    { numRuns: EXECUCOES }
  );
});

/* ==========================================================
 * Property 17: Reinício por jornada
 * ========================================================== */

const idDeProblema = fc.oneof({ weight: 6, arbitrary: fc.integer({ min: 1, max: 13 }) }, { weight: 1, arbitrary: fc.constant(null) });

const estadoQualquer = fc
  .record({
    problemaId: idDeProblema,
    texto: fc.string({ maxLength: 60 }),
    chave: fc.option(fc.uuid({ version: 4 }), { nil: null }),
    estado: fc.constantFrom('ocioso', 'enviando', 'enviado'),
    enviado: fc.option(fc.record({ comentario: fc.string({ minLength: 1, maxLength: 60 }) }), { nil: null }),
    nota: fc.option(fc.integer({ min: 1, max: 5 }), { nil: null })
  })
  // fc.record cria objetos sem protótipo; o deepStrictEqual os distingue de objetos comuns.
  .map((e) => ({
    problemaId: e.problemaId,
    texto: e.texto,
    chave: e.chave,
    estado: e.estado,
    enviado: e.enviado === null ? null : { comentario: e.enviado.comentario },
    nota: e.nota
  }));

const doisIdsDiferentes = fc.tuple(idDeProblema, idDeProblema).filter(([a, b]) => a !== b);

function estadoInicial(problemaId) {
  return { problemaId, texto: '', chave: null, estado: 'ocioso', enviado: null, nota: null };
}

// Feature: resolved-feedback-comment, Property 17: Reinício por jornada
// **Validates: Requirements 4.5, 7.9**
test('Property 17: outro problema reinicia o estado sem alterar o anterior; o mesmo problema mantém', () => {
  fc.assert(
    fc.property(estadoQualquer, doisIdsDiferentes, (base, [a, b]) => {
      const primeiro = congelar(Object.assign({}, base, { problemaId: a }));
      const fotografia = clonar(primeiro);

      // Segundo problema: estado inicial, objeto novo, primeiro intacto.
      const segundo = feedback.garantirEstado(primeiro, b);
      assert.deepEqual(segundo, estadoInicial(b));
      assert.notEqual(segundo, primeiro);
      assert.deepEqual(primeiro, fotografia);

      // Mesmo problema: devolve o próprio estado existente.
      assert.equal(feedback.garantirEstado(primeiro, a), primeiro);

      // novoEstado sempre devolve o inicial, descartando qualquer "já enviado".
      assert.deepEqual(feedback.novoEstado(b), estadoInicial(b));
      assert.deepEqual(feedback.novoEstado(a), estadoInicial(a));
      assert.notEqual(feedback.novoEstado(a), feedback.novoEstado(a));
    }),
    { numRuns: EXECUCOES }
  );
});

// Feature: resolved-feedback-comment, Property 17: Reinício por jornada
// **Validates: Requirements 4.5, 7.9**
test('Property 17: aoExibir zera texto, chave e nota em ocioso e preserva enviando e enviado', () => {
  fc.assert(
    fc.property(estadoQualquer, idDeProblema, (base, outro) => {
      const original = congelar(base);
      const fotografia = clonar(original);

      // Mesmo problema.
      const mesmo = feedback.aoExibir(original, original.problemaId);
      if (original.estado === 'ocioso') {
        assert.deepEqual(mesmo, Object.assign({}, fotografia, { texto: '', chave: null, nota: null }));
      } else {
        assert.deepEqual(mesmo, Object.assign({}, fotografia, { nota: null }));
      }

      // Outro problema (ou igual): sempre coerente com garantirEstado.
      const aoOutro = feedback.aoExibir(original, outro);
      if (outro === original.problemaId) {
        assert.deepEqual(aoOutro, mesmo);
      } else {
        assert.deepEqual(aoOutro, estadoInicial(outro));
      }

      // A entrada não foi alterada.
      assert.deepEqual(original, fotografia);
    }),
    { numRuns: EXECUCOES }
  );
});
