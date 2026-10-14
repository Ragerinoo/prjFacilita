'use strict';
// Testes de propriedade da camada de envio do feedback (js/feedback.js):
// seleção do modo e do destino (Propriedade 10), requisição em Modo_API
// (Propriedade 12) e classificação do resultado do envio (Propriedade 13).
// Tudo com dublês: fetch espião, AbortController e temporizador falsos.
const test = require('node:test');
const assert = require('node:assert/strict');
const path = require('node:path');

const { fc, payloadFeedback, urlDeConfiguracao } = require('../geradores.js');
const {
  criarFetchFalso,
  criarStorageFalso,
  criarAbortControllerFalso,
  criarTemporizadorFalso
} = require('../falsos.js');

const base = require(path.join(__dirname, '..', '..', 'js', 'chamado.js'));
const feedback = require(path.join(__dirname, '..', '..', 'js', 'feedback.js')).criar(base);

const NUM_RUNS = 200;

/* ==========================================================
 * Apoio comum
 * ========================================================== */

// Monta o Ponto_de_Integracao_de_Feedback com todos os dublês.
function montarAmbiente(config, fetchFalso, opcoes) {
  const o = opcoes || {};
  const storage = criarStorageFalso();
  const temporizador = criarTemporizadorFalso();
  const AbortControllerFalso = criarAbortControllerFalso();
  const ponto = feedback.criarPontoDeIntegracao({
    config,
    fetch: fetchFalso,
    AbortController: o.semAbortController ? undefined : AbortControllerFalso,
    setTimeout: temporizador.setTimeout,
    clearTimeout: temporizador.clearTimeout,
    storage
  });
  return { ponto, storage, temporizador, AbortControllerFalso };
}

// Cede o turno até as microtarefas pendentes terminarem.
const esvaziarMicrotarefas = () => new Promise((resolve) => setImmediate(resolve));

// Só URLs que levam ao Modo_API.
const urlDeApi = urlDeConfiguracao.filter((u) => u.modo === 'api');

/* ==========================================================
 * Propriedade 10: Seleção do modo e do destino
 * ========================================================== */

// Feature: resolved-feedback-comment, Property 10: Seleção do modo e do destino
// **Validates: Requirements 10.4, 10.5, 10.6**
test('Propriedade 10: o modo depende só de API_FEEDBACK_URL e API_CHAMADOS_URL nunca é destino', async () => {
  // URL de feedback: o gerador com oráculo, mais ausente e valores que não são texto.
  const feedbackConfig = fc.oneof(
    { weight: 6, arbitrary: urlDeConfiguracao },
    {
      weight: 1,
      arbitrary: fc
        .constantFrom(undefined, null, 0, 42, true, false, {}, [], ['https://exemplo.com/x'])
        .map((url) => ({ url, modo: 'prototipo' }))
    }
  );
  // URL de chamados: qualquer valor de configuração (inclusive API válida), ou ausente.
  const chamadosConfig = fc.oneof(
    urlDeConfiguracao.map((u) => u.url),
    fc.constantFrom(undefined, '', 'https://chamados.exemplo.com/api/chamados', 'http://localhost:8080/chamados')
  );

  await fc.assert(
    fc.asyncProperty(feedbackConfig, chamadosConfig, payloadFeedback, async (alvo, urlChamados, payload) => {
      const config = { API_FEEDBACK_URL: alvo.url, API_CHAMADOS_URL: urlChamados, TIMEOUT_FEEDBACK_MS: 10000 };
      const fetchFalso = criarFetchFalso({ status: 200 });
      const { ponto, storage } = montarAmbiente(config, fetchFalso);

      assert.equal(feedback.modoDoFeedback(config), alvo.modo);

      const resultado = await ponto.enviar(payload);

      if (alvo.modo === 'api') {
        assert.equal(fetchFalso.chamadas.length, 1);
        const destino = fetchFalso.chamadas[0].url;
        assert.equal(destino, alvo.url);
        if (typeof urlChamados === 'string' && urlChamados !== alvo.url) {
          assert.notEqual(destino, urlChamados);
        }
        assert.deepEqual(resultado, { ok: true, modo: 'api' });
        // Modo_API não grava no repositório local.
        assert.equal(storage.contar('setItem'), 0);
      } else {
        // Modo_Prototipo: o fetch nunca é chamado, mesmo com API_CHAMADOS_URL preenchida.
        assert.equal(fetchFalso.chamadas.length, 0);
        assert.deepEqual(resultado, { ok: true, modo: 'prototipo' });
        assert.equal(storage.contar('setItem'), 1);
        assert.equal(storage.chamadas.find((c) => c.metodo === 'setItem').chave, feedback.CHAVE_REPOSITORIO);
      }
    }),
    { numRuns: NUM_RUNS }
  );
});

