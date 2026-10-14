'use strict';
// Testes do núcleo (js/chamado.js) sobre o Chamado e o Payload. Cada tarefa
// acrescenta testes independentes neste arquivo.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const {
  fc,
  nomeBruto,
  emailBruto,
  telefoneValidoComOraculo,
  descricaoBruta,
  chamado,
  chamadoUnicode,
  chamadoGravado,
  listaDeChamados,
  listaDeChamadosUnicos,
  instanteIso
} = require('../geradores.js');
const { criarRelogio, criarStorageFalso } = require('../falsos.js');
const nucleo = require(path.join(__dirname, '..', '..', 'js', 'chamado.js'));

/* ==========================================================
 * Apoio: relógio falso com fuso
 * ========================================================== */

// Contrato (design, Data Models): os 14 campos do Payload_do_Chamado.
const CAMPOS_DO_CONTRATO = [
  'versaoContrato', 'chaveIdempotencia', 'abertoEm', 'nome', 'email', 'telefone',
  'descricao', 'aceiteTermos', 'aceiteEm', 'modelo', 'problemaId', 'problemaTitulo',
  'passosPercorridos', 'totalPassos'
];

const ISO_COM_FUSO = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}[+-]\d{2}:\d{2}$/;

// Date que se comporta como se o dispositivo estivesse no fuso `offsetIso`
// (ex.: '-03:00'): getters locais e getTimezoneOffset seguem esse fuso.
class DateComFuso extends Date {
  constructor(instanteMs, minutosALeste) {
    super(instanteMs);
    this.minutosALeste = minutosALeste;
  }
  getTimezoneOffset() { return -this.minutosALeste; }
  _deslocado() { return new Date(this.getTime() + this.minutosALeste * 60000); }
  getFullYear() { return this._deslocado().getUTCFullYear(); }
  getMonth() { return this._deslocado().getUTCMonth(); }
  getDate() { return this._deslocado().getUTCDate(); }
  getHours() { return this._deslocado().getUTCHours(); }
  getMinutes() { return this._deslocado().getUTCMinutes(); }
  getSeconds() { return this._deslocado().getUTCSeconds(); }
  getMilliseconds() { return this._deslocado().getUTCMilliseconds(); }
}

function dateComFuso(instanteMs, offsetIso) {
  const m = /^([+-])(\d{2}):(\d{2})$/.exec(offsetIso);
  const minutosALeste = (m[1] === '-' ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3]));
  return new DateComFuso(instanteMs, minutosALeste);
}

// Relógio falso (falsos.js) cujo agora() devolve um Date no fuso pedido.
function relogioComFuso(instanteMs, offsetIso) {
  const base = criarRelogio(instanteMs);
  return {
    agora: () => dateComFuso(base.agora().getTime(), offsetIso)
  };
}

// Formulário válido bruto + resumo da jornada + chave + relógio + variante de formato.
const entradaDoChamado = fc.record({
  nomeBruto,
  emailBruto,
  telefone: telefoneValidoComOraculo,
  descricaoBruta,
  base: chamado, // fornece chave, modelo, problema e passos
  instante: fc.integer({ min: Date.UTC(2000, 0, 1), max: Date.UTC(2100, 11, 31) }),
  fuso: instanteIso.map((iso) => iso.slice(-6)),
  // Variações aceitas por montarChamado
  agoraComoFuncao: fc.boolean(),
  nomesAlternativos: fc.boolean(),
  versaoNaConfig: fc.boolean(),
  agrupamento: fc.constantFrom('soltos', 'valores', 'normalizado')
});

