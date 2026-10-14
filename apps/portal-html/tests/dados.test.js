'use strict';
/*
 * Testes de exemplo sobre js/data.js (objeto TRES_DATA.CHAMADO e chaves antigas).
 * Requisitos: 1.2, 1.3, 2.8, 6.6, 6.7, 6.8, 6.15, 7.4, 12.3
 */
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function carregarDados() {
  const arquivo = path.join(__dirname, '..', 'js', 'data.js');
  const codigo = fs.readFileSync(arquivo, 'utf8');
  const janela = {};
  const contexto = vm.createContext({ window: janela });
  vm.runInContext(codigo, contexto, { filename: arquivo });
  return janela.TRES_DATA;
}

const D = carregarDados();
const CH = D.CHAMADO;
const T = CH.textos;

test('data.js define TRES_DATA com o objeto CHAMADO', () => {
  assert.equal(typeof D, 'object');
  assert.equal(typeof CH, 'object');
  assert.equal(typeof CH.config, 'object');
  assert.equal(typeof CH.privacidade, 'object');
  assert.equal(typeof T, 'object');
});

test('título: tem "chamado" e "aberto" e até 80 caracteres (1.2)', () => {
  const t = T.tituloChamado;
  assert.equal(typeof t, 'string');
  assert.ok(t.length >= 1 && t.length <= 80, `tamanho ${t.length}`);
  assert.match(t, /chamado/i);
  assert.match(t, /aberto/i);
});

test('introdução: até 300 caracteres, com "time responsável" e "analis…" (1.3)', () => {
  const t = T.introChamado;
  assert.equal(typeof t, 'string');
  assert.ok(t.length >= 1 && t.length <= 300, `tamanho ${t.length}`);
  assert.match(t, /time respons[aá]vel/i);
  assert.match(t, /analis/i);
});

test('rótulo dos passos não afirma execução pelo consumidor (2.8)', () => {
  const t = T.resumoLegendaPassos;
  assert.equal(typeof t, 'string');
  assert.ok(t.length > 0);
  for (const proibida of ['feito', 'executado', 'realizado', 'concluído', 'concluido']) {
    assert.ok(!t.toLowerCase().includes(proibida), `contém "${proibida}"`);
  }
});

test('rótulo exato do aceite (6.6)', () => {
  assert.equal(T.rotuloAceite, 'Li e concordo com os termos para envio dos meus dados');
});

test('botão "Ler os termos" (6.7)', () => {
  assert.equal(T.botaoLerTermos, 'Ler os termos');
});

test('mensagem de termos em elaboração (6.8)', () => {
  assert.equal(T.termosEmElaboracao, 'Texto dos termos em elaboração');
});

test('API_CHAMADOS_URL vazia por padrão (7.4)', () => {
  assert.equal(CH.config.API_CHAMADOS_URL, '');
});

test('prazo de retorno ilustrativo é 2 dias úteis e ainda não validado', () => {
  assert.equal(CH.config.PRAZO_RETORNO_DIAS_UTEIS, 2);
  assert.equal(CH.config.PRAZO_RETORNO_VALIDADO, false);
});

test('TIMEOUT_ENVIO_MS está presente e é número positivo', () => {
  assert.equal(typeof CH.config.TIMEOUT_ENVIO_MS, 'number');
  assert.ok(CH.config.TIMEOUT_ENVIO_MS > 0);
});

test('controlador e contato de privacidade estão marcados como PENDENTE (6.15)', () => {
  assert.equal(CH.privacidade.controlador, 'PENDENTE');
  assert.equal(CH.privacidade.contato, 'PENDENTE');
  assert.equal(CH.privacidade.politicaUrl, '');
});

test('chaves antigas de TRES_DATA continuam intactas (12.3)', () => {
  for (const chave of ['CONTATO', 'COMO_FAZER', 'CATEGORIAS', 'PROBLEMAS', 'MODELOS', 'BOTOES_BEBIDA', 'AVISOS_GERAIS', 'MODELO_3D']) {
    assert.ok(chave in D, `falta ${chave}`);
    assert.notEqual(D[chave], undefined, chave);
    assert.notEqual(D[chave], null, chave);
  }
  assert.ok(Array.isArray(D.PROBLEMAS));
  assert.equal(D.PROBLEMAS.length, 13);
  assert.equal(D.CONTATO.telefone, '0800 979 2021');
  assert.equal(D.CONTATO.email, 'atendimento@3coracoes.com.br');
});

/*
 * Testes de exemplo sobre TRES_DATA.FEEDBACK (spec resolved-feedback-comment, tarefa 8.23).
 * Requisitos: 2.3, 10.16, 13.2, 13.5, 13.6, 14.8
 */
const FB = D.FEEDBACK;
const TF = FB && FB.textos;
const CODIGO_DADOS = fs.readFileSync(path.join(__dirname, '..', 'js', 'data.js'), 'utf8');
const LINHAS_DADOS = CODIGO_DADOS.split(/\r?\n/);

const CHAVES_TEXTOS_FEEDBACK = [
  'rotulo', 'opcional', 'avisoNaoIdentificacao', 'contador', 'botaoEnviar', 'botaoEnviando',
  'erroVazio', 'anuncioErroVazio', 'agradecimento', 'falha'
];

