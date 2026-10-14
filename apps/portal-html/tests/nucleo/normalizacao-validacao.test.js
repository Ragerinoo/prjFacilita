'use strict';
// Testes de propriedade da normalização e da validação (js/chamado.js).
// Cada propriedade fica em um `test` próprio; outras tarefas acrescentam
// testes a este arquivo.

const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const nucleo = require(path.join(__dirname, '..', '..', 'js', 'chamado.js'));
const {
  fc,
  textoUnicodeCompleto,
  nomeValido,
  nomeBruto,
  emailValido,
  emailBruto,
  emailInvalido,
  descricaoValida,
  descricaoBruta,
  descricaoCurta,
  descricaoLonga,
  textoParaDescricao,
  telefoneValidoComOraculo,
  telefoneValido,
  telefoneInvalido
} = require('../geradores.js');

test('Property 1: normalização de texto é idempotente', () => {
  // Texto qualquer: Unicode completo (com surrogates soltos) ou o formato
  // bruto de Nome, E-mail e Descrição, como o consumidor digitaria.
  const textoQualquer = fc.oneof(textoUnicodeCompleto, nomeBruto, emailBruto, descricaoBruta);
  const normalizacoes = [
    ['normalizarNome', nucleo.normalizarNome],
    ['normalizarEmail', nucleo.normalizarEmail],
    ['normalizarDescricao', nucleo.normalizarDescricao]
  ];

  // Feature: ticket-opening-screen, Property 1: Normalização de texto é idempotente
  fc.assert(
    fc.property(textoQualquer, (texto) => {
      for (const [nome, normalizar] of normalizacoes) {
        const uma = normalizar(texto);
        const duas = normalizar(uma);
        assert.equal(duas, uma, nome + ' não é idempotente para ' + JSON.stringify(texto));
      }
    }),
    { numRuns: 200 }
  );
});

test('Property 2: telefone válido normaliza para 10 ou 11 dígitos', () => {
  // Feature: ticket-opening-screen, Property 2: Telefone válido normaliza para 10 ou 11 dígitos
  // **Validates: Requirements 5.3, 7.3, 10.5**
  fc.assert(
    fc.property(telefoneValidoComOraculo, ({ nacional, texto }) => {
      const normalizado = nucleo.normalizarTelefone(texto);
      const contexto = ' para ' + JSON.stringify(texto);

      assert.equal(typeof normalizado, 'string', 'resultado não é texto' + contexto);
      assert.match(normalizado, /^[0-9]{10,11}$/, 'não são 10 ou 11 dígitos 0-9' + contexto);
      assert.equal(normalizado, nacional, 'difere do número nacional esperado' + contexto);
      assert.equal(nucleo.normalizarTelefone(normalizado), normalizado, 'não é idempotente' + contexto);
    }),
    { numRuns: 300 }
  );
});

test('Property 3: validação do telefone', () => {
  const CODIGOS = ['vazio', 'tamanho', 'formato'];

  // Feature: ticket-opening-screen, Property 3: Validação do telefone
  // **Validates: Requirements 5.3, 5.4**
  fc.assert(
    fc.property(
      fc.oneof(
        telefoneValido.map((texto) => ({ valido: true, texto })),
        telefoneInvalido.map((texto) => ({ valido: false, texto })),
        // vazio ou apenas espaços
        fc
          .array(fc.constantFrom(' ', '\t', '\n', '\u00A0'), { maxLength: 8 })
          .map((partes) => ({ valido: false, texto: partes.join(''), vazio: true }))
      ),
      ({ valido, texto, vazio }) => {
        const codigo = nucleo.validarTelefone(texto);
        const contexto = ' para ' + JSON.stringify(texto);

        if (valido) {
          assert.equal(codigo, null, 'telefone válido foi rejeitado' + contexto);
        } else {
          assert.ok(CODIGOS.includes(codigo), 'telefone inválido sem código válido (' + codigo + ')' + contexto);
          if (vazio) assert.equal(codigo, 'vazio', 'vazio deveria devolver "vazio"' + contexto);
        }
      }
    ),
    { numRuns: 300 }
  );
});

