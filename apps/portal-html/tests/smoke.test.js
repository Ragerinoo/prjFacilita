'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const nucleo = require(path.join(__dirname, '..', 'js', 'chamado.js'));

test('js/chamado.js carrega em Node e exporta LIMITES', () => {
  assert.equal(typeof nucleo.LIMITES, 'object');
  assert.equal(nucleo.LIMITES.nome.min, 3);
  assert.equal(nucleo.LIMITES.descricao.max, 500);
  assert.equal(nucleo.LIMITES.maxChamados, 50);
});

test('js/feedback.js carrega com criar(chamado) e expõe a API pública do design', () => {
  const feedback = require(path.join(__dirname, '..', 'js', 'feedback.js')).criar(nucleo);

  const funcoes = [
    'normalizarComentario', 'validarComentario', 'limitarComentario', 'formatarContador',
    'novoEstado', 'garantirEstado', 'aoExibir', 'editarTexto', 'escolherNota',
    'prepararEnvio', 'concluirEnvio', 'montarPayload', 'serializar', 'desserializar',
    'modoDoFeedback', 'criarPontoDeIntegracao', 'eventoComentario', 'textosValidos'
  ];
  for (const nome of funcoes) {
    assert.equal(typeof feedback[nome], 'function', nome);
  }

  assert.deepEqual(feedback.LIMITES, { comentario: { min: 1, max: 500 }, maxFeedbacks: 50 });
  assert.equal(feedback.CHAVE_REPOSITORIO, 'tres-autoatendimento-feedbacks');
  assert.deepEqual(feedback.CAMPOS_PAYLOAD, [
    'versaoContrato', 'chaveIdempotencia', 'enviadoEm', 'comentario', 'nota', 'problemaId', 'modelo'
  ]);
  assert.ok(Array.isArray(feedback.CHAVES_TEXTOS_OBRIGATORIOS));
  assert.ok(feedback.CHAVES_TEXTOS_OBRIGATORIOS.length > 0);
  assert.ok(Array.isArray(feedback.CHAVES_TEXTOS_OBRIGATORIAS));
  assert.deepEqual(feedback.CHAVES_TEXTOS_OBRIGATORIAS, feedback.CHAVES_TEXTOS_OBRIGATORIOS);

  // Uso mínimo: o núcleo responde de fato, não só exporta nomes.
  assert.equal(feedback.validarComentario('   '), 'vazio');
  assert.equal(feedback.validarComentario('ok'), null);
  assert.equal(feedback.novoEstado(3).estado, 'ocioso');
});

test('infraestrutura: geradores e falsos carregam e produzem valores', () => {
  const g = require('./geradores.js');
  const f = require('./falsos.js');

  for (const nome of ['nomeValido', 'emailValido', 'telefoneValido', 'descricaoValida', 'protocoloLocal', 'chamadoGravado', 'eventoMetrica']) {
    assert.ok(g.fc.sample(g[nome], 5).length === 5, nome);
  }
  const storage = f.criarStorageFalso({ lancaEmSetItem: true });
  assert.throws(() => storage.setItem('k', 'v'));
  assert.equal(f.criarSorteio([7, 9])(5), 2);
});
