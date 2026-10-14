'use strict';
// Geradores (arbitraries do fast-check) compartilhados pelos testes do núcleo.
//
// Dependem só dos FORMATOS definidos no design (nome, e-mail, telefone,
// descrição, protocolo, Chamado, eventos de métrica), nunca das funções de
// js/chamado.js. Assim os testes podem usar estes geradores como oráculo
// independente da implementação.
//
// Contagem de caracteres: String.length (unidades UTF-16), como no design.

const fc = require('fast-check');

/* ==========================================================
 * 1. Texto Unicode
 * ========================================================== */

// Pedaços que costumam quebrar serialização, escape e normalização.
const FRAGMENTOS_ESPECIAIS = [
  '😀', '🧡', '👨‍👩‍👧', '🇧🇷', // emojis (alguns com ZWJ e bandeiras)
  'á', 'é', 'í', 'ó', 'ú', 'ã', 'õ', 'â', 'ê', 'ô', 'ç', 'ü', 'Á', 'Ç', 'Ñ',
  'e\u0301', // acento combinante
  '\n', '\r\n', '\r', '\t', '\u2028', '\u2029',
  '"', "'", '`', '\\', '\\n', '\\u0041', '<', '>', '&', '</script>', '<b>x</b>',
  '\u0000', '\u00A0', '\u200B', ' ',
  '\uD800', '\uDBFF', '\uDC00', '\uDFFF' // surrogates soltos (alto e baixo)
];

const fragmentoEspecial = fc.constantFrom(...FRAGMENTOS_ESPECIAIS);

// Qualquer unidade de código UTF-16, inclusive surrogates soltos.
const textoBinario = fc.string({ unit: 'binary', maxLength: 120 });

// Mistura de palavras comuns e fragmentos especiais.
const textoMisto = fc
  .array(
    fc.oneof(
      { weight: 3, arbitrary: fragmentoEspecial },
      { weight: 2, arbitrary: fc.string({ maxLength: 12 }) },
      { weight: 1, arbitrary: fc.string({ unit: 'grapheme', maxLength: 6 }) }
    ),
    { maxLength: 30 }
  )
  .map((partes) => partes.join(''));

// Unicode completo: o que o consumidor pode digitar ou colar.
const textoUnicodeCompleto = fc.oneof(textoBinario, textoMisto);

// O mesmo, sem surrogates soltos (útil onde o oráculo exige UTF-16 bem formado).
const textoUnicodeBemFormado = textoUnicodeCompleto.map((s) => s.toWellFormed());

/* ==========================================================
 * 2. Nome
 * ========================================================== */

const LETRAS = 'abcdefghijklmnopqrstuvwxyzáàâãéêíóôõúüçABCDEFGHIJKLMNOPQRSTUVWXYZÁÂÃÉÊÍÓÔÕÚÇ'.split('');
const letra = fc.constantFrom(...LETRAS);
const palavra = (minLength, maxLength) => fc.string({ unit: letra, minLength, maxLength });

// Separadores entre palavras: o validador deve reduzi-los a um espaço.
const separadorDePalavras = fc.constantFrom(' ', '  ', '\t', '\n', ' \u00A0', '   ');
const espacosDasPontas = fc.constantFrom('', ' ', '  ', '\t', '\n', ' \u00A0 ');

// Nome já "limpo": palavras separadas por um único espaço, 3 a 79 caracteres,
// com ao menos uma letra.
const nomeValido = fc
  .tuple(palavra(3, 15), fc.array(palavra(1, 15), { maxLength: 4 }))
  .map(([primeira, resto]) => [primeira].concat(resto).join(' '));

// Nome como digitado: espaços nas pontas e separadores irregulares.
const nomeBruto = fc
  .tuple(
    espacosDasPontas,
    palavra(3, 15),
    fc.array(fc.tuple(separadorDePalavras, palavra(1, 15)), { maxLength: 4 }),
    espacosDasPontas
  )
  .map(([ini, primeira, resto, fim]) =>
    ini + primeira + resto.map(([sep, p]) => sep + p).join('') + fim
  );

/* ==========================================================
 * 3. E-mail
 * ========================================================== */

const emailLocal = fc.stringMatching(/^[a-z0-9][a-z0-9._+-]{0,20}$/);
const emailRotulo = fc.stringMatching(/^[a-z0-9]{1,10}$/);
const emailTld = fc.stringMatching(/^[a-z]{2,6}$/);