// Feature: resolved-feedback-comment, Property 10: Seleção do modo e do destino
// **Validates: Requirements 10.4, 10.5, 10.6**
test('Propriedade 10: o modo não muda quando só API_CHAMADOS_URL muda', () => {
  fc.assert(
    fc.property(
      urlDeConfiguracao,
      fc.array(fc.oneof(urlDeConfiguracao.map((u) => u.url), fc.constantFrom(undefined, null, 7)), {
        minLength: 1,
        maxLength: 5
      }),
      (alvo, chamadosVariados) => {
        for (const chamados of chamadosVariados) {
          assert.equal(feedback.modoDoFeedback({ API_FEEDBACK_URL: alvo.url, API_CHAMADOS_URL: chamados }), alvo.modo);
        }
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

/* ==========================================================
 * Propriedade 12: Requisição em Modo_API
 * ========================================================== */

// Feature: resolved-feedback-comment, Property 12: Requisição em Modo_API
// **Validates: Requirements 10.7**
test('Propriedade 12: um único POST JSON com o payload serializado, sem credenciais', async () => {
  await fc.assert(
    fc.asyncProperty(urlDeApi, payloadFeedback, fc.integer({ min: 1, max: 60000 }), async (alvo, payload, ms) => {
      // fc.record gera objetos sem protótipo; a cópia comum serve de oráculo.
      const copiaDoPayload = { ...payload };
      const fotoDoPayload = JSON.stringify(payload);
      const config = { API_FEEDBACK_URL: alvo.url, API_CHAMADOS_URL: 'https://outro.exemplo.com/chamados', TIMEOUT_FEEDBACK_MS: ms };
      const fetchFalso = criarFetchFalso({ status: 201 });
      const { ponto, storage, temporizador, AbortControllerFalso } = montarAmbiente(config, fetchFalso);

      const resultado = await ponto.enviar(payload);

      // Exatamente uma chamada ao fetch.
      assert.equal(fetchFalso.chamadas.length, 1);
      const { url, init } = fetchFalso.chamadas[0];

      assert.equal(url, alvo.url);
      assert.equal(init.method, 'POST');

      // Cabeçalho Content-Type: application/json (e nenhum outro cabeçalho).
      assert.deepEqual(init.headers, { 'Content-Type': 'application/json' });

      // Corpo: texto cujo JSON lido é igual ao payload e que é o payload serializado.
      assert.equal(typeof init.body, 'string');
      assert.deepEqual(JSON.parse(init.body), copiaDoPayload);
      assert.equal(init.body, feedback.serializar(payload));

      // Sinal de cancelamento presente, vindo do AbortController injetado.
      assert.ok(init.signal, 'sinal de cancelamento ausente');
      assert.equal(AbortControllerFalso.instancias.length, 1);
      assert.equal(init.signal, AbortControllerFalso.instancias[0].signal);
      assert.equal(init.signal.aborted, false);

      // Requisição anônima e sem cache.
      assert.equal(init.credentials, 'omit');
      assert.equal(init.cache, 'no-store');
      assert.equal(init.referrerPolicy, 'no-referrer');

      // O prazo vem de TIMEOUT_FEEDBACK_MS e o temporizador é limpo ao concluir.
      assert.equal(temporizador.pendentes(), 0);
      assert.equal(temporizador.limpos().length, 1);

      // O envio não altera o payload e não grava localmente.
      assert.equal(JSON.stringify(payload), fotoDoPayload);
      assert.equal(storage.chamadas.length, 0);
      assert.deepEqual(resultado, { ok: true, modo: 'api' });
    }),
    { numRuns: NUM_RUNS }
  );
});

// Feature: resolved-feedback-comment, Property 12: Requisição em Modo_API
// **Validates: Requirements 10.7**
test('Propriedade 12: o prazo agendado é o de TIMEOUT_FEEDBACK_MS', async () => {
  await fc.assert(
    fc.asyncProperty(urlDeApi, payloadFeedback, fc.integer({ min: 1, max: 60000 }), async (alvo, payload, ms) => {
      const config = { API_FEEDBACK_URL: alvo.url, TIMEOUT_FEEDBACK_MS: ms };
      const fetchFalso = criarFetchFalso({ semResposta: true });
      const { ponto, temporizador, AbortControllerFalso } = montarAmbiente(config, fetchFalso);

      const promessa = ponto.enviar(payload);
      assert.equal(temporizador.pendentes(), 1);

      temporizador.avancar(ms - 1);
      assert.equal(AbortControllerFalso.instancias[0].signal.aborted, false);
      temporizador.avancar(1);
      assert.equal(AbortControllerFalso.instancias[0].signal.aborted, true);

      assert.deepEqual(await promessa, { ok: false, categoria: 'timeout' });
      assert.equal(fetchFalso.chamadas.length, 1);
    }),
    { numRuns: NUM_RUNS }
  );
});

/* ==========================================================
 * Propriedade 13: Classificação do resultado do envio
 * ========================================================== */

// Resposta que registra qualquer acesso além de status e ok (ler corpo, clonar etc.).
function criarRespostaEspia(status, acessos) {
  const alvo = { status, ok: status >= 200 && status <= 299 };
  return new Proxy(alvo, {
    get(obj, prop) {
      if (prop === 'status' || prop === 'ok') return obj[prop];
      // Promise.resolve(resposta) consulta `then` para detectar thenables; não é leitura de corpo.
      if (prop === 'then') return undefined;
      acessos.push(String(prop));
      // Qualquer método de leitura de corpo que o núcleo tentasse usar falha alto.
      return () => Promise.reject(new Error('corpo lido: ' + String(prop)));
    }
  });
}

const statusDeResposta = fc.oneof(
  { weight: 1, arbitrary: fc.constantFrom(100, 101, 199, 200, 201, 202, 204, 206, 226, 299, 300, 301, 302, 304, 399, 400, 401, 404, 409, 422, 429, 500, 502, 503, 599) },
  { weight: 3, arbitrary: fc.integer({ min: 100, max: 599 }) }
);

// Feature: resolved-feedback-comment, Property 13: Classificação do resultado do envio
// **Validates: Requirements 10.9, 10.10**
test('Propriedade 13: 2xx é sucesso sem ler o corpo; fora de 2xx é http com o status', async () => {
  await fc.assert(
    fc.asyncProperty(urlDeApi, payloadFeedback, statusDeResposta, async (alvo, payload, status) => {
      const acessos = [];
      const chamadas = [];
      const fetchEspiao = (url, init) => {
        chamadas.push({ url, init });
        return Promise.resolve(criarRespostaEspia(status, acessos));
      };
      const { ponto, temporizador } = montarAmbiente({ API_FEEDBACK_URL: alvo.url, TIMEOUT_FEEDBACK_MS: 10000 }, fetchEspiao);

      const resultado = await ponto.enviar(payload);

      if (status >= 200 && status <= 299) {
        assert.deepEqual(resultado, { ok: true, modo: 'api' });
      } else {
        assert.deepEqual(resultado, { ok: false, categoria: 'http', status });
      }
      assert.deepEqual(acessos, [], 'o corpo da resposta não pode ser lido');
      assert.equal(chamadas.length, 1);
      assert.equal(temporizador.pendentes(), 0);
    }),
    { numRuns: NUM_RUNS }
  );
});

// Feature: resolved-feedback-comment, Property 13: Classificação do resultado do envio
// **Validates: Requirements 10.9, 10.10**
test('Propriedade 13: o corpo da resposta (vazio, JSON, texto ou ausente) não influencia o resultado', async () => {
  const corpo = fc.oneof(
    fc.constant(undefined),
    fc.constant(''),
    fc.string({ unit: 'binary', maxLength: 40 }),
    fc.jsonValue(),
    fc.constant('{"protocolo": "X-1"'),
    fc.constant({ protocolo: 'TRES-20260101-ABCDEF', ok: false, erro: 'x' })
  );
  await fc.assert(
    fc.asyncProperty(urlDeApi, payloadFeedback, statusDeResposta, corpo, async (alvo, payload, status, corpoDaResposta) => {
      const fetchFalso = criarFetchFalso({ status, corpo: corpoDaResposta });
      const { ponto } = montarAmbiente({ API_FEEDBACK_URL: alvo.url, TIMEOUT_FEEDBACK_MS: 10000 }, fetchFalso);

      const resultado = await ponto.enviar(payload);

      const esperado =
        status >= 200 && status <= 299 ? { ok: true, modo: 'api' } : { ok: false, categoria: 'http', status };
      assert.deepEqual(resultado, esperado);
      assert.equal(fetchFalso.chamadas.length, 1);
      // O corpo da resposta não aparece no resultado.
      assert.deepEqual(Object.keys(resultado).sort(), Object.keys(esperado).sort());
    }),
    { numRuns: NUM_RUNS }
  );
});

// Feature: resolved-feedback-comment, Property 13: Classificação do resultado do envio
// **Validates: Requirements 10.9, 10.10**
test('Propriedade 13: rejeição do fetch resolve como rede, com uma só chamada', async () => {
  const motivo = fc.oneof(
    fc.string({ maxLength: 30 }).map((m) => new TypeError(m)),
    fc.string({ maxLength: 30 }).map((m) => new Error(m)),
    fc.string({ maxLength: 30 }).map((m) => {
      const e = new Error(m);
      e.name = 'NetworkError';
      return e;
    }),
    fc.constantFrom('falhou', '', undefined, null, 0, { codigo: 'ECONNRESET' })
  );
  await fc.assert(
    fc.asyncProperty(urlDeApi, payloadFeedback, motivo, async (alvo, payload, razao) => {
      const chamadas = [];
      const fetchRejeita = (url, init) => {
        chamadas.push({ url, init });
        return Promise.reject(razao);
      };
      const { ponto, temporizador } = montarAmbiente({ API_FEEDBACK_URL: alvo.url, TIMEOUT_FEEDBACK_MS: 10000 }, fetchRejeita);

      const resultado = await ponto.enviar(payload);

      assert.deepEqual(resultado, { ok: false, categoria: 'rede' });
      assert.equal(chamadas.length, 1);
      assert.equal(temporizador.pendentes(), 0);
    }),
    { numRuns: NUM_RUNS }
  );
});

// Feature: resolved-feedback-comment, Property 13: Classificação do resultado do envio
// **Validates: Requirements 10.9, 10.10**
test('Propriedade 13: sem resposta no prazo resolve como timeout, sem retentativa', async () => {
  await fc.assert(
    fc.asyncProperty(
      urlDeApi,
      payloadFeedback,
      fc.integer({ min: 1, max: 60000 }),
      fc.boolean(),
      fc.integer({ min: 0, max: 120000 }),
      async (alvo, payload, ms, semAbortController, folga) => {
        const fetchFalso = criarFetchFalso({ semResposta: true });
        const { ponto, temporizador } = montarAmbiente(
          { API_FEEDBACK_URL: alvo.url, TIMEOUT_FEEDBACK_MS: ms },
          fetchFalso,
          { semAbortController }
        );

        let resultado = null;
        const promessa = ponto.enviar(payload).then((r) => {
          resultado = r;
          return r;
        });

        // Antes do prazo, ainda não há resultado.
        temporizador.avancar(ms - 1);
        await esvaziarMicrotarefas();
        assert.equal(resultado, null, 'resolveu antes do prazo');

        // No prazo, estoura.
        temporizador.avancar(1);
        assert.deepEqual(await promessa, { ok: false, categoria: 'timeout' });

        // Passado mais tempo, nada é reenviado.
        temporizador.avancar(folga);
        await esvaziarMicrotarefas();
        assert.equal(fetchFalso.chamadas.length, 1);
        assert.equal(temporizador.pendentes(), 0);
      }
    ),
    { numRuns: NUM_RUNS }
  );
});

// Feature: resolved-feedback-comment, Property 13: Classificação do resultado do envio
// **Validates: Requirements 10.9, 10.10**
test('Propriedade 13: o envio sempre resolve, nunca rejeita, para qualquer comportamento do fetch', async () => {
  const comportamento = fc.oneof(
    statusDeResposta.map((status) => ({ status })),
    statusDeResposta.map((status) => ({ status, corpo: 'texto qualquer' })),
    fc.constant({ rejeita: new TypeError('Failed to fetch') }),
    fc.constant({ semResposta: true })
  );
  await fc.assert(
    fc.asyncProperty(urlDeApi, payloadFeedback, comportamento, async (alvo, payload, comp) => {
      const ms = 5000;
      const fetchFalso = criarFetchFalso(comp);
      const { ponto, temporizador } = montarAmbiente({ API_FEEDBACK_URL: alvo.url, TIMEOUT_FEEDBACK_MS: ms }, fetchFalso);

      const promessa = ponto.enviar(payload);
      temporizador.avancar(ms);
      const resultado = await promessa; // se rejeitasse, o teste falharia aqui

      assert.equal(typeof resultado.ok, 'boolean');
      assert.ok(fetchFalso.chamadas.length <= 1);
      if (resultado.ok) {
        assert.deepEqual(resultado, { ok: true, modo: 'api' });
      } else {
        assert.ok(['rede', 'timeout', 'http'].includes(resultado.categoria));
        assert.equal('status' in resultado, resultado.categoria === 'http');
      }
    }),
    { numRuns: NUM_RUNS }
  );
});
