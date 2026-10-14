'use strict';
// Testes de exemplo e de borda do núcleo (js/chamado.js), sem fast-check.
// Cobrem: ordem e códigos dos erros, DDD 55, tempo limite e rede em Modo_API,
// chave de idempotência sem crypto.randomUUID e limite de 64 caracteres do protocolo.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const {
  criarFetchFalso,
  criarStorageFalso,
  criarAbortControllerFalso,
  criarTemporizadorFalso,
  criarRelogio,
  criarSorteio
} = require('../falsos.js');
const nucleo = require(path.join(__dirname, '..', '..', 'js', 'chamado.js'));

/* ==========================================================
 * Apoio comum
 * ========================================================== */

const URL_API = 'https://api.exemplo.com/chamados';

const FORMULARIO_VALIDO = {
  nome: 'Maria da Silva',
  email: 'maria@exemplo.com',
  telefone: '(11) 98765-4321',
  descricao: 'A máquina não liga depois da limpeza.',
  aceite: true
};

function formulario(alteracoes) {
  return Object.assign({}, FORMULARIO_VALIDO, alteracoes);
}

function codigos(resultado) {
  return resultado.erros.map((e) => e.campo + ':' + e.codigo);
}

function montarChamadoDeExemplo() {
  return nucleo.montarChamado({
    agora: criarRelogio().agora,
    config: { VERSAO_CONTRATO: '1' },
    chaveIdempotencia: '11111111-2222-4333-8444-555555555555',
    nome: 'Maria da Silva',
    email: 'maria@exemplo.com',
    telefone: '11987654321',
    descricao: 'A máquina não liga depois da limpeza.',
    modelo: 'luna',
    problemaId: 'nao-liga',
    problemaTitulo: 'Não liga',
    passosPercorridos: [{ posicao: 1, texto: 'Verifique a tomada.' }],
    totalPassos: 3
  });
}

// Ponto_de_Integracao em Modo_API com todos os dublês.
function montarApi(comportamentoFetch) {
  const fetchFalso = criarFetchFalso(comportamentoFetch);
  const temporizador = criarTemporizadorFalso();
  const AbortControllerFalso = criarAbortControllerFalso();
  const storage = criarStorageFalso();
  const ponto = nucleo.criarPontoDeIntegracao({
    config: { API_CHAMADOS_URL: URL_API, TIMEOUT_ENVIO_MS: 10000 },
    fetch: fetchFalso,
    AbortController: AbortControllerFalso,
    setTimeout: temporizador.setTimeout,
    clearTimeout: temporizador.clearTimeout,
    storage,
    agora: criarRelogio().agora,
    sorteio: criarSorteio([1, 2, 3])
  });
  return { ponto, fetchFalso, temporizador, AbortControllerFalso, storage };
}

/* ==========================================================
 * 1. Ordem e códigos dos erros (Requisitos 5.3, 5.8)
 * ========================================================== */

test('formulário válido não tem erros', () => {
  const r = nucleo.validarFormulario(FORMULARIO_VALIDO);
  assert.equal(r.valido, true);
  assert.deepEqual(r.erros, []);
});

test('tudo vazio: erros na ordem nome, email, telefone, descricao, aceite', () => {
  const r = nucleo.validarFormulario({ nome: '', email: '', telefone: '', descricao: '', aceite: false });
  assert.equal(r.valido, false);
  assert.deepEqual(codigos(r), [
    'nome:vazio',
    'email:vazio',
    'telefone:vazio',
    'descricao:vazio',
    'aceite:aceite'
  ]);
});

test('apenas espaços contam como vazio', () => {
  const r = nucleo.validarFormulario(formulario({ nome: '   ', descricao: ' \n ' }));
  assert.deepEqual(codigos(r), ['nome:vazio', 'descricao:vazio']);
});

test('código "tamanho" para nome, e-mail, telefone e descrição', () => {
  assert.equal(nucleo.validarNome('Jo'), 'tamanho');
  assert.equal(nucleo.validarNome('a'.repeat(101)), 'tamanho');
  assert.equal(nucleo.validarEmail('a'.repeat(250) + '@b.co'), 'tamanho');
  assert.equal(nucleo.validarTelefone('123'), 'tamanho');
  assert.equal(nucleo.validarTelefone('1'.repeat(21)), 'tamanho');
  assert.equal(nucleo.validarDescricao('curta'), 'tamanho');
  assert.equal(nucleo.validarDescricao('x'.repeat(501)), 'tamanho');
});

test('código "formato" para nome, e-mail e telefone', () => {
  assert.equal(nucleo.validarNome('12345'), 'formato');
  assert.equal(nucleo.validarEmail('maria@exemplo'), 'formato');
  assert.equal(nucleo.validarEmail('maria@@exemplo.com'), 'formato');
  assert.equal(nucleo.validarEmail('ma ria@exemplo.com'), 'formato');
  assert.equal(nucleo.validarTelefone('abc'), 'formato');
  assert.equal(nucleo.validarTelefone('0598765432'), 'formato'); // DDD 05
  assert.equal(nucleo.validarTelefone('11887654321'), 'formato'); // 11 dígitos sem o 9
});