const emailPartes = fc.record({
  local: emailLocal,
  rotulos: fc.array(emailRotulo, { minLength: 1, maxLength: 3 }),
  tld: emailTld
});

const montarEmail = ({ local, rotulos, tld }) => local + '@' + rotulos.concat([tld]).join('.');

// E-mail válido, em minúsculas.
const emailValido = emailPartes.map(montarEmail);

// E-mail como digitado: maiúsculas e espaços nas pontas.
const emailBruto = fc
  .tuple(espacosDasPontas, emailValido, espacosDasPontas, fc.boolean())
  .map(([ini, e, fim, maiusculo]) => ini + (maiusculo ? e.toUpperCase() : e) + fim);

// Mutações que quebram o formato.
const emailInvalido = fc
  .tuple(
    emailPartes,
    fc.constantFrom(
      'sem-arroba',
      'duas-arrobas',
      'espaco-no-meio',
      'local-vazio',
      'sem-ponto',
      'ponto-final',
      'rotulo-vazio',
      'tld-numerico',
      'tld-curto'
    )
  )
  .map(([p, defeito]) => {
    const dominio = p.rotulos.concat([p.tld]).join('.');
    switch (defeito) {
      case 'sem-arroba': return p.local + dominio;
      case 'duas-arrobas': return p.local + '@@' + dominio;
      case 'espaco-no-meio': return p.local + ' x@' + dominio;
      case 'local-vazio': return '@' + dominio;
      case 'sem-ponto': return p.local + '@' + p.rotulos[0];
      case 'ponto-final': return p.local + '@' + dominio + '.';
      case 'rotulo-vazio': return p.local + '@' + p.rotulos[0] + '..' + p.tld;
      case 'tld-numerico': return p.local + '@' + p.rotulos[0] + '.123';
      default: return p.local + '@' + p.rotulos[0] + '.a';
    }
  });

/* ==========================================================
 * 4. Telefone
 * ========================================================== */

const digito = fc.constantFrom(...'0123456789'.split(''));
const digitos = (minLength, maxLength) => fc.string({ unit: digito, minLength, maxLength });

const ddd = fc.integer({ min: 11, max: 99 }).map(String);
const numeroFixo = digitos(8, 8); // 10 dígitos no total
const numeroCelular = digitos(8, 8).map((n) => '9' + n); // 11 dígitos no total

// 10 ou 11 dígitos com DDD entre 11 e 99 e (com 11) o terceiro dígito igual a 9.
const telefoneNacional = fc.tuple(ddd, fc.oneof(numeroFixo, numeroCelular)).map(([d, n]) => d + n);

const SEPARADORES_TELEFONE = ['(', ')', ' ', '-', '.'];
const SEPARADORES_MAXIMOS = 6; // mantém o texto com no máximo 20 caracteres

// Intercala separadores permitidos entre os dígitos (no máximo 6) e,
// opcionalmente, um '+' no início.
function intercalar(texto, lacunas, comMais) {
  let colocados = 0;
  let saida = comMais ? '+' : '';
  for (let i = 0; i < texto.length; i++) {
    const sep = lacunas[i];
    if (sep && colocados < SEPARADORES_MAXIMOS) {
      saida += sep;
      colocados += 1;
    }
    saida += texto[i];
  }
  return saida;
}

const lacunasDeSeparadores = fc.array(fc.option(fc.constantFrom(...SEPARADORES_TELEFONE), { nil: null, freq: 4 }), {
  minLength: 13,
  maxLength: 13
});

// Telefone válido como digitado: separadores aleatórios, com ou sem '55',
// com ou sem '+'. Devolve { nacional, texto } para servir de oráculo.
const telefoneValidoComOraculo = fc
  .record({
    nacional: telefoneNacional,
    comPrefixo: fc.boolean(),
    comMais: fc.boolean(),
    lacunas: lacunasDeSeparadores
  })
  .map(({ nacional, comPrefixo, comMais, lacunas }) => {
    const todos = (comPrefixo ? '55' : '') + nacional;
    return { nacional, texto: intercalar(todos, lacunas, comMais) };
  });

const telefoneValido = telefoneValidoComOraculo.map((t) => t.texto);

