'use strict';
// Testes do núcleo (js/chamado.js) sobre a camada de envio (Ponto_de_Integracao).
// Cada tarefa acrescenta testes independentes neste arquivo; os helpers comuns
// ficam no topo.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { fc, chamado, chamadoGravado, sequenciaDeSorteio } = require('../geradores.js');
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

const CHAVE_CHAMADOS = 'tres-autoatendimento-chamados';

// Monta o Ponto_de_Integracao com todos os dublês. `fetchFalso` e `storage`
// são devolvidos para o teste conferir chamadas e gravações.
function montarAmbiente(urlDaApi, comportamentoFetch, sequencia) {
  const fetchFalso = criarFetchFalso(comportamentoFetch || { status: 200, corpo: { protocolo: 'PROTOCOLO-API-1' } });
  const storage = criarStorageFalso();
  const temporizador = criarTemporizadorFalso();
  const ponto = nucleo.criarPontoDeIntegracao({
    config: { API_CHAMADOS_URL: urlDaApi, TIMEOUT_ENVIO_MS: 10000 },
    fetch: fetchFalso,
    AbortController: criarAbortControllerFalso(),
    setTimeout: temporizador.setTimeout,
    clearTimeout: temporizador.clearTimeout,
    storage,
    agora: criarRelogio().agora,
    sorteio: criarSorteio(sequencia)
  });
  return { ponto, fetchFalso, storage };
}

// Geradores de URL com classificação conhecida (oráculo independente).
const rotuloDns = fc.stringMatching(/^[a-z][a-z0-9]{0,9}$/);
const tldDns = fc.stringMatching(/^[a-z]{2,6}$/);
const hostDns = fc
  .tuple(fc.array(rotuloDns, { minLength: 1, maxLength: 3 }), tldDns)
  .map(([rotulos, tld]) => rotulos.concat([tld]).join('.'))
  .filter((h) => h !== 'localhost');
const portaOpcional = fc.option(fc.integer({ min: 1, max: 65535 }).map((p) => ':' + p), { nil: '' });
const caminhoOpcional = fc.option(fc.stringMatching(/^\/[a-z0-9/_-]{0,20}$/), { nil: '' });

const HOSTS_LOCAIS = ['localhost', '127.0.0.1'];

// Devem resolver para 'api'.
const urlDeApi = fc.oneof(
  fc.tuple(hostDns, portaOpcional, caminhoOpcional).map(([h, p, c]) => 'https://' + h + p + c),
  fc.tuple(fc.constantFrom(...HOSTS_LOCAIS), portaOpcional, caminhoOpcional).map(([h, p, c]) => 'http://' + h + p + c),
  fc.tuple(fc.constantFrom(...HOSTS_LOCAIS), portaOpcional, caminhoOpcional).map(([h, p, c]) => 'https://' + h + p + c)
);

// Hosts parecidos com os permitidos, mas diferentes.
const HOSTS_PARECIDOS = [
  'localhost.evil.com', 'evil-localhost.com', 'mylocalhost', 'localhost.localdomain',
  '127.0.0.10', '127.0.0.100', '127.0.0.2', '127.0.1.1', '1127.0.0.1.com',
  '127.0.0.1.evil.com', '0.0.0.0', '10.0.0.1', '192.168.0.10', '[::1]'
];

// Devem resolver para 'prototipo' (texto).
const urlDePrototipo = fc.oneof(
  fc.constantFrom('', ' ', '   ', '\t', '\n', ' \n\t '),
  // sem protocolo
  fc.tuple(hostDns, caminhoOpcional).map(([h, c]) => h + c),
  fc.constantFrom('localhost', 'localhost:3000', '127.0.0.1:8080', '//api.exemplo.com/chamados', '/api/chamados', 'api/chamados'),
  // outros protocolos
  fc.tuple(hostDns, caminhoOpcional).map(([h, c]) => 'ftp://' + h + c),
  fc.tuple(hostDns, caminhoOpcional).map(([h, c]) => 'ws://' + h + c),
  fc.tuple(hostDns, caminhoOpcional).map(([h, c]) => 'wss://' + h + c),
  fc.constantFrom(
    'javascript:alert(1)', 'javascript://localhost/%0Aalert(1)', 'file:///etc/passwd', 'file://localhost/tmp/x',
    'data:text/plain,ola', 'data:text/html;base64,PHNjcmlwdD4=', 'blob:https://exemplo.com/x', 'mailto:a@b.com'
  ),
  // http: em outro host
  fc.tuple(hostDns, portaOpcional, caminhoOpcional).map(([h, p, c]) => 'http://' + h + p + c),
  fc.tuple(fc.constantFrom(...HOSTS_PARECIDOS), portaOpcional, caminhoOpcional).map(([h, p, c]) => 'http://' + h + p + c),
  // https: sem host ou malformada
  fc.constantFrom('https://', 'https:', 'http://', 'http:', 'https:///', 'http://:80', 'https://[', 'http://exa mplo.com'),
  // host permitido só como credencial ou caminho; o host real é outro
  hostDns.map((h) => 'http://localhost@' + h),
  hostDns.map((h) => 'http://127.0.0.1:80@' + h),
  hostDns.map((h) => 'http://' + h + '/localhost'),
  hostDns.map((h) => 'http://' + h + '/?u=http://127.0.0.1')
);

// Valores que nem são texto.
const valorNaoTexto = fc.oneof(
  fc.constantFrom(undefined, null, true, false, 0, 1, NaN, Infinity),
  fc.integer(),
  fc.double(),
  fc.array(fc.string(), { maxLength: 3 }),
  fc.dictionary(fc.string({ maxLength: 5 }), fc.string({ maxLength: 5 }), { maxKeys: 3 })
);

// Oráculo para texto qualquer: a regra do design escrita sobre o URL da plataforma.
function modoEsperado(texto) {
  if (typeof texto !== 'string') return 'prototipo';
  let u;
  try {
    u = new URL(texto.trim());
  } catch (e) {
    return 'prototipo';
  }
  if (u.protocol === 'https:' && u.hostname) return 'api';
  if (u.protocol === 'http:' && (u.hostname === 'localhost' || u.hostname === '127.0.0.1')) return 'api';
  return 'prototipo';
}

/* ==========================================================
 * Property 18: Seleção do modo de envio
 * ========================================================== */

test('resolverModo: URLs https: válidas e http: em localhost/127.0.0.1 resolvem para api', () => {
  fc.assert(
    fc.property(urlDeApi, (url) => {
      assert.equal(nucleo.resolverModo(url), 'api', url);
    }),
    { numRuns: 200 }
  );
});

test('resolverModo: vazio, não-texto, URL inválida, outros protocolos e http: em outro host resolvem para prototipo', () => {
  fc.assert(
    fc.property(fc.oneof(urlDePrototipo, valorNaoTexto), (url) => {
      assert.equal(nucleo.resolverModo(url), 'prototipo', typeof url === 'string' ? url : typeof url);
    }),
    { numRuns: 300 }
  );
});

