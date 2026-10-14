'use strict';
// Testes do núcleo (js/chamado.js) sobre identificadores: protocolo local e
// chave de idempotência. Cada tarefa acrescenta testes independentes neste arquivo.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { fc, dataLocal, sequenciaDeSorteio, protocoloLocal } = require('../geradores.js');
const { criarSorteio } = require('../falsos.js');
const nucleo = require(path.join(__dirname, '..', '..', 'js', 'chamado.js'));

/* ==========================================================
 * Property 10: Formato do protocolo local
 * ========================================================== */

const dois = (n) => String(n).padStart(2, '0');

// Oráculo independente: dia existe no calendário (Date.UTC normaliza datas
// inexistentes, então a ida e volta só fecha para datas reais).
function diaExisteNoCalendario(ano, mes, dia) {
  const d = new Date(Date.UTC(2000, mes - 1, dia));
  d.setUTCFullYear(ano);
  return d.getUTCFullYear() === ano && d.getUTCMonth() === mes - 1 && d.getUTCDate() === dia;
}

// Feature: ticket-opening-screen, Property 10: Formato do protocolo local
test('Property 10: gerarProtocolo devolve TRES-AAAAMMDD-XXXXXX com a data local e ehProtocoloLocal aceita', () => {
  fc.assert(
    fc.property(dataLocal, sequenciaDeSorteio, (data, sequencia) => {
      const protocolo = nucleo.gerarProtocolo(data, criarSorteio(sequencia));

      const m = /^TRES-(\d{4})(\d{2})(\d{2})-([A-Z0-9]{6})$/.exec(protocolo);
      assert.notEqual(m, null, 'formato TRES-AAAAMMDD-XXXXXX: ' + protocolo);
      assert.equal(protocolo.length, 'TRES-AAAAMMDD-XXXXXX'.length);

      const ano = Number(m[1]);
      const mes = Number(m[2]);
      const dia = Number(m[3]);

      // AAAAMMDD é a data local informada
      assert.equal(ano, data.getFullYear());
      assert.equal(mes, data.getMonth() + 1);
      assert.equal(dia, data.getDate());
      assert.equal(m[1] + m[2] + m[3], data.getFullYear() + dois(data.getMonth() + 1) + dois(data.getDate()));

      // mês 01-12 e dia existente no calendário
      assert.ok(mes >= 1 && mes <= 12, 'mês entre 01 e 12');
      assert.ok(diaExisteNoCalendario(ano, mes, dia), 'dia existe no calendário');

      // sufixo: exatamente 6 caracteres A-Z0-9
      assert.equal(m[4].length, 6);

      assert.equal(nucleo.ehProtocoloLocal(protocolo), true);
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 10: Formato do protocolo local
test('Property 10: ehProtocoloLocal rejeita variações do formato (minúsculas, data inexistente, tamanho errado, quebra de linha final)', () => {
  fc.assert(
    fc.property(dataLocal, sequenciaDeSorteio, (data, sequencia) => {
      const protocolo = nucleo.gerarProtocolo(data, criarSorteio(sequencia));
      assert.equal(nucleo.ehProtocoloLocal(protocolo), true);

      const [prefixo, aaaammdd, sufixo] = protocolo.split('-');

      const variacoes = [
        // minúsculas
        ['prefixo em minúsculas', protocolo.toLowerCase()],
        ['prefixo "Tres"', 'Tres-' + aaaammdd + '-' + sufixo],
        ['sufixo com minúscula', prefixo + '-' + aaaammdd + '-' + sufixo.slice(0, 5) + 'a'],
        // tamanho errado
        ['sufixo com 5 caracteres', protocolo.slice(0, -1)],
        ['sufixo com 7 caracteres', protocolo + 'A'],
        ['data com 7 dígitos', prefixo + '-' + aaaammdd.slice(1) + '-' + sufixo],
        ['data com 9 dígitos', prefixo + '-' + aaaammdd + '0-' + sufixo],
        ['vazio', ''],
        // quebra de linha e espaços nas pontas
        ['quebra de linha final', protocolo + '\n'],
        ['CRLF final', protocolo + '\r\n'],
        ['quebra de linha inicial', '\n' + protocolo],
        ['espaço final', protocolo + ' '],
        ['espaço inicial', ' ' + protocolo],
        // separadores e caracteres fora do alfabeto
        ['sem hífens', prefixo + aaaammdd + sufixo],
        ['sufixo com símbolo', prefixo + '-' + aaaammdd + '-' + sufixo.slice(0, 5) + '_'],
        ['prefixo trocado', 'ABCD-' + aaaammdd + '-' + sufixo],
        // data inexistente
        ['mês 00', prefixo + '-' + aaaammdd.slice(0, 4) + '00' + aaaammdd.slice(6) + '-' + sufixo],
        ['mês 13', prefixo + '-' + aaaammdd.slice(0, 4) + '13' + aaaammdd.slice(6) + '-' + sufixo],
        ['dia 00', prefixo + '-' + aaaammdd.slice(0, 6) + '00-' + sufixo],
        ['dia 32', prefixo + '-' + aaaammdd.slice(0, 6) + '32-' + sufixo],
        ['31 de abril', prefixo + '-' + aaaammdd.slice(0, 4) + '0431-' + sufixo],
        ['30 de fevereiro', prefixo + '-' + aaaammdd.slice(0, 4) + '0230-' + sufixo],
        ['29 de fevereiro em ano não bissexto (2023)', 'TRES-20230229-' + sufixo],
        ['29 de fevereiro em 2100 (não bissexto)', 'TRES-21000229-' + sufixo]
      ];

      for (const [descricao, texto] of variacoes) {
        assert.equal(nucleo.ehProtocoloLocal(texto), false, descricao + ': ' + JSON.stringify(texto));
      }
    }),
    { numRuns: 100 }
  );
});

test('ehProtocoloLocal aceita 29 de fevereiro só em ano bissexto e rejeita entradas que não são texto', () => {
  assert.equal(nucleo.ehProtocoloLocal('TRES-20240229-ABC123'), true);
  assert.equal(nucleo.ehProtocoloLocal('TRES-20000229-ABC123'), true);
  assert.equal(nucleo.ehProtocoloLocal('TRES-20230229-ABC123'), false);
  assert.equal(nucleo.ehProtocoloLocal('TRES-21000229-ABC123'), false);
  [null, undefined, 123, {}, [], true].forEach((x) => assert.equal(nucleo.ehProtocoloLocal(x), false));
});

/* ==========================================================
 * Property 11: Protocolo local único
 * ========================================================== */

const TENTATIVAS = 10;
const SORTEIOS_POR_TENTATIVA = 6;

// Oráculo: os candidatos que o sorteio produz, na ordem, 6 sorteios cada.
function candidatos(data, sequencia, quantidade) {
  const sorteio = criarSorteio(sequencia);
  const lista = [];
  for (let i = 0; i < quantidade; i++) lista.push(nucleo.gerarProtocolo(data, sorteio));
  return lista;
}

// Feature: ticket-opening-screen, Property 11: Protocolo local único
test('Property 11: gerarProtocoloUnico devolve protocolo fora de existentes, ou null após exatamente 10 colisões', () => {
  fc.assert(
    fc.property(
      dataLocal,
      sequenciaDeSorteio,
      fc.integer({ min: 0, max: TENTATIVAS + 2 }), // quantos candidatos iniciais já existem
      fc.array(protocoloLocal, { maxLength: 8 }), // ruído: protocolos quaisquer
      (data, sequencia, colisoes, ruido) => {
        const previstos = candidatos(data, sequencia, TENTATIVAS);
        const existentes = previstos.slice(0, colisoes).concat(ruido);

        const sorteio = criarSorteio(sequencia);
        const resultado = nucleo.gerarProtocoloUnico(existentes, data, sorteio);

        // Oráculo: primeira tentativa (1..10) cujo candidato não está na lista.
        const indice = previstos.findIndex((c) => existentes.indexOf(c) === -1);

        if (indice === -1) {
          assert.equal(resultado, null, 'todas as 10 tentativas colidiram');
          assert.equal(sorteio.chamadas, TENTATIVAS * SORTEIOS_POR_TENTATIVA, 'exatamente 10 tentativas');
        } else {
          assert.equal(resultado, previstos[indice], 'devolve o primeiro candidato livre');
          assert.equal(sorteio.chamadas, (indice + 1) * SORTEIOS_POR_TENTATIVA, 'para na primeira tentativa livre');
          assert.ok(nucleo.ehProtocoloLocal(resultado), 'formato de protocolo local');
        }

        // nunca devolve um protocolo repetido
        if (resultado !== null) assert.equal(existentes.indexOf(resultado), -1);
        // no máximo 10 tentativas, 6 sorteios cada
        assert.ok(sorteio.chamadas <= TENTATIVAS * SORTEIOS_POR_TENTATIVA);
        assert.equal(sorteio.chamadas % SORTEIOS_POR_TENTATIVA, 0);
      }
    ),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 11: Protocolo local único
test('Property 11: sorteio que repete sempre o mesmo sufixo com esse protocolo já existente devolve null após 10 tentativas', () => {
  fc.assert(
    fc.property(
      dataLocal,
      fc.integer({ min: 0, max: 2 ** 31 - 1 }),
      fc.array(protocoloLocal, { maxLength: 8 }),
      (data, valor, ruido) => {
        const repetido = nucleo.gerarProtocolo(data, criarSorteio([valor]));
        const existentes = ruido.concat([repetido]);

        const sorteio = criarSorteio([valor]);
        assert.equal(nucleo.gerarProtocoloUnico(existentes, data, sorteio), null);
        assert.equal(sorteio.chamadas, TENTATIVAS * SORTEIOS_POR_TENTATIVA, '10 tentativas x 6 sorteios');
      }
    ),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 11: Protocolo local único
test('Property 11: se a primeira tentativa colide e a segunda não, devolve a segunda', () => {
  fc.assert(
    fc.property(
      dataLocal,
      sequenciaDeSorteio,
      fc.array(protocoloLocal, { maxLength: 8 }),
      (data, sequencia, ruido) => {
        const [primeiro, segundo] = candidatos(data, sequencia, 2);
        fc.pre(primeiro !== segundo);
        const existentes = ruido.filter((p) => p !== segundo).concat([primeiro]);

        const sorteio = criarSorteio(sequencia);
        assert.equal(nucleo.gerarProtocoloUnico(existentes, data, sorteio), segundo);
        assert.equal(sorteio.chamadas, 2 * SORTEIOS_POR_TENTATIVA, 'duas tentativas, 6 sorteios cada');
      }
    ),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 11: Protocolo local único
test('Property 11: gerarProtocoloUnico não muta a lista de existentes', () => {
  fc.assert(
    fc.property(
      dataLocal,
      sequenciaDeSorteio,
      fc.integer({ min: 0, max: TENTATIVAS }),
      fc.array(protocoloLocal, { maxLength: 8 }),
      (data, sequencia, colisoes, ruido) => {
        const existentes = candidatos(data, sequencia, colisoes).concat(ruido);
        const copia = existentes.slice();
        Object.freeze(existentes); // qualquer escrita lançaria TypeError em modo estrito

        nucleo.gerarProtocoloUnico(existentes, data, criarSorteio(sequencia));

        assert.deepEqual(existentes, copia);
      }
    ),
    { numRuns: 100 }
  );
});

/* ==========================================================
 * Property 12: Chave de idempotência
 * ========================================================== */

const { bytes16 } = require('../geradores.js');

// UUID v4: 8-4-4-4-12 hexadecimal minúsculo, versão 4, variante em [89ab].
const PADRAO_UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function verificarUuidV4(texto, contexto) {
  assert.equal(typeof texto, 'string', contexto + ': é texto');
  assert.equal(texto.length, 36, contexto + ': 36 caracteres');
  assert.match(texto, PADRAO_UUID_V4, contexto + ': formato UUID v4');
}

// Executa `corpo` com globalThis.crypto substituído (ou removido, se `valor`
// for undefined) e RESTAURA sempre o descritor original. Em Node moderno
// crypto é um getter em globalThis, por isso usa defineProperty.
function comCryptoSubstituido(valor, corpo) {
  const original = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  try {
    Object.defineProperty(globalThis, 'crypto', {
      configurable: true,
      enumerable: original ? original.enumerable : false,
      writable: true,
      value: valor
    });
    return corpo();
  } finally {
    if (original) Object.defineProperty(globalThis, 'crypto', original);
    else delete globalThis.crypto;
  }
}

// Feature: ticket-opening-screen, Property 12: Chave de idempotência
test('Property 12: uuidV4(bytes16) devolve UUID versão 4 e não altera o array recebido', () => {
  fc.assert(
    fc.property(bytes16, (bytes) => {
      const copia = bytes.slice();
      const uuid = nucleo.uuidV4(bytes);

      verificarUuidV4(uuid, 'uuidV4');
      assert.deepEqual(bytes, copia, 'o array recebido não muda');

      // Oráculo: os demais bits vêm dos bytes de entrada.
      const hex = uuid.replace(/-/g, '');
      for (let i = 0; i < 16; i++) {
        const byte = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
        if (i === 6) assert.equal(byte, (bytes[i] & 0x0f) | 0x40, 'byte 6 mantém o nibble baixo');
        else if (i === 8) assert.equal(byte, (bytes[i] & 0x3f) | 0x80, 'byte 8 mantém os 6 bits baixos');
        else assert.equal(byte, bytes[i], 'byte ' + i + ' inalterado');
      }

      // Congelado: qualquer escrita lançaria TypeError em modo estrito.
      assert.equal(nucleo.uuidV4(Object.freeze(bytes.slice())), uuid);
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 12: Chave de idempotência
test('Property 12: gerarChaveIdempotencia(sorteio falso) é determinística para a mesma sequência e tem formato UUID v4', () => {
  fc.assert(
    fc.property(sequenciaDeSorteio, (sequencia) => {
      const a = nucleo.gerarChaveIdempotencia(criarSorteio(sequencia));
      const b = nucleo.gerarChaveIdempotencia(criarSorteio(sequencia));

      verificarUuidV4(a, 'chave com sorteio');
      assert.equal(a, b, 'mesma sequência, mesma chave');

      // Oráculo: a chave é o uuidV4 dos 16 primeiros sorteios(256).
      const sorteio = criarSorteio(sequencia);
      const bytes = [];
      for (let i = 0; i < 16; i++) bytes.push(sorteio(256));
      assert.equal(a, nucleo.uuidV4(bytes));
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 12: Chave de idempotência
test('Property 12: gerarChaveIdempotencia() sem argumento tem formato UUID v4 e chamadas seguidas diferem', () => {
  fc.assert(
    fc.property(fc.constant(null), () => {
      const chaves = [];
      for (let i = 0; i < 5; i++) chaves.push(nucleo.gerarChaveIdempotencia());

      chaves.forEach((c) => verificarUuidV4(c, 'chave aleatória'));
      assert.equal(new Set(chaves).size, chaves.length, 'sem repetições: ' + chaves.join(' '));
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 12: Chave de idempotência
test('Property 12: sem crypto.randomUUID (só getRandomValues, ou sem crypto algum) a chave segue em formato UUID v4 e sem repetição', () => {
  const semRandomUUID = {
    getRandomValues(buf) {
      for (let i = 0; i < buf.length; i++) buf[i] = Math.floor(Math.random() * 256);
      return buf;
    }
  };
  const cenarios = [
    ['crypto sem randomUUID', semRandomUUID],
    ['sem crypto', undefined],
    ['crypto nulo', null],
    ['crypto vazio', {}]
  ];

  for (const [nome, valor] of cenarios) {
    comCryptoSubstituido(valor, () => {
      assert.equal(globalThis.crypto, valor, nome + ': substituição aplicada');
      fc.assert(
        fc.property(fc.constant(null), () => {
          const chaves = [];
          for (let i = 0; i < 5; i++) chaves.push(nucleo.gerarChaveIdempotencia());
          chaves.forEach((c) => verificarUuidV4(c, nome));
          assert.equal(new Set(chaves).size, chaves.length, nome + ': sem repetições');
        }),
        { numRuns: 100 }
      );
    });
  }

  // crypto original restaurado
  assert.equal(typeof globalThis.crypto?.randomUUID, 'function', 'crypto restaurado');
});