// Telefone que deve ser rejeitado, por motivos variados.
const telefoneInvalido = fc.oneof(
  // caractere fora do conjunto permitido
  fc
    .tuple(telefoneNacional, fc.constantFrom('a', 'x', '#', '/', '_', '*', 'ª'), fc.nat({ max: 10 }))
    .map(([n, c, pos]) => n.slice(0, pos) + c + n.slice(pos)),
  // poucos dígitos (1 a 9)
  digitos(1, 9),
  // dígitos demais (14 a 18)
  digitos(14, 18),
  // DDD abaixo de 11 (00 a 10)
  fc.tuple(fc.integer({ min: 0, max: 10 }), numeroFixo).map(([d, n]) => String(d).padStart(2, '0') + n),
  // 12 ou 13 dígitos sem o prefixo 55
  fc
    .tuple(fc.integer({ min: 10, max: 99 }).filter((p) => p !== 55), telefoneNacional)
    .map(([p, n]) => String(p) + n),
  // 11 dígitos cujo terceiro dígito não é 9
  fc
    .tuple(ddd, fc.constantFrom('0', '1', '2', '3', '4', '5', '6', '7', '8'), digitos(8, 8))
    .map(([d, t, n]) => d + t + n),
  // '+' fora do início
  telefoneNacional.map((n) => n.slice(0, 2) + '+' + n.slice(2))
);

/* ==========================================================
 * 5. Descrição
 * ========================================================== */

// Unidades de um só código UTF-16, para o comprimento ser previsível.
const UNIDADES_DESCRICAO = (
  'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789' +
  'áéíóúãõâêôçüÁÉÍÓÚÃÕÂÊÔÇ' +
  ' .,;:!?-_()"\'\\<>&\n\t'
).split('');
const unidadeDescricao = fc.constantFrom(...UNIDADES_DESCRICAO);
const unidadeVisivel = fc.constantFrom(...UNIDADES_DESCRICAO.filter((c) => c.trim() !== ''));

// Descrição cujo texto aparado tem de 10 a 500 caracteres.
const descricaoValida = fc
  .tuple(unidadeVisivel, fc.string({ unit: unidadeDescricao, minLength: 8, maxLength: 498 }), unidadeVisivel)
  .map(([a, meio, b]) => a + meio + b);

// Descrição como digitada: com espaços e quebras nas pontas.
const descricaoBruta = fc
  .tuple(espacosDasPontas, descricaoValida, espacosDasPontas)
  .map(([ini, d, fim]) => ini + d + fim);

// Descrição curta demais (aparada, 1 a 9 caracteres).
const descricaoCurta = fc
  .tuple(unidadeVisivel, fc.string({ unit: unidadeDescricao, minLength: 0, maxLength: 7 }), unidadeVisivel)
  .map(([a, meio, b]) => a + meio + b);

// Descrição longa demais (aparada, 501 a 700 caracteres).
const descricaoLonga = fc
  .tuple(unidadeVisivel, fc.string({ unit: unidadeDescricao, minLength: 499, maxLength: 698 }), unidadeVisivel)
  .map(([a, meio, b]) => a + meio + b);

// Texto qualquer para exercitar truncamento e contador (0 a 700 unidades UTF-16).
const textoParaDescricao = fc.string({ unit: fc.oneof(unidadeDescricao, fc.constantFrom('😀', 'é', '\uD800')), maxLength: 700 });

/* ==========================================================
 * 6. Identificadores
 * ========================================================== */

const ALFABETO_PROTOCOLO = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'.split('');

// Data local qualquer entre 2000 e 2100.
const dataLocal = fc.date({
  min: new Date(2000, 0, 1),
  max: new Date(2100, 11, 31),
  noInvalidDate: true
});

const doisDigitos = (n) => String(n).padStart(2, '0');
const prefixoDeData = (d) => 'TRES-' + d.getFullYear() + doisDigitos(d.getMonth() + 1) + doisDigitos(d.getDate());

// Protocolo no formato TRES-AAAAMMDD-XXXXXX (data do calendário local).
const protocoloLocal = fc
  .tuple(dataLocal, fc.string({ unit: fc.constantFrom(...ALFABETO_PROTOCOLO), minLength: 6, maxLength: 6 }))
  .map(([d, sufixo]) => prefixoDeData(d) + '-' + sufixo);

