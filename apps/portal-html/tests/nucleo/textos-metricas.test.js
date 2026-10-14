'use strict';
// Testes do núcleo (js/chamado.js) sobre textos de confirmação e métricas.
// Cada tarefa acrescenta testes independentes neste arquivo.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { fc, textoUnicodeCompleto } = require('../geradores.js');
const nucleo = require(path.join(__dirname, '..', '..', 'js', 'chamado.js'));

/* ==========================================================
 * Property 23: Prazo de retorno
 * ========================================================== */

// Qualquer valor que NÃO seja inteiro de 1 a 30.
const valorForaDoPrazo = fc.oneof(
  fc.constantFrom(
    0, -0, -1, 31, 32, 100, 1e9, 0.5, 1.5, 29.999, 30.0001, NaN, Infinity, -Infinity,
    Number.MAX_SAFE_INTEGER, Number.MIN_SAFE_INTEGER, Number.MAX_VALUE, Number.MIN_VALUE,
    '', '1', '15', '30', '2 dias', 'abc', ' ', 'NaN',
    null, undefined, true, false, [], [5], {}, { valueOf: () => 5 }, () => 5, Symbol('x'), 10n
  ),
  fc.integer({ max: 0 }),
  fc.integer({ min: 31 }),
  fc.double({ noNaN: false }).filter((x) => !(Number.isInteger(x) && x >= 1 && x <= 30)),
  fc.double({ min: 1, max: 30, noNaN: true, noDefaultInfinity: true }).filter((x) => !Number.isInteger(x)),
  fc.string(),
  fc.object()
);