test('códigos distintos aparecem juntos e em ordem; aceite só vale com true', () => {
  const r = nucleo.validarFormulario({
    nome: '12345',
    email: 'maria@exemplo',
    telefone: '123',
    descricao: 'curta',
    aceite: 'true'
  });
  assert.deepEqual(codigos(r), [
    'nome:formato',
    'email:formato',
    'telefone:tamanho',
    'descricao:tamanho',
    'aceite:aceite'
  ]);
});

test('validarFormulario não altera a entrada', () => {
  const entrada = formulario({ nome: '  Maria   da Silva ', email: ' MARIA@Exemplo.com ' });
  const copia = JSON.parse(JSON.stringify(entrada));
  nucleo.validarFormulario(entrada);
  assert.deepEqual(entrada, copia);
});

/* ==========================================================
 * 2. DDD 55 e prefixo 55 do telefone (Requisito 5.3)
 * ========================================================== */

test('DDD 55 com 11 dígitos não perde o 55', () => {
  assert.equal(nucleo.normalizarTelefone('55987654321'), '55987654321');
  assert.equal(nucleo.normalizarTelefone('(55) 98765-4321'), '55987654321');
  assert.equal(nucleo.validarTelefone('55987654321'), null);
});

test('DDD 55 com 10 dígitos não perde o 55', () => {
  assert.equal(nucleo.normalizarTelefone('5533334444'), '5533334444');
  assert.equal(nucleo.validarTelefone('5533334444'), null);
});

test('prefixo 55 com DDD 55 (13 dígitos) vira 55999999999', () => {
  assert.equal(nucleo.normalizarTelefone('5555999999999'), '55999999999');
  assert.equal(nucleo.validarTelefone('5555999999999'), null);
});

test('prefixo 55 com 12 dígitos é removido; sem 55 com 12 ou 13 dígitos é inválido', () => {
  assert.equal(nucleo.normalizarTelefone('+55 11 3333-4444'), '1133334444');
  assert.equal(nucleo.validarTelefone('+55 11 3333-4444'), null);
  assert.equal(nucleo.validarTelefone('111987654321'), 'tamanho');
  assert.equal(nucleo.normalizarTelefone('111987654321'), '111987654321');
});

/* ==========================================================
 * 3. Tempo limite e falha de rede em Modo_API (Requisitos 7.9, 7.10)
 * ========================================================== */

test('fetch que nunca responde: ao vencer o tempo limite, enviar resolve "timeout" e o sinal foi abortado', async () => {
  const { ponto, fetchFalso, temporizador, AbortControllerFalso } = montarApi({ semResposta: true });

  const envio = ponto.enviar(montarChamadoDeExemplo());
  assert.equal(fetchFalso.chamadas.length, 1);
  assert.equal(AbortControllerFalso.instancias.length, 1);
  assert.equal(AbortControllerFalso.instancias[0].signal.aborted, false);

  temporizador.avancar(10000);
  const resultado = await envio;

  assert.deepEqual(resultado, { ok: false, categoria: 'timeout' });
  assert.equal(AbortControllerFalso.instancias[0].signal.aborted, true);
  assert.equal(fetchFalso.chamadas.length, 1, 'sem retentativa automática');
});

test('antes do tempo limite o envio continua pendente e o sinal não é abortado', async () => {
  const { ponto, temporizador, AbortControllerFalso } = montarApi({ semResposta: true });

  let terminou = false;
  const envio = ponto.enviar(montarChamadoDeExemplo()).then((r) => {
    terminou = true;
    return r;
  });

  temporizador.avancar(9999);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(terminou, false);
  assert.equal(AbortControllerFalso.instancias[0].signal.aborted, false);

  temporizador.avancar(1);
  assert.deepEqual(await envio, { ok: false, categoria: 'timeout' });
});

test('falha de rede (fetch rejeita) resolve "rede" e não aborta o sinal', async () => {
  const { ponto, fetchFalso, AbortControllerFalso } = montarApi({ rejeita: new TypeError('Failed to fetch') });

  const resultado = await ponto.enviar(montarChamadoDeExemplo());

  assert.deepEqual(resultado, { ok: false, categoria: 'rede' });
  assert.equal(fetchFalso.chamadas.length, 1);
  assert.equal(AbortControllerFalso.instancias[0].signal.aborted, false);
});