// 16 bytes para uuidV4.
const bytes16 = fc.array(fc.integer({ min: 0, max: 255 }), { minLength: 16, maxLength: 16 });

const uuidV4 = fc.uuid({ version: 4 });

// Sequência de inteiros para alimentar um sorteio determinístico
// (ver criarSorteio em falsos.js).
const sequenciaDeSorteio = fc.array(fc.integer({ min: 0, max: 2 ** 31 - 1 }), { minLength: 1, maxLength: 64 });

// Protocolo devolvido por um back end: texto de 1 a 64 caracteres.
const protocoloApi = fc.string({ unit: 'binary', minLength: 1, maxLength: 64 }).filter((s) => s.trim().length > 0);

/* ==========================================================
 * 7. Chamado
 * ========================================================== */

const IDS_MODELO = ['lov', 'modo', 'passione', 'luna', 'touch'];
const OFFSETS_DE_FUSO = ['-03:00', '-04:00', '-02:00', '+00:00', '+01:00', '+05:30'];

// ISO 8601 com deslocamento de fuso (não 'Z'), ex.: 2026-10-13T14:32:10.123-03:00
const instanteIso = fc
  .tuple(
    fc.date({ min: new Date('2000-01-01T00:00:00Z'), max: new Date('2100-12-31T23:59:59Z'), noInvalidDate: true }),
    fc.constantFrom(...OFFSETS_DE_FUSO)
  )
  .map(([d, offset]) => d.toISOString().slice(0, 23) + offset);

// Passos percorridos: posições crescentes, sem repetição, dentro de 1..total.
const passosEtotal = fc
  .integer({ min: 1, max: 8 })
  .chain((total) =>
    fc.tuple(
      fc.constant(total),
      fc.uniqueArray(fc.integer({ min: 1, max: total }), { maxLength: total }).map((p) => p.sort((a, b) => a - b)),
      fc.array(textoUnicodeCompleto, { minLength: total, maxLength: total })
    )
  )
  .map(([total, posicoes, textos]) => ({
    totalPassos: total,
    passosPercorridos: posicoes.map((posicao) => ({ posicao, texto: textos[posicao - 1] }))
  }));

// Chamado "realista": campos já normalizados e válidos (os 14 campos do contrato).
const chamado = fc
  .record({
    chaveIdempotencia: uuidV4,
    abertoEm: instanteIso,
    nome: nomeValido,
    email: emailValido,
    telefone: telefoneNacional,
    descricao: descricaoValida,
    modelo: fc.option(fc.constantFrom(...IDS_MODELO), { nil: null }),
    problemaId: fc.integer({ min: 1, max: 13 }),
    problemaTitulo: textoUnicodeCompleto,
    passos: passosEtotal
  })
  .map(({ passos, ...resto }) => ({
    versaoContrato: '1',
    chaveIdempotencia: resto.chaveIdempotencia,
    abertoEm: resto.abertoEm,
    nome: resto.nome,
    email: resto.email,
    telefone: resto.telefone,
    descricao: resto.descricao,
    aceiteTermos: true,
    aceiteEm: resto.abertoEm,
    modelo: resto.modelo,
    problemaId: resto.problemaId,
    problemaTitulo: resto.problemaTitulo,
    passosPercorridos: passos.passosPercorridos,
    totalPassos: passos.totalPassos
  }));

// Chamado com Unicode completo (emojis, aspas, '\', '<', '>', '&', quebras de
// linha e surrogates soltos) em todos os campos de texto livre. Serve para
// as propriedades de ida e volta.
const chamadoUnicode = fc
  .tuple(chamado, textoUnicodeCompleto, textoUnicodeCompleto, textoUnicodeCompleto)
  .map(([c, nome, email, descricao]) => Object.assign({}, c, { nome, email, descricao }));

// Chamado já gravado no repositório do Modo_Prototipo.
const chamadoGravado = fc
  .tuple(chamadoUnicode, protocoloLocal)
  .map(([c, protocolo]) => Object.assign({}, c, { protocolo, modoEnvio: 'prototipo' }));

const listaDeChamados = (opcoes) =>
  fc.array(chamadoGravado, Object.assign({ maxLength: 8 }, opcoes));