// Monta a entrada de montarChamado a partir dos dados gerados. Função pura:
// chamá-la duas vezes devolve estruturas iguais (o relógio é passado de fora).
function montarEntrada(d, relogio) {
  const c = d.base;
  const textos = {
    nome: d.nomeBruto,
    email: d.emailBruto,
    telefone: d.telefone.texto,
    descricao: d.descricaoBruta
  };
  const entrada = {
    agora: d.agoraComoFuncao ? relogio.agora : relogio.agora(),
    problemaId: c.problemaId,
    problemaTitulo: c.problemaTitulo,
    totalPassos: c.totalPassos
  };
  const passos = c.passosPercorridos.map((p) => ({ posicao: p.posicao, texto: p.texto }));

  if (d.nomesAlternativos) {
    entrada.chave = c.chaveIdempotencia;
    entrada.passos = passos;
    entrada.modeloId = c.modelo;
  } else {
    entrada.chaveIdempotencia = c.chaveIdempotencia;
    entrada.passosPercorridos = passos;
    entrada.modelo = c.modelo;
  }
  if (d.versaoNaConfig) entrada.config = { VERSAO_CONTRATO: c.versaoContrato };
  else entrada.versaoContrato = c.versaoContrato;

  if (d.agrupamento === 'soltos') Object.assign(entrada, textos);
  else entrada[d.agrupamento] = textos;
  return entrada;
}

/* ==========================================================
 * Property 13: Conteúdo do Chamado e do Payload
 * ========================================================== */

// Feature: ticket-opening-screen, Property 13: Conteúdo do Chamado e do Payload
test('Property 13: montarChamado e montarPayload devolvem os 14 campos do contrato com conteúdo normalizado', () => {
  fc.assert(
    fc.property(
      entradaDoChamado,
      fc.string({ maxLength: 12 }),
      fc.constantFrom('prototipo', 'api'),
      (d, protocolo, modoEnvio) => {
        const relogio = relogioComFuso(d.instante, d.fuso);
        const entrada = montarEntrada(d, relogio);
        const referencia = montarEntrada(d, relogio); // cópia independente para conferir a não mutação

        const c = nucleo.montarChamado(entrada);

        // não muta a entrada (agora, quando Date, é comparado por valor)
        assert.deepStrictEqual(entrada, referencia, 'montarChamado não altera a entrada');

        // exatamente os 14 campos do contrato
        assert.deepStrictEqual(Object.keys(c).sort(), CAMPOS_DO_CONTRATO.slice().sort());

        // normalização (oráculo independente)
        assert.equal(c.nome, d.nomeBruto.trim().replace(/\s+/g, ' '));
        assert.equal(c.email, d.emailBruto.trim().toLowerCase());
        assert.equal(c.telefone, d.telefone.nacional);
        assert.match(c.telefone, /^\d{10,11}$/);
        assert.equal(c.descricao, d.descricaoBruta.trim());

        // aceite e instantes
        assert.equal(c.aceiteTermos, true);
        for (const campo of ['abertoEm', 'aceiteEm']) {
          assert.match(c[campo], ISO_COM_FUSO, campo + ' em ISO 8601 com fuso: ' + c[campo]);
          assert.ok(!c[campo].includes('Z'), campo + ' nunca termina em Z');
          assert.ok(/[+-]\d{2}:\d{2}$/.test(c[campo]));
          assert.equal(c[campo].slice(-6), d.fuso, campo + ' usa o fuso do relógio');
          assert.equal(Date.parse(c[campo]), d.instante, campo + ' representa o instante do relógio');
        }
        assert.equal(c.aceiteEm, c.abertoEm, 'abertoEm e aceiteEm são iguais');

        // jornada, chave e demais campos copiados
        assert.equal(c.versaoContrato, d.base.versaoContrato);
        assert.equal(c.chaveIdempotencia, d.base.chaveIdempotencia);
        assert.equal(c.modelo, d.base.modelo);
        assert.equal(c.problemaId, d.base.problemaId);
        assert.equal(c.problemaTitulo, d.base.problemaTitulo);
        assert.equal(c.totalPassos, d.base.totalPassos);
        assert.deepStrictEqual(c.passosPercorridos, d.base.passosPercorridos, 'passos na ordem percorrida');

        // montarPayload: mesmo com protocolo, modoEnvio e campo extra no chamado
        const comExtras = Object.assign({}, c, { protocolo, modoEnvio, campoExtra: 'x' });
        const copiaDoChamado = Object.assign({}, comExtras);
        const payload = nucleo.montarPayload(comExtras);

        assert.deepStrictEqual(Object.keys(payload).sort(), CAMPOS_DO_CONTRATO.slice().sort());
        assert.ok(!('protocolo' in payload), 'sem protocolo');
        assert.ok(!('modoEnvio' in payload), 'sem modoEnvio');
        assert.ok(!('campoExtra' in payload), 'sem campo extra');
        for (const campo of CAMPOS_DO_CONTRATO) {
          assert.deepStrictEqual(payload[campo], c[campo], 'payload.' + campo + ' igual ao do chamado');
        }

        // montarPayload não muta o chamado
        assert.deepStrictEqual(comExtras, copiaDoChamado, 'montarPayload não altera o chamado');
        assert.deepStrictEqual(Object.keys(comExtras), Object.keys(copiaDoChamado));
      }
    ),
    { numRuns: 100 }
  );
});