test('resposta recebida a tempo cancela o temporizador', async () => {
  const { ponto, temporizador } = montarApi({ status: 200, corpo: { protocolo: 'ABC-1' } });

  const resultado = await ponto.enviar(montarChamadoDeExemplo());

  assert.deepEqual(resultado, { ok: true, protocolo: 'ABC-1', modo: 'api' });
  assert.equal(temporizador.pendentes(), 0);
});

/* ==========================================================
 * 4. Chave de idempotência sem crypto.randomUUID (Requisito 7.12)
 * ========================================================== */

const PADRAO_UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

// Substitui globalThis.crypto durante `corpo` e restaura SEMPRE o estado original.
function comCryptoSubstituido(valor, corpo) {
  const descritor = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  Object.defineProperty(globalThis, 'crypto', { value: valor, configurable: true, writable: true, enumerable: false });
  try {
    return corpo();
  } finally {
    if (descritor) {
      Object.defineProperty(globalThis, 'crypto', descritor);
    } else {
      delete globalThis.crypto;
    }
  }
}

test('sem crypto.randomUUID mas com getRandomValues: UUID v4 válido', () => {
  const sintetico = {
    getRandomValues(buf) {
      for (let i = 0; i < buf.length; i++) buf[i] = (i * 37 + 11) & 255;
      return buf;
    }
  };
  const chave = comCryptoSubstituido(sintetico, () => nucleo.gerarChaveIdempotencia());
  assert.match(chave, PADRAO_UUID_V4);
});

test('sem crypto algum: cai em Math.random e ainda gera UUID v4 válido', () => {
  const chaves = comCryptoSubstituido(undefined, () => [
    nucleo.gerarChaveIdempotencia(),
    nucleo.gerarChaveIdempotencia()
  ]);
  chaves.forEach((chave) => assert.match(chave, PADRAO_UUID_V4));
  assert.notEqual(chaves[0], chaves[1]);
});

test('crypto.randomUUID que devolve valor fora do formato é ignorado', () => {
  const sintetico = {
    randomUUID: () => 'curto',
    getRandomValues(buf) {
      buf.fill(7);
      return buf;
    }
  };
  const chave = comCryptoSubstituido(sintetico, () => nucleo.gerarChaveIdempotencia());
  assert.match(chave, PADRAO_UUID_V4);
});

test('crypto original é restaurado depois da substituição, mesmo com erro', () => {
  const antes = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  assert.throws(() =>
    comCryptoSubstituido(undefined, () => {
      throw new Error('falha proposital');
    })
  );
  const depois = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  assert.equal(typeof depois, typeof antes);
  if (antes && depois) {
    assert.equal(depois.get, antes.get);
    assert.equal(depois.value, antes.value);
  }
  assert.match(nucleo.gerarChaveIdempotencia(), PADRAO_UUID_V4);
});

/* ==========================================================
 * 5. Protocolo de 64 e 65 caracteres em Modo_API (Requisitos 7.9, 7.11)
 * ========================================================== */

test('interpretarRespostaApi: protocolo com 64 caracteres é aceito', () => {
  const protocolo = 'P'.repeat(64);
  assert.deepEqual(nucleo.interpretarRespostaApi(200, { protocolo }), { ok: true, protocolo });
});

test('interpretarRespostaApi: protocolo com 65 caracteres é rejeitado', () => {
  const r = nucleo.interpretarRespostaApi(200, { protocolo: 'P'.repeat(65) });
  assert.deepEqual(r, { ok: false, categoria: 'resposta-invalida' });
});

test('interpretarRespostaApi: o limite vale depois do trim', () => {
  const dentro = '  ' + 'P'.repeat(64) + '  ';
  assert.deepEqual(nucleo.interpretarRespostaApi(201, { protocolo: dentro }), { ok: true, protocolo: 'P'.repeat(64) });
  assert.equal(nucleo.interpretarRespostaApi(200, { protocolo: ' '.repeat(5) }).categoria, 'resposta-invalida');
  assert.equal(nucleo.interpretarRespostaApi(200, { protocolo: '' }).categoria, 'resposta-invalida');
});

test('enviar em Modo_API: protocolo de 64 caracteres vira sucesso', async () => {
  const protocolo = 'A1'.repeat(32);
  assert.equal(protocolo.length, 64);
  const { ponto } = montarApi({ status: 200, corpo: { protocolo } });

  const resultado = await ponto.enviar(montarChamadoDeExemplo());

  assert.deepEqual(resultado, { ok: true, protocolo, modo: 'api' });
});

test('enviar em Modo_API: protocolo de 65 caracteres vira "resposta-invalida"', async () => {
  const { ponto, storage } = montarApi({ status: 200, corpo: { protocolo: 'A'.repeat(65) } });

  const resultado = await ponto.enviar(montarChamadoDeExemplo());

  assert.deepEqual(resultado, { ok: false, categoria: 'resposta-invalida' });
  assert.equal(storage.chamadas.length, 0, 'Modo_API não toca no repositório local');
});