// Lista com protocolos todos diferentes (como o repositório mantém).
const listaDeChamadosUnicos = (opcoes) =>
  fc.uniqueArray(chamadoGravado, Object.assign({ maxLength: 8, selector: (c) => c.protocolo }, opcoes));

/* ==========================================================
 * 8. Eventos de métrica
 * ========================================================== */

const instanteUtc = fc
  .date({ min: new Date('2000-01-01T00:00:00Z'), max: new Date('2100-12-31T23:59:59Z'), noInvalidDate: true })
  .map((d) => d.toISOString());

const baseDoEvento = {
  em: instanteUtc,
  problema: fc.integer({ min: 1, max: 13 }),
  modelo: fc.option(fc.constantFrom(...IDS_MODELO), { nil: null })
};

const eventoResolvido = fc.record(Object.assign({ tipo: fc.constant('resolvido') }, baseDoEvento));
const eventoSuporte = fc.record(Object.assign({ tipo: fc.constant('suporte') }, baseDoEvento));
const eventoChamado = fc.record(
  Object.assign({}, baseDoEvento, {
    tipo: fc.constant('chamado'),
    protocolo: protocoloLocal,
    modo: fc.constantFrom('prototipo', 'api'),
    passos: fc.nat({ max: 20 })
  })
);
const eventoAvaliacao = fc
  .tuple(
    fc.record(
      Object.assign({}, baseDoEvento, {
        tipo: fc.constant('avaliacao'),
        nota: fc.integer({ min: 1, max: 5 }),
        desfecho: fc.constantFrom('resolvido', 'chamado')
      })
    ),
    protocoloLocal
  )
  .map(([e, protocolo]) => (e.desfecho === 'chamado' ? Object.assign({}, e, { protocolo }) : e));

const eventoMetrica = fc.oneof(eventoResolvido, eventoSuporte, eventoChamado, eventoAvaliacao);
const listaDeEventos = fc.array(eventoMetrica, { maxLength: 60 });

/* ==========================================================
 * 9. Feedback (comentário opcional da Tela_de_Resolvido)
 * ========================================================== */

// Miolo do comentário: mistura de texto comum, fragmentos especiais, e-mails
// e telefones no meio do texto (o Sistema não os detecta nem os remove) e
// pedaços binários com surrogates soltos.
const nucleoDoComentario = fc
  .array(
    fc.oneof(
      { weight: 3, arbitrary: fragmentoEspecial },
      { weight: 3, arbitrary: fc.string({ maxLength: 20 }) },
      { weight: 1, arbitrary: emailValido },
      { weight: 1, arbitrary: telefoneValido },
      { weight: 1, arbitrary: fc.string({ unit: 'binary', maxLength: 30 }) }
    ),
    { maxLength: 40 }
  )
  .map((partes) => partes.join(''));

const pontasDoComentario = fc.constantFrom('', ' ', '  ', '\t', '\n', '\r\n', '\n\n', ' \u00A0 ', '\u2028');

// Comentário como digitado ou colado, de qualquer tamanho: pode estar vazio,
// ter só espaços, passar de 500 unidades UTF-16 e conter surrogates soltos.
const comentarioBruto = fc.oneof(
  { weight: 3, arbitrary: fc.tuple(pontasDoComentario, nucleoDoComentario, pontasDoComentario).map(([i, m, f]) => i + m + f) },
  { weight: 2, arbitrary: fc.string({ unit: 'binary', maxLength: 600 }) },
  { weight: 1, arbitrary: fc.constantFrom('', ' ', '\n', ' \n\t ', '\u00A0') }
);

// Comentário válido já normalizado: o texto aparado tem de 1 a 500 unidades
// UTF-16. Miolo livre entre dois caracteres visíveis (quebras e espaços ficam
// só por dentro, então trim() não muda nada). Cobre os limites 1 e 500.
const comentarioValido = fc.oneof(
  { weight: 1, arbitrary: unidadeVisivel },
  {
    weight: 4,
    arbitrary: fc
      .tuple(unidadeVisivel, nucleoDoComentario.map((s) => s.slice(0, 498)), unidadeVisivel)
      .map(([a, m, b]) => a + m + b)
  },
  {
    weight: 1,
    arbitrary: fc
      // 'binary' pode gerar pontos de código fora do plano básico (2 unidades UTF-16): corta em 498 unidades.
      .tuple(unidadeVisivel, fc.string({ unit: 'binary', minLength: 498, maxLength: 498 }), unidadeVisivel)
      .map(([a, m, b]) => a + m.slice(0, 498) + b)
  }
);