// ---------------------------------------------------------------------------
// Property 4: validação do nome
// Oráculo independente: separa por espaços em branco e junta com um espaço
// (sem usar normalizarNome), mede com String.length e procura letras com \p{L}.
// ---------------------------------------------------------------------------

function esperadoNome(texto) {
  const normalizado = texto.split(/\s+/).filter((parte) => parte.length > 0).join(' ');
  if (normalizado.length === 0) return 'vazio';
  if (normalizado.length < 3 || normalizado.length > 100) return 'tamanho';
  if (!/\p{L}/u.test(normalizado)) return 'formato';
  return null;
}

// Textos que o oráculo e a implementação devem tratar igual: Unicode completo,
// nomes brutos e construções de borda (tamanhos, dígitos, símbolos, espaços).
const caracteresDeBorda = fc.constantFrom('a', 'é', 'Ç', '1', '7', '-', '!', '@', '😀', ' ', '\t', '\n', '\u00A0');
const nomeDeBorda = fc.oneof(
  fc.string({ unit: caracteresDeBorda, maxLength: 110 }),
  fc.integer({ min: 0, max: 110 }).chain((n) =>
    fc.constantFrom('a', 'ã', '5', '#', ' ').map((c) => c.repeat(n))
  ),
  // símbolos/dígitos com uma única letra no fim
  fc.tuple(fc.string({ unit: fc.constantFrom('1', '2', '-', '.', '!', ' '), maxLength: 50 }), fc.constantFrom('a', 'é', 'Z'))
    .map(([resto, l]) => resto + l)
);

test('Property 4: validação do nome', () => {
  // Feature: ticket-opening-screen, Property 4: Validação do nome
  // **Validates: Requirements 5.1**
  fc.assert(
    fc.property(
      fc.oneof(textoUnicodeCompleto, nomeBruto, nomeValido, nomeDeBorda),
      (texto) => {
        const obtido = nucleo.validarNome(texto);
        const esperado = esperadoNome(texto);
        assert.equal(obtido, esperado, 'código divergente para ' + JSON.stringify(texto));
        assert.equal(obtido === null, esperado === null);
      }
    ),
    { numRuns: 300 }
  );
});

test('Property 4: nome aceito continua aceito com espaços extras', () => {
  const espacos = fc.array(fc.constantFrom(' ', '  ', '\t', '\n', '\u00A0'), { maxLength: 4 }).map((p) => p.join(''));

  // Feature: ticket-opening-screen, Property 4: Validação do nome
  // **Validates: Requirements 5.1**
  fc.assert(
    fc.property(
      nomeValido,
      espacos,
      espacos,
      fc.array(fc.constantFrom(' ', '   ', '\t'), { minLength: 1, maxLength: 3 }),
      (nome, antes, depois, extras) => {
        assert.equal(nucleo.validarNome(nome), null, 'nome válido foi rejeitado: ' + JSON.stringify(nome));
        // duplica o primeiro espaço interno (se houver) e acrescenta espaços nas pontas
        const duplicado = nome.replace(' ', ' ' + extras.join(''));
        for (const variante of [antes + nome + depois, duplicado, antes + duplicado + depois]) {
          assert.equal(nucleo.validarNome(variante), null, 'variante rejeitada: ' + JSON.stringify(variante));
        }
      }
    ),
    { numRuns: 200 }
  );
});