/* ==========================================================
 * Property 14: Ida e volta do Chamado no repositório
 * ========================================================== */

const CHAVE_ESPERADA = 'tres-autoatendimento-chamados';

// Compara caractere a caractere (unidades UTF-16), inclusive surrogates soltos.
// deepStrictEqual compara strings por valor, então já é exato; o JSON.stringify
// abaixo reforça a conferência da ordem e dos campos.
function assertChamadosIguais(lido, original, contexto) {
  assert.deepStrictEqual(lido, original, contexto);
  assert.equal(JSON.stringify(lido), JSON.stringify(original), contexto + ' (JSON)');
}

// Feature: ticket-opening-screen, Property 14: Ida e volta do Chamado no repositório
test('Property 14: gravar no repositório e ler de volta devolve o Chamado idêntico, com Unicode completo', () => {
  fc.assert(
    fc.property(chamadoGravado, listaDeChamados({ maxLength: 5 }), (unico, lista) => {
      // Um único Chamado
      const storage = criarStorageFalso();
      const repo = nucleo.criarRepositorio(storage);
      repo.gravar([unico]);

      const lido = repo.ler();
      assert.equal(lido.length, 1);
      assertChamadosIguais(lido[0], unico, 'chamado lido');
      for (const campo of Object.keys(unico)) {
        assert.ok(campo in lido[0], 'campo presente: ' + campo);
      }
      assert.deepStrictEqual(Object.keys(lido[0]), Object.keys(unico), 'mesmos campos, mesma ordem');

      // A chave usada é a do contrato
      assert.equal(CHAVE_ESPERADA, nucleo.CHAVE_REPOSITORIO);
      const gravacoes = storage.chamadas.filter((c) => c.metodo === 'setItem');
      assert.equal(gravacoes.length, 1);
      assert.equal(gravacoes[0].chave, CHAVE_ESPERADA);
      assert.deepStrictEqual(Object.keys(storage.instantaneo()), [CHAVE_ESPERADA]);
      assert.ok(storage.chamadas.filter((c) => c.metodo === 'getItem').every((c) => c.chave === CHAVE_ESPERADA));

      // Uma lista inteira, na mesma ordem
      const storageLista = criarStorageFalso();
      const repoLista = nucleo.criarRepositorio(storageLista);
      repoLista.gravar(lista);
      assertChamadosIguais(repoLista.ler(), lista, 'lista lida');

      // Outro repositório sobre o mesmo storage enxerga o mesmo conteúdo
      assertChamadosIguais(nucleo.criarRepositorio(storageLista).ler(), lista, 'lista lida por outro repositório');
    }),
    { numRuns: 300 }
  );
});