// Comentário longo demais: o texto aparado tem de 501 a 802 unidades UTF-16.
const comentarioLongo = fc
  .tuple(unidadeVisivel, fc.string({ unit: 'binary', minLength: 499, maxLength: 800 }), unidadeVisivel)
  .map(([a, m, b]) => a + m.slice(0, 800) + b);

// Payload_do_Feedback válido: exatamente os 7 campos do contrato (versão "1").
const payloadFeedback = fc.record({
  versaoContrato: fc.constant('1'),
  chaveIdempotencia: uuidV4,
  enviadoEm: instanteIso,
  comentario: comentarioValido,
  nota: fc.option(fc.integer({ min: 1, max: 5 }), { nil: null }),
  problemaId: fc.integer({ min: 1, max: 13 }),
  modelo: fc.option(fc.constantFrom(...IDS_MODELO), { nil: null })
});

// Lista de Payloads com chaves de idempotência distintas (como o repositório mantém).
const listaDeFeedbacksCom = (opcoes) =>
  fc.uniqueArray(payloadFeedback, Object.assign({ maxLength: 120, selector: (p) => p.chaveIdempotencia }, opcoes));

// 0 a 120 itens; um terço das listas passa de 50 para exercitar o teto do repositório.
const listaDeFeedbacks = fc.oneof(
  { weight: 2, arbitrary: listaDeFeedbacksCom() },
  { weight: 1, arbitrary: listaDeFeedbacksCom({ minLength: 51, maxLength: 120, size: 'max' }) }
);

// Valor de API_FEEDBACK_URL com o modo esperado como oráculo:
// { url, modo }, em que modo é 'api' ou 'prototipo'.
const hostComPonto = fc
  .tuple(fc.array(emailRotulo, { minLength: 1, maxLength: 3 }), emailTld)
  .map(([rotulos, tld]) => rotulos.concat([tld]).join('.')); // sempre com ponto: nunca é 'localhost'
const caminhoDeUrl = fc.stringMatching(/^(\/[a-z0-9_-]{1,10}){0,3}$/);
const portaOpcional = fc.option(fc.integer({ min: 1024, max: 65535 }), { nil: null }).map((p) => (p === null ? '' : ':' + p));
const folgaDaUrl = fc.constantFrom('', ' ', '\n');

const urlDeConfiguracao = fc.oneof(
  // vazia ou só espaços
  fc.constantFrom('', ' ', '  ', '\n', '\t ').map((url) => ({ url, modo: 'prototipo' })),
  // texto que não é URL absoluta
  fc
    .constantFrom('abc', 'api/feedbacks', '/api/feedbacks', 'https://', 'http://', ':::', 'não é url', 'exemplo.com/api')
    .map((url) => ({ url, modo: 'prototipo' })),
  // outros esquemas
  fc
    .tuple(hostComPonto, caminhoDeUrl)
    .chain(([h, c]) =>
      fc.constantFrom('ftp://' + h + c, 'ws://' + h + c, 'wss://' + h + c, 'file:///' + h + c, 'mailto:a@' + h)
    )
    .map((url) => ({ url, modo: 'prototipo' })),
  fc
    .constantFrom('javascript:alert(1)', 'JAVASCRIPT:void(0)', 'data:text/plain,x', 'blob:https://exemplo.com/x')
    .map((url) => ({ url, modo: 'prototipo' })),
  // http: em hosts que não são locais
  fc
    .tuple(hostComPonto, portaOpcional, caminhoDeUrl)
    .map(([h, p, c]) => ({ url: 'http://' + h + p + c, modo: 'prototipo' })),
  fc
    .constantFrom('http://localhost.exemplo.com/x', 'http://127.0.0.2/x', 'http://128.0.0.1/x', 'http://10.0.0.1/x', 'http://[::1]/x')
    .map((url) => ({ url, modo: 'prototipo' })),
  // http: em localhost e 127.0.0.1
  fc
    .tuple(fc.constantFrom('localhost', '127.0.0.1'), portaOpcional, caminhoDeUrl, folgaDaUrl)
    .map(([h, p, c, f]) => ({ url: f + 'http://' + h + p + c + f, modo: 'api' })),
  // https: em qualquer host
  fc
    .tuple(fc.oneof(hostComPonto, fc.constant('localhost')), portaOpcional, caminhoDeUrl, folgaDaUrl)
    .map(([h, p, c, f]) => ({ url: f + 'https://' + h + p + c + f, modo: 'api' }))
);