test('resolverModo: exemplos de borda do requisito (host exato, não prefixo nem sufixo)', () => {
  assert.equal(nucleo.resolverModo('http://localhost.evil.com'), 'prototipo');
  assert.equal(nucleo.resolverModo('http://127.0.0.10'), 'prototipo');
  assert.equal(nucleo.resolverModo('http://localhost:8080/chamados'), 'api');
  assert.equal(nucleo.resolverModo('http://127.0.0.1:3000/chamados'), 'api');
  assert.equal(nucleo.resolverModo('https://api.exemplo.com/chamados'), 'api');
  assert.equal(nucleo.resolverModo('http://api.exemplo.com/chamados'), 'prototipo');
  assert.equal(nucleo.resolverModo(undefined), 'prototipo');
  assert.equal(nucleo.resolverModo(''), 'prototipo');
  assert.equal(nucleo.resolverModo('   '), 'prototipo');
});

// Feature: ticket-opening-screen, Property 18: Seleção do modo de envio
test('Property 18: resolverModo bate com a regra para qualquer texto e, em prototipo, enviar nunca chama o fetch', async () => {
  const textoQualquer = fc.oneof(
    fc.string({ maxLength: 60 }),
    fc.webUrl({ validSchemes: ['http', 'https', 'ftp'] }),
    urlDeApi,
    urlDePrototipo
  );

  // (a) classificação de qualquer texto
  fc.assert(
    fc.property(textoQualquer, (url) => {
      assert.equal(nucleo.resolverModo(url), modoEsperado(url), JSON.stringify(url));
    }),
    { numRuns: 300 }
  );

  // (b) envio em prototipo: zero chamadas ao fetch e gravação no storage local
  await fc.assert(
    fc.asyncProperty(fc.oneof(urlDePrototipo, valorNaoTexto), chamado, sequenciaDeSorteio, async (url, c, sequencia) => {
      const { ponto, fetchFalso, storage } = montarAmbiente(url, undefined, sequencia);
      const resultado = await ponto.enviar(c);

      assert.equal(fetchFalso.chamadas.length, 0);
      assert.equal(resultado.ok, true);
      assert.equal(resultado.modo, 'prototipo');
      assert.equal(storage.contar('setItem'), 1);
      const gravados = JSON.parse(storage.dados.get(CHAVE_CHAMADOS));
      assert.equal(gravados.length, 1);
      assert.equal(gravados[0].protocolo, resultado.protocolo);
      assert.equal(gravados[0].modoEnvio, 'prototipo');
      assert.equal(gravados[0].chaveIdempotencia, c.chaveIdempotencia);
    }),
    { numRuns: 150 }
  );

  // (c) envio em api: um único fetch, na URL configurada, e nada no storage local
  await fc.assert(
    fc.asyncProperty(urlDeApi, chamado, sequenciaDeSorteio, async (url, c, sequencia) => {
      const { ponto, fetchFalso, storage } = montarAmbiente(url, undefined, sequencia);
      const resultado = await ponto.enviar(c);

      assert.equal(fetchFalso.chamadas.length, 1);
      assert.equal(fetchFalso.chamadas[0].url, url);
      assert.equal(resultado.ok, true);
      assert.equal(resultado.modo, 'api');
      assert.equal(resultado.protocolo, 'PROTOCOLO-API-1');
      assert.equal(storage.contar('setItem'), 0);
      assert.equal(storage.dados.has(CHAVE_CHAMADOS), false);
    }),
    { numRuns: 150 }
  );
});

/* ==========================================================
 * Property 19: Requisição em Modo_API
 * ========================================================== */

// Como montarAmbiente, mas com o tempo limite configurável e espiões em
// AbortController, setTimeout e clearTimeout.
function montarAmbienteApi(urlDaApi, timeoutMs, comportamentoFetch, sequencia) {
  const fetchFalso = criarFetchFalso(comportamentoFetch);
  const storage = criarStorageFalso();
  const temporizador = criarTemporizadorFalso();
  const AbortControllerFalso = criarAbortControllerFalso();
  const agendados = [];
  const limpos = [];
  const ponto = nucleo.criarPontoDeIntegracao({
    config: { API_CHAMADOS_URL: urlDaApi, TIMEOUT_ENVIO_MS: timeoutMs },
    fetch: fetchFalso,
    AbortController: AbortControllerFalso,
    setTimeout(fn, ms) {
      const id = temporizador.setTimeout(fn, ms);
      agendados.push({ id, ms });
      return id;
    },
    clearTimeout(id) {
      limpos.push(id);
      temporizador.clearTimeout(id);
    },
    storage,
    agora: criarRelogio().agora,
    sorteio: criarSorteio(sequencia)
  });
  return { ponto, fetchFalso, storage, AbortControllerFalso, temporizador, agendados, limpos };
}

const CAMPOS_DO_CONTRATO = [
  'versaoContrato', 'chaveIdempotencia', 'abertoEm', 'nome', 'email', 'telefone',
  'descricao', 'aceiteTermos', 'aceiteEm', 'modelo', 'problemaId', 'problemaTitulo',
  'passosPercorridos', 'totalPassos'
];

// O resultado não pode conter dados pessoais do chamado nem nada do corpo da
// resposta da API. `permitido` é o JSON do resultado esperado (o esqueleto).
// A conferência é ESTRUTURAL, não por substring: busca por substring gera falso
// positivo quando um dado curto do chamado (nome "a", "ok", "api") ou um
// protocolo legítimo da API (ex.: "ecoa") coincide com parte do esqueleto.
// Aqui: (1) o resultado tem exatamente as chaves do esqueleto, (2) cada valor é
// igual ao do esqueleto, e (3) a única parte do resultado que pode vir da
// resposta da API (o protocolo) é o valor esperado, nunca o eco do chamado.
function assertSemDadosPessoais(resultado, c, permitido) {
  const esqueleto = JSON.parse(permitido);
  assert.deepEqual(Object.keys(resultado).sort(), Object.keys(esqueleto).sort(), 'chaves do resultado');
  for (const chave of Object.keys(esqueleto)) {
    assert.deepEqual(resultado[chave], esqueleto[chave], 'valor de ' + chave);
  }
  // Nenhuma chave do resultado carrega objeto/lista (onde caberia um eco do corpo).
  for (const valor of Object.values(resultado)) {
    assert.notEqual(typeof valor, 'object', 'valor aninhado no resultado');
  }
  // O resultado nunca é, nem tem como valor, o objeto do chamado.
  for (const campo of ['nome', 'email', 'telefone', 'descricao']) {
    assert.equal(Object.prototype.hasOwnProperty.call(resultado, campo), false, 'campo ' + campo + ' no resultado');
  }
}