// Feature: ticket-opening-screen, Property 14: Ida e volta do Chamado no repositório
test('Property 14: serializar seguido de desserializar devolve o Chamado idêntico', () => {
  fc.assert(
    fc.property(chamadoGravado, listaDeChamados({ maxLength: 5 }), (c, lista) => {
      const texto = nucleo.serializar(c);
      assert.equal(typeof texto, 'string');
      assertChamadosIguais(nucleo.desserializar(texto), c, 'chamado desserializado');

      // Reserializar o resultado dá o mesmo texto
      assert.equal(nucleo.serializar(nucleo.desserializar(texto)), texto);

      const textoLista = nucleo.serializar(lista);
      assertChamadosIguais(nucleo.desserializar(textoLista), lista, 'lista desserializada');
      assertChamadosIguais(nucleo.lerLista(textoLista), lista, 'lista via lerLista');
    }),
    { numRuns: 300 }
  );
});

/* ==========================================================
 * Property 15: Ida e volta do Payload
 * ========================================================== */

// Confere a ida e volta do Payload de um Chamado: o texto serializado é JSON
// válido, suas chaves são exatamente os 14 campos do contrato e o resultado de
// desserializar é igual ao payload, campo a campo e caractere a caractere.
function conferirIdaEVoltaDoPayload(c) {
  const payload = nucleo.montarPayload(c);
  const texto = nucleo.serializar(payload);

  assert.equal(typeof texto, 'string');

  // JSON válido, lido pelo parser nativo (independente de desserializar)
  let nativo;
  assert.doesNotThrow(() => { nativo = JSON.parse(texto); }, 'o texto serializado é JSON válido');

  // chaves exatamente iguais aos 14 campos do contrato
  assert.deepStrictEqual(Object.keys(nativo).sort(), CAMPOS_DO_CONTRATO.slice().sort());

  const volta = nucleo.desserializar(texto);
  assert.deepStrictEqual(Object.keys(volta).sort(), CAMPOS_DO_CONTRATO.slice().sort());
  assert.ok(!('protocolo' in volta), 'sem protocolo');
  assert.ok(!('modoEnvio' in volta), 'sem modoEnvio');

  // igual ao payload original (todos os 14 campos)
  assert.deepStrictEqual(volta, payload, 'desserializar(serializar(payload)) é igual ao payload');
  for (const campo of CAMPOS_DO_CONTRATO) {
    assert.deepStrictEqual(volta[campo], payload[campo], 'campo ' + campo);
    assert.deepStrictEqual(volta[campo], c[campo], 'campo ' + campo + ' igual ao do chamado');
  }

  // textos idênticos caractere a caractere (unidades UTF-16, inclusive surrogates soltos)
  for (const campo of ['nome', 'email', 'descricao', 'problemaTitulo']) {
    assert.equal(volta[campo].length, c[campo].length, campo + ': mesmo comprimento');
    assert.equal(volta[campo], c[campo], campo + ': mesmo texto');
  }

  // passosPercorridos: mesmos itens, na mesma ordem
  assert.equal(volta.passosPercorridos.length, c.passosPercorridos.length);
  c.passosPercorridos.forEach((passo, i) => {
    assert.equal(volta.passosPercorridos[i].posicao, passo.posicao, 'posição do passo ' + i);
    assert.equal(volta.passosPercorridos[i].texto, passo.texto, 'texto do passo ' + i);
  });
  assert.deepStrictEqual(
    volta.passosPercorridos.map((p) => p.posicao),
    c.passosPercorridos.map((p) => p.posicao),
    'mesma ordem dos passos'
  );

  // reserializar dá o mesmo texto
  assert.equal(nucleo.serializar(volta), texto);
}

// Feature: ticket-opening-screen, Property 15: Ida e volta do Payload
test('Property 15: desserializar(serializar(montarPayload(c))) é igual a montarPayload(c), com Unicode completo', () => {
  fc.assert(
    fc.property(chamadoUnicode, (c) => {
      conferirIdaEVoltaDoPayload(c);
    }),
    { numRuns: 300 }
  );
});