// Feature: ticket-opening-screen, Property 23: Prazo de retorno
// **Validates: Requirements 8.7, 8.9**
test('Property 23: formatarPrazo(N) para inteiro de 1 a 30 devolve "N dias úteis" ("1 dia útil" para 1), sem data nem hora', () => {
  fc.assert(
    fc.property(fc.integer({ min: 1, max: 30 }), (n) => {
      const texto = nucleo.formatarPrazo(n);
      assert.equal(typeof texto, 'string');
      assert.equal(texto, n === 1 ? '1 dia útil' : n + ' dias úteis');
      assert.ok(texto.includes(String(n)));
      // sem data limite: nenhuma data (dd/mm, aaaa-mm-dd, ano) nem hora (hh:mm)
      assert.doesNotMatch(texto, /\d{1,2}[/.-]\d{1,2}|\d{4}|\d{1,2}:\d{2}|\d{1,2}\s*h\b/i);
      // o único número do texto é o próprio prazo
      assert.deepEqual(texto.match(/\d+/g), [String(n)]);
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 23: Prazo de retorno
// **Validates: Requirements 8.7, 8.9**
test('Property 23: formatarPrazo devolve null para qualquer valor que não seja inteiro de 1 a 30', () => {
  fc.assert(
    fc.property(valorForaDoPrazo, (valor) => {
      assert.equal(nucleo.formatarPrazo(valor), null);
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 23: Prazo de retorno
// **Validates: Requirements 8.7, 8.9**
test('Property 23: limites do prazo (0, 1, 30, 31) e valores não numéricos', () => {
  assert.equal(nucleo.formatarPrazo(0), null);
  assert.equal(nucleo.formatarPrazo(1), '1 dia útil');
  assert.equal(nucleo.formatarPrazo(2), '2 dias úteis');
  assert.equal(nucleo.formatarPrazo(30), '30 dias úteis');
  assert.equal(nucleo.formatarPrazo(31), null);
  assert.equal(nucleo.formatarPrazo(1.5), null);
  assert.equal(nucleo.formatarPrazo(NaN), null);
  assert.equal(nucleo.formatarPrazo(Infinity), null);
  assert.equal(nucleo.formatarPrazo('5'), null);
  assert.equal(nucleo.formatarPrazo(null), null);
  assert.equal(nucleo.formatarPrazo(undefined), null);
  assert.equal(nucleo.formatarPrazo({}), null);
});

/* ==========================================================
 * Property 24: Texto dos canais de retorno
 * ========================================================== */

const fs = require('node:fs');
const vm = require('node:vm');

// Modelo real de js/data.js (TRES_DATA.CHAMADO.textos.canaisConfirmacao).
function carregarModeloCanais() {
  const arquivo = path.join(__dirname, '..', '..', 'js', 'data.js');
  const janela = {};
  const contexto = vm.createContext({ window: janela });
  vm.runInContext(fs.readFileSync(arquivo, 'utf8'), contexto, { filename: arquivo });
  return janela.TRES_DATA.CHAMADO.textos.canaisConfirmacao;
}

const MODELO_CANAIS = carregarModeloCanais();
// Pedaços fixos do modelo, entre os marcadores {telefone} e {email}.
const PEDACOS_CANAIS = MODELO_CANAIS.split(/\{telefone\}|\{email\}/);

// Fragmentos que um replace ingênuo reinterpretaria ou que quebram HTML/script.
const fragmentoPerigoso = fc.constantFrom(
  '$&', '$1', '$$', '$`', "$'", '$<x>', '{email}', '{telefone}', '{', '}', '{}', '{x}',
  '<b>', '</script>', '<script>', '"', "'", '`', '\\', '&amp;', '😀', '\uD800', '\uDC00'
);

// Unicode completo, com fragmentos perigosos misturados.
const valorDeCanal = fc.oneof(
  textoUnicodeCompleto,
  fc.array(fc.oneof(fragmentoPerigoso, fc.string({ maxLength: 8 })), { maxLength: 6 }).map((p) => p.join(''))
);

// Valores sem chaves: o resultado não pode conter nenhum marcador.
const valorSemChaves = valorDeCanal.map((s) => s.replace(/[{}]/g, ''));

// Feature: ticket-opening-screen, Property 24: Texto dos canais de retorno
// **Validates: Requirements 8.6, 8.8**
test('Property 24: montarTextoCanais contém telefone e e-mail literalmente e mantém o resto do modelo', () => {
  fc.assert(
    fc.property(valorDeCanal, valorDeCanal, (telefone, email) => {
      const texto = nucleo.montarTextoCanais(MODELO_CANAIS, telefone, email);
      assert.equal(typeof texto, 'string');
      assert.ok(texto.includes(telefone), 'telefone literal');
      assert.ok(texto.includes(email), 'e-mail literal');
      // oráculo exato: os valores entram sem reinterpretação ($, marcadores, HTML)
      assert.equal(texto, PEDACOS_CANAIS[0] + telefone + PEDACOS_CANAIS[1] + email + PEDACOS_CANAIS[2]);
      // o texto restante do modelo permanece
      for (const pedaco of PEDACOS_CANAIS) assert.ok(texto.includes(pedaco));
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 24: Texto dos canais de retorno
// **Validates: Requirements 8.6, 8.8**
test('Property 24: montarTextoCanais não deixa os marcadores {telefone}/{email} e menciona WhatsApp e e-mail', () => {
  fc.assert(
    fc.property(valorSemChaves, valorSemChaves, (telefone, email) => {
      const texto = nucleo.montarTextoCanais(MODELO_CANAIS, telefone, email);
      assert.ok(!texto.includes('{telefone}'));
      assert.ok(!texto.includes('{email}'));
      assert.ok(texto.includes('WhatsApp'));
      assert.match(texto, /e-mail/i);
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 24: Texto dos canais de retorno
// **Validates: Requirements 8.6, 8.8**
test('Property 24: preencherModelo troca marcadores sem reinterpretar valores e mantém marcador sem valor', () => {
  fc.assert(
    fc.property(valorDeCanal, valorDeCanal, (a, b) => {
      const modelo = 'A {a} B {b} C {c} D {a}';
      const texto = nucleo.preencherModelo(modelo, { a, b });
      assert.equal(texto, 'A ' + a + ' B ' + b + ' C {c} D ' + a);
      // sem valores, nada muda
      assert.equal(nucleo.preencherModelo(modelo, {}), modelo);
      assert.equal(nucleo.preencherModelo(modelo, null), modelo);
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 24: Texto dos canais de retorno
// **Validates: Requirements 8.6, 8.8**
test('Property 24: exemplos com $&, $1, {email}, <b>, </script> e aspas', () => {
  const tel = '$& $1 {email} <b>"x"</script>';
  const mail = "a'b@x.com $` {telefone}";
  const texto = nucleo.montarTextoCanais(MODELO_CANAIS, tel, mail);
  assert.equal(texto, PEDACOS_CANAIS[0] + tel + PEDACOS_CANAIS[1] + mail + PEDACOS_CANAIS[2]);
  assert.equal(nucleo.preencherModelo('{x} e {y}', { x: '$&' }), '$& e {y}');
  assert.equal(
    nucleo.montarTextoCanais(MODELO_CANAIS, '11987654321', 'ana@exemplo.com'),
    'Vamos falar com você pelo WhatsApp, no número 11987654321, e por e-mail, em ana@exemplo.com.'
  );
});

/* ==========================================================
 * Property 25: Resumo de métricas preserva a deflexão
 * ========================================================== */

const { listaDeEventos, eventoMetrica, eventoChamado, eventoAvaliacao } = require('../geradores.js');

// Evento 'comentario' (definido localmente): { tipo, em, problema, modelo }.
const eventoComentarioLocal = fc.record({
  tipo: fc.constant('comentario'),
  em: fc
    .date({ min: new Date('2000-01-01T00:00:00Z'), max: new Date('2100-12-31T23:59:59Z'), noInvalidDate: true })
    .map((d) => d.toISOString()),
  problema: fc.integer({ min: 1, max: 13 }),
  modelo: fc.oneof(fc.constant('nao-informado'), fc.constantFrom('luna', 'passione', 'lov', 'modo', 'touch'))
});

// Lista de eventos de métrica com eventos 'comentario' intercalados.
const listaComComentarios = fc
  .tuple(listaDeEventos, fc.array(eventoComentarioLocal, { maxLength: 20 }), fc.array(fc.nat(), { maxLength: 20 }))
  .map(([eventos, comentarios, posicoes]) => {
    const saida = eventos.slice();
    comentarios.forEach((c, i) => {
      saida.splice((posicoes[i] || 0) % (saida.length + 1), 0, c);
    });
    return saida;
  });

// Oráculo independente: conta com filter/reduce direto sobre a lista.
function resumoEsperado(eventos) {
  const resolvidos = eventos.filter((e) => e.tipo === 'resolvido');
  const suporte = eventos.filter((e) => e.tipo === 'suporte');
  const soma = resolvidos.length + suporte.length;
  const porProblema = {};
  for (const e of resolvidos.concat(suporte)) {
    const chave = String(e.problema);
    porProblema[chave] = porProblema[chave] || { resolvidos: 0, suporte: 0 };
  }
  for (const e of resolvidos) porProblema[String(e.problema)].resolvidos += 1;
  for (const e of suporte) porProblema[String(e.problema)].suporte += 1;
  return {
    resolvidos: resolvidos.length,
    encaminhadosAoSuporte: suporte.length,
    deflexaoPercentual: soma === 0 ? null : Math.round((resolvidos.length / soma) * 100),
    porProblema,
    chamadosAbertos: eventos.filter((e) => e.tipo === 'chamado').length,
    comentarios: eventos.filter((e) => e.tipo === 'comentario').length
  };
}

// Entradas inválidas que devem ser ignoradas: itens que não são objetos,
// listas dentro da lista e objetos de tipo desconhecido.
const itemInvalido = fc.oneof(
  fc.constantFrom(null, undefined, 0, 1, -1, NaN, true, false, '', 'resolvido', 'suporte', 'chamado', [], ['resolvido'], () => 1),
  fc.integer(),
  fc.string(),
  fc.array(fc.anything(), { maxLength: 3 }),
  fc.record({
    tipo: fc.oneof(
      fc.constantFrom('desconhecido', 'Resolvido', 'SUPORTE', 'avaliação', '', ' ', 'resolvido ', 'x'),
      fc.string().filter((t) => !['resolvido', 'suporte', 'chamado', 'avaliacao', 'comentario'].includes(t)),
      fc.constantFrom(null, undefined, 1, true, ['resolvido'], {})
    ),
    problema: fc.integer({ min: 1, max: 13 })
  }),
  fc.constantFrom({}, { problema: 1 }, { tipo: undefined })
);

// Lista de eventos válidos com itens inválidos intercalados.
const listaComRuido = fc
  .tuple(listaDeEventos, fc.array(itemInvalido, { maxLength: 20 }), fc.array(fc.nat(), { maxLength: 20 }))
  .map(([eventos, ruido, posicoes]) => {
    const saida = eventos.slice();
    ruido.forEach((item, i) => {
      const pos = saida.length === 0 ? 0 : posicoes[i % Math.max(posicoes.length, 1)] % (saida.length + 1);
      saida.splice(pos || 0, 0, item);
    });
    return { eventos, mista: saida };
  });

// Feature: ticket-opening-screen, Property 25: Resumo de métricas preserva a deflexão
// **Validates: Requirements 9.5, 9.6**
test('Property 25: resumirEventos conta resolvidos, suporte, chamados, deflexão e porProblema como o oráculo', () => {
  fc.assert(
    fc.property(listaComComentarios, (eventos) => {
      const r = nucleo.resumirEventos(eventos);
      const esperado = resumoEsperado(eventos);
      assert.equal(r.comentarios, esperado.comentarios);
      assert.equal(r.resolvidos, esperado.resolvidos);
      assert.equal(r.encaminhadosAoSuporte, esperado.encaminhadosAoSuporte);
      assert.equal(r.deflexaoPercentual, esperado.deflexaoPercentual);
      assert.equal(r.chamadosAbertos, esperado.chamadosAbertos);
      assert.deepEqual(r.porProblema, esperado.porProblema);
      // coerência: a soma por problema fecha com os totais
      const valores = Object.values(r.porProblema);
      assert.equal(valores.reduce((s, p) => s + p.resolvidos, 0), r.resolvidos);
      assert.equal(valores.reduce((s, p) => s + p.suporte, 0), r.encaminhadosAoSuporte);
      // deflexão: null sem decisões; senão inteiro de 0 a 100
      if (r.resolvidos + r.encaminhadosAoSuporte === 0) {
        assert.equal(r.deflexaoPercentual, null);
      } else {
        assert.equal(
          r.deflexaoPercentual,
          Math.round((r.resolvidos / (r.resolvidos + r.encaminhadosAoSuporte)) * 100)
        );
        assert.ok(Number.isInteger(r.deflexaoPercentual));
        assert.ok(r.deflexaoPercentual >= 0 && r.deflexaoPercentual <= 100);
      }
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 25: Resumo de métricas preserva a deflexão
// **Validates: Requirements 9.5, 9.6**
test('Property 25: eventos "chamado", "avaliacao" e "comentario" não alteram resolvidos, suporte, deflexão nem porProblema', () => {
  fc.assert(
    fc.property(
      listaComComentarios,
      fc.array(fc.oneof(eventoChamado, eventoAvaliacao, eventoComentarioLocal), { maxLength: 20 }),
      fc.array(fc.nat(), { maxLength: 20 }),
      (eventos, extras, posicoes) => {
        const base = eventos.filter((e) => e.tipo === 'resolvido' || e.tipo === 'suporte');
        const comExtras = base.slice();
        extras.forEach((extra, i) => {
          comExtras.splice((posicoes[i] || 0) % (comExtras.length + 1), 0, extra);
        });

        const rBase = nucleo.resumirEventos(base);
        const rExtras = nucleo.resumirEventos(comExtras);
        const rOriginal = nucleo.resumirEventos(eventos);

        for (const r of [rExtras, rOriginal]) {
          assert.equal(r.resolvidos, rBase.resolvidos);
          assert.equal(r.encaminhadosAoSuporte, rBase.encaminhadosAoSuporte);
          assert.equal(r.deflexaoPercentual, rBase.deflexaoPercentual);
          assert.deepEqual(r.porProblema, rBase.porProblema);
        }
        // sem eventos "chamado" na base, o contador reflete só os acrescentados
        assert.equal(rBase.chamadosAbertos, 0);
        assert.equal(rExtras.chamadosAbertos, extras.filter((e) => e.tipo === 'chamado').length);
        assert.equal(rOriginal.chamadosAbertos, eventos.filter((e) => e.tipo === 'chamado').length);
        // eventos "comentario" só alimentam o contador de comentários
        assert.equal(rBase.comentarios, 0);
        assert.equal(rExtras.comentarios, extras.filter((e) => e.tipo === 'comentario').length);
        assert.equal(rOriginal.comentarios, eventos.filter((e) => e.tipo === 'comentario').length);
      }
    ),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 25: Resumo de métricas preserva a deflexão
// **Validates: Requirements 9.5, 9.6**
test('Property 25: remover os eventos "chamado" só zera chamadosAbertos', () => {
  fc.assert(
    fc.property(listaComComentarios, (eventos) => {
      const semChamados = eventos.filter((e) => e.tipo !== 'chamado');
      const r = nucleo.resumirEventos(eventos);
      const s = nucleo.resumirEventos(semChamados);
      assert.equal(s.chamadosAbertos, 0);
      assert.deepEqual(Object.assign({}, r, { chamadosAbertos: 0 }), s);
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 25: Resumo de métricas preserva a deflexão
// **Validates: Requirements 9.5, 9.6**
test('Property 25: entradas inválidas (não-lista, itens não-objeto, tipos desconhecidos) são ignoradas sem lançar', () => {
  const naoLista = fc.oneof(
    fc.constantFrom(null, undefined, 0, 1, NaN, true, false, '', 'resolvido', {}, { length: 2, 0: { tipo: 'resolvido' } }, () => []),
    fc.integer(),
    fc.string(),
    fc.object()
  );
  fc.assert(
    fc.property(naoLista, (entrada) => {
      const r = nucleo.resumirEventos(entrada);
      assert.deepEqual(r, {
        resolvidos: 0,
        encaminhadosAoSuporte: 0,
        deflexaoPercentual: null,
        porProblema: {},
        chamadosAbertos: 0,
        comentarios: 0
      });
    }),
    { numRuns: 100 }
  );
  fc.assert(
    fc.property(listaComRuido, ({ eventos, mista }) => {
      assert.deepEqual(nucleo.resumirEventos(mista), nucleo.resumirEventos(eventos));
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 25: Resumo de métricas preserva a deflexão
// **Validates: Requirements 9.5, 9.6**
test('Property 25: exemplos de deflexão (lista vazia, 1 de 3, 2 de 3, só suporte)', () => {
  const ev = (tipo, problema) => ({ tipo, problema, em: '2026-01-01T00:00:00.000Z', modelo: null });
  assert.equal(nucleo.resumirEventos([]).deflexaoPercentual, null);
  assert.equal(nucleo.resumirEventos([ev('chamado', 1), ev('avaliacao', 1)]).deflexaoPercentual, null);
  assert.equal(nucleo.resumirEventos([ev('resolvido', 1), ev('suporte', 1), ev('suporte', 2)]).deflexaoPercentual, 33);
  assert.equal(nucleo.resumirEventos([ev('resolvido', 1), ev('resolvido', 2), ev('suporte', 2)]).deflexaoPercentual, 67);
  assert.equal(nucleo.resumirEventos([ev('suporte', 1)]).deflexaoPercentual, 0);
  assert.deepEqual(nucleo.resumirEventos([ev('resolvido', 1), ev('suporte', 1), ev('suporte', 2), ev('chamado', 2)]), {
    resolvidos: 1,
    encaminhadosAoSuporte: 2,
    deflexaoPercentual: 33,
    porProblema: { 1: { resolvidos: 1, suporte: 1 }, 2: { resolvidos: 0, suporte: 1 } },
    chamadosAbertos: 1,
    comentarios: 0
  });
  // eventos "comentario" são contados à parte e ignorados nos demais cálculos
  assert.deepEqual(
    nucleo.resumirEventos([ev('resolvido', 1), ev('comentario', 1), ev('comentario', 5), ev('suporte', 2), ev('chamado', 2)]),
    {
      resolvidos: 1,
      encaminhadosAoSuporte: 1,
      deflexaoPercentual: 50,
      porProblema: { 1: { resolvidos: 1, suporte: 0 }, 2: { resolvidos: 0, suporte: 1 } },
      chamadosAbertos: 1,
      comentarios: 2
    }
  );
});

/* ==========================================================
 * Property 26: Eventos de métrica sem dados pessoais
 * ========================================================== */

const { chamadoUnicode, protocoloLocal } = require('../geradores.js');

const CAMPOS_EVENTO_CHAMADO = ['tipo', 'em', 'problema', 'modelo', 'protocolo', 'modo', 'passos'];
const CAMPOS_EVENTO_AVALIACAO = ['tipo', 'em', 'problema', 'modelo', 'nota', 'desfecho', 'protocolo'];
const CAMPOS_PESSOAIS = ['nome', 'email', 'telefone', 'descricao'];

// Marcadores longos e únicos: evitam falso positivo da busca por substring
// (um nome curto como "a" apareceria em qualquer chave do JSON).
const MARCADOR_NOME = '«§NOME-PESSOAL-7f3a91§»';
const MARCADOR_EMAIL = '«§EMAIL-PESSOAL-c20b4d§»';
const MARCADOR_TELEFONE = '«§TEL-PESSOAL-5e8d02§»';
const MARCADOR_DESCRICAO = '«§DESCRICAO-PESSOAL-19ab6c§»';

// Chamado com Unicode completo e marcadores únicos no início de cada dado pessoal.
const chamadoMarcado = chamadoUnicode.map((c) =>
  Object.assign({}, c, {
    nome: MARCADOR_NOME + c.nome,
    email: MARCADOR_EMAIL + c.email,
    telefone: MARCADOR_TELEFONE + c.telefone,
    descricao: MARCADOR_DESCRICAO + c.descricao
  })
);

const MARCADORES = [MARCADOR_NOME, MARCADOR_EMAIL, MARCADOR_TELEFONE, MARCADOR_DESCRICAO];

// Valores quaisquer para `passos` e `modo` (válidos e inválidos).
const passosQualquer = fc.oneof(
  fc.nat({ max: 1000 }),
  fc.integer(),
  fc.double({ noNaN: false }),
  fc.constantFrom(0, -0, 1, -1, 1.5, NaN, Infinity, -Infinity, '3', '', null, undefined, true, [], {}),
  fc.string()
);
const modoQualquer = fc.oneof(
  fc.constantFrom('api', 'prototipo', 'API', 'Api', '', ' api', 'rede', null, undefined, 1, true, {}),
  fc.string()
);
const notaQualquer = fc.oneof(
  fc.integer({ min: 1, max: 5 }),
  fc.integer(),
  fc.double({ noNaN: false }),
  fc.constantFrom(0, 6, 1.5, 4.9999, NaN, Infinity, -Infinity, '3', '', null, undefined, true, [], [3], {})
);

const ehInteiroNaoNegativo = (x) => typeof x === 'number' && Number.isInteger(x) && x >= 0;
const ehNotaValida = (x) => typeof x === 'number' && Number.isInteger(x) && x >= 1 && x <= 5;

// Nenhum campo pessoal, nem como chave nem como valor (individual ou no JSON).
function assertSemDadosPessoais(evento, c) {
  for (const campo of CAMPOS_PESSOAIS) {
    assert.ok(!(campo in evento), 'evento não tem o campo ' + campo);
  }
  const json = JSON.stringify(evento);
  for (const marcador of MARCADORES) {
    assert.ok(!json.includes(marcador), 'JSON não contém ' + marcador);
  }
  // valores individuais: nenhum é igual ao texto completo de um dado pessoal
  for (const valor of Object.values(evento)) {
    for (const campo of CAMPOS_PESSOAIS) {
      assert.notEqual(valor, c[campo]);
      if (typeof valor === 'string') assert.ok(!valor.includes(c[campo]), 'valor não contém ' + campo);
    }
  }
}

// Feature: ticket-opening-screen, Property 26: Eventos de métrica sem dados pessoais
// **Validates: Requirements 6.13, 9.2, 9.9**
test('Property 26: eventoChamado tem só os campos permitidos e nenhum dado pessoal do Chamado', () => {
  fc.assert(
    fc.property(chamadoMarcado, protocoloLocal, modoQualquer, passosQualquer, (c, protocolo, modo, passos) => {
      const e = nucleo.eventoChamado(c, protocolo, modo, passos);
      assert.deepEqual(Object.keys(e).sort(), CAMPOS_EVENTO_CHAMADO.slice().sort());
      assert.equal(e.tipo, 'chamado');
      assert.equal(e.problema, c.problemaId);
      assert.equal(e.modelo, c.modelo === null || c.modelo === '' ? 'nao-informado' : c.modelo);
      assert.equal(e.protocolo, protocolo);
      assert.ok(e.modo === 'api' || e.modo === 'prototipo');
      assert.equal(e.modo, modo === 'api' ? 'api' : 'prototipo');
      assert.ok(ehInteiroNaoNegativo(e.passos), 'passos é inteiro >= 0');
      assert.equal(e.passos, ehInteiroNaoNegativo(passos) ? passos : 0);
      assert.equal(typeof e.em, 'string');
      assertSemDadosPessoais(e, c);
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 26: Eventos de métrica sem dados pessoais
// **Validates: Requirements 6.13, 9.3, 9.9**
test('Property 26: eventoAvaliacao tem só os campos permitidos e nenhum dado pessoal do Chamado', () => {
  fc.assert(
    fc.property(chamadoMarcado, protocoloLocal, fc.integer({ min: 1, max: 5 }), (c, protocolo, nota) => {
      const e = nucleo.eventoAvaliacao(c, protocolo, nota);
      assert.notEqual(e, null);
      assert.deepEqual(Object.keys(e).sort(), CAMPOS_EVENTO_AVALIACAO.slice().sort());
      assert.equal(e.tipo, 'avaliacao');
      assert.equal(e.desfecho, 'chamado');
      assert.equal(e.nota, nota);
      assert.equal(e.problema, c.problemaId);
      assert.equal(e.modelo, c.modelo === null || c.modelo === '' ? 'nao-informado' : c.modelo);
      assert.equal(e.protocolo, protocolo);
      assert.equal(typeof e.em, 'string');
      assertSemDadosPessoais(e, c);
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 26: Eventos de métrica sem dados pessoais
// **Validates: Requirements 9.3, 9.9**
test('Property 26: eventoAvaliacao devolve null para nota que não é inteiro de 1 a 5', () => {
  fc.assert(
    fc.property(chamadoMarcado, protocoloLocal, notaQualquer, (c, protocolo, nota) => {
      const e = nucleo.eventoAvaliacao(c, protocolo, nota);
      if (ehNotaValida(nota)) {
        assert.notEqual(e, null);
        assert.equal(e.nota, nota);
      } else {
        assert.equal(e, null);
      }
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 26: Eventos de métrica sem dados pessoais
// **Validates: Requirements 6.13, 9.2, 9.9**
test('Property 26: eventos de Chamado sem marcadores (Unicode completo) não repetem nenhum dado pessoal em campo algum', () => {
  fc.assert(
    fc.property(chamadoUnicode, protocoloLocal, fc.constantFrom('api', 'prototipo'), fc.nat({ max: 20 }), fc.integer({ min: 1, max: 5 }),
      (c, protocolo, modo, passos, nota) => {
        const eventos = [nucleo.eventoChamado(c, protocolo, modo, passos), nucleo.eventoAvaliacao(c, protocolo, nota)];
        for (const e of eventos) {
          for (const campo of CAMPOS_PESSOAIS) assert.ok(!(campo in e));
          // sem substring crua (nome curto bateria com chaves): só campos permitidos
          // e valores que não coincidem com o texto completo de um dado pessoal
          for (const valor of Object.values(e)) {
            for (const campo of CAMPOS_PESSOAIS) {
              if (c[campo].length > 0) assert.notEqual(valor, c[campo]);
            }
          }
        }
        // o JSON só reflete as chaves permitidas e sobrevive à ida e volta
        for (const e of eventos) assert.deepEqual(JSON.parse(JSON.stringify(e)), e);
      }
    ),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 26: Eventos de métrica sem dados pessoais
// **Validates: Requirements 6.13, 9.2, 9.3, 9.9**
test('Property 26: exemplos de eventoChamado e eventoAvaliacao (modelo vazio, passos e modo inválidos, nota inválida)', () => {
  const c = {
    nome: 'Ana Souza', email: 'ana@exemplo.com', telefone: '11987654321',
    descricao: 'Minha máquina não liga desde ontem', modelo: '', problemaId: 3
  };
  const e = nucleo.eventoChamado(c, 'TRES-20260101-ABC123', 'qualquer', -4, '2026-01-01T00:00:00.000Z');
  assert.deepEqual(e, {
    tipo: 'chamado', em: '2026-01-01T00:00:00.000Z', problema: 3, modelo: 'nao-informado',
    protocolo: 'TRES-20260101-ABC123', modo: 'prototipo', passos: 0
  });
  const a = nucleo.eventoAvaliacao(c, 'TRES-20260101-ABC123', 5, '2026-01-01T00:00:00.000Z');
  assert.deepEqual(a, {
    tipo: 'avaliacao', em: '2026-01-01T00:00:00.000Z', problema: 3, modelo: 'nao-informado',
    nota: 5, desfecho: 'chamado', protocolo: 'TRES-20260101-ABC123'
  });
  for (const nota of [0, 6, 2.5, '4', NaN, null, undefined]) {
    assert.equal(nucleo.eventoAvaliacao(c, 'TRES-20260101-ABC123', nota), null);
  }
});

/* ==========================================================
 * Property 27: Decisão do link da política de privacidade
 * ========================================================== */

// Oráculo independente: o link aparece se e somente se o texto aparado é uma
// URL http:/https: válida com host; nesse caso, devolve o texto aparado.
function linkEsperado(texto) {
  if (typeof texto !== 'string') return null;
  const aparado = texto.trim();
  let u;
  try {
    u = new URL(aparado);
  } catch (e) {
    return null;
  }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;
  if (!u.hostname) return null;
  return aparado;
}

const rotuloDeHost = fc.stringMatching(/^[a-z0-9]{1,10}$/);
const hostValido = fc.oneof(
  fc.array(rotuloDeHost, { minLength: 1, maxLength: 3 }).map((r) => r.join('.') + '.com'),
  fc.constantFrom('localhost', '127.0.0.1', '192.168.0.10', '[::1]', 'exemplo.com.br')
);
const portaOpcional = fc.option(fc.integer({ min: 1, max: 65535 }).map((p) => ':' + p), { nil: '' });
const caminhoOpcional = fc.oneof(
  fc.constant(''),
  fc.constant('/'),
  fc.array(fc.stringMatching(/^[a-z0-9_-]{1,8}$/), { minLength: 1, maxLength: 4 }).map((s) => '/' + s.join('/'))
);
const consultaOpcional = fc.oneof(
  fc.constant(''),
  fc.stringMatching(/^[a-z0-9=&_-]{1,12}$/).map((q) => '?' + q)
);
const fragmentoOpcional = fc.oneof(fc.constant(''), fc.stringMatching(/^[a-z0-9_-]{1,8}$/).map((f) => '#' + f));
const pontasDaUrl = fc.constantFrom('', ' ', '  ', '\t', '\n', '\r\n', ' \u00A0 ', '\u2003');

// URL http:/https: válida (esquema em maiúsculas ou minúsculas), com espaços nas pontas.
const urlHttpValida = fc
  .tuple(
    fc.constantFrom('http', 'https', 'HTTP', 'HTTPS', 'Https'),
    hostValido,
    portaOpcional,
    caminhoOpcional,
    consultaOpcional,
    fragmentoOpcional
  )
  .map(([esquema, host, porta, caminho, consulta, fragmento]) => esquema + '://' + host + porta + caminho + consulta + fragmento);

const urlHttpComPontas = fc
  .tuple(pontasDaUrl, urlHttpValida, pontasDaUrl)
  .map(([ini, url, fim]) => ({ url, texto: ini + url + fim }));

const textoAusenteOuVazio = fc.constantFrom(
  undefined, null, '', ' ', '   ', '\t', '\n', '\r\n', ' \t\n ', '\u00A0', '\u2003', '\uFEFF'
);

const naoTexto = fc.constantFrom(
  0, 1, -1, NaN, Infinity, true, false, [], ['https://exemplo.com'], {}, { href: 'https://exemplo.com' },
  { toString: () => 'https://exemplo.com' }, () => 'https://exemplo.com', Symbol('x'), 10n, new Date(0), new URL('https://exemplo.com')
);

const semProtocolo = fc.oneof(
  fc.constantFrom(
    'exemplo.com', 'www.exemplo.com', 'exemplo.com/politica', '//exemplo.com/politica', '/politica',
    'politica.html', 'localhost:3000/politica', 'exemplo.com:8080', '?https://exemplo.com', '#https://exemplo.com',
    'https//exemplo.com', 'https:/', 'texto qualquer', 'ht tp://exemplo.com'
  ),
  hostValido.map((h) => h + '/politica'),
  textoUnicodeCompleto
);

const outroProtocolo = fc
  .tuple(
    fc.constantFrom(
      'javascript:alert(1)', 'javascript://exemplo.com/%0Aalert(1)', 'data:text/html,<b>oi</b>',
      'file:///C:/politica.pdf', 'file://exemplo.com/politica', 'ftp://exemplo.com/politica',
      'mailto:privacidade@exemplo.com', 'blob:https://exemplo.com/0000', 'ws://exemplo.com', 'wss://exemplo.com',
      'tel:+5511999999999', 'about:blank', 'chrome://settings', 'JAVASCRIPT:alert(1)', 'Data:text/plain,x',
      'sftp://exemplo.com', 'ssh://exemplo.com'
    ),
    pontasDaUrl,
    pontasDaUrl
  )
  .map(([url, ini, fim]) => ini + url + fim);

const semHostOuMalformada = fc
  .tuple(
    fc.constantFrom(
      'http://', 'https://', 'http:///', 'https:///politica', 'http:', 'https:', 'http:exemplo.com', 'https:politica',
      'http://:80', 'https://:443/politica', 'http://?q=1', 'https://#x', 'http://exemplo .com', 'https://exemplo com/x',
      'http://[::1', 'https://exemplo.com:99999', 'https://exemplo.com:abc', 'http://%', 'https://exa mple.com',
      'http://<>', 'https://^', 'http://a b', 'http://[x]', 'https://999.999.999.999.999', 'http://exemplo.com:-1'
    ),
    pontasDaUrl,
    pontasDaUrl
  )
  .map(([url, ini, fim]) => ini + url + fim);

// Feature: ticket-opening-screen, Property 27: Decisão do link da política de privacidade
// **Validates: Requirements 6.5, 6.17**
test('Property 27: URL http:/https: válida com host (portas, caminhos, query, espaços nas pontas) devolve a URL aparada', () => {
  fc.assert(
    fc.property(urlHttpComPontas, ({ url, texto }) => {
      // pré-condição do gerador: o oráculo também aceita o texto
      assert.equal(linkEsperado(texto), url);
      const link = nucleo.politicaLink(texto);
      assert.equal(link, url);
      assert.equal(link, texto.trim());
      assert.equal(nucleo.politicaLink(link), link, 'idempotente');
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 27: Decisão do link da política de privacidade
// **Validates: Requirements 6.5, 6.17**
test('Property 27: texto ausente, vazio, só espaços ou que não é texto devolve null', () => {
  fc.assert(
    fc.property(fc.oneof(textoAusenteOuVazio, naoTexto), (valor) => {
      assert.equal(nucleo.politicaLink(valor), null);
      assert.equal(linkEsperado(valor), null);
    }),
    { numRuns: 100 }
  );
  assert.equal(nucleo.politicaLink(), null);
});

// Feature: ticket-opening-screen, Property 27: Decisão do link da política de privacidade
// **Validates: Requirements 6.5, 6.17**
test('Property 27: texto sem protocolo devolve null', () => {
  fc.assert(
    fc.property(semProtocolo, (texto) => {
      const esperado = linkEsperado(texto);
      assert.equal(nucleo.politicaLink(texto), esperado);
    }),
    { numRuns: 200 }
  );
  for (const texto of ['exemplo.com', 'www.exemplo.com/politica', '//exemplo.com/politica', '/politica']) {
    assert.equal(nucleo.politicaLink(texto), null);
  }
});

// Feature: ticket-opening-screen, Property 27: Decisão do link da política de privacidade
// **Validates: Requirements 6.5, 6.17**
test('Property 27: outros protocolos (javascript:, data:, file:, ftp:, mailto:, blob:) devolvem null', () => {
  fc.assert(
    fc.property(outroProtocolo, (texto) => {
      assert.equal(nucleo.politicaLink(texto), null);
      assert.equal(linkEsperado(texto), null);
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 27: Decisão do link da política de privacidade
// **Validates: Requirements 6.5, 6.17**
test('Property 27: http/https sem host e URL malformada devolvem null', () => {
  fc.assert(
    fc.property(semHostOuMalformada, (texto) => {
      assert.equal(nucleo.politicaLink(texto), linkEsperado(texto));
    }),
    { numRuns: 100 }
  );
  for (const texto of ['http://', 'https://', 'http:///', 'http:', 'https://:443/politica', 'http://?q=1', 'http://[::1', 'https://exa mple.com']) {
    assert.equal(nucleo.politicaLink(texto), null, texto);
  }
  // Pela WHATWG, barras a mais após http(s): são ignoradas e "politica" vira o host:
  // é uma URL com host, então o oráculo e o núcleo concordam em aceitar.
  assert.equal(nucleo.politicaLink('https:///politica'), 'https:///politica');
});

// Feature: ticket-opening-screen, Property 27: Decisão do link da política de privacidade
// **Validates: Requirements 6.5, 6.17**
test('Property 27: para qualquer texto, politicaLink coincide com o oráculo new URL(texto.trim())', () => {
  const qualquerEntrada = fc.oneof(
    urlHttpComPontas.map((x) => x.texto),
    outroProtocolo,
    semHostOuMalformada,
    semProtocolo,
    textoAusenteOuVazio,
    naoTexto,
    fc.string(),
    fc.webUrl().chain((u) => fc.tuple(pontasDaUrl, pontasDaUrl).map(([ini, fim]) => ini + u + fim)),
    fc.webUrl({ validSchemes: ['http', 'https', 'ftp', 'file'] })
  );
  fc.assert(
    fc.property(qualquerEntrada, (entrada) => {
      const esperado = linkEsperado(entrada);
      const obtido = nucleo.politicaLink(entrada);
      assert.equal(obtido, esperado);
      // o link só existe para http:/https: e nunca é mais longo que a entrada
      if (obtido !== null) {
        assert.equal(typeof obtido, 'string');
        assert.match(obtido, /^https?:/i);
        assert.equal(obtido, obtido.trim());
      }
    }),
    { numRuns: 300 }
  );
});

// Feature: ticket-opening-screen, Property 27: Decisão do link da política de privacidade
// **Validates: Requirements 6.5, 6.17**
test('Property 27: exemplos concretos da decisão do link', () => {
  assert.equal(nucleo.politicaLink('https://exemplo.com/politica'), 'https://exemplo.com/politica');
  assert.equal(nucleo.politicaLink('  http://localhost:8080/p?x=1#a  '), 'http://localhost:8080/p?x=1#a');
  assert.equal(nucleo.politicaLink('\n\thttps://exemplo.com\n'), 'https://exemplo.com');
  for (const texto of [
    undefined, null, '', '   ', 42, {}, 'exemplo.com', 'javascript:alert(1)', 'data:text/html,x', 'file:///x',
    'ftp://exemplo.com', 'mailto:a@b.com', 'blob:https://exemplo.com/1', 'https://', 'http:///', 'https://exa mple.com'
  ]) {
    assert.equal(nucleo.politicaLink(texto), null, String(texto));
  }
});

/* ==========================================================
 * Property 28: Conteúdo indisponível
 * ========================================================== */

// TRES_DATA.CHAMADO real (js/data.js, carregado via vm).
function carregarChamadoReal() {
  const arquivo = path.join(__dirname, '..', '..', 'js', 'data.js');
  const janela = {};
  const contexto = vm.createContext({ window: janela });
  vm.runInContext(fs.readFileSync(arquivo, 'utf8'), contexto, { filename: arquivo });
  return janela.TRES_DATA.CHAMADO;
}

const CHAMADO_REAL = carregarChamadoReal();
const CHAVES_OBRIGATORIAS = nucleo.CHAVES_TEXTOS_OBRIGATORIOS;

// Cópia profunda (JSON): o CHAMADO é só dados e o vm cria objetos de outro realm.
const copiarChamado = () => JSON.parse(JSON.stringify(CHAMADO_REAL));

function congelarProfundo(valor) {
  if (valor && typeof valor === 'object' && !Object.isFrozen(valor)) {
    Object.freeze(valor);
    Object.values(valor).forEach(congelarProfundo);
  }
  return valor;
}

// Alterações que deixam um texto obrigatório inválido: ausente, vazio, só espaços ou não texto.
const alteracaoDeTexto = fc.oneof(
  fc.constant({ tipo: 'remover' }),
  fc.constantFrom('', ' ', '   ', '\t', '\n', '\r\n', '\u00A0', '\u2003', '\uFEFF', ' \t\n ')
    .map((valor) => ({ tipo: 'definir', valor })),
  fc.array(fc.constantFrom(' ', '\t', '\n', '\u00A0', '\u2003', '\uFEFF'), { minLength: 1, maxLength: 12 })
    .map((p) => ({ tipo: 'definir', valor: p.join('') })),
  fc.constantFrom(null, undefined, 0, 1, -1, NaN, Infinity, true, false, [], ['texto'], {}, { toString: () => 'texto' })
    .map((valor) => ({ tipo: 'definir', valor })),
  fc.oneof(fc.integer(), fc.double(), fc.boolean(), fc.array(fc.string(), { maxLength: 3 }), fc.object({ maxDepth: 1 }))
    .map((valor) => ({ tipo: 'definir', valor }))
);

// Uma ou mais chaves obrigatórias, cada uma com a sua alteração.
const alteracoesDeTextos = fc.uniqueArray(
  fc.tuple(fc.constantFrom(...CHAVES_OBRIGATORIAS), alteracaoDeTexto),
  { minLength: 1, maxLength: 10, selector: ([chave]) => chave }
);

function aplicarAlteracoes(chamado, alteracoes) {
  for (const [chave, alteracao] of alteracoes) {
    if (alteracao.tipo === 'remover') delete chamado.textos[chave];
    else chamado.textos[chave] = alteracao.valor;
  }
  return chamado;
}

// Valores que não são objeto (config/privacidade/textos), além de "ausente".
// Inclui arrays (typeof 'object', mas não são objeto de configuração).
const naoObjeto = fc.constantFrom(
  'ausente', null, undefined, 0, 1, -1, NaN, true, false, '', 'texto', ' ', () => ({}),
  [], [1, 2], [{}], ['x']
);

const secaoObrigatoria = fc.constantFrom('config', 'privacidade', 'textos');

// Entradas que não são um objeto de dados do chamado.
const entradaNaoObjeto = fc.oneof(
  fc.constantFrom(
    null, undefined, 0, 1, -1, NaN, Infinity, true, false, '', ' ', 'texto', [], [1, 2], [{}], [copiarChamado()],
    () => copiarChamado(), Symbol('x'), 10n
  ),
  fc.integer(),
  fc.double(),
  fc.string(),
  fc.array(fc.anything(), { maxLength: 4 })
);

// Feature: ticket-opening-screen, Property 28: Conteúdo indisponível
// **Validates: Requirements 12.6**
test('Property 28: textosValidos é true para o CHAMADO real de data.js, inclusive em cópia profunda', () => {
  assert.equal(nucleo.textosValidos(CHAMADO_REAL), true);
  assert.equal(nucleo.textosValidos(copiarChamado()), true);
  fc.assert(
    fc.property(fc.constant(null), () => {
      assert.equal(nucleo.textosValidos(copiarChamado()), true);
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 28: Conteúdo indisponível
// **Validates: Requirements 12.6**
test('Property 28: textosValidos é false se qualquer chave obrigatória estiver ausente, vazia, só com espaços ou não for texto', () => {
  fc.assert(
    fc.property(alteracoesDeTextos, (alteracoes) => {
      const chamado = aplicarAlteracoes(copiarChamado(), alteracoes);
      assert.equal(nucleo.textosValidos(chamado), false);
    }),
    { numRuns: 300 }
  );
});

// Feature: ticket-opening-screen, Property 28: Conteúdo indisponível
// **Validates: Requirements 12.6**
test('Property 28: cada chave obrigatória sozinha, removida ou esvaziada, torna o conteúdo inválido', () => {
  fc.assert(
    fc.property(fc.constantFrom(...CHAVES_OBRIGATORIAS), alteracaoDeTexto, (chave, alteracao) => {
      const chamado = aplicarAlteracoes(copiarChamado(), [[chave, alteracao]]);
      assert.equal(nucleo.textosValidos(chamado), false, chave);
    }),
    { numRuns: 300 }
  );
  for (const chave of CHAVES_OBRIGATORIAS) {
    for (const alteracao of [{ tipo: 'remover' }, { tipo: 'definir', valor: '' }, { tipo: 'definir', valor: '  \t ' }, { tipo: 'definir', valor: 5 }]) {
      assert.equal(nucleo.textosValidos(aplicarAlteracoes(copiarChamado(), [[chave, alteracao]])), false, chave);
    }
  }
});

// Feature: ticket-opening-screen, Property 28: Conteúdo indisponível
// **Validates: Requirements 12.6**
test('Property 28: textosValidos é false se config, privacidade ou textos faltarem ou não forem objetos', () => {
  fc.assert(
    fc.property(secaoObrigatoria, naoObjeto, (secao, valor) => {
      const chamado = copiarChamado();
      if (valor === 'ausente') delete chamado[secao];
      else chamado[secao] = valor;
      assert.equal(nucleo.textosValidos(chamado), false, secao + ' = ' + String(valor));
    }),
    { numRuns: 100 }
  );
  // Combinação: seção inválida junto com alterações nos textos continua inválida.
  fc.assert(
    fc.property(secaoObrigatoria, naoObjeto, alteracoesDeTextos, (secao, valor, alteracoes) => {
      const chamado = aplicarAlteracoes(copiarChamado(), alteracoes);
      if (valor === 'ausente') delete chamado[secao];
      else chamado[secao] = valor;
      assert.equal(nucleo.textosValidos(chamado), false);
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 28: Conteúdo indisponível
// **Validates: Requirements 12.6**
test('Property 28: array no lugar de config, privacidade ou textos é rejeitado (não é objeto)', () => {
  for (const secao of ['config', 'privacidade', 'textos']) {
    for (const valor of [[], [1, 2], [{}], [copiarChamado()[secao]]]) {
      const chamado = copiarChamado();
      chamado[secao] = valor;
      assert.equal(nucleo.textosValidos(chamado), false, secao + ' = array');
    }
  }
  // O próprio dadosChamado como array (mesmo com as chaves penduradas) também é inválido.
  const comoArray = Object.assign([], copiarChamado());
  assert.equal(nucleo.textosValidos(comoArray), false);
});

// Feature: ticket-opening-screen, Property 28: Conteúdo indisponível
// **Validates: Requirements 12.6**
test('Property 28: entradas que não são objeto (null, undefined, números, texto, array) devolvem false sem lançar', () => {
  fc.assert(
    fc.property(entradaNaoObjeto, (entrada) => {
      assert.equal(nucleo.textosValidos(entrada), false);
    }),
    { numRuns: 200 }
  );
  assert.equal(nucleo.textosValidos(), false);
  assert.equal(nucleo.textosValidos({}), false);
});

// Feature: ticket-opening-screen, Property 28: Conteúdo indisponível
// **Validates: Requirements 12.6**
test('Property 28: textosValidos não altera a entrada (válida ou inválida) e não lança', () => {
  fc.assert(
    fc.property(fc.option(alteracoesDeTextos, { nil: null }), (alteracoes) => {
      const chamado = alteracoes ? aplicarAlteracoes(copiarChamado(), alteracoes) : copiarChamado();
      const antes = JSON.stringify(chamado);
      // Congelado: qualquer escrita na entrada falharia (modo estrito) ou seria ignorada.
      congelarProfundo(chamado);
      const resultado = nucleo.textosValidos(chamado);
      assert.equal(resultado, alteracoes === null);
      assert.equal(JSON.stringify(chamado), antes);
      assert.equal(Object.isFrozen(chamado), true);
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 28: Conteúdo indisponível
// **Validates: Requirements 12.6**
test('Property 28: FRASE_CONTEUDO_INDISPONIVEL é texto não vazio e a lista de chaves obrigatórias é válida', () => {
  assert.equal(typeof nucleo.FRASE_CONTEUDO_INDISPONIVEL, 'string');
  assert.ok(nucleo.FRASE_CONTEUDO_INDISPONIVEL.trim().length > 0);
  assert.ok(Array.isArray(CHAVES_OBRIGATORIAS));
  assert.ok(CHAVES_OBRIGATORIAS.length > 0);
  assert.equal(new Set(CHAVES_OBRIGATORIAS).size, CHAVES_OBRIGATORIAS.length, 'sem chaves repetidas');
  for (const chave of CHAVES_OBRIGATORIAS) {
    assert.equal(typeof chave, 'string');
    assert.ok(chave.length > 0);
  }
});

// Feature: ticket-opening-screen, Property 28: Conteúdo indisponível
// **Validates: Requirements 12.6**
test('Property 28: toda chave de CHAVES_TEXTOS_OBRIGATORIOS existe em textos de data.js com texto não vazio', () => {
  const textos = CHAMADO_REAL.textos;
  for (const chave of CHAVES_OBRIGATORIAS) {
    assert.ok(Object.prototype.hasOwnProperty.call(textos, chave), 'falta em data.js: ' + chave);
    assert.equal(typeof textos[chave], 'string', chave);
    assert.ok(textos[chave].trim().length > 0, 'vazio em data.js: ' + chave);
  }
});

// Feature: ticket-opening-screen, Property 28: Conteúdo indisponível
// **Validates: Requirements 12.6**
test('Property 28: toda chave referenciada por data-texto em index.html existe em textos de data.js', () => {
  const arquivo = path.join(__dirname, '..', '..', 'index.html');
  const html = fs.readFileSync(arquivo, 'utf8');
  const usadas = new Set();
  for (const m of html.matchAll(/\bdata-texto\s*=\s*(?:"([^"]*)"|'([^']*)')/g)) usadas.add(m[1] !== undefined ? m[1] : m[2]);
  assert.ok(usadas.size > 0, 'index.html deve referenciar ao menos um data-texto');
  const textos = CHAMADO_REAL.textos;
  for (const chave of usadas) {
    assert.ok(Object.prototype.hasOwnProperty.call(textos, chave), 'index.html usa data-texto="' + chave + '" que não existe em data.js');
    assert.equal(typeof textos[chave], 'string', chave);
    assert.ok(textos[chave].trim().length > 0, 'vazio em data.js: ' + chave);
  }
});