// Feature: ticket-opening-screen, Property 19: Requisição em Modo_API
test('Property 19: em Modo_API, enviar faz um único POST JSON com o payload do chamado e usa só o fetch', async () => {
  await fc.assert(
    fc.asyncProperty(
      urlDeApi,
      chamado,
      fc.integer({ min: 1, max: 120000 }),
      sequenciaDeSorteio,
      async (url, c, timeoutMs, sequencia) => {
        const antes = JSON.stringify(c);
        const esperado = nucleo.serializar(nucleo.montarPayload(c));
        const protocoloDaApi = '7731-0042';
        // A resposta devolve, além do protocolo, um eco dos dados pessoais:
        // nada disso pode chegar ao resultado.
        const env = montarAmbienteApi(
          url,
          timeoutMs,
          { status: 201, corpo: { protocolo: protocoloDaApi, eco: { nome: c.nome, email: c.email, telefone: c.telefone, descricao: c.descricao } } },
          sequencia
        );
        const resultado = await env.ponto.enviar(c);

        // exatamente um fetch, na URL configurada
        assert.equal(env.fetchFalso.chamadas.length, 1);
        const { url: urlChamada, init } = env.fetchFalso.chamadas[0];
        assert.equal(urlChamada, url);

        // método, cabeçalho, corpo e opções de privacidade
        assert.equal(init.method, 'POST');
        assert.deepEqual(init.headers, { 'Content-Type': 'application/json' });
        assert.equal(typeof init.body, 'string');
        assert.equal(init.body, esperado);
        assert.deepEqual(JSON.parse(init.body), JSON.parse(nucleo.serializar(nucleo.montarPayload(c))));
        const corpo = JSON.parse(init.body);
        assert.deepEqual(Object.keys(corpo).sort(), CAMPOS_DO_CONTRATO.slice().sort());
        assert.equal('protocolo' in corpo, false);
        assert.equal('modoEnvio' in corpo, false);
        assert.equal(init.credentials, 'omit');
        assert.equal(init.cache, 'no-store');
        assert.equal(init.referrerPolicy, 'no-referrer');

        // sinal do AbortController falso
        assert.equal(env.AbortControllerFalso.instancias.length, 1);
        assert.equal(init.signal, env.AbortControllerFalso.instancias[0].signal);

        // temporizador agendado com o tempo limite configurado e limpo ao final
        assert.equal(env.agendados.length, 1);
        assert.equal(env.agendados[0].ms, timeoutMs);
        assert.deepEqual(env.limpos, [env.agendados[0].id]);
        assert.equal(env.temporizador.pendentes(), 0);
        assert.equal(init.signal.aborted, false);

        // não toca no storage nem gera protocolo local
        assert.equal(env.storage.chamadas.length, 0);
        assert.equal(env.storage.contar('setItem'), 0);
        assert.equal(env.storage.contar('getItem'), 0);
        assert.equal(env.storage.dados.size, 0);

        // resultado: só ok, protocolo da API e modo; sem corpo da resposta nem dados pessoais
        assert.deepEqual(resultado, { ok: true, protocolo: protocoloDaApi, modo: 'api' });
        assertSemDadosPessoais(resultado, c, JSON.stringify({ ok: true, protocolo: protocoloDaApi, modo: 'api' }));
        // sem copiar o corpo: o resultado não tem a chave `eco` (checagem estrutural)
        assert.equal('eco' in resultado, false);

        // o chamado não é alterado
        assert.equal(JSON.stringify(c), antes);
      }
    ),
    { numRuns: 150 }
  );
});

// Feature: ticket-opening-screen, Property 19: Requisição em Modo_API
test('Property 19: mesmo com resposta de erro ou inválida, a requisição é única e o resultado não vaza dados pessoais', async () => {
  const respostas = fc.constantFrom(
    { comportamento: 'http', status: 500 },
    { comportamento: 'http', status: 400 },
    { comportamento: 'invalida', status: 200 },
    { comportamento: 'invalida', status: 204 },
    { comportamento: 'rede' }
  );

  await fc.assert(
    fc.asyncProperty(urlDeApi, chamado, fc.integer({ min: 1, max: 120000 }), respostas, async (url, c, timeoutMs, r) => {
      const eco = { nome: c.nome, email: c.email, telefone: c.telefone, descricao: c.descricao };
      let comportamento;
      if (r.comportamento === 'http') comportamento = { status: r.status, corpo: { erro: 'falhou', eco } };
      else if (r.comportamento === 'invalida') comportamento = { status: r.status, corpo: { protocolo: 123, eco } };
      else comportamento = { rejeita: new TypeError('Failed to fetch') };

      const env = montarAmbienteApi(url, timeoutMs, comportamento);
      const resultado = await env.ponto.enviar(c);

      // uma única requisição, sem retentativa, sem storage
      assert.equal(env.fetchFalso.chamadas.length, 1);
      assert.equal(env.fetchFalso.chamadas[0].init.body, nucleo.serializar(nucleo.montarPayload(c)));
      assert.equal(env.storage.chamadas.length, 0);

      // temporizador agendado com o tempo configurado e sempre limpo
      assert.equal(env.agendados.length, 1);
      assert.equal(env.agendados[0].ms, timeoutMs);
      assert.deepEqual(env.limpos, [env.agendados[0].id]);

      // resultado de falha, sem protocolo local, corpo da resposta nem dados pessoais
      assert.equal(resultado.ok, false);
      assert.equal('protocolo' in resultado, false);
      const esperado =
        r.comportamento === 'http'
          ? { ok: false, categoria: 'http', status: r.status }
          : r.comportamento === 'invalida'
            ? { ok: false, categoria: 'resposta-invalida' }
            : { ok: false, categoria: 'rede' };
      assert.deepEqual(resultado, esperado);
      assertSemDadosPessoais(resultado, c, JSON.stringify(esperado));
      // sem copiar o corpo da resposta (estrutural, não por substring)
      assert.equal('eco' in resultado, false);
      assert.equal('erro' in resultado, false);
    }),
    { numRuns: 150 }
  );
});

/* ==========================================================
 * Property 20: Classificação da resposta da API
 * ========================================================== */

// Protocolo da API: 1 a 64 caracteres sem espaço nas pontas e que NÃO tem a
// forma do protocolo local (TRES-AAAAMMDD-XXXXXX), para provar que o valor
// devolvido vem da API e não do cliente.
const protocoloDaApiValido = fc
  .stringMatching(/^[A-Za-z0-9._-]{1,64}$/)
  .filter((p) => !nucleo.ehProtocoloLocal(p));
const espacoAoRedor = fc.stringMatching(/^[ \t\n\r]{0,5}$/);
const protocoloComEspacos = fc.tuple(espacoAoRedor, protocoloDaApiValido, espacoAoRedor);

// Status 2xx e status fora de 200..299 (inclui 1xx, 3xx, 4xx, 5xx, NaN e não-número).
const status2xx = fc.integer({ min: 200, max: 299 });
const statusFora = fc.oneof(
  fc.integer({ min: 100, max: 199 }),
  fc.integer({ min: 300, max: 599 }),
  fc.integer({ min: -1000, max: 99 }),
  fc.integer({ min: 600, max: 100000 }),
  fc.constantFrom(NaN, Infinity, -Infinity),
  fc.constantFrom(undefined, null, true, false, '200', '404', 'ok', '', {}, [], [200])
);