// Feature: ticket-opening-screen, Property 15: Ida e volta do Payload
test('Property 15: a ida e volta do Payload ignora protocolo e modoEnvio do Chamado gravado', () => {
  fc.assert(
    fc.property(chamadoGravado, (c) => {
      assert.ok('protocolo' in c && 'modoEnvio' in c, 'o chamado gerado traz protocolo e modoEnvio');
      conferirIdaEVoltaDoPayload(c);
    }),
    { numRuns: 300 }
  );
});

/* ==========================================================
 * Property 16: Leitura tolerante do repositório
 * ========================================================== */

// true se o texto é JSON válido (lido pelo parser nativo).
function ehJsonValido(texto) {
  try { JSON.parse(texto); return true; } catch (e) { return false; }
}

// Texto que não é JSON: lixo qualquer, inclusive surrogates soltos.
const textoQueNaoEJson = fc.oneof(
  fc.string({ unit: 'binary', maxLength: 80 }),
  fc.string({ maxLength: 80 }),
  fc.constantFrom('abc', 'undefined', 'NaN', '{', '[', '{"a":', '[1,2', "{'a':1}", '[,]', 'nulo', '<html>')
).filter((t) => !ehJsonValido(t));

// JSON truncado: uma lista válida de Chamados cortada antes do ']' final.
const jsonTruncado = fc
  .tuple(listaDeChamados({ maxLength: 3 }), fc.nat(1000))
  .map(([lista, n]) => {
    const texto = JSON.stringify(lista);
    return texto.slice(0, n % texto.length); // nunca o texto inteiro
  });

// JSON válido que não é uma lista: objeto, número, texto, null, booleano.
const jsonQueNaoELista = fc
  .oneof(
    fc.jsonValue().filter((v) => !Array.isArray(v)),
    fc.object(),
    fc.double({ noNaN: true, noDefaultInfinity: true }),
    fc.integer(),
    fc.string({ unit: 'binary', maxLength: 40 }),
    fc.constantFrom(null, true, false, 0, '', {}, 'texto')
  )
  .map((v) => JSON.stringify(v));

// Itens que não são objetos: null, número, texto, booleano e listas.
const itemQueNaoEObjeto = fc.oneof(
  fc.constant(null),
  fc.integer(),
  fc.double({ noNaN: true, noDefaultInfinity: true }),
  fc.string({ unit: 'binary', maxLength: 20 }),
  fc.boolean(),
  fc.array(fc.jsonValue(), { maxLength: 3 })
);

// Qualquer conteúdo armazenado que não forma uma lista de Chamados.
const conteudoIlegivel = fc.oneof(
  fc.constantFrom(null, undefined, ''),
  textoQueNaoEJson,
  jsonTruncado,
  jsonQueNaoELista,
  fc.array(itemQueNaoEObjeto, { maxLength: 6 }).map((itens) => JSON.stringify(itens)) // lista só de itens que não são objetos
);

// Feature: ticket-opening-screen, Property 16: Leitura tolerante do repositório
test('Property 16: lerLista devolve [] sem lançar para null, undefined, vazio e texto que não é JSON', () => {
  fc.assert(
    fc.property(textoQueNaoEJson, (texto) => {
      assert.deepStrictEqual(nucleo.lerLista(texto), []);
    }),
    { numRuns: 200 }
  );
  assert.deepStrictEqual(nucleo.lerLista(null), []);
  assert.deepStrictEqual(nucleo.lerLista(undefined), []);
  assert.deepStrictEqual(nucleo.lerLista(''), []);
});