// Comentários que antecedem a linha que declara `chave:` dentro do bloco FEEDBACK.
function comentariosAntes(chave) {
  const inicio = LINHAS_DADOS.findIndex((l) => l.includes('const FEEDBACK'));
  assert.ok(inicio >= 0, 'bloco FEEDBACK não encontrado em data.js');
  const idx = LINHAS_DADOS.findIndex((l, i) => i > inicio && new RegExp('^\\s*' + chave + '\\s*:').test(l));
  assert.ok(idx >= 0, `chave ${chave} não encontrada no bloco FEEDBACK`);
  const achados = [];
  for (let i = idx - 1; i >= 0 && /^\s*\/\//.test(LINHAS_DADOS[i]); i--) achados.unshift(LINHAS_DADOS[i]);
  return achados.join('\n');
}

test('FEEDBACK existe em TRES_DATA, com config e textos (13.2)', () => {
  assert.equal(typeof FB, 'object');
  assert.notEqual(FB, null);
  assert.equal(typeof FB.config, 'object');
  assert.equal(typeof TF, 'object');
  assert.notEqual(FB, CH);
});

test('API_FEEDBACK_URL e API_CHAMADOS_URL vazias no repositório (14.8)', () => {
  assert.equal(FB.config.API_FEEDBACK_URL, '');
  assert.equal(CH.config.API_CHAMADOS_URL, '');
});

test('config do feedback: tempo limite positivo e versão do contrato em texto', () => {
  assert.equal(typeof FB.config.TIMEOUT_FEEDBACK_MS, 'number');
  assert.ok(FB.config.TIMEOUT_FEEDBACK_MS > 0);
  assert.equal(typeof FB.config.VERSAO_CONTRATO_FEEDBACK, 'string');
  assert.ok(FB.config.VERSAO_CONTRATO_FEEDBACK.trim().length > 0);
});

test('todas as chaves obrigatórias de FEEDBACK.textos são texto não vazio (13.1, 13.4)', () => {
  for (const chave of CHAVES_TEXTOS_FEEDBACK) {
    assert.ok(chave in TF, `falta ${chave}`);
    assert.equal(typeof TF[chave], 'string', chave);
    assert.ok(TF[chave].trim().length > 0, `${chave} vazio`);
  }
});

test('aviso de não identificação: 1 a 200 caracteres e pede para não escrever dados pessoais (2.3)', () => {
  const t = TF.avisoNaoIdentificacao;
  assert.ok(t.length >= 1 && t.length <= 200, `tamanho ${t.length}`);
  assert.match(t, /n[aã]o escreva/i);
  assert.match(t, /nome/i);
  assert.match(t, /e-?mail/i);
  assert.match(t, /telefone/i);
  assert.match(t, /dados pessoais/i);
});

test('nenhum texto do feedback usa palavras vagas (13.5)', () => {
  for (const [chave, valor] of Object.entries(TF)) {
    assert.ok(!/rapidamente/i.test(valor), `${chave} contém "rapidamente"`);
    assert.ok(!/adequad/i.test(valor), `${chave} contém "adequado"`);
  }
});

test('API_FEEDBACK_URL, tempo limite, versão do contrato e aviso trazem PENDENTE ou ILUSTRATIVO (10.16, 13.6)', () => {
  for (const chave of ['API_FEEDBACK_URL', 'TIMEOUT_FEEDBACK_MS', 'VERSAO_CONTRATO_FEEDBACK', 'avisoNaoIdentificacao']) {
    assert.match(comentariosAntes(chave), /PENDENTE|ILUSTRATIVO/, `sem marcação junto de ${chave}`);
  }
});

test('lista de pontos em aberto com o back end está registrada como PENDENTE em data.js (10.16)', () => {
  const inicio = CODIGO_DADOS.indexOf('const FEEDBACK');
  assert.ok(inicio >= 0);
  const bloco = CODIGO_DADOS.slice(inicio);
  for (const termo of [/autentica/i, /CORS/, /esquema do banco/i, /idempot/i, /reten/i]) {
    assert.match(bloco, termo);
  }
  assert.match(bloco, /PENDENTE \(back end\)/);
});

test('FEEDBACK.textos não tem chave de aviso de protótipo (P6)', () => {
  for (const chave of Object.keys(TF)) {
    assert.ok(!/prot[oó]tipo/i.test(chave), `chave de protótipo: ${chave}`);
  }
  assert.ok(!('avisoPrototipo' in TF));
});

test('TRES_DATA.CHAMADO continua idêntico ao anterior à funcionalidade (13.2)', () => {
  assert.deepEqual(Object.keys(CH), ['config', 'privacidade', 'textos']);
  assert.deepEqual(
    Object.keys(CH.config),
    ['API_CHAMADOS_URL', 'TIMEOUT_ENVIO_MS', 'PRAZO_RETORNO_DIAS_UTEIS', 'PRAZO_RETORNO_VALIDADO', 'VERSAO_CONTRATO']
  );
  assert.equal(Object.keys(CH.textos).length, 55);
  assert.ok(!Object.keys(CH.textos).some((k) => /feedback|comentario/i.test(k)));
  const hash = require('node:crypto').createHash('sha256').update(JSON.stringify(CH)).digest('hex');
  assert.equal(hash, '508f912557a04285735966a0fd00523bf7e4a7cf0a33294e4d89243c40ad776a');
});