test('Property 4: casos de borda do nome', () => {
  const casos = [
    ['', 'vazio'],
    ['   ', 'vazio'],
    ['\t\n \u00A0', 'vazio'],
    ['a', 'tamanho'],
    ['ab', 'tamanho'],
    ['  ab  ', 'tamanho'],
    ['a  b', null], // normaliza para 'a b' (3 caracteres)
    ['abc', null],
    ['  abc  ', null],
    ['é'.repeat(2), 'tamanho'],
    ['é'.repeat(3), null],
    ['Ç'.repeat(3), null],
    ['a'.repeat(100), null],
    ['a'.repeat(101), 'tamanho'],
    [' ' + 'a'.repeat(100) + ' ', null],
    ['a'.repeat(50) + '     ' + 'a'.repeat(49), null], // 100 após reduzir espaços
    ['a'.repeat(50) + ' ' + 'a'.repeat(50), 'tamanho'], // 101
    ['123', 'formato'],
    ['1234567', 'formato'],
    ['---', 'formato'],
    ['!@#$%', 'formato'],
    ['12 34', 'formato'],
    ['1a2', null],
    ['--é', null],
    ['José da Silva', null],
    ['Ação', null]
  ];
  for (const [texto, esperado] of casos) {
    assert.equal(nucleo.validarNome(texto), esperado, 'nome ' + JSON.stringify(texto.slice(0, 30)) + ' (' + texto.length + ')');
  }
});

// ---------------------------------------------------------------------------
// Property 5: validação do e-mail
// Oráculo independente: uma única expressão regular sobre o texto aparado
// (a implementação percorre as partes uma a uma), com os códigos
// 'vazio' (nada após o trim), 'tamanho' (mais de 254) e 'formato'.
//   local: 1+ caracteres sem '@' nem espaço em branco
//   domínio: rótulos não vazios (sem '@', espaço ou ponto) separados por ponto
//   terminação: último rótulo só de letras ASCII, 2 ou mais
// ---------------------------------------------------------------------------

const REGEX_EMAIL = /^[^@\s]+@(?:[^@\s.]+\.)+[a-zA-Z]{2,}$/;

function esperadoEmail(texto) {
  const aparado = texto.trim();
  if (aparado.length === 0) return 'vazio';
  if (aparado.length > 254) return 'tamanho';
  return REGEX_EMAIL.test(aparado) ? null : 'formato';
}

// Constrói um e-mail com exatamente `total` caracteres: local de 'a' + '@x.com'.
const emailComTamanho = (total) => 'a'.repeat(total - '@x.com'.length) + '@x.com';

// Caracteres e pedaços que exercitam as bordas do formato.
const pedacosDeEmail = fc.constantFrom(
  'a', 'Z', '7', 'é', '.', '..', '@', '@@', ' ', '\t', '\n', '\u00A0', '-', '_', '+', '😀', 'com', 'COM', 'br', 'x1'
);
const emailDeBorda = fc.oneof(
  fc.array(pedacosDeEmail, { maxLength: 10 }).map((p) => p.join('')),
  // quase válidos: monta partes e escolhe livremente cada uma
  fc
    .tuple(
      fc.constantFrom('', 'a', 'jo.ao', 'a b', 'a@b', '😀'),
      fc.constantFrom('', '@', '@@'),
      fc.constantFrom('', 'x', 'x.y', '.x', 'x.', 'x..y', 'ex.com', 'ex.COM', 'ex.c', 'ex.c0m', 'ex.123', 'ex.com.br', 'ex com.br', 'EX.CoM'),
      fc.constantFrom('', ' ', '\t', '\n', ' \u00A0 ')
    )
    .map(([local, arroba, dominio, borda]) => borda + local + arroba + dominio + borda),
  // perto do limite de 254 caracteres
  fc.integer({ min: 245, max: 262 }).map(emailComTamanho),
  fc.integer({ min: 245, max: 262 }).map((n) => ' ' + emailComTamanho(n) + ' ')
);

test('Property 5: validação do e-mail', () => {
  // Feature: ticket-opening-screen, Property 5: Validação do e-mail
  // **Validates: Requirements 5.2**
  fc.assert(
    fc.property(
      fc.oneof(textoUnicodeCompleto, emailValido, emailBruto, emailInvalido, emailDeBorda),
      (texto) => {
        const obtido = nucleo.validarEmail(texto);
        const esperado = esperadoEmail(texto);
        assert.equal(obtido, esperado, 'código divergente para ' + JSON.stringify(texto));
        assert.equal(obtido === null, esperado === null);
      }
    ),
    { numRuns: 500 }
  );
});