// Ações sobre o formulário, para o teste baseado em modelo (Propriedade 16).
//   editar:           { tipo: 'editar', texto }
//   enviar:           { tipo: 'enviar', texto, nota, modelo } (entrada de prepararEnvio)
//   concluirSucesso:  { tipo: 'concluirSucesso' }
//   concluirFalha:    { tipo: 'concluirFalha', categoria }
//   reexibir:         { tipo: 'reexibir', problemaId } (volta à tela, mesmo problema ou outro)
const acaoDoFormulario = fc.oneof(
  { weight: 3, arbitrary: comentarioBruto.map((texto) => ({ tipo: 'editar', texto })) },
  {
    weight: 4,
    arbitrary: fc
      .record({
        texto: fc.oneof(comentarioValido, comentarioBruto),
        nota: fc.option(fc.integer({ min: 1, max: 5 }), { nil: null }),
        modelo: fc.option(fc.constantFrom(...IDS_MODELO), { nil: null })
      })
      .map((e) => Object.assign({ tipo: 'enviar' }, e))
  },
  { weight: 2, arbitrary: fc.constant({ tipo: 'concluirSucesso' }) },
  {
    weight: 2,
    arbitrary: fc
      .constantFrom('rede', 'timeout', 'http', 'armazenamento')
      .map((categoria) => ({ tipo: 'concluirFalha', categoria }))
  },
  { weight: 2, arbitrary: fc.integer({ min: 1, max: 3 }).map((problemaId) => ({ tipo: 'reexibir', problemaId })) }
);

// Evento `comentario`: só tipo, instante, problema e modelo ('nao-informado' sem modelo).
const eventoComentario = fc.record({
  tipo: fc.constant('comentario'),
  em: instanteUtc,
  problema: fc.integer({ min: 1, max: 13 }),
  modelo: fc.constantFrom(...IDS_MODELO, 'nao-informado')
});

// `eventoMetrica` e `listaDeEventos` ficam como estavam; as versões abaixo
// somam o evento `comentario` a eles.
const eventoMetricaComComentario = fc.oneof(
  { weight: 4, arbitrary: eventoMetrica },
  { weight: 1, arbitrary: eventoComentario }
);
const listaDeEventosComComentarios = fc.array(eventoMetricaComComentario, { maxLength: 60 });

/* ==========================================================
 * Exportação
 * ========================================================== */

module.exports = {
  fc,
  // Unicode
  FRAGMENTOS_ESPECIAIS,
  fragmentoEspecial,
  textoBinario,
  textoMisto,
  textoUnicodeCompleto,
  textoUnicodeBemFormado,
  // nome
  nomeValido,
  nomeBruto,
  // e-mail
  emailValido,
  emailBruto,
  emailInvalido,
  // telefone
  telefoneNacional,
  telefoneValido,
  telefoneValidoComOraculo,
  telefoneInvalido,
  // descrição
  descricaoValida,
  descricaoBruta,
  descricaoCurta,
  descricaoLonga,
  textoParaDescricao,
  // identificadores
  dataLocal,
  protocoloLocal,
  bytes16,
  uuidV4,
  sequenciaDeSorteio,
  protocoloApi,
  // chamado
  IDS_MODELO,
  instanteIso,
  chamado,
  chamadoUnicode,
  chamadoGravado,
  listaDeChamados,
  listaDeChamadosUnicos,
  // métricas
  eventoResolvido,
  eventoSuporte,
  eventoChamado,
  eventoAvaliacao,
  eventoMetrica,
  listaDeEventos,
  // feedback
  comentarioBruto,
  comentarioValido,
  comentarioLongo,
  payloadFeedback,
  listaDeFeedbacks,
  listaDeFeedbacksCom,
  urlDeConfiguracao,
  acaoDoFormulario,
  eventoComentario,
  eventoMetricaComComentario,
  listaDeEventosComComentarios
};