// Feature: ticket-opening-screen, Property 16: Leitura tolerante do repositório
test('Property 16: lerLista devolve [] sem lançar para JSON truncado', () => {
  fc.assert(
    fc.property(jsonTruncado, (texto) => {
      assert.equal(ehJsonValido(texto), false, 'o gerador produz JSON inválido');
      assert.deepStrictEqual(nucleo.lerLista(texto), []);
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 16: Leitura tolerante do repositório
test('Property 16: lerLista devolve [] sem lançar para JSON válido que não é lista', () => {
  fc.assert(
    fc.property(jsonQueNaoELista, (texto) => {
      assert.equal(ehJsonValido(texto), true);
      assert.ok(!Array.isArray(JSON.parse(texto)));
      assert.deepStrictEqual(nucleo.lerLista(texto), []);
    }),
    { numRuns: 200 }
  );
  for (const texto of ['{}', '0', '42', '"texto"', 'null', 'true', 'false', '{"protocolo":"x"}']) {
    assert.deepStrictEqual(nucleo.lerLista(texto), [], texto);
  }
});

// Feature: ticket-opening-screen, Property 16: Leitura tolerante do repositório
test('Property 16: lerLista descarta itens que não são objetos e mantém os objetos, na ordem', () => {
  const itemMisto = fc.oneof(
    chamadoGravado.map((c) => ({ c, objeto: true })),
    itemQueNaoEObjeto.map((c) => ({ c, objeto: false }))
  );
  fc.assert(
    fc.property(fc.array(itemMisto, { maxLength: 10 }), (itens) => {
      const texto = JSON.stringify(itens.map((i) => i.c));
      const esperado = itens.filter((i) => i.objeto).map((i) => i.c);

      const lido = nucleo.lerLista(texto);
      assert.ok(Array.isArray(lido));
      assertChamadosIguais(lido, esperado, 'só os objetos, na ordem original');
      assert.ok(lido.every((x) => x !== null && typeof x === 'object' && !Array.isArray(x)));
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 16: Leitura tolerante do repositório
test('Property 16: lerLista nunca lança, qualquer que seja o texto, e devolve sempre uma lista de objetos', () => {
  fc.assert(
    fc.property(
      fc.oneof(conteudoIlegivel, fc.string({ unit: 'binary', maxLength: 80 }), listaDeChamados({ maxLength: 4 }).map((l) => JSON.stringify(l))),
      (texto) => {
        let lido;
        assert.doesNotThrow(() => { lido = nucleo.lerLista(texto); });
        assert.ok(Array.isArray(lido));
        assert.ok(lido.every((x) => x !== null && typeof x === 'object' && !Array.isArray(x)));

        // oráculo independente
        let esperado = [];
        if (typeof texto === 'string' && ehJsonValido(texto)) {
          const v = JSON.parse(texto);
          if (Array.isArray(v)) esperado = v.filter((x) => x !== null && typeof x === 'object' && !Array.isArray(x));
        }
        assert.deepStrictEqual(lido, esperado);
      }
    ),
    { numRuns: 300 }
  );
});

// Feature: ticket-opening-screen, Property 16: Leitura tolerante do repositório
test('Property 16: criarRepositorio(storage).ler() nunca lança: getItem que lança ou conteúdo corrompido dão []', () => {
  // getItem que lança
  fc.assert(
    fc.property(fc.boolean(), (comConteudo) => {
      const storage = criarStorageFalso({
        lancaEmGetItem: true,
        inicial: comConteudo ? { [CHAVE_ESPERADA]: '[{"a":1}]' } : {}
      });
      const repo = nucleo.criarRepositorio(storage);
      let lido;
      assert.doesNotThrow(() => { lido = repo.ler(); });
      assert.deepStrictEqual(lido, []);
      assert.ok(storage.contar('getItem') >= 1, 'o getItem foi de fato exercitado');
    }),
    { numRuns: 100 }
  );

  // conteúdo ilegível ou ausente
  fc.assert(
    fc.property(conteudoIlegivel, (conteudo) => {
      const inicial = typeof conteudo === 'string' ? { [CHAVE_ESPERADA]: conteudo } : {};
      const repo = nucleo.criarRepositorio(criarStorageFalso({ inicial }));
      let lido;
      assert.doesNotThrow(() => { lido = repo.ler(); });
      assert.deepStrictEqual(lido, []);
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 16: Leitura tolerante do repositório
test('Property 16: depois de ler conteúdo ilegível, gravar um novo Chamado resulta em lista com esse único Chamado', () => {
  const origemIlegivel = fc.oneof(
    conteudoIlegivel.map((conteudo) => ({ conteudo, lanca: false })),
    fc.constant({ conteudo: '[{"a":1}]', lanca: true }) // getItem lança
  );
  fc.assert(
    fc.property(origemIlegivel, chamadoGravado, ({ conteudo, lanca }, novo) => {
      const inicial = typeof conteudo === 'string' ? { [CHAVE_ESPERADA]: conteudo } : {};
      const storage = criarStorageFalso({ inicial, lancaEmGetItem: lanca });
      const repo = nucleo.criarRepositorio(storage);

      const lista = repo.ler();
      assert.deepStrictEqual(lista, []);

      const nova = nucleo.adicionarComLimite(lista, novo, 50);
      assert.equal(nova.length, 1);
      assert.doesNotThrow(() => repo.gravar(nova));

      // lê de volta pelo storage (sem a falha de leitura): só o novo Chamado
      storage.lancaEmGetItem = false;
      const lido = nucleo.criarRepositorio(storage).ler();
      assertChamadosIguais(lido, [novo], 'lista com o novo Chamado como único item');
      assertChamadosIguais(nucleo.lerLista(storage.instantaneo()[CHAVE_ESPERADA]), [novo], 'conteúdo gravado');
    }),
    { numRuns: 200 }
  );
});

/* ==========================================================
 * Property 17: Limite de 50 chamados
 * ========================================================== */

const LIMITE = 50;

// Listas de 0 a 60 chamados (cobre abaixo, exatamente e acima do limite).
const listaAteSessenta = listaDeChamadosUnicos({ maxLength: 60 });
// Listas de exatamente 50 chamados.
const listaDeCinquenta = listaDeChamadosUnicos({ minLength: LIMITE, maxLength: LIMITE });

// Congela a lista e cada chamado (para provar que nada é mutado).
function congelar(lista) {
  lista.forEach((c) => Object.freeze(c));
  return Object.freeze(lista);
}

// Confere todas as propriedades de um resultado de adicionarComLimite(lista, novo, 50).
function conferirLimite(lista, novo) {
  const antes = JSON.stringify(lista);
  const copiaAntes = lista.slice();
  congelar(lista);

  const resultado = nucleo.adicionarComLimite(lista, novo, LIMITE);

  assert.ok(Array.isArray(resultado));
  assert.ok(resultado.length <= LIMITE, 'no máximo 50 itens');
  assert.equal(resultado[resultado.length - 1], novo, 'o novo chamado é o último');

  // mantém os mais recentes, na ordem original: os últimos 50 de lista + novo
  const esperado = copiaAntes.concat([novo]).slice(-LIMITE);
  assert.equal(resultado.length, esperado.length);
  esperado.forEach((c, i) => assert.equal(resultado[i], c, 'item ' + i + ' igual, na mesma ordem'));
  assert.deepStrictEqual(resultado, esperado);

  if (copiaAntes.length < LIMITE) {
    assert.equal(resultado.length, copiaAntes.length + 1, 'nada é descartado abaixo do limite');
    copiaAntes.forEach((c, i) => assert.equal(resultado[i], c));
  } else {
    assert.equal(resultado.length, LIMITE);
    const descartados = copiaAntes.length - (LIMITE - 1);
    assert.deepStrictEqual(resultado.slice(0, -1), copiaAntes.slice(descartados), 'descarta os mais antigos');
  }

  // não muta a lista recebida
  assert.equal(lista.length, copiaAntes.length);
  assert.equal(JSON.stringify(lista), antes);
  lista.forEach((c, i) => assert.equal(c, copiaAntes[i]));
  assert.notEqual(resultado, lista, 'devolve uma nova lista');
  return resultado;
}

// Feature: ticket-opening-screen, Property 17: Limite de 50 chamados
test('Property 17: adicionarComLimite(lista, novo, 50) devolve no máximo 50 itens, termina com o novo e mantém os mais recentes', () => {
  fc.assert(
    fc.property(listaAteSessenta, chamadoGravado, (lista, novo) => {
      conferirLimite(lista, novo);
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 17: Limite de 50 chamados
test('Property 17: com lista de exatamente 50, o mais antigo sai e o novo entra', () => {
  fc.assert(
    fc.property(listaDeCinquenta, chamadoGravado, (lista, novo) => {
      assert.equal(lista.length, LIMITE);
      const primeiro = lista[0];
      const resultado = conferirLimite(lista, novo);

      assert.equal(resultado.length, LIMITE);
      assert.ok(!resultado.includes(primeiro), 'o primeiro (mais antigo) saiu');
      assert.equal(resultado[0], lista[1], 'o segundo passa a ser o primeiro');
      assert.equal(resultado[LIMITE - 1], novo);
      assert.deepStrictEqual(resultado.slice(0, LIMITE - 1), lista.slice(1));
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 17: Limite de 50 chamados
test('Property 17: com menos de 50 itens nada é descartado', () => {
  fc.assert(
    fc.property(listaDeChamadosUnicos({ maxLength: LIMITE - 1 }), chamadoGravado, (lista, novo) => {
      const resultado = conferirLimite(lista, novo);
      assert.equal(resultado.length, lista.length + 1);
      assert.deepStrictEqual(resultado.slice(0, -1), lista);
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 17: Limite de 50 chamados
test('Property 17: aplicado repetidamente, a lista nunca passa de 50 e preserva os 50 mais recentes', () => {
  fc.assert(
    fc.property(listaAteSessenta, listaDeChamadosUnicos({ minLength: 1, maxLength: 60 }), (inicial, novos) => {
      let atual = inicial.slice(0, LIMITE);
      const historico = atual.slice();

      for (const novo of novos) {
        atual = nucleo.adicionarComLimite(atual, novo, LIMITE);
        historico.push(novo);
        assert.ok(atual.length <= LIMITE, 'nunca ultrapassa 50');
        assert.equal(atual[atual.length - 1], novo);
      }
      assert.deepStrictEqual(atual, historico.slice(-LIMITE), 'preserva os 50 mais recentes, na ordem');
      assert.equal(atual.length, Math.min(historico.length, LIMITE));
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 17: Limite de 50 chamados
test('Property 17: pelo repositório (ler, adicionarComLimite, gravar), o armazenamento nunca passa de 50 chamados', () => {
  fc.assert(
    fc.property(listaDeChamadosUnicos({ minLength: 1, maxLength: 60 }), (chamados) => {
      const storage = criarStorageFalso();
      const repo = nucleo.criarRepositorio(storage);

      chamados.forEach((novo, i) => {
        repo.gravar(nucleo.adicionarComLimite(repo.ler(), novo, LIMITE));

        const lido = nucleo.criarRepositorio(storage).ler();
        assert.ok(lido.length <= LIMITE, 'nunca ultrapassa 50 no storage');
        assert.equal(lido.length, Math.min(i + 1, LIMITE));
        assertChamadosIguais(lido[lido.length - 1], novo, 'o último lido é o recém-gravado');
      });

      const esperado = chamados.slice(-LIMITE);
      assertChamadosIguais(repo.ler(), esperado, 'os 50 mais recentes, na ordem');
      assert.deepStrictEqual(Object.keys(storage.instantaneo()), [CHAVE_ESPERADA]);
    }),
    { numRuns: 100 }
  );
});