test('Property 5: e-mail montado corretamente é aceito, em qualquer caixa e com espaços nas pontas', () => {
  // Feature: ticket-opening-screen, Property 5: Validação do e-mail
  // **Validates: Requirements 5.2**
  fc.assert(
    fc.property(emailValido, emailBruto, (valido, bruto) => {
      assert.equal(nucleo.validarEmail(valido), null, 'válido rejeitado: ' + JSON.stringify(valido));
      assert.equal(nucleo.validarEmail(valido.toUpperCase()), null, 'maiúsculas rejeitadas: ' + JSON.stringify(valido));
      assert.equal(nucleo.validarEmail(bruto), null, 'bruto rejeitado: ' + JSON.stringify(bruto));
    }),
    { numRuns: 200 }
  );
});

test('Property 5: mutação do e-mail válido é rejeitada com "formato"', () => {
  // Feature: ticket-opening-screen, Property 5: Validação do e-mail
  // **Validates: Requirements 5.2**
  fc.assert(
    fc.property(emailInvalido, (texto) => {
      assert.equal(nucleo.validarEmail(texto), 'formato', 'inválido não rejeitado: ' + JSON.stringify(texto));
    }),
    { numRuns: 200 }
  );
});

test('Property 5: casos de borda do e-mail', () => {
  const casos = [
    ['', 'vazio'],
    ['   ', 'vazio'],
    ['\t\n \u00A0', 'vazio'],
    ['a@b.co', null],
    ['  a@b.co  ', null],
    ['A@B.CO', null],
    ['Joao.Silva@Exemplo.COM.BR', null],
    ['a@b.c', 'formato'], // terminação de 1 letra
    ['a@b.c0', 'formato'], // terminação com dígito
    ['a@b.123', 'formato'],
    ['a@b.co1', 'formato'],
    ['a@@b.co', 'formato'],
    ['a@b@c.co', 'formato'],
    ['@b.co', 'formato'],
    ['a@', 'formato'],
    ['a', 'formato'],
    ['a@b', 'formato'], // domínio sem ponto
    ['a@.b.co', 'formato'],
    ['a@b.co.', 'formato'],
    ['a@b..co', 'formato'],
    ['a b@c.co', 'formato'],
    ['a@b .co', 'formato'],
    ['a@b.co x', 'formato'],
    ['a\tb@c.co', 'formato'],
    ['a@b.c\no', 'formato'],
    [emailComTamanho(254), null],
    [emailComTamanho(255), 'tamanho'],
    [' ' + emailComTamanho(254) + ' ', null], // 254 após o trim
    [' ' + emailComTamanho(255) + ' ', 'tamanho'],
    ['a'.repeat(300), 'tamanho'] // tamanho vence formato
  ];
  for (const [texto, esperado] of casos) {
    assert.equal(nucleo.validarEmail(texto), esperado, 'e-mail ' + JSON.stringify(texto.slice(0, 40)) + ' (' + texto.length + ')');
  }
  assert.equal(emailComTamanho(254).length, 254);
  assert.equal(emailComTamanho(255).length, 255);
});

// ---------------------------------------------------------------------------
// Property 6: descrição, contador e truncamento
// Oráculo independente: String.prototype.trim e String.length (unidades
// UTF-16), com os códigos 'vazio' (nada após o trim) e 'tamanho' (< 10 ou > 500).
// ---------------------------------------------------------------------------

function esperadoDescricao(texto) {
  const aparado = texto.trim();
  if (aparado.length === 0) return 'vazio';
  if (aparado.length < 10 || aparado.length > 500) return 'tamanho';
  return null;
}

