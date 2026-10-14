/*
 * feedback.js - núcleo sem DOM do comentário opcional da tela de problema resolvido.
 *
 * Script clássico (sem type="module"), carregado depois de js/chamado.js.
 * Exporta uma fábrica: criar(base) recebe o módulo do chamado (TRESChamado) e
 * devolve a API do feedback. Assim os utilitários do chamado são reaproveitados
 * sem copiar código e sem usar carregamento de módulos dentro de js/.
 *
 *   - No navegador: TRESFeedback = criar(TRESChamado), ou null se o módulo
 *     base não estiver carregado (a tela então omite o formulário).
 *   - Em Node (testes): module.exports = { criar }, e o teste passa o módulo base.
 *
 * Não lê DOM, relógio, sorteio, armazenamento nem rede por conta própria:
 * o que for "mundo externo" entra por parâmetro.
 *
 * Contagem de caracteres: String.length (unidades UTF-16), o mesmo critério
 * do atributo maxlength do navegador.
 */
(function (raiz, fabrica) {
  if (typeof module === 'object' && module.exports) {
    module.exports = { criar: fabrica };
  } else {
    raiz.TRESFeedback = raiz.TRESChamado ? fabrica(raiz.TRESChamado) : null;
  }
})(typeof window !== 'undefined' ? window : globalThis, function criar(base) {
  'use strict';

  /* ==========================================================
   * 1. Constantes
   * ========================================================== */

  var LIMITES = {
    comentario: { min: 1, max: 500 },
    maxFeedbacks: 50
  };

  // Chave do Repositorio_de_Feedbacks (só Modo_Prototipo), separada das
  // chaves de métricas e de chamados.
  var CHAVE_REPOSITORIO = 'tres-autoatendimento-feedbacks';

  // Campos do contrato provisório (Payload_do_Feedback, versão "1"), na ordem de saída.
  var CAMPOS_PAYLOAD = [
    'versaoContrato', 'chaveIdempotencia', 'enviadoEm', 'comentario', 'nota',
    'problemaId', 'modelo'
  ];

  // Chaves de TRES_DATA.FEEDBACK.textos que a tela usa. Se qualquer uma faltar
  // ou estiver vazia, o formulário é omitido (ver textosValidos).
  var CHAVES_TEXTOS_OBRIGATORIOS = [
    'rotulo', 'opcional', 'avisoNaoIdentificacao', 'contador',
    'botaoEnviar', 'botaoEnviando',
    'erroVazio', 'anuncioErroVazio',
    'agradecimento', 'falha'
  ];

  /* ==========================================================
   * 2. Utilitários internos
   * ========================================================== */

  // Converte qualquer entrada em texto; null e undefined viram ''.
  function paraTexto(s) {
    if (typeof s === 'string') return s;
    if (s === null || s === undefined) return '';
    return String(s);
  }

  /* ==========================================================
   * 3. Comentário: normalização, validação, limite e contador
   * ========================================================== */

  // Remove espaços e quebras de linha das pontas; preserva os internos.
  // Idempotente: normalizar duas vezes dá o mesmo resultado que uma.
  function normalizarComentario(s) {
    return paraTexto(s).trim();
  }

  // → null (válido), 'vazio' (nada depois da normalização) ou 'tamanho' (mais de 500).
  function validarComentario(s) {
    var c = normalizarComentario(s);
    if (c.length < LIMITES.comentario.min) return 'vazio';
    if (c.length > LIMITES.comentario.max) return 'tamanho';
    return null;
  }

  // Mantém só os primeiros 500 caracteres (igual ao maxlength).
  function limitarComentario(s) {
    return paraTexto(s).slice(0, LIMITES.comentario.max);
  }

  // modelo = texto com {n} e {max} (ex.: "{n} de {max} caracteres").
  // Aceita o texto digitado ou já o seu comprimento.
  // A troca é literal, feita por base.preencherModelo.
  function formatarContador(modelo, s) {
    var n = typeof s === 'number' ? s : paraTexto(s).length;
    return base.preencherModelo(modelo, { n: n, max: LIMITES.comentario.max });
  }

  /* ==========================================================
   * 4. Estado do formulário, payload e serialização
   *    (tarefa 3.2: novoEstado, garantirEstado, aoExibir, editarTexto,
   *    escolherNota, prepararEnvio, concluirEnvio, montarPayload,
   *    serializar, desserializar)
   * ========================================================== */

  // Cópia rasa de um objeto (o estado é sempre tratado como imutável).
  function copiar(o) {
    var r = {};
    var k;
    for (k in o) {
      if (Object.prototype.hasOwnProperty.call(o, k)) r[k] = o[k];
    }
    return r;
  }

  // Nota válida: inteiro de 1 a 5; qualquer outra coisa vira null.
  function notaValida(n) {
    return typeof n === 'number' && isFinite(n) && Math.floor(n) === n && n >= 1 && n <= 5 ? n : null;
  }

  function ehObjeto(x) {
    return x !== null && typeof x === 'object';
  }

  // Estado inicial da jornada do comentário (só em memória).
  function novoEstado(problemaId) {
    return {
      problemaId: problemaId === undefined ? null : problemaId,
      texto: '',
      chave: null,
      estado: 'ocioso',
      enviado: null,
      nota: null
    };
  }

  // Mesmo objeto se o problema coincide; senão, estado novo (jornada nova).
  function garantirEstado(estado, problemaId) {
    var alvo = problemaId === undefined ? null : problemaId;
    if (ehObjeto(estado) && estado.problemaId === alvo) return estado;
    return novoEstado(alvo);
  }

  // Ao exibir a tela: em 'ocioso' zera texto, chave e nota; 'enviando' e
  // 'enviado' são mantidos (a nota sempre volta a null: estrelas neutras).
  function aoExibir(estado, problemaId) {
    var e = copiar(garantirEstado(estado, problemaId));
    e.nota = null;
    if (e.estado === 'ocioso') {
      e.texto = '';
      e.chave = null;
    }
    return e;
  }

  // Só em 'ocioso' aceita edição; trunca em 500.
  function editarTexto(estado, s) {
    if (!ehObjeto(estado) || estado.estado !== 'ocioso') return estado;
    var e = copiar(estado);
    e.texto = limitarComentario(s);
    return e;
  }

  function escolherNota(estado, n) {
    var e = copiar(estado);
    e.nota = notaValida(n);
    return e;
  }

  // Monta exatamente os 7 campos do contrato; ignora qualquer outro campo.
  // entrada = { chave, texto, nota, problemaId, modelo, agora, versao? }
  // agora: função que devolve Date (ou um Date).
  function montarPayload(entrada) {
    var e = ehObjeto(entrada) ? entrada : {};
    var instante = typeof e.agora === 'function' ? e.agora() : e.agora;
    var pid = e.problemaId;
    var modelo = typeof e.modelo === 'string' && e.modelo.trim() !== '' ? e.modelo : null;
    return {
      versaoContrato: typeof e.versao === 'string' && e.versao !== '' ? e.versao : '1',
      chaveIdempotencia: e.chave,
      enviadoEm: base.formatarIsoComFuso(instante),
      comentario: normalizarComentario(e.texto),
      nota: notaValida(e.nota),
      problemaId: typeof pid === 'number' && isFinite(pid) && Math.floor(pid) === pid ? pid : null,
      modelo: modelo
    };
  }

  // entrada = { texto, nota, problemaId, modelo, agora, sorteio?, versao? }
  // Não altera o estado recebido.
  function prepararEnvio(estado, entrada) {
    if (!ehObjeto(estado) || estado.estado !== 'ocioso') {
      return { ok: false, codigo: 'ocupado' };
    }
    var e = ehObjeto(entrada) ? entrada : {};
    var codigo = validarComentario(e.texto);
    if (codigo !== null) return { ok: false, codigo: codigo };

    var chave = estado.chave || base.gerarChaveIdempotencia(e.sorteio);
    var payload = montarPayload({
      chave: chave,
      texto: e.texto,
      nota: e.nota,
      problemaId: e.problemaId,
      modelo: e.modelo,
      agora: e.agora,
      versao: e.versao
    });
    var novo = copiar(estado);
    novo.texto = paraTexto(e.texto);
    novo.chave = chave;
    novo.estado = 'enviando';
    return { ok: true, estado: novo, payload: payload };
  }

  // Sucesso → 'enviado'; falha → 'ocioso' mantendo texto e chave (retentativa).
  function concluirEnvio(estado, resultado, payload) {
    if (!ehObjeto(estado) || estado.estado !== 'enviando') return estado;
    var e = copiar(estado);
    if (ehObjeto(resultado) && resultado.ok === true) {
      e.estado = 'enviado';
      e.enviado = { comentario: ehObjeto(payload) ? payload.comentario : normalizarComentario(estado.texto) };
    } else {
      e.estado = 'ocioso';
    }
    return e;
  }

  function serializar(x) {
    return base.serializar(x);
  }

  function desserializar(t) {
    return base.desserializar(t);
  }

  /* ==========================================================
   * 5. Modo e camada de envio (Ponto_de_Integracao_de_Feedback)
   *    (tarefa 3.3: modoDoFeedback, criarPontoDeIntegracao)
   *
   * enviar(payload) devolve sempre uma Promise que RESOLVE:
   *   { ok: true, modo: 'prototipo' | 'api' }
   *   { ok: false, categoria, status? }  (status só em 'http')
   * Categorias: 'rede', 'timeout', 'http', 'armazenamento'.
   * Não há protocolo nem leitura do corpo da resposta: qualquer 2xx basta.
   * Nada aqui escreve em console nem copia o corpo da resposta ou o texto
   * do comentário para o resultado.
   * ========================================================== */

  var TIMEOUT_FEEDBACK_PADRAO_MS = 10000;

  function falhaEnvio(categoria) {
    return { ok: false, categoria: categoria };
  }

  // Só API_FEEDBACK_URL decide o modo; API_CHAMADOS_URL nunca é consultada.
  function modoDoFeedback(config) {
    var c = config && typeof config === 'object' ? config : {};
    return base.resolverModo(c.API_FEEDBACK_URL);
  }

  // deps = { config, fetch, AbortController, setTimeout, clearTimeout, storage }
  function criarPontoDeIntegracao(deps) {
    var d = deps && typeof deps === 'object' ? deps : {};
    var config = d.config && typeof d.config === 'object' ? d.config : {};

    // Funções do ambiente ficam em variáveis locais e são chamadas sem
    // objeto-dono (fetch e setTimeout do navegador não aceitam outro `this`).
    var fnFetch = d.fetch;
    var ClasseAbort = d.AbortController;
    var fnSetTimeout = typeof d.setTimeout === 'function' ? d.setTimeout : globalThis.setTimeout;
    var fnClearTimeout = typeof d.clearTimeout === 'function' ? d.clearTimeout : globalThis.clearTimeout;

    function tempoLimite() {
      var t = config.TIMEOUT_FEEDBACK_MS;
      return typeof t === 'number' && isFinite(t) && t > 0 ? t : TIMEOUT_FEEDBACK_PADRAO_MS;
    }

    // Qualquer 2xx é sucesso, com ou sem corpo (o corpo nunca é lido).
    // Fora de 2xx → 'http', só com o número do status.
    function classificarStatus(resposta) {
      var status = resposta ? resposta.status : undefined;
      if (typeof status === 'number' && status >= 200 && status <= 299) {
        return { ok: true, modo: 'api' };
      }
      return { ok: false, categoria: 'http', status: status };
    }

    // Modo_API: um único fetch, sem retentativa, sem repositório local.
    function enviarApi(payload) {
      var temporizador = null;
      var temporizadorAtivo = false;
      var estourou = false;

      function limpar() {
        if (temporizadorAtivo) {
          temporizadorAtivo = false;
          try {
            fnClearTimeout(temporizador);
          } catch (erro) { /* nada a fazer */ }
        }
      }

      function traduzirErroDoFetch(erro) {
        if (estourou || (erro && erro.name === 'AbortError')) return falhaEnvio('timeout');
        return falhaEnvio('rede');
      }

      try {
        var init = {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: base.serializar(payload),
          credentials: 'omit',
          cache: 'no-store',
          referrerPolicy: 'no-referrer'
        };
        var url = config.API_FEEDBACK_URL;
        var ms = tempoLimite();
        var requisicao;

        if (typeof ClasseAbort === 'function') {
          // Caminho principal: AbortController + temporizador que aborta.
          var controlador = new ClasseAbort();
          init.signal = controlador.signal;
          temporizador = fnSetTimeout(function () {
            estourou = true;
            try {
              controlador.abort();
            } catch (erro) { /* nada a fazer */ }
          }, ms);
          temporizadorAtivo = true;

          requisicao = Promise.resolve(fnFetch(url, init)).then(classificarStatus, traduzirErroDoFetch);
        } else {
          // Alternativa sem AbortController: corrida com um temporizador.
          // O fetch segue em segundo plano, mas o resultado é 'timeout'.
          var corrida = new Promise(function (resolve) {
            temporizador = fnSetTimeout(function () {
              estourou = true;
              resolve(falhaEnvio('timeout'));
            }, ms);
            temporizadorAtivo = true;
          });
          var andamento = Promise.resolve(fnFetch(url, init)).then(classificarStatus, traduzirErroDoFetch);
          requisicao = Promise.race([andamento, corrida]);
        }

        return requisicao.then(
          function (resultado) {
            limpar();
            return resultado;
          },
          function () {
            limpar();
            return falhaEnvio('rede');
          }
        );
      } catch (erro) {
        // fetch lançou de forma síncrona, ou a montagem da requisição falhou.
        limpar();
        return Promise.resolve(traduzirErroDoFetch(erro));
      }
    }

    // Modo_Prototipo: nenhuma requisição de rede; só o repositório local.
    function enviarPrototipo(payload) {
      var p = ehObjeto(payload) ? payload : {};
      var lista;
      try {
        // Leitura que lança é falha de armazenamento (repositorio.ler()
        // engoliria o erro e a gravação seguinte apagaria o que existe).
        lista = base.lerLista(d.storage.getItem(CHAVE_REPOSITORIO));
      } catch (erro) {
        return falhaEnvio('armazenamento');
      }

      // Retentativa idempotente: mesma chave já gravada → sucesso sem gravar de novo.
      var chave = p.chaveIdempotencia;
      if (typeof chave === 'string' && chave.length > 0) {
        for (var i = 0; i < lista.length; i++) {
          if (lista[i].chaveIdempotencia === chave) return { ok: true, modo: 'prototipo' };
        }
      }

      try {
        base.criarRepositorio(d.storage, CHAVE_REPOSITORIO)
          .gravar(base.adicionarComLimite(lista, payload, LIMITES.maxFeedbacks));
      } catch (erro) {
        return falhaEnvio('armazenamento');
      }
      return { ok: true, modo: 'prototipo' };
    }

    return {
      enviar: function (payload) {
        try {
          if (modoDoFeedback(config) === 'api') return enviarApi(payload);
          return Promise.resolve(enviarPrototipo(payload));
        } catch (erro) {
          return Promise.resolve(falhaEnvio('rede'));
        }
      }
    };
  }

  /* ==========================================================
   * 6. Métricas e verificação de conteúdo
   *    (tarefa 3.4: eventoComentario, textosValidos)
   * ========================================================== */

  // Instante do evento em ISO 8601 UTC (mesmo padrão dos demais eventos).
  // Aceita Date, texto pronto ou função que devolve um dos dois; sem valor
  // (ou inválido) usa o instante atual.
  function instanteDoEvento(em) {
    var v = typeof em === 'function' ? em() : em;
    if (typeof v === 'string' && v.length > 0) return v;
    if (v instanceof Date && !isNaN(v.getTime())) return v.toISOString();
    return new Date().toISOString();
  }

  // Evento 'comentario' da métrica: { tipo, em, problema, modelo }.
  // Nunca leva texto, nota, tamanho nem chave de idempotência.
  // Modelo ausente (null, vazio ou não textual) vira 'nao-informado'.
  function eventoComentario(payload, em) {
    var p = ehObjeto(payload) ? payload : {};
    var m = p.modelo;
    return {
      tipo: 'comentario',
      em: instanteDoEvento(em),
      problema: p.problemaId,
      modelo: typeof m === 'string' && m.length > 0 ? m : 'nao-informado'
    };
  }

  // true só se config e textos são objetos simples e todas as chaves
  // obrigatórias são texto não vazio após trim. Nunca lança nem altera a entrada.
  function textosValidos(dadosFeedback) {
    function simples(x) {
      return ehObjeto(x) && !Array.isArray(x);
    }
    if (!simples(dadosFeedback) || !simples(dadosFeedback.config) || !simples(dadosFeedback.textos)) {
      return false;
    }
    for (var i = 0; i < CHAVES_TEXTOS_OBRIGATORIOS.length; i++) {
      var v = dadosFeedback.textos[CHAVES_TEXTOS_OBRIGATORIOS[i]];
      if (typeof v !== 'string' || v.trim() === '') return false;
    }
    return true;
  }

  /* ==========================================================
   * 7. API pública
   *    Cada tarefa acrescenta suas linhas ao grupo correspondente,
   *    sem reorganizar o que já está aqui.
   * ========================================================== */

  var api = {};

  // Constantes
  api.LIMITES = LIMITES;
  api.CHAVE_REPOSITORIO = CHAVE_REPOSITORIO;
  api.CAMPOS_PAYLOAD = CAMPOS_PAYLOAD;
  api.CHAVES_TEXTOS_OBRIGATORIOS = CHAVES_TEXTOS_OBRIGATORIOS;
  api.CHAVES_TEXTOS_OBRIGATORIAS = CHAVES_TEXTOS_OBRIGATORIOS; // mesmo array, grafia usada em tasks.md

  // Comentário
  api.normalizarComentario = normalizarComentario;
  api.validarComentario = validarComentario;
  api.limitarComentario = limitarComentario;
  api.formatarContador = formatarContador;

  // Estado, payload e serialização (3.2)
  api.novoEstado = novoEstado;
  api.garantirEstado = garantirEstado;
  api.aoExibir = aoExibir;
  api.editarTexto = editarTexto;
  api.escolherNota = escolherNota;
  api.prepararEnvio = prepararEnvio;
  api.concluirEnvio = concluirEnvio;
  api.montarPayload = montarPayload;
  api.serializar = serializar;
  api.desserializar = desserializar;

  // Modo e camada de envio (3.3)
  api.modoDoFeedback = modoDoFeedback;
  api.criarPontoDeIntegracao = criarPontoDeIntegracao;

  // Métricas e conteúdo (3.4)
  api.eventoComentario = eventoComentario;
  api.textosValidos = textosValidos;

  return api;
});