// Valores de `protocolo` que a API não pode aceitar.
const protocoloInvalido = fc.oneof(
  fc.constantFrom('', ' ', '   ', '\t', '\n', ' \t\r\n '),
  fc.stringMatching(/^[ \t\n\r]{0,6}$/),
  fc.tuple(espacoAoRedor, fc.stringMatching(/^[A-Za-z0-9]{65,90}$/), espacoAoRedor).map(([a, p, b]) => a + p + b),
  fc.constantFrom(undefined, null, true, false, 0, 1, 42, NaN, {}, [], ['PROTO-1'], { valor: 'PROTO-1' }),
  fc.integer(),
  fc.double()
);

// Corpos 2xx que não são objeto simples.
const corpoNaoObjeto = fc.oneof(
  fc.constantFrom(null, undefined, true, false, 0, 1, 'texto', '', '{"protocolo":"X"}'),
  fc.integer(),
  fc.double(),
  fc.string({ maxLength: 20 }),
  fc.array(fc.string({ maxLength: 8 }), { maxLength: 3 }),
  protocoloDaApiValido.map((p) => [{ protocolo: p }])
);

// Feature: ticket-opening-screen, Property 20: Classificação da resposta da API
test('Property 20: interpretarRespostaApi aceita 2xx com protocolo de 1 a 64 caracteres e devolve o valor aparado', () => {
  fc.assert(
    fc.property(
      status2xx,
      protocoloComEspacos,
      fc.dictionary(fc.constantFrom('eco', 'mensagem', 'id', 'dados'), fc.string({ maxLength: 8 }), { maxKeys: 3 }),
      (status, [antes, protocolo, depois], extras) => {
        const corpo = Object.assign({}, extras, { protocolo: antes + protocolo + depois });
        assert.deepEqual(nucleo.interpretarRespostaApi(status, corpo), { ok: true, protocolo });
      }
    ),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 20: Classificação da resposta da API
test('Property 20: interpretarRespostaApi em 2xx com protocolo ausente, vazio, longo ou não-texto devolve resposta-invalida', () => {
  fc.assert(
    fc.property(status2xx, protocoloInvalido, (status, valor) => {
      assert.deepEqual(nucleo.interpretarRespostaApi(status, { protocolo: valor }), { ok: false, categoria: 'resposta-invalida' });
    }),
    { numRuns: 200 }
  );

  // protocolo ausente
  fc.assert(
    fc.property(status2xx, fc.dictionary(fc.constantFrom('eco', 'mensagem', 'id', 'Protocolo', 'protocol'), fc.string({ maxLength: 8 }), { maxKeys: 3 }), (status, corpo) => {
      assert.deepEqual(nucleo.interpretarRespostaApi(status, corpo), { ok: false, categoria: 'resposta-invalida' });
    }),
    { numRuns: 100 }
  );

  // corpo null, array ou não-objeto
  fc.assert(
    fc.property(status2xx, corpoNaoObjeto, (status, corpo) => {
      assert.deepEqual(nucleo.interpretarRespostaApi(status, corpo), { ok: false, categoria: 'resposta-invalida' });
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 20: Classificação da resposta da API
test('Property 20: interpretarRespostaApi fora de 200..299 devolve categoria http com o status, qualquer que seja o corpo', () => {
  const corpoQualquer = fc.oneof(corpoNaoObjeto, protocoloDaApiValido.map((p) => ({ protocolo: p })));
  fc.assert(
    fc.property(statusFora, corpoQualquer, (status, corpo) => {
      const r = nucleo.interpretarRespostaApi(status, corpo);
      assert.equal(r.ok, false);
      assert.equal(r.categoria, 'http');
      assert.equal('protocolo' in r, false);
      assert.ok(Object.is(r.status, status), 'status repassado: ' + String(status));
    }),
    { numRuns: 200 }
  );
});

// Feature: ticket-opening-screen, Property 20: Classificação da resposta da API
test('Property 20: no Modo_API, 2xx válido devolve ok, modo api e o protocolo aparado da API, sem copiar o corpo nem gerar protocolo local', async () => {
  await fc.assert(
    fc.asyncProperty(urlDeApi, chamado, status2xx, protocoloComEspacos, async (url, c, status, [antes, protocolo, depois]) => {
      const env = montarAmbienteApi(
        url,
        10000,
        { status, corpo: { protocolo: antes + protocolo + depois, eco: { nome: c.nome, email: c.email, telefone: c.telefone, descricao: c.descricao }, extra: 'nao-copiar' } }
      );
      const resultado = await env.ponto.enviar(c);

      assert.deepEqual(resultado, { ok: true, protocolo, modo: 'api' });
      assert.equal(nucleo.ehProtocoloLocal(resultado.protocolo), false);
      // sem copiar o corpo: nenhuma chave além de ok/protocolo/modo (estrutural;
      // o protocolo da API pode legitimamente conter "eco", "ecoa" etc.)
      assert.deepEqual(Object.keys(resultado).sort(), ['modo', 'ok', 'protocolo']);
      assert.equal('eco' in resultado, false);
      assert.equal('extra' in resultado, false);
      assertSemDadosPessoais(resultado, c, JSON.stringify({ ok: true, protocolo, modo: 'api' }));
      assert.equal(env.fetchFalso.chamadas.length, 1);
      assert.equal(env.storage.chamadas.length, 0);
    }),
    { numRuns: 120 }
  );
});

// Feature: ticket-opening-screen, Property 20: Classificação da resposta da API
test('Property 20: no Modo_API, 2xx inválido, json() que rejeita e status fora de 2xx são classificados sem copiar o corpo', async () => {
  const caso = fc.oneof(
    // 2xx com protocolo inválido
    fc.tuple(status2xx, protocoloInvalido).map(([status, valor]) => ({
      comportamento: { status, corpo: { protocolo: valor } },
      esperado: { ok: false, categoria: 'resposta-invalida' }
    })),
    // 2xx com corpo que não é objeto
    fc.tuple(status2xx, fc.constantFrom(null, [], [{ protocolo: 'X-1' }], 7, true)).map(([status, corpo]) => ({
      comportamento: { status, corpo },
      esperado: { ok: false, categoria: 'resposta-invalida' }
    })),
    // 2xx cujo json() rejeita (sem corpo ou texto que não é JSON)
    fc.tuple(status2xx, fc.constantFrom(undefined, '<html>', 'nao e json', '{')).map(([status, corpo]) => ({
      comportamento: corpo === undefined ? { status } : { status, corpo },
      esperado: { ok: false, categoria: 'resposta-invalida' }
    })),
    // fora de 2xx
    fc.tuple(fc.oneof(fc.integer({ min: 100, max: 199 }), fc.integer({ min: 300, max: 599 }))).map(([status]) => ({
      comportamento: { status, corpo: { protocolo: 'PROTOCOLO-DA-API' } },
      esperado: { ok: false, categoria: 'http', status }
    }))
  );

  await fc.assert(
    fc.asyncProperty(urlDeApi, chamado, caso, async (url, c, { comportamento, esperado }) => {
      const env = montarAmbienteApi(url, 10000, comportamento);
      const resultado = await env.ponto.enviar(c);

      assert.deepEqual(resultado, esperado);
      assert.equal('protocolo' in resultado, false);
      assert.equal('modo' in resultado, false);
      assert.equal(env.fetchFalso.chamadas.length, 1);
      assert.equal(env.storage.chamadas.length, 0);
      assertSemDadosPessoais(resultado, c, JSON.stringify(esperado));
    }),
    { numRuns: 150 }
  );
});

// Feature: ticket-opening-screen, Property 20: Classificação da resposta da API
test('Property 20: no Modo_API, json() que lança de forma síncrona também vira resposta-invalida', async () => {
  await fc.assert(
    fc.asyncProperty(urlDeApi, chamado, status2xx, async (url, c, status) => {
      const temporizador = criarTemporizadorFalso();
      const storage = criarStorageFalso();
      let chamadas = 0;
      const ponto = nucleo.criarPontoDeIntegracao({
        config: { API_CHAMADOS_URL: url, TIMEOUT_ENVIO_MS: 10000 },
        fetch() {
          chamadas += 1;
          return Promise.resolve({
            status,
            json() {
              throw new SyntaxError('Unexpected token');
            }
          });
        },
        AbortController: criarAbortControllerFalso(),
        setTimeout: temporizador.setTimeout,
        clearTimeout: temporizador.clearTimeout,
        storage,
        agora: criarRelogio().agora,
        sorteio: criarSorteio()
      });
      const resultado = await ponto.enviar(c);

      assert.deepEqual(resultado, { ok: false, categoria: 'resposta-invalida' });
      assert.equal(chamadas, 1);
      assert.equal(storage.chamadas.length, 0);
      assert.equal(temporizador.pendentes(), 0);
    }),
    { numRuns: 100 }
  );
});

/* ==========================================================
 * Property 21: Envio em Modo_Prototipo é idempotente por chave
 * ========================================================== */

const CHAVE_EVENTOS = 'tres-autoatendimento-eventos';
const LIMITE_CHAMADOS = 50;

// Sorteio que nunca repete o sufixo de um protocolo: o k-ésimo protocolo
// sorteado usa os 6 dígitos (base `max`) do número `semente + k`. Assim o
// teste não depende de colisão por acaso e os protocolos gerados são únicos.
function criarSorteioDeSufixosUnicos(semente) {
  let chamadas = 0;
  return function sorteio(max) {
    const protocolo = semente + Math.floor(chamadas / 6);
    const posicao = chamadas % 6;
    chamadas += 1;
    let v = protocolo;
    for (let i = 0; i < posicao; i++) v = Math.floor(v / max);
    return v % max;
  };
}

// Modo_Prototipo com repositório inicial e chave de métricas preenchidos.
function montarAmbientePrototipo(urlDaApi, listaInicial, semente) {
  const fetchFalso = criarFetchFalso({ status: 200, corpo: { protocolo: 'NAO-DEVE-SER-USADO' } });
  const eventosIniciais = '[{"tipo":"resolvido","em":"2026-01-01T00:00:00.000Z","problema":1,"modelo":null}]';
  const inicial = { [CHAVE_EVENTOS]: eventosIniciais };
  if (listaInicial) inicial[CHAVE_CHAMADOS] = JSON.stringify(listaInicial);
  const storage = criarStorageFalso({ inicial });
  const temporizador = criarTemporizadorFalso();
  const ponto = nucleo.criarPontoDeIntegracao({
    config: { API_CHAMADOS_URL: urlDaApi, TIMEOUT_ENVIO_MS: 10000 },
    fetch: fetchFalso,
    AbortController: criarAbortControllerFalso(),
    setTimeout: temporizador.setTimeout,
    clearTimeout: temporizador.clearTimeout,
    storage,
    agora: criarRelogio().agora,
    sorteio: criarSorteioDeSufixosUnicos(semente)
  });
  return { ponto, fetchFalso, storage, eventosIniciais };
}

// O que o repositório deve guardar para o chamado `c` com o protocolo `p`.
function comoGravado(c, protocolo) {
  return Object.assign(JSON.parse(JSON.stringify(c)), { protocolo, modoEnvio: 'prototipo' });
}

function lerGravados(storage) {
  return JSON.parse(storage.dados.get(CHAVE_CHAMADOS));
}

const semente = fc.integer({ min: 0, max: 1000000 });

// Feature: ticket-opening-screen, Property 21: Envio em Modo_Prototipo é idempotente por chave
test('Property 21: reenviar o mesmo chamado (em série ou em paralelo) devolve o mesmo protocolo e grava um único item', async () => {
  await fc.assert(
    fc.asyncProperty(
      fc.oneof(urlDePrototipo, valorNaoTexto),
      fc.array(chamadoGravado, { maxLength: 6 }),
      chamado,
      fc.integer({ min: 1, max: 5 }),
      fc.boolean(),
      semente,
      async (url, anteriores, c, repeticoes, emParalelo, sem) => {
        // lista anterior sem a chave do chamado novo, com protocolos únicos
        const inicial = anteriores
          .filter((a) => a.chaveIdempotencia !== c.chaveIdempotencia)
          .map((a, i) => Object.assign({}, a, { protocolo: 'TRES-20200101-ANT' + String(i).padStart(3, '0') }));
        const inicialSerializada = JSON.stringify(inicial);
        const env = montarAmbientePrototipo(url, inicial, sem);
        const antes = JSON.stringify(c);

        let resultados;
        if (emParalelo) {
          // as chamadas partem juntas: nenhuma espera a outra terminar
          const promessas = [];
          for (let i = 0; i < repeticoes + 1; i++) promessas.push(env.ponto.enviar(c));
          resultados = await Promise.all(promessas);
        } else {
          resultados = [];
          for (let i = 0; i < repeticoes; i++) resultados.push(await env.ponto.enviar(c));
        }

        // mesma resposta em todas as chamadas, com protocolo local válido
        const primeiro = resultados[0];
        assert.equal(primeiro.ok, true);
        assert.equal(primeiro.modo, 'prototipo');
        assert.equal(nucleo.ehProtocoloLocal(primeiro.protocolo), true, primeiro.protocolo);
        resultados.forEach((r) => assert.deepEqual(r, primeiro));

        // um único item novo, no fim, com o protocolo devolvido; anteriores intactos
        const gravados = lerGravados(env.storage);
        assert.equal(gravados.length, inicial.length + 1);
        assert.deepEqual(gravados.slice(0, inicial.length), JSON.parse(inicialSerializada));
        assert.deepEqual(gravados[inicial.length], comoGravado(c, primeiro.protocolo));
        assert.equal(gravados[inicial.length].modoEnvio, 'prototipo');
        assert.equal(gravados.filter((g) => g.chaveIdempotencia === c.chaveIdempotencia).length, 1);
        assert.equal(gravados.filter((g) => g.protocolo === primeiro.protocolo).length, 1);

        // só a primeira chamada grava; o fetch nunca é usado
        assert.equal(env.storage.contar('setItem'), 1);
        assert.equal(env.fetchFalso.chamadas.length, 0);

        // métricas intocadas e chamado de entrada inalterado
        assert.equal(env.storage.dados.get(CHAVE_EVENTOS), env.eventosIniciais);
        assert.equal(env.storage.chamadas.some((x) => x.chave === CHAVE_EVENTOS), false);
        assert.equal(JSON.stringify(c), antes);
      }
    ),
    { numRuns: 150 }
  );
});

// Feature: ticket-opening-screen, Property 21: Envio em Modo_Prototipo é idempotente por chave
test('Property 21: duas chamadas simultâneas a enviar() no mesmo ponto não gravam duplicado (gravação ocorre na própria chamada)', async () => {
  await fc.assert(
    fc.asyncProperty(fc.oneof(urlDePrototipo, valorNaoTexto), chamado, semente, async (url, c, sem) => {
      const env = montarAmbientePrototipo(url, undefined, sem);

      // sem await entre as duas chamadas: se houvesse janela entre ler e
      // gravar, as duas leriam o repositório vazio
      const p1 = env.ponto.enviar(c);
      const p2 = env.ponto.enviar(c);
      assert.equal(env.storage.contar('setItem'), 1, 'a gravação já aconteceu de forma síncrona');

      const [r1, r2] = await Promise.all([p1, p2]);
      assert.equal(r1.ok, true);
      assert.deepEqual(r2, r1);
      assert.equal(lerGravados(env.storage).length, 1);
      assert.equal(lerGravados(env.storage)[0].protocolo, r1.protocolo);
      assert.equal(env.storage.contar('setItem'), 1);
      assert.equal(env.fetchFalso.chamadas.length, 0);
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 21: Envio em Modo_Prototipo é idempotente por chave
test('Property 21: chamados com chaves diferentes recebem protocolos únicos e ficam todos gravados, preservando os anteriores', async () => {
  await fc.assert(
    fc.asyncProperty(
      fc.oneof(urlDePrototipo, valorNaoTexto),
      fc.array(chamadoGravado, { maxLength: 6 }),
      fc.uniqueArray(chamado, { minLength: 2, maxLength: 8, selector: (c) => c.chaveIdempotencia }),
      fc.boolean(),
      semente,
      async (url, anteriores, novos, emParalelo, sem) => {
        const chavesNovas = new Set(novos.map((c) => c.chaveIdempotencia));
        const inicial = anteriores
          .filter((a) => !chavesNovas.has(a.chaveIdempotencia))
          .map((a, i) => Object.assign({}, a, { protocolo: 'TRES-20200101-ANT' + String(i).padStart(3, '0') }));
        const inicialSerializada = JSON.stringify(inicial);
        const env = montarAmbientePrototipo(url, inicial, sem);

        let resultados;
        if (emParalelo) {
          resultados = await Promise.all(novos.map((c) => env.ponto.enviar(c)));
        } else {
          resultados = [];
          for (const c of novos) resultados.push(await env.ponto.enviar(c));
        }

        resultados.forEach((r) => {
          assert.equal(r.ok, true);
          assert.equal(r.modo, 'prototipo');
          assert.equal(nucleo.ehProtocoloLocal(r.protocolo), true, r.protocolo);
        });
        const protocolos = resultados.map((r) => r.protocolo);
        assert.equal(new Set(protocolos).size, novos.length, 'protocolos diferentes entre si');

        // anteriores preservados e novos gravados, em ordem, com o protocolo devolvido
        const gravados = lerGravados(env.storage);
        assert.equal(gravados.length, inicial.length + novos.length);
        assert.deepEqual(gravados.slice(0, inicial.length), JSON.parse(inicialSerializada));
        novos.forEach((c, i) => {
          assert.deepEqual(gravados[inicial.length + i], comoGravado(c, protocolos[i]));
        });
        const todos = gravados.map((g) => g.protocolo);
        assert.equal(new Set(todos).size, todos.length, 'nenhum protocolo repetido no repositório');
        inicial.forEach((a) => assert.equal(protocolos.includes(a.protocolo), false));

        // reenviar qualquer um deles depois não acrescenta nada
        const setItemAntes = env.storage.contar('setItem');
        for (let i = 0; i < novos.length; i++) {
          const r = await env.ponto.enviar(novos[i]);
          assert.deepEqual(r, resultados[i]);
        }
        assert.equal(lerGravados(env.storage).length, gravados.length);
        assert.equal(env.storage.contar('setItem'), setItemAntes);

        assert.equal(env.fetchFalso.chamadas.length, 0);
        assert.equal(env.storage.dados.get(CHAVE_EVENTOS), env.eventosIniciais);
      }
    ),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 21: Envio em Modo_Prototipo é idempotente por chave
test('Property 21: ao passar de 50 chamados gravados, o mais antigo sai e os mais recentes ficam', async () => {
  await fc.assert(
    fc.asyncProperty(
      fc.oneof(urlDePrototipo, valorNaoTexto),
      fc.array(chamadoGravado, { minLength: 1, maxLength: 4 }),
      fc.integer({ min: 44, max: LIMITE_CHAMADOS }),
      fc.uniqueArray(chamado, { minLength: 1, maxLength: 9, selector: (c) => c.chaveIdempotencia }),
      fc.boolean(),
      semente,
      async (url, modelos, tamanhoInicial, novos, emParalelo, sem) => {
        // repositório já com `tamanhoInicial` itens (até o limite), chaves e protocolos únicos
        const inicial = Array.from({ length: tamanhoInicial }, (_, i) =>
          Object.assign({}, modelos[i % modelos.length], {
            chaveIdempotencia: 'chave-anterior-' + i,
            protocolo: 'TRES-20200101-ANT' + String(i).padStart(3, '0')
          })
        );
        const env = montarAmbientePrototipo(url, inicial, sem);

        let resultados;
        if (emParalelo) {
          resultados = await Promise.all(novos.map((c) => env.ponto.enviar(c)));
        } else {
          resultados = [];
          for (const c of novos) resultados.push(await env.ponto.enviar(c));
        }
        resultados.forEach((r) => assert.equal(r.ok, true));

        // esperado: os 50 mais recentes de (anteriores + novos), na ordem de envio
        const esperados = JSON.parse(JSON.stringify(inicial))
          .concat(novos.map((c, i) => comoGravado(c, resultados[i].protocolo)))
          .slice(-LIMITE_CHAMADOS);
        const gravados = lerGravados(env.storage);
        assert.equal(gravados.length, Math.min(LIMITE_CHAMADOS, tamanhoInicial + novos.length));
        assert.ok(gravados.length <= LIMITE_CHAMADOS);
        assert.deepEqual(gravados, esperados);

        // o mais recente é sempre o último chamado enviado
        assert.equal(gravados[gravados.length - 1].chaveIdempotencia, novos[novos.length - 1].chaveIdempotencia);
        // se passou do limite, os mais antigos saíram
        const excedente = tamanhoInicial + novos.length - LIMITE_CHAMADOS;
        if (excedente > 0) {
          const chavesGravadas = new Set(gravados.map((g) => g.chaveIdempotencia));
          for (let i = 0; i < excedente; i++) assert.equal(chavesGravadas.has('chave-anterior-' + i), false);
        }
        const protocolos = gravados.map((g) => g.protocolo);
        assert.equal(new Set(protocolos).size, protocolos.length);

        assert.equal(env.fetchFalso.chamadas.length, 0);
        assert.equal(env.storage.dados.get(CHAVE_EVENTOS), env.eventosIniciais);
      }
    ),
    { numRuns: 100 }
  );
});

/* ==========================================================
 * Property 22: Falha de registro não deixa rastro
 * ========================================================== */

const METODOS_DE_CONSOLE = ['log', 'error', 'warn', 'info', 'debug'];

// Executa `fn` com os cinco métodos de console trocados por espiões e devolve
// { valor, chamadas }. Os originais voltam sempre, mesmo se `fn` falhar.
async function comConsoleEspiado(fn) {
  const originais = {};
  let chamadas = 0;
  METODOS_DE_CONSOLE.forEach((nome) => {
    originais[nome] = console[nome];
    console[nome] = () => {
      chamadas += 1;
    };
  });
  try {
    const valor = await fn();
    return { valor, chamadas };
  } finally {
    METODOS_DE_CONSOLE.forEach((nome) => {
      console[nome] = originais[nome];
    });
  }
}

// Lista anterior com protocolos e chaves únicos, sem a chave do chamado novo.
// `tamanho` null mantém a lista como veio; um número a expande até esse
// tamanho (50 = repositório no limite).
function listaAnterior(modelos, tamanho, c) {
  if (tamanho === null) {
    return modelos
      .filter((a) => a.chaveIdempotencia !== c.chaveIdempotencia)
      .map((a, i) => Object.assign({}, a, { protocolo: 'TRES-20200101-ANT' + String(i).padStart(3, '0') }));
  }
  return Array.from({ length: tamanho }, (_, i) =>
    Object.assign({}, modelos[i % modelos.length], {
      chaveIdempotencia: 'chave-anterior-' + i,
      protocolo: 'TRES-20200101-ANT' + String(i).padStart(3, '0')
    })
  );
}

// Modo_Prototipo com falhas programáveis. Repositório e chave de métricas
// partem preenchidos; `fetch` e `AbortController` existem para provar que não
// são usados.
function montarAmbienteComFalha(urlDaApi, lista, falhas, sorteio) {
  const fetchFalso = criarFetchFalso({ status: 200, corpo: { protocolo: 'NAO-DEVE-SER-USADO' } });
  const eventosIniciais = '[{"tipo":"resolvido","em":"2026-01-01T00:00:00.000Z","problema":1,"modelo":null}]';
  const inicial = { [CHAVE_EVENTOS]: eventosIniciais };
  if (lista) inicial[CHAVE_CHAMADOS] = JSON.stringify(lista);
  const storage = criarStorageFalso(Object.assign({ inicial }, falhas));
  const temporizador = criarTemporizadorFalso();
  const ponto = nucleo.criarPontoDeIntegracao({
    config: { API_CHAMADOS_URL: urlDaApi, TIMEOUT_ENVIO_MS: 10000 },
    fetch: fetchFalso,
    AbortController: criarAbortControllerFalso(),
    setTimeout: temporizador.setTimeout,
    clearTimeout: temporizador.clearTimeout,
    storage,
    agora: criarRelogio().agora,
    sorteio
  });
  return { ponto, fetchFalso, storage, instantaneoInicial: storage.instantaneo() };
}

const tamanhoInicial = fc.oneof(fc.constant(null), fc.constant(LIMITE_CHAMADOS));
const modelosGravados = fc.array(chamadoGravado, { minLength: 1, maxLength: 6 });
// null = repositório ainda inexistente
const comOuSemRepositorio = fc.boolean();

// Conferências comuns a toda falha de registro.
function assertFalhaSemRastro(resultado, c, categoria, env) {
  assert.deepEqual(resultado, { ok: false, categoria });
  assert.equal('protocolo' in resultado, false);
  assertSemDadosPessoais(resultado, c, JSON.stringify({ ok: false, categoria }));
  // nada de rede
  assert.equal(env.fetchFalso.chamadas.length, 0);
  // métricas intocadas
  assert.equal(env.storage.chamadas.some((x) => x.chave === CHAVE_EVENTOS), false);
  assert.equal(env.storage.dados.get(CHAVE_EVENTOS), env.instantaneoInicial[CHAVE_EVENTOS]);
  // o conteúdo armazenado é idêntico ao de antes
  assert.deepEqual(env.storage.instantaneo(), env.instantaneoInicial);
}

// Feature: ticket-opening-screen, Property 22: Falha de registro não deixa rastro
test('Property 22: em Modo_Prototipo, setItem que lança devolve armazenamento e deixa o repositório e as métricas intactos', async () => {
  await fc.assert(
    fc.asyncProperty(
      fc.oneof(urlDePrototipo, valorNaoTexto),
      modelosGravados,
      tamanhoInicial,
      comOuSemRepositorio,
      chamado,
      sequenciaDeSorteio,
      async (url, modelos, tamanho, comRepositorio, c, sequencia) => {
        const lista = listaAnterior(modelos, tamanho, c);
        const env = montarAmbienteComFalha(url, comRepositorio ? lista : undefined, { lancaEmSetItem: true }, criarSorteio(sequencia));
        const antes = JSON.stringify(c);

        const { valor: resultado, chamadas } = await comConsoleEspiado(() => env.ponto.enviar(c));

        assertFalhaSemRastro(resultado, c, 'armazenamento', env);
        // só tentou gravar o repositório de chamados, uma vez, e nunca a chave de métricas
        assert.equal(env.storage.contar('setItem') <= 1, true);
        assert.equal(env.storage.chamadas.filter((x) => x.metodo === 'setItem').every((x) => x.chave === CHAVE_CHAMADOS), true);
        assert.equal(env.storage.contar('removeItem'), 0);
        assert.equal(chamadas, 0, 'console usado durante o envio');
        assert.equal(JSON.stringify(c), antes);
      }
    ),
    { numRuns: 120 }
  );
});

// Feature: ticket-opening-screen, Property 22: Falha de registro não deixa rastro
test('Property 22: em Modo_Prototipo, getItem que lança devolve armazenamento sem gravar nem apagar nada', async () => {
  await fc.assert(
    fc.asyncProperty(
      fc.oneof(urlDePrototipo, valorNaoTexto),
      modelosGravados,
      tamanhoInicial,
      comOuSemRepositorio,
      chamado,
      sequenciaDeSorteio,
      fc.boolean(),
      async (url, modelos, tamanho, comRepositorio, c, sequencia, tambemSetItem) => {
        const lista = listaAnterior(modelos, tamanho, c);
        const falhas = { lancaEmGetItem: true, lancaEmSetItem: tambemSetItem };
        const env = montarAmbienteComFalha(url, comRepositorio ? lista : undefined, falhas, criarSorteio(sequencia));

        const { valor: resultado, chamadas } = await comConsoleEspiado(() => env.ponto.enviar(c));

        assertFalhaSemRastro(resultado, c, 'armazenamento', env);
        // a leitura falhou: nada foi gravado, removido nem sobrescrito por uma lista vazia
        assert.equal(env.storage.contar('setItem'), 0);
        assert.equal(env.storage.contar('removeItem'), 0);
        assert.equal(chamadas, 0, 'console usado durante o envio');
      }
    ),
    { numRuns: 120 }
  );
});

// Feature: ticket-opening-screen, Property 22: Falha de registro não deixa rastro
test('Property 22: em Modo_Prototipo, sorteio que só gera protocolo já existente esgota as 10 tentativas e devolve protocolo sem gravar', async () => {
  await fc.assert(
    fc.asyncProperty(
      fc.oneof(urlDePrototipo, valorNaoTexto),
      modelosGravados,
      tamanhoInicial,
      chamado,
      fc.integer({ min: 0, max: 35 }),
      async (url, modelos, tamanho, c, constante) => {
        // o protocolo que o sorteio constante sempre produz, com o relógio do ambiente
        const colidente = nucleo.gerarProtocolo(criarRelogio().agora(), () => constante);
        const existente = Object.assign({}, modelos[0], { chaveIdempotencia: 'chave-colidente', protocolo: colidente });
        const lista = [existente].concat(listaAnterior(modelos, tamanho, c)).slice(0, LIMITE_CHAMADOS);

        let usos = 0;
        const sorteioConstante = (max) => {
          usos += 1;
          return constante % max;
        };
        const env = montarAmbienteComFalha(url, lista, {}, sorteioConstante);

        const { valor: resultado, chamadas } = await comConsoleEspiado(() => env.ponto.enviar(c));

        assertFalhaSemRastro(resultado, c, 'protocolo', env);
        assert.equal(usos, 60, '10 tentativas de 6 sorteios cada');
        assert.equal(env.storage.contar('setItem'), 0);
        assert.equal(env.storage.contar('removeItem'), 0);
        assert.equal(chamadas, 0, 'console usado durante o envio');
      }
    ),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 22: Falha de registro não deixa rastro
test('Property 22: em Modo_Prototipo, a falha vem sempre como Promise resolvida, mesmo com sorteio e relógio que lançam', async () => {
  await fc.assert(
    fc.asyncProperty(fc.oneof(urlDePrototipo, valorNaoTexto), modelosGravados, chamado, async (url, modelos, c) => {
      const lista = listaAnterior(modelos, null, c);
      const env = montarAmbienteComFalha(url, lista, {}, () => {
        throw new Error('sorteio indisponível (falso)');
      });

      const { valor: promessa, chamadas } = await comConsoleEspiado(async () => {
        const p = env.ponto.enviar(c);
        assert.equal(p instanceof Promise, true);
        return p;
      });

      assertFalhaSemRastro(promessa, c, 'protocolo', env);
      assert.equal(env.storage.contar('setItem'), 0);
      assert.equal(chamadas, 0, 'console usado durante o envio');
    }),
    { numRuns: 100 }
  );
});

// Feature: ticket-opening-screen, Property 22: Falha de registro não deixa rastro
test('Property 22: em Modo_API, rede, HTTP de erro, resposta inválida e tempo esgotado falham sem protocolo, sem storage e sem console', async () => {
  const cenarios = fc.oneof(
    fc.constant({ tipo: 'rede', categoria: 'rede', comportamento: { rejeita: new TypeError('Failed to fetch') } }),
    fc.integer({ min: 100, max: 599 })
      .filter((s) => s < 200 || s > 299)
      .map((s) => ({ tipo: 'http', categoria: 'http', status: s, comportamento: { status: s, corpo: { erro: 'falhou' } } })),
    fc
      .constantFrom(
        { protocolo: 123 },
        { protocolo: '' },
        { protocolo: '   ' },
        { protocolo: 'x'.repeat(65) },
        { outro: 'sem protocolo' },
        [],
        null,
        'texto solto'
      )
      .chain((corpo) => fc.integer({ min: 200, max: 299 }).map((s) => ({ tipo: 'invalida', categoria: 'resposta-invalida', comportamento: { status: s, corpo } }))),
    fc.integer({ min: 200, max: 299 }).map((s) => ({ tipo: 'invalida', categoria: 'resposta-invalida', comportamento: { status: s } })),
    fc.constant({ tipo: 'timeout', categoria: 'timeout', comportamento: { semResposta: true } })
  );

  await fc.assert(
    fc.asyncProperty(
      urlDeApi,
      chamado,
      fc.integer({ min: 1, max: 120000 }),
      cenarios,
      modelosGravados,
      async (url, c, timeoutMs, cenario, modelos) => {
        const env = montarAmbienteApi(url, timeoutMs, cenario.comportamento);
        // storage com conteúdo preexistente: tem de continuar idêntico
        env.storage.dados.set(CHAVE_CHAMADOS, JSON.stringify(listaAnterior(modelos, null, c)));
        env.storage.dados.set(CHAVE_EVENTOS, '[]');
        const instantaneoInicial = env.storage.instantaneo();

        const { valor: resultado, chamadas } = await comConsoleEspiado(() => {
          const p = env.ponto.enviar(c);
          if (cenario.tipo === 'timeout') env.temporizador.avancar(timeoutMs);
          return p;
        });

        const esperado = { ok: false, categoria: cenario.categoria };
        if (cenario.tipo === 'http') esperado.status = cenario.status;
        assert.deepEqual(resultado, esperado);
        assert.equal('protocolo' in resultado, false);
        assertSemDadosPessoais(resultado, c, JSON.stringify(esperado));

        // uma única requisição e nenhuma chamada ao storage local
        assert.equal(env.fetchFalso.chamadas.length, 1);
        assert.equal(env.storage.chamadas.length, 0);
        assert.deepEqual(env.storage.instantaneo(), instantaneoInicial);

        // nenhum console durante o envio
        assert.equal(chamadas, 0, 'console usado durante o envio');
      }
    ),
    { numRuns: 150 }
  );
});