// Descrição com exatamente `n` caracteres após o trim, com espaços e quebras nas pontas.
const descricaoComTamanho = (n) => 'x'.repeat(n);
const bordasDeDescricao = fc
  .tuple(
    fc.constantFrom(0, 1, 8, 9, 10, 11, 499, 500, 501, 502),
    fc.constantFrom('', ' ', '\n', '\t ', '\u00A0'),
    fc.constantFrom('', ' ', '\n', ' \t\n')
  )
  .map(([n, ini, fim]) => ini + descricaoComTamanho(n) + fim);

test('Property 6: validação da descrição aceita se e somente se o texto aparado tem de 10 a 500 caracteres', () => {
  // Feature: ticket-opening-screen, Property 6: Descrição, contador e truncamento
  // **Validates: Requirements 4.9, 4.10, 5.5, 5.13**
  fc.assert(
    fc.property(
      fc.oneof(textoUnicodeCompleto, textoParaDescricao, descricaoBruta, descricaoValida, descricaoCurta, descricaoLonga, bordasDeDescricao),
      (texto) => {
        const obtido = nucleo.validarDescricao(texto);
        const esperado = esperadoDescricao(texto);
        const contexto = ' para ' + JSON.stringify(texto.slice(0, 40)) + ' (' + texto.length + ')';
        assert.equal(obtido, esperado, 'código divergente' + contexto);
        assert.equal(obtido === null, texto.trim().length >= 10 && texto.trim().length <= 500, 'aceite divergente' + contexto);
      }
    ),
    { numRuns: 500 }
  );
});

test('Property 6: descrições dos geradores recebem o código esperado', () => {
  // Feature: ticket-opening-screen, Property 6: Descrição, contador e truncamento
  // **Validates: Requirements 4.9, 4.10, 5.5, 5.13**
  fc.assert(
    fc.property(descricaoValida, descricaoBruta, descricaoCurta, descricaoLonga, (valida, bruta, curta, longa) => {
      assert.equal(nucleo.validarDescricao(valida), null, 'válida rejeitada: ' + JSON.stringify(valida.slice(0, 40)));
      assert.equal(nucleo.validarDescricao(bruta), null, 'bruta rejeitada: ' + JSON.stringify(bruta.slice(0, 40)));
      assert.equal(nucleo.validarDescricao(curta), 'tamanho', 'curta não rejeitada: ' + JSON.stringify(curta));
      assert.equal(nucleo.validarDescricao(longa), 'tamanho', 'longa não rejeitada (' + longa.trim().length + ')');
    }),
    { numRuns: 200 }
  );
});

test('Property 6: limitarDescricao mantém os 500 primeiros caracteres e é idempotente', () => {
  // Feature: ticket-opening-screen, Property 6: Descrição, contador e truncamento
  // **Validates: Requirements 4.9, 4.10, 5.5, 5.13**
  fc.assert(
    fc.property(fc.oneof(textoParaDescricao, textoUnicodeCompleto, descricaoLonga, descricaoBruta), (texto) => {
      const limitado = nucleo.limitarDescricao(texto);
      const contexto = ' para texto de ' + texto.length + ' caracteres';

      assert.equal(limitado, texto.slice(0, 500), 'diferente de slice(0, 500)' + contexto);
      assert.ok(limitado.length <= 500, 'passou de 500' + contexto);
      assert.ok(texto.startsWith(limitado), 'não é prefixo do original' + contexto);
      if (texto.length <= 500) assert.equal(limitado, texto, 'alterou texto de até 500' + contexto);
      assert.equal(nucleo.limitarDescricao(limitado), limitado, 'não é idempotente' + contexto);
    }),
    { numRuns: 300 }
  );
});

test('Property 6: contador mostra "N de 500 caracteres" e nunca passa de 500 depois de limitar', () => {
  // Feature: ticket-opening-screen, Property 6: Descrição, contador e truncamento
  // **Validates: Requirements 4.9, 4.10, 5.5, 5.13**
  fc.assert(
    fc.property(fc.oneof(textoParaDescricao, textoUnicodeCompleto, descricaoLonga), (texto) => {
      const limitado = nucleo.limitarDescricao(texto);
      const contexto = ' para texto de ' + texto.length + ' caracteres';

      assert.equal(nucleo.formatarContador(texto), texto.length + ' de 500 caracteres', 'contador do texto' + contexto);
      assert.equal(nucleo.formatarContador(texto.length), texto.length + ' de 500 caracteres', 'contador do número' + contexto);
      assert.equal(nucleo.formatarContador(limitado), limitado.length + ' de 500 caracteres', 'contador do limitado' + contexto);
      assert.match(nucleo.formatarContador(limitado), /^([0-9]|[1-9][0-9]|[1-4][0-9]{2}|500) de 500 caracteres$/, 'N acima de 500' + contexto);
    }),
    { numRuns: 300 }
  );
});

test('Property 6: casos de borda da descrição, do limite e do contador', () => {
  const casos = [
    ['', 'vazio'],
    ['   \n\t ', 'vazio'],
    [descricaoComTamanho(9), 'tamanho'],
    [descricaoComTamanho(10), null],
    [descricaoComTamanho(500), null],
    [descricaoComTamanho(501), 'tamanho'],
    ['  ' + descricaoComTamanho(9) + '  ', 'tamanho'], // espaços não contam
    ['  ' + descricaoComTamanho(10) + '\n', null],
    ['  ' + descricaoComTamanho(500) + '  ', null], // 500 após o trim, 504 no total
    ['\n' + descricaoComTamanho(501) + ' ', 'tamanho']
  ];
  for (const [texto, esperado] of casos) {
    assert.equal(nucleo.validarDescricao(texto), esperado, 'descrição de ' + texto.length + ' caracteres');
  }

  // limitarDescricao
  assert.equal(nucleo.limitarDescricao(''), '');
  assert.equal(nucleo.limitarDescricao(descricaoComTamanho(499)), descricaoComTamanho(499));
  assert.equal(nucleo.limitarDescricao(descricaoComTamanho(500)), descricaoComTamanho(500));
  assert.equal(nucleo.limitarDescricao(descricaoComTamanho(501)), descricaoComTamanho(500));
  assert.equal(nucleo.limitarDescricao(descricaoComTamanho(700)).length, 500);
  assert.equal(nucleo.limitarDescricao('ab' + 'x'.repeat(600)), 'ab' + 'x'.repeat(498));

  // formatarContador
  assert.equal(nucleo.formatarContador(''), '0 de 500 caracteres');
  assert.equal(nucleo.formatarContador(0), '0 de 500 caracteres');
  assert.equal(nucleo.formatarContador('abc'), '3 de 500 caracteres');
  assert.equal(nucleo.formatarContador(500), '500 de 500 caracteres');
  assert.equal(nucleo.formatarContador(descricaoComTamanho(500)), '500 de 500 caracteres');
  assert.equal(nucleo.formatarContador('😀'), '2 de 500 caracteres'); // unidades UTF-16
});

// ---------------------------------------------------------------------------
// Property 7: validade do formulário, ordem e contagem dos erros
// Oráculo: a classe de cada campo (válido/inválido) vem do gerador usado; o
// código esperado de cada campo inválido vem dos validadores individuais.
// ---------------------------------------------------------------------------

const ORDEM_CAMPOS = ['nome', 'email', 'telefone', 'descricao', 'aceite'];

function congelarEmProfundidade(valor) {
  if (valor !== null && typeof valor === 'object' && !Object.isFrozen(valor)) {
    Object.freeze(valor);
    for (const chave of Object.keys(valor)) congelarEmProfundidade(valor[chave]);
  }
  return valor;
}

// Cada campo vem acompanhado da sua classe: { valido, valor }.
const nomeInvalidoP7 = fc.constantFrom('', '   ', '\t\n', 'a', 'ab', ' b ', '123', '---', '1 2 3', 'a'.repeat(101));
const campoNome = fc.oneof(
  fc.oneof(nomeValido, nomeBruto).map((valor) => ({ valido: true, valor })),
  nomeInvalidoP7.map((valor) => ({ valido: false, valor }))
);
const campoEmail = fc.oneof(
  fc.oneof(emailValido, emailBruto).map((valor) => ({ valido: true, valor })),
  fc.oneof(emailInvalido, fc.constantFrom('', '   ')).map((valor) => ({ valido: false, valor }))
);
const campoTelefone = fc.oneof(
  telefoneValido.map((valor) => ({ valido: true, valor })),
  fc.oneof(telefoneInvalido, fc.constantFrom('', '   ')).map((valor) => ({ valido: false, valor }))
);
const campoDescricao = fc.oneof(
  fc.oneof(descricaoValida, descricaoBruta).map((valor) => ({ valido: true, valor })),
  fc.oneof(descricaoCurta, descricaoLonga, fc.constantFrom('', '  \n ')).map((valor) => ({ valido: false, valor }))
);
// Aceite: true, false e valores que não são exatamente `true`.
const campoAceite = fc.oneof(
  { weight: 4, arbitrary: fc.constant({ valido: true, valor: true }) },
  { weight: 3, arbitrary: fc.constant({ valido: false, valor: false }) },
  {
    weight: 1,
    arbitrary: fc.constantFrom('true', 1, 'on', null, undefined, {}, []).map((valor) => ({ valido: false, valor }))
  }
);

test('Property 7: validade, ordem, códigos e contagem dos erros do formulário', () => {
  // Feature: ticket-opening-screen, Property 7: Validade do formulário, ordem e contagem dos erros
  // **Validates: Requirements 5.6, 5.8, 5.9, 5.14, 5.15, 5.16**
  fc.assert(
    fc.property(campoNome, campoEmail, campoTelefone, campoDescricao, campoAceite, (nome, email, telefone, descricao, aceite) => {
      const campos = { nome, email, telefone, descricao, aceite };
      const entrada = congelarEmProfundidade({
        nome: nome.valor,
        email: email.valor,
        telefone: telefone.valor,
        descricao: descricao.valor,
        aceite: aceite.valor
      });
      const copia = JSON.stringify(entrada);
      const contexto = ' para ' + JSON.stringify(entrada).slice(0, 200);

      const r = nucleo.validarFormulario(entrada);

      // esperado: campos inválidos na ordem nome, email, telefone, descricao, aceite
      const esperados = [];
      for (const campo of ORDEM_CAMPOS) {
        if (campos[campo].valido) continue;
        const codigo = campo === 'aceite' ? 'aceite' : nucleo['validar' + (campo === 'descricao' ? 'Descricao' : campo[0].toUpperCase() + campo.slice(1))](entrada[campo]);
        assert.notEqual(codigo, null, 'gerador de ' + campo + ' inválido produziu valor aceito' + contexto);
        esperados.push({ campo, codigo });
      }
      for (const campo of ['nome', 'email', 'telefone', 'descricao']) {
        if (campos[campo].valido) {
          const validador = nucleo['validar' + (campo === 'descricao' ? 'Descricao' : campo[0].toUpperCase() + campo.slice(1))];
          assert.equal(validador(entrada[campo]), null, 'gerador de ' + campo + ' válido produziu valor rejeitado' + contexto);
        }
      }

      assert.equal(r.valido, esperados.length === 0, 'valido divergente' + contexto);
      assert.equal(r.valido, ORDEM_CAMPOS.every((c) => campos[c].valido), 'valido != todos os campos válidos' + contexto);
      assert.deepEqual(r.erros, esperados, 'erros divergentes (campos, códigos ou ordem)' + contexto);
      assert.ok(r.erros.length >= 0 && r.erros.length <= 5, 'contagem fora de 0..5' + contexto);
      assert.equal(r.erros.length, ORDEM_CAMPOS.filter((c) => !campos[c].valido).length, 'contagem divergente' + contexto);
      if (!r.valido) assert.ok(r.erros.length >= 1, 'inválido sem erros' + contexto);

      // 'aceite' presente sempre que aceite !== true, com código 'aceite'
      const temAceite = r.erros.some((e) => e.campo === 'aceite' && e.codigo === 'aceite');
      assert.equal(temAceite, entrada.aceite !== true, 'item aceite divergente' + contexto);

      // normalizado
      assert.deepEqual(
        r.normalizado,
        {
          nome: nucleo.normalizarNome(entrada.nome),
          email: nucleo.normalizarEmail(entrada.email),
          telefone: nucleo.normalizarTelefone(entrada.telefone),
          descricao: nucleo.normalizarDescricao(entrada.descricao)
        },
        'normalizado divergente' + contexto
      );

      // entrada intacta
      assert.equal(JSON.stringify(entrada), copia, 'entrada alterada' + contexto);
      assert.ok(Object.isFrozen(entrada));
    }),
    { numRuns: 300 }
  );
});

test('Property 7: formulário com todos os campos válidos e aceite true é válido; sem aceite, só o aceite falha', () => {
  // Feature: ticket-opening-screen, Property 7: Validade do formulário, ordem e contagem dos erros
  // **Validates: Requirements 5.6, 5.8, 5.9, 5.14, 5.15, 5.16**
  fc.assert(
    fc.property(
      nomeBruto,
      emailBruto,
      telefoneValido,
      descricaoBruta,
      fc.constantFrom(false, 'true', 1, null, undefined),
      (nome, email, telefone, descricao, naoAceite) => {
        const base = { nome, email, telefone, descricao };
        const ok = nucleo.validarFormulario(congelarEmProfundidade(Object.assign({}, base, { aceite: true })));
        assert.equal(ok.valido, true);
        assert.deepEqual(ok.erros, []);

        const sem = nucleo.validarFormulario(congelarEmProfundidade(Object.assign({}, base, { aceite: naoAceite })));
        assert.equal(sem.valido, false);
        assert.deepEqual(sem.erros, [{ campo: 'aceite', codigo: 'aceite' }]);
        assert.deepEqual(sem.normalizado, ok.normalizado, 'normalizado não depende do aceite');
      }
    ),
    { numRuns: 200 }
  );
});

test('Property 7: entradas ausentes ou nulas geram os 5 erros, em ordem', () => {
  // Feature: ticket-opening-screen, Property 7: Validade do formulário, ordem e contagem dos erros
  // **Validates: Requirements 5.6, 5.8, 5.9, 5.14, 5.15, 5.16**
  const ausente = fc.constantFrom(undefined, null);
  const camposAusentes = fc.record(
    {
      nome: ausente,
      email: ausente,
      telefone: ausente,
      descricao: ausente,
      aceite: ausente
    },
    { requiredKeys: [] }
  );
  const entradas = fc.oneof(camposAusentes, fc.constantFrom(undefined, null, {}, [], 'texto', 42));

  fc.assert(
    fc.property(entradas, (entrada) => {
      congelarEmProfundidade(entrada);
      const r = nucleo.validarFormulario(entrada);
      const contexto = ' para ' + JSON.stringify(entrada);

      assert.equal(r.valido, false, 'valido' + contexto);
      assert.equal(r.erros.length, 5, 'deveria ter 5 erros' + contexto);
      assert.deepEqual(r.erros.map((e) => e.campo), ORDEM_CAMPOS, 'ordem' + contexto);
      assert.equal(r.erros[4].codigo, 'aceite');
      for (const e of r.erros.slice(0, 4)) assert.equal(e.codigo, 'vazio', 'código de ' + e.campo + contexto);
      assert.deepEqual(r.normalizado, { nome: '', email: '', telefone: '', descricao: '' }, 'normalizado' + contexto);
    }),
    { numRuns: 100 }
  );
});
