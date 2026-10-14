/*
 * chamado.js - núcleo sem DOM da tela de abertura de chamado.
 *
 * Script clássico (sem type="module"). No navegador expõe window.TRESChamado;
 * em Node exporta por module.exports (usado nos testes em tests/).
 * Não lê DOM, relógio, sorteio, localStorage nem rede por conta própria:
 * o que for "mundo externo" entra por parâmetro.
 *
 * Contagem de caracteres: String.length (unidades UTF-16), o mesmo critério
 * do atributo maxlength do navegador.
 */
(function (raiz, fabrica) {
  var api = fabrica();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else raiz.TRESChamado = api;
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  /* ==========================================================
   * 1. Constantes
   * ========================================================== */

  var LIMITES = {
    nome: { min: 3, max: 100 },
    email: { max: 254 },
    telefone: { max: 20 },
    descricao: { min: 10, max: 500 },
    protocolo: { max: 64 },
    tentativasProtocolo: 10,
    maxChamados: 50
  };

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
   * 3. Normalização
   * ========================================================== */

  // Remove espaços das pontas e reduz sequências de espaço a um espaço.
  function normalizarNome(s) {
    return paraTexto(s).trim().replace(/\s+/g, ' ');
  }

  // Remove espaços das pontas e converte para minúsculas.
  function normalizarEmail(s) {
    return paraTexto(s).trim().toLowerCase();
  }

  // Remove espaços das pontas; quebras de linha internas são preservadas.
  function normalizarDescricao(s) {
    return paraTexto(s).trim();
  }

  // Devolve só dígitos. Remove o prefixo 55 apenas com 12 ou 13 dígitos
  // começando em 55 (DDD 55 com 10 ou 11 dígitos não perde nada).
  function normalizarTelefone(s) {
    var digitos = paraTexto(s).replace(/\D/g, '');
    if ((digitos.length === 12 || digitos.length === 13) && digitos.slice(0, 2) === '55') {
      return digitos.slice(2);
    }
    return digitos;
  }

  /* ==========================================================
   * 4. Validação
   *    Cada validar* devolve null (válido) ou um código:
   *    'vazio', 'tamanho' ou 'formato'.
   * ========================================================== */

  function validarNome(s) {
    var n = normalizarNome(s);
    if (n.length === 0) return 'vazio';
    if (n.length < LIMITES.nome.min || n.length > LIMITES.nome.max) return 'tamanho';
    if (!/\p{L}/u.test(n)) return 'formato';
    return null;
  }

  function validarEmail(s) {
    var e = paraTexto(s).trim();
    if (e.length === 0) return 'vazio';
    if (e.length > LIMITES.email.max) return 'tamanho';
    if (/\s/.test(e)) return 'formato';

    var partes = e.split('@');
    if (partes.length !== 2) return 'formato';
    var local = partes[0];
    var dominio = partes[1];
    if (local.length === 0) return 'formato';

    var rotulos = dominio.split('.');
    if (rotulos.length < 2) return 'formato';
    for (var i = 0; i < rotulos.length; i++) {
      if (rotulos[i].length === 0) return 'formato';
    }
    if (!/^[a-z]{2,}$/i.test(rotulos[rotulos.length - 1])) return 'formato';
    return null;
  }

  function validarTelefone(s) {
    var bruto = paraTexto(s);
    var t = bruto.trim();
    if (t.length === 0) return 'vazio';
    if (bruto.length > LIMITES.telefone.max) return 'tamanho';

    // Apenas dígitos, ( ) espaço - . e '+' somente no início.
    if (!/^\+?[0-9() .\-]*$/.test(t)) return 'formato';

    var digitos = t.replace(/\D/g, '');
    var n = digitos.length;
    if (n === 12 || n === 13) {
      if (digitos.slice(0, 2) !== '55') return 'tamanho';
      digitos = digitos.slice(2);
      n = digitos.length;
    }
    if (n !== 10 && n !== 11) return 'tamanho';

    var ddd = parseInt(digitos.slice(0, 2), 10);
    if (ddd < 11 || ddd > 99) return 'formato';
    if (n === 11 && digitos.charAt(2) !== '9') return 'formato';
    return null;
  }

  function validarDescricao(s) {
    var d = normalizarDescricao(s);
    if (d.length === 0) return 'vazio';
    if (d.length < LIMITES.descricao.min || d.length > LIMITES.descricao.max) return 'tamanho';
    return null;
  }

  // v = { nome, email, telefone, descricao, aceite }
  // → { valido, erros: [{ campo, codigo }], normalizado }
  // Erros na ordem nome, email, telefone, descricao, aceite. Não altera v.
  function validarFormulario(v) {
    var entrada = v && typeof v === 'object' ? v : {};
    var erros = [];

    var verificacoes = [
      ['nome', validarNome],
      ['email', validarEmail],
      ['telefone', validarTelefone],
      ['descricao', validarDescricao]
    ];
    for (var i = 0; i < verificacoes.length; i++) {
      var codigo = verificacoes[i][1](entrada[verificacoes[i][0]]);
      if (codigo !== null) erros.push({ campo: verificacoes[i][0], codigo: codigo });
    }
    if (entrada.aceite !== true) erros.push({ campo: 'aceite', codigo: 'aceite' });

    return {
      valido: erros.length === 0,
      erros: erros,
      normalizado: {
        nome: normalizarNome(entrada.nome),
        email: normalizarEmail(entrada.email),
        telefone: normalizarTelefone(entrada.telefone),
        descricao: normalizarDescricao(entrada.descricao)
      }
    };
  }

  /* ==========================================================
   * 5. Descrição: limite e contador
   * ========================================================== */

  // Mantém só os primeiros 500 caracteres (igual ao maxlength).
  function limitarDescricao(s) {
    return paraTexto(s).slice(0, LIMITES.descricao.max);
  }

  // Aceita o texto digitado ou já o seu comprimento.
  // → "N de 500 caracteres"
  function formatarContador(entrada) {
    var n = typeof entrada === 'number' ? entrada : paraTexto(entrada).length;
    return n + ' de ' + LIMITES.descricao.max + ' caracteres';
  }

  /* ==========================================================
   * 6. Jornada: passos percorridos e resumo
   * ========================================================== */

  function ehPosicaoValida(posicao, total) {
    return typeof posicao === 'number' && isFinite(posicao) &&
      Math.floor(posicao) === posicao && posicao >= 1 && posicao <= total;
  }

  // Devolve um novo { problemaId, posicoes }; não muta a entrada.
  // Zera ao mudar de problema; ignora posição repetida ou fora de 1..total;
  // novas posições entram no fim (ordem de exibição).
  function registrarPasso(passos, problemaId, posicao, total) {
    var atual = passos && typeof passos === 'object' ? passos : {};
    var mesmoProblema = atual.problemaId === problemaId && Array.isArray(atual.posicoes);
    var totalValido = typeof total === 'number' && isFinite(total) && total >= 1
      ? Math.floor(total) : 0;

    var posicoes = [];
    if (mesmoProblema) {
      for (var i = 0; i < atual.posicoes.length; i++) {
        var p = atual.posicoes[i];
        if (ehPosicaoValida(p, totalValido) && posicoes.indexOf(p) === -1) posicoes.push(p);
      }
    }
    if (ehPosicaoValida(posicao, totalValido) && posicoes.indexOf(posicao) === -1) {
      posicoes.push(posicao);
    }
    return { problemaId: problemaId, posicoes: posicoes };
  }

  // { modeloNome, problema, posicoes }
  // → { modelo, problemaTitulo, passos: [texto], vistos, total }
  // null significa "Não informado". Os textos dos passos saem sem alteração,
  // na ordem da solução do problema.
  function montarResumo(entrada) {
    var e = entrada && typeof entrada === 'object' ? entrada : {};
    var modelo = typeof e.modeloNome === 'string' && e.modeloNome.length > 0 ? e.modeloNome : null;
    var problema = e.problema && typeof e.problema === 'object' && Array.isArray(e.problema.passos)
      ? e.problema : null;

    if (!problema) {
      return { modelo: modelo, problemaTitulo: null, passos: [], vistos: 0, total: 0 };
    }

    var lista = problema.passos;
    var total = lista.length;
    var vistas = Array.isArray(e.posicoes) ? e.posicoes : [];
    var textos = [];
    for (var pos = 1; pos <= total; pos++) {
      if (vistas.indexOf(pos) === -1) continue;
      var passo = lista[pos - 1];
      var texto = passo && typeof passo === 'object' ? passo.texto : passo;
      textos.push(typeof texto === 'string' ? texto : paraTexto(texto));
    }

    var titulo = typeof problema.titulo === 'string' && problema.titulo.length > 0
      ? problema.titulo : null;
    return {
      modelo: modelo,
      problemaTitulo: titulo,
      passos: textos,
      vistos: textos.length,
      total: total
    };
  }

  /* ==========================================================
   * 7. Sessão por problema
   * ========================================================== */

  function novaSessao(problemaId) {
    return {
      problemaId: problemaId,
      valores: { nome: '', email: '', telefone: '', descricao: '' },
      aceite: false,
      chave: null,
      estado: 'ocioso',
      aberto: null
    };
  }

  // Mantém a sessão se for do mesmo problema; senão cria uma nova
  // (sem alterar a sessão recebida).
  function garantirSessao(sessao, problemaId) {
    if (sessao && typeof sessao === 'object' && sessao.problemaId === problemaId) return sessao;
    return novaSessao(problemaId);
  }

  /* ==========================================================
   * 8. Identificadores: protocolo local e chave de idempotência
   *    sorteio(max) devolve um inteiro de 0 a max-1.
   * ========================================================== */

  var ALFABETO_PROTOCOLO = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789';
  var PADRAO_PROTOCOLO = /^TRES-(\d{4})(\d{2})(\d{2})-[A-Z0-9]{6}$/;

  // Objeto crypto do ambiente, quando existe (navegador ou Node recente).
  function obterCrypto() {
    if (typeof globalThis !== 'undefined' && globalThis.crypto) return globalThis.crypto;
    return null;
  }

  // Sorteio padrão: crypto.getRandomValues quando disponível, senão Math.random.
  function sorteioPadrao(max) {
    var c = obterCrypto();
    if (c && typeof c.getRandomValues === 'function' && typeof Uint32Array === 'function') {
      var buf = new Uint32Array(1);
      c.getRandomValues(buf);
      return buf[0] % max;
    }
    return Math.floor(Math.random() * max);
  }

  // Garante um inteiro em 0..max-1 mesmo se a fonte devolver algo fora do contrato.
  function indiceSeguro(sorteio, max) {
    var n = Math.floor(Number(sorteio(max)));
    if (!isFinite(n)) return 0;
    n = n % max;
    return n < 0 ? n + max : n;
  }

  function preencher(n, tamanho) {
    var t = String(n);
    while (t.length < tamanho) t = '0' + t;
    return t;
  }

  function ehBissexto(ano) {
    return (ano % 4 === 0 && ano % 100 !== 0) || ano % 400 === 0;
  }

  // true se ano/mes/dia formam uma data real do calendário.
  function dataExiste(ano, mes, dia) {
    if (mes < 1 || mes > 12 || dia < 1) return false;
    var dias = [31, ehBissexto(ano) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    return dia <= dias[mes - 1];
  }

  // → "TRES-AAAAMMDD-XXXXXX". dataLocal é um Date; usa a data LOCAL do
  // dispositivo (getFullYear/getMonth/getDate), não UTC.
  function gerarProtocolo(dataLocal, sorteio) {
    var fonte = typeof sorteio === 'function' ? sorteio : sorteioPadrao;
    var data = dataLocal instanceof Date ? dataLocal : new Date();
    var aaaammdd = preencher(data.getFullYear(), 4) +
      preencher(data.getMonth() + 1, 2) +
      preencher(data.getDate(), 2);
    var sufixo = '';
    for (var i = 0; i < 6; i++) {
      sufixo += ALFABETO_PROTOCOLO.charAt(indiceSeguro(fonte, ALFABETO_PROTOCOLO.length));
    }
    return 'TRES-' + aaaammdd + '-' + sufixo;
  }

  // Até LIMITES.tentativasProtocolo tentativas; null se todas colidirem.
  function gerarProtocoloUnico(existentes, dataLocal, sorteio) {
    var usados = Array.isArray(existentes) ? existentes : [];
    for (var t = 0; t < LIMITES.tentativasProtocolo; t++) {
      var candidato = gerarProtocolo(dataLocal, sorteio);
      if (usados.indexOf(candidato) === -1) return candidato;
    }
    return null;
  }

  // true se casa com ^TRES-\d{8}-[A-Z0-9]{6}$ e a data AAAAMMDD existe.
  function ehProtocoloLocal(s) {
    if (typeof s !== 'string') return false;
    var m = PADRAO_PROTOCOLO.exec(s);
    if (!m) return false;
    return dataExiste(parseInt(m[1], 10), parseInt(m[2], 10), parseInt(m[3], 10));
  }

  // 16 bytes → UUID versão 4 (36 caracteres). Ajusta versão e variante
  // sem alterar o array recebido.
  function uuidV4(bytes16) {
    var b = [];
    for (var i = 0; i < 16; i++) {
      var v = bytes16 && bytes16[i] !== undefined ? Number(bytes16[i]) : 0;
      b.push(isFinite(v) ? Math.floor(v) & 255 : 0);
    }
    b[6] = (b[6] & 0x0f) | 0x40;
    b[8] = (b[8] & 0x3f) | 0x80;
    var hex = '';
    for (var j = 0; j < 16; j++) {
      hex += (b[j] < 16 ? '0' : '') + b[j].toString(16);
    }
    return hex.slice(0, 8) + '-' + hex.slice(8, 12) + '-' + hex.slice(12, 16) + '-' +
      hex.slice(16, 20) + '-' + hex.slice(20);
  }

  // Com sorteio: usa-o como fonte dos 16 bytes (sorteio(256)).
  // Sem sorteio: crypto.randomUUID → crypto.getRandomValues → Math.random.
  function gerarChaveIdempotencia(sorteio) {
    var bytes = [];
    var i;
    if (typeof sorteio === 'function') {
      for (i = 0; i < 16; i++) bytes.push(indiceSeguro(sorteio, 256));
      return uuidV4(bytes);
    }
    var c = obterCrypto();
    if (c && typeof c.randomUUID === 'function') {
      var u = c.randomUUID();
      if (typeof u === 'string' && u.length === 36) return u;
    }
    if (c && typeof c.getRandomValues === 'function' && typeof Uint8Array === 'function') {
      var buf = new Uint8Array(16);
      c.getRandomValues(buf);
      for (i = 0; i < 16; i++) bytes.push(buf[i]);
      return uuidV4(bytes);
    }
    for (i = 0; i < 16; i++) bytes.push(Math.floor(Math.random() * 256));
    return uuidV4(bytes);
  }

  /* ==========================================================
   * 9. Textos, prazo, modo, política e verificação de conteúdo
   * ========================================================== */

  // Única frase escrita fora de data.js (exceção ao requisito 12.3): quando
  // os textos do chamado faltam, não há de onde ler a mensagem de
  // "conteúdo indisponível".
  var FRASE_CONTEUDO_INDISPONIVEL = 'Esta tela está indisponível no momento. Tente novamente mais tarde.';

  // Chaves de TRES_DATA.CHAMADO.textos que as telas de chamado e de
  // confirmação usam. Se qualquer uma faltar ou estiver vazia, a tela de
  // chamado mostra FRASE_CONTEUDO_INDISPONIVEL e desabilita o envio.
  var CHAVES_TEXTOS_OBRIGATORIOS = [
    'tituloChamado', 'introChamado',
    'resumoTitulo', 'resumoRotuloModelo', 'resumoRotuloProblema', 'resumoRotuloPassos',
    'resumoContagem', 'resumoLegendaPassos', 'resumoSemPassos', 'resumoVer', 'resumoOcultar',
    'naoInformado',
    'formTitulo', 'rotuloNome', 'rotuloEmail', 'rotuloTelefone', 'rotuloDescricao',
    'obrigatorio', 'ajudaTelefone', 'contadorDescricao',
    'privacidade', 'privacidadePolitica', 'rotuloAceite', 'botaoLerTermos', 'termosEmElaboracao',
    'erroAceite', 'erroVazio', 'erroNome', 'erroEmail', 'erroTelefone', 'erroDescricao',
    'anuncioErros', 'anuncioErrosSingular',
    'prazoFrase', 'canaisFormulario', 'canaisConfirmacao',
    'botaoAbrirChamado', 'botaoEnviando', 'anuncioEnviando', 'anuncioSucesso',
    'falha', 'falhaAlternativa', 'conteudoIndisponivel',
    'tituloConfirmacao', 'confirmacaoRecebido', 'confirmacaoConferir', 'protocoloRotulo',
    'rotuloEmailConfirmacao', 'rotuloTelefoneConfirmacao', 'avisoPrototipo', 'avaliacaoTitulo',
    'botaoRever', 'botaoEscolherOutro', 'botaoOutroProblema', 'botaoVoltarInicio'
  ];

  // Interpreta uma URL; devolve o objeto URL ou null.
  function lerUrl(s) {
    if (typeof s !== 'string' || typeof URL !== 'function') return null;
    var t = s.trim();
    if (t.length === 0) return null;
    try {
      return new URL(t);
    } catch (erro) {
      return null;
    }
  }

  // "2 dias úteis", "1 dia útil" ou null se não for inteiro de 1 a 30.
  function formatarPrazo(dias) {
    if (typeof dias !== 'number' || !isFinite(dias) || Math.floor(dias) !== dias) return null;
    if (dias < 1 || dias > 30) return null;
    return dias === 1 ? '1 dia útil' : dias + ' dias úteis';
  }

  // Troca marcadores {chave} por texto literal, numa única passagem: o valor
  // inserido nunca é reinterpretado (nem como marcador, nem como padrão do
  // String.replace, como $& ou $1). Marcador sem valor é mantido como está.
  // Não trata HTML: o resultado deve ir para o DOM por textContent.
  function preencherModelo(texto, valores) {
    var base = paraTexto(texto);
    var dados = valores && typeof valores === 'object' ? valores : {};
    return base.replace(/\{([^{}]+)\}/g, function (marcador, chave) {
      if (!Object.prototype.hasOwnProperty.call(dados, chave)) return marcador;
      return paraTexto(dados[chave]);
    });
  }

  // Substitui só {telefone} e {email} do modelo, por texto literal.
  function montarTextoCanais(modelo, telefone, email) {
    var base = paraTexto(modelo);
    var tel = paraTexto(telefone);
    var mail = paraTexto(email);
    return base.replace(/\{(telefone|email)\}/g, function (marcador, chave) {
      return chave === 'telefone' ? tel : mail;
    });
  }

  // Devolve a URL aparada se for http: ou https: válida; senão null.
  function politicaLink(url) {
    var u = lerUrl(url);
    if (!u) return null;
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;
    if (!u.hostname) return null;
    return url.trim();
  }

  // 'api' só para https: ou http: em localhost/127.0.0.1; senão 'prototipo'.
  function resolverModo(url) {
    var u = lerUrl(url);
    if (!u || !u.hostname) return 'prototipo';
    if (u.protocol === 'https:') return 'api';
    if (u.protocol === 'http:' && (u.hostname === 'localhost' || u.hostname === '127.0.0.1')) {
      return 'api';
    }
    return 'prototipo';
  }

  // true somente se config, privacidade e todos os textos obrigatórios
  // existem e (os textos) não estão vazios após trim.
  function textosValidos(dadosChamado) {
    // Objeto simples: rejeita null, tipos primitivos e arrays.
    function ehObjetoSimples(x) {
      return !!x && typeof x === 'object' && !Array.isArray(x);
    }
    if (!ehObjetoSimples(dadosChamado)) return false;
    if (!ehObjetoSimples(dadosChamado.config)) return false;
    if (!ehObjetoSimples(dadosChamado.privacidade)) return false;
    var textos = dadosChamado.textos;
    if (!ehObjetoSimples(textos)) return false;
    for (var i = 0; i < CHAVES_TEXTOS_OBRIGATORIOS.length; i++) {
      var valor = textos[CHAVES_TEXTOS_OBRIGATORIOS[i]];
      if (typeof valor !== 'string' || valor.trim().length === 0) return false;
    }
    return true;
  }

  /* ==========================================================
   * 10. Chamado, Payload e serialização
   * ========================================================== */

  // Campos do contrato com o back end (Payload_do_Chamado), na ordem de saída.
  var CAMPOS_PAYLOAD = [
    'versaoContrato', 'chaveIdempotencia', 'abertoEm', 'nome', 'email', 'telefone',
    'descricao', 'aceiteTermos', 'aceiteEm', 'modelo', 'problemaId', 'problemaTitulo',
    'passosPercorridos', 'totalPassos'
  ];

  // Chave do localStorage do Repositorio_de_Chamados (só Modo_Prototipo).
  var CHAVE_REPOSITORIO = 'tres-autoatendimento-chamados';

  // Date → ISO 8601 com o deslocamento de fuso do próprio Date
  // (ex.: 2026-10-13T14:32:10.123-03:00), nunca 'Z'.
  function formatarIsoComFuso(data) {
    var d = data instanceof Date && !isNaN(data.getTime()) ? data : new Date();
    var desloc = -d.getTimezoneOffset(); // minutos a leste de UTC
    var sinal = desloc < 0 ? '-' : '+';
    var abs = Math.abs(desloc);
    return preencher(d.getFullYear(), 4) + '-' +
      preencher(d.getMonth() + 1, 2) + '-' +
      preencher(d.getDate(), 2) + 'T' +
      preencher(d.getHours(), 2) + ':' +
      preencher(d.getMinutes(), 2) + ':' +
      preencher(d.getSeconds(), 2) + '.' +
      preencher(d.getMilliseconds(), 3) +
      sinal + preencher(Math.floor(abs / 60), 2) + ':' + preencher(abs % 60, 2);
  }

  // Devolve o primeiro valor definido entre os nomes dados, olhando a própria
  // entrada e depois os grupos opcionais `valores` e `normalizado`.
  function pegar(entrada, nomes) {
    var fontes = [entrada, entrada.valores, entrada.normalizado];
    for (var f = 0; f < fontes.length; f++) {
      var fonte = fontes[f];
      if (!fonte || typeof fonte !== 'object') continue;
      for (var n = 0; n < nomes.length; n++) {
        if (fonte[nomes[n]] !== undefined) return fonte[nomes[n]];
      }
    }
    return undefined;
  }

  // entrada = {
  //   agora: () => Date (ou um Date), config: { VERSAO_CONTRATO } (ou versaoContrato),
  //   chaveIdempotencia (ou chave), nome, email, telefone, descricao,
  //   modelo (id ou null), problemaId, problemaTitulo,
  //   passosPercorridos (ou passos): [{ posicao, texto }], totalPassos
  // }
  // → Chamado com os 14 campos do contrato. abertoEm e aceiteEm saem do mesmo
  // instante (uma única chamada a agora()). Não altera a entrada.
  function montarChamado(entrada) {
    var e = entrada && typeof entrada === 'object' ? entrada : {};

    var instante = typeof e.agora === 'function' ? e.agora() : e.agora;
    var iso = formatarIsoComFuso(instante);

    var versao = pegar(e, ['versaoContrato']);
    if (versao === undefined && e.config && typeof e.config === 'object') {
      versao = e.config.VERSAO_CONTRATO;
    }

    var modelo = pegar(e, ['modelo', 'modeloId']);
    var passos = pegar(e, ['passosPercorridos', 'passos']);
    var lista = [];
    if (Array.isArray(passos)) {
      for (var i = 0; i < passos.length; i++) {
        var p = passos[i] && typeof passos[i] === 'object' ? passos[i] : {};
        lista.push({ posicao: p.posicao, texto: p.texto });
      }
    }

    var chave = pegar(e, ['chaveIdempotencia', 'chave']);
    var titulo = pegar(e, ['problemaTitulo']);

    return {
      versaoContrato: paraTexto(versao),
      chaveIdempotencia: paraTexto(chave),
      abertoEm: iso,
      nome: normalizarNome(pegar(e, ['nome'])),
      email: normalizarEmail(pegar(e, ['email'])),
      telefone: normalizarTelefone(pegar(e, ['telefone'])),
      descricao: normalizarDescricao(pegar(e, ['descricao'])),
      aceiteTermos: true,
      aceiteEm: iso,
      modelo: typeof modelo === 'string' && modelo.length > 0 ? modelo : null,
      problemaId: pegar(e, ['problemaId']),
      problemaTitulo: titulo === undefined || titulo === null ? '' : paraTexto(titulo),
      passosPercorridos: lista,
      totalPassos: pegar(e, ['totalPassos'])
    };
  }

  // Copia só os 14 campos do contrato: sem protocolo, sem modoEnvio e sem
  // nenhum campo extra. Não altera o chamado.
  function montarPayload(chamado) {
    var c = chamado && typeof chamado === 'object' ? chamado : {};
    var payload = {};
    for (var i = 0; i < CAMPOS_PAYLOAD.length; i++) {
      var campo = CAMPOS_PAYLOAD[i];
      if (campo === 'passosPercorridos') {
        var origem = Array.isArray(c.passosPercorridos) ? c.passosPercorridos : [];
        var copia = [];
        for (var j = 0; j < origem.length; j++) {
          var p = origem[j] && typeof origem[j] === 'object' ? origem[j] : {};
          copia.push({ posicao: p.posicao, texto: p.texto });
        }
        payload.passosPercorridos = copia;
      } else {
        payload[campo] = c[campo];
      }
    }
    return payload;
  }

  function serializar(x) {
    return JSON.stringify(x);
  }

  // Lança SyntaxError se o texto não for JSON válido (como JSON.parse).
  function desserializar(texto) {
    return JSON.parse(texto);
  }

  /* ==========================================================
   * 11. Repositorio_de_Chamados (Modo_Prototipo)
   * ========================================================== */

  function ehObjetoSimples(x) {
    return x !== null && typeof x === 'object' && !Array.isArray(x);
  }

  // Texto armazenado → lista de chamados. Nunca lança: texto ausente, vazio,
  // JSON inválido ou JSON que não seja lista viram []. Itens que não são
  // objetos são descartados.
  function lerLista(texto) {
    if (typeof texto !== 'string' || texto.length === 0) return [];
    var valor;
    try {
      valor = JSON.parse(texto);
    } catch (erro) {
      return [];
    }
    if (!Array.isArray(valor)) return [];
    var lista = [];
    for (var i = 0; i < valor.length; i++) {
      if (ehObjetoSimples(valor[i])) lista.push(valor[i]);
    }
    return lista;
  }

  // Devolve uma nova lista: o chamado entra no fim e ficam os `max` mais
  // recentes. Não muta a lista recebida.
  function adicionarComLimite(lista, chamado, max) {
    var limite = typeof max === 'number' && isFinite(max) ? Math.floor(max) : LIMITES.maxChamados;
    var nova = Array.isArray(lista) ? lista.slice() : [];
    nova.push(chamado);
    if (limite < 1) return [];
    return nova.length > limite ? nova.slice(nova.length - limite) : nova;
  }

  // storage = { getItem, setItem } (como localStorage).
  // ler() nunca lança (getItem que lança vira lista vazia);
  // gravar(lista) lança se o armazenamento falhar.
  function criarRepositorio(storage, chave) {
    var k = typeof chave === 'string' && chave.length > 0 ? chave : CHAVE_REPOSITORIO;
    return {
      ler: function () {
        try {
          return lerLista(storage.getItem(k));
        } catch (erro) {
          return [];
        }
      },
      gravar: function (lista) {
        storage.setItem(k, serializar(lista));
      }
    };
  }

  /* ==========================================================
   * 12. Camada de envio (Ponto_de_Integracao)
   *
   * enviar(chamado) devolve sempre uma Promise que RESOLVE:
   *   { ok: true, protocolo, modo: 'prototipo' | 'api' }
   *   { ok: false, categoria, status? }  (status só em 'http')
   * Categorias: 'rede', 'timeout', 'http', 'resposta-invalida',
   * 'armazenamento', 'protocolo'.
   * Nada aqui escreve em console nem copia dados pessoais ou o corpo
   * da resposta para o resultado.
   * ========================================================== */

  var TIMEOUT_ENVIO_PADRAO_MS = 10000;

  function falha(categoria) {
    return { ok: false, categoria: categoria };
  }

  // Classifica a resposta do back end sem tocar em rede.
  // Fora de 200 a 299 → 'http' (só o número do status vai no resultado).
  // 2xx com `protocolo` texto de 1 a 64 caracteres após trim → ok, com o
  // protocolo aparado; qualquer outro corpo → 'resposta-invalida'.
  function interpretarRespostaApi(status, corpo) {
    if (typeof status !== 'number' || !isFinite(status) || status < 200 || status > 299) {
      return { ok: false, categoria: 'http', status: status };
    }
    if (corpo !== null && typeof corpo === 'object' && !Array.isArray(corpo) &&
        typeof corpo.protocolo === 'string') {
      var protocolo = corpo.protocolo.trim();
      if (protocolo.length >= 1 && protocolo.length <= LIMITES.protocolo.max) {
        return { ok: true, protocolo: protocolo };
      }
    }
    return falha('resposta-invalida');
  }

  // Lê o corpo de uma resposta já recebida e a classifica. Nunca rejeita.
  function classificarResposta(resposta) {
    var status = resposta ? resposta.status : undefined;
    if (typeof status !== 'number' || status < 200 || status > 299) {
      return Promise.resolve(interpretarRespostaApi(status, null));
    }
    var lendo;
    try {
      lendo = Promise.resolve(resposta.json());
    } catch (erro) {
      return Promise.resolve(falha('resposta-invalida'));
    }
    return lendo.then(
      function (corpo) {
        var r = interpretarRespostaApi(status, corpo);
        return r.ok ? { ok: true, protocolo: r.protocolo, modo: 'api' } : r;
      },
      function () {
        return falha('resposta-invalida');
      }
    );
  }

  // deps = { config, fetch, AbortController, setTimeout, clearTimeout,
  //          storage, agora, sorteio }
  function criarPontoDeIntegracao(deps) {
    var d = deps && typeof deps === 'object' ? deps : {};
    var config = d.config && typeof d.config === 'object' ? d.config : {};

    // Funções do ambiente são guardadas em variáveis locais e chamadas sem
    // objeto-dono (fetch e setTimeout do navegador não aceitam outro `this`).
    var fnFetch = d.fetch;
    var ClasseAbort = d.AbortController;
    var fnSetTimeout = typeof d.setTimeout === 'function' ? d.setTimeout : globalThis.setTimeout;
    var fnClearTimeout = typeof d.clearTimeout === 'function' ? d.clearTimeout : globalThis.clearTimeout;

    function tempoLimite() {
      var t = config.TIMEOUT_ENVIO_MS;
      return typeof t === 'number' && isFinite(t) && t > 0 ? t : TIMEOUT_ENVIO_PADRAO_MS;
    }

    // Modo_API: um único fetch, sem retentativa, sem repositório local e
    // sem protocolo local.
    function enviarApi(chamado) {
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
        if (estourou || (erro && erro.name === 'AbortError')) return falha('timeout');
        return falha('rede');
      }

      try {
        var init = {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: serializar(montarPayload(chamado)),
          credentials: 'omit',
          cache: 'no-store',
          referrerPolicy: 'no-referrer'
        };
        var url = config.API_CHAMADOS_URL;
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

          requisicao = Promise.resolve(fnFetch(url, init)).then(classificarResposta, traduzirErroDoFetch);
        } else {
          // Alternativa sem AbortController: corrida com um temporizador.
          // O fetch segue em segundo plano, mas o resultado é 'timeout'.
          var corrida = new Promise(function (resolve) {
            temporizador = fnSetTimeout(function () {
              estourou = true;
              resolve(falha('timeout'));
            }, ms);
            temporizadorAtivo = true;
          });
          var andamento = Promise.resolve(fnFetch(url, init)).then(classificarResposta, traduzirErroDoFetch);
          requisicao = Promise.race([andamento, corrida]);
        }

        return requisicao.then(
          function (resultado) {
            limpar();
            return resultado;
          },
          function () {
            limpar();
            return falha('rede');
          }
        );
      } catch (erro) {
        // fetch lançou de forma síncrona, ou a montagem da requisição falhou.
        limpar();
        return Promise.resolve(traduzirErroDoFetch(erro));
      }
    }

    // Modo_Prototipo: nenhuma requisição de rede; só o repositório local.
    function enviarPrototipo(chamado) {
      var c = chamado && typeof chamado === 'object' ? chamado : {};
      var repositorio;
      var lista;
      try {
        repositorio = criarRepositorio(d.storage);
        // Leitura que lança é falha de armazenamento (repositorio.ler()
        // engoliria o erro e a gravação seguinte apagaria o que existe).
        var texto = d.storage.getItem(CHAVE_REPOSITORIO);
        lista = lerLista(texto);
      } catch (erro) {
        return falha('armazenamento');
      }

      // Retentativa idempotente: mesma chave → mesmo protocolo, sem gravar.
      var chave = c.chaveIdempotencia;
      if (typeof chave === 'string' && chave.length > 0) {
        for (var i = 0; i < lista.length; i++) {
          if (lista[i].chaveIdempotencia === chave &&
              typeof lista[i].protocolo === 'string' && lista[i].protocolo.length > 0) {
            return { ok: true, protocolo: lista[i].protocolo, modo: 'prototipo' };
          }
        }
      }

      var protocolo;
      try {
        var usados = [];
        for (var j = 0; j < lista.length; j++) usados.push(lista[j].protocolo);
        var data = typeof d.agora === 'function' ? d.agora() : new Date();
        protocolo = gerarProtocoloUnico(usados, data, d.sorteio);
      } catch (erro) {
        return falha('protocolo');
      }
      if (protocolo === null) return falha('protocolo');

      var gravado = {};
      for (var campo in c) {
        if (Object.prototype.hasOwnProperty.call(c, campo)) gravado[campo] = c[campo];
      }
      gravado.protocolo = protocolo;
      gravado.modoEnvio = 'prototipo';

      try {
        repositorio.gravar(adicionarComLimite(lista, gravado, LIMITES.maxChamados));
      } catch (erro) {
        return falha('armazenamento');
      }
      return { ok: true, protocolo: protocolo, modo: 'prototipo' };
    }

    return {
      enviar: function (chamado) {
        try {
          if (resolverModo(config.API_CHAMADOS_URL) === 'api') {
            return enviarApi(chamado);
          }
          return Promise.resolve(enviarPrototipo(chamado));
        } catch (erro) {
          return Promise.resolve(falha('rede'));
        }
      }
    };
  }

  /* ==========================================================
   * 13. Métricas: resumo e eventos
   *     Nenhum evento recebe nome, e-mail, telefone nem descrição.
   * ========================================================== */

  // Mesma semântica do antigo TRESMetricas.resumo de app.js:
  // resolvidos, encaminhadosAoSuporte, deflexaoPercentual (percentual inteiro
  // arredondado, ou null quando a soma é 0) e porProblema só consideram
  // eventos 'resolvido' e 'suporte'. chamadosAbertos conta eventos 'chamado'.
  // Eventos 'avaliacao' e 'chamado' não entram nos quatro valores originais.
  // comentarios conta eventos 'comentario' (0 se não houver); esses eventos
  // também ficam fora de todos os outros cálculos.
  // Entrada que não é lista e itens que não são objetos são ignorados.
  function resumirEventos(eventos) {
    var lista = Array.isArray(eventos) ? eventos : [];
    var resolvidos = 0;
    var suporte = 0;
    var chamados = 0;
    var comentarios = 0;
    var porProblema = {};

    for (var i = 0; i < lista.length; i++) {
      var e = lista[i];
      if (!ehObjetoSimples(e)) continue;
      if (e.tipo === 'chamado') {
        chamados += 1;
        continue;
      }
      if (e.tipo === 'comentario') {
        comentarios += 1;
        continue;
      }
      if (e.tipo !== 'resolvido' && e.tipo !== 'suporte') continue;

      var ehResolvido = e.tipo === 'resolvido';
      if (ehResolvido) resolvidos += 1;
      else suporte += 1;

      var k = e.problema;
      if (k === '__proto__') continue; // evita poluir o protótipo do objeto
      if (!Object.prototype.hasOwnProperty.call(porProblema, k)) {
        porProblema[k] = { resolvidos: 0, suporte: 0 };
      }
      porProblema[k][ehResolvido ? 'resolvidos' : 'suporte'] += 1;
    }

    var total = resolvidos + suporte;
    return {
      resolvidos: resolvidos,
      encaminhadosAoSuporte: suporte,
      deflexaoPercentual: total ? Math.round((resolvidos / total) * 100) : null,
      porProblema: porProblema,
      chamadosAbertos: chamados,
      comentarios: comentarios
    };
  }

  // Instante do evento no mesmo formato do app.js atual (ISO 8601 em UTC,
  // Date#toISOString). Aceita Date, texto já pronto ou função que devolve um
  // dos dois; sem valor (ou inválido) usa o instante atual.
  function instanteDoEvento(em) {
    var v = typeof em === 'function' ? em() : em;
    if (typeof v === 'string' && v.length > 0) return v;
    if (v instanceof Date && !isNaN(v.getTime())) return v.toISOString();
    return new Date().toISOString();
  }

  // Mesmo padrão do app.js: modelo ausente vira 'nao-informado'.
  function modeloDoEvento(c) {
    var m = c && typeof c === 'object' ? c.modelo : null;
    return typeof m === 'string' && m.length > 0 ? m : 'nao-informado';
  }

  function problemaDoEvento(c) {
    return c && typeof c === 'object' ? c.problemaId : undefined;
  }

  // Evento 'chamado': { tipo, em, problema, modelo, protocolo, modo, passos }.
  // `passos` é inteiro >= 0 (qualquer outro valor vira 0); `modo` é 'api' ou
  // 'prototipo' (qualquer outro valor vira 'prototipo'). `em` é opcional.
  function eventoChamado(c, protocolo, modo, passos, em) {
    var n = typeof passos === 'number' && isFinite(passos) && Math.floor(passos) === passos && passos >= 0
      ? passos : 0;
    return {
      tipo: 'chamado',
      em: instanteDoEvento(em),
      problema: problemaDoEvento(c),
      modelo: modeloDoEvento(c),
      protocolo: paraTexto(protocolo),
      modo: modo === 'api' ? 'api' : 'prototipo',
      passos: n
    };
  }

  // Evento 'avaliacao' da confirmação do chamado:
  // { tipo, em, problema, modelo, nota, desfecho: 'chamado', protocolo }.
  // Devolve null se a nota não for inteiro de 1 a 5. `em` é opcional.
  function eventoAvaliacao(c, protocolo, nota, em) {
    if (typeof nota !== 'number' || Math.floor(nota) !== nota || nota < 1 || nota > 5) return null;
    return {
      tipo: 'avaliacao',
      em: instanteDoEvento(em),
      problema: problemaDoEvento(c),
      modelo: modeloDoEvento(c),
      nota: nota,
      desfecho: 'chamado',
      protocolo: paraTexto(protocolo)
    };
  }

  /* ==========================================================
   * API pública (as tarefas seguintes acrescentam funções aqui)
   * ========================================================== */

  var api = {};

  // Constantes
  api.LIMITES = LIMITES;

  // Normalização
  api.normalizarNome = normalizarNome;
  api.normalizarEmail = normalizarEmail;
  api.normalizarDescricao = normalizarDescricao;
  api.normalizarTelefone = normalizarTelefone;

  // Validação
  api.validarNome = validarNome;
  api.validarEmail = validarEmail;
  api.validarTelefone = validarTelefone;
  api.validarDescricao = validarDescricao;
  api.validarFormulario = validarFormulario;

  // Descrição
  api.limitarDescricao = limitarDescricao;
  api.formatarContador = formatarContador;

  // Jornada e sessão
  api.registrarPasso = registrarPasso;
  api.montarResumo = montarResumo;
  api.novaSessao = novaSessao;
  api.garantirSessao = garantirSessao;

  // Identificadores
  api.gerarProtocolo = gerarProtocolo;
  api.gerarProtocoloUnico = gerarProtocoloUnico;
  api.ehProtocoloLocal = ehProtocoloLocal;
  api.uuidV4 = uuidV4;
  api.gerarChaveIdempotencia = gerarChaveIdempotencia;

  // Textos, prazo, modo, política e conteúdo
  api.FRASE_CONTEUDO_INDISPONIVEL = FRASE_CONTEUDO_INDISPONIVEL;
  api.CHAVES_TEXTOS_OBRIGATORIOS = CHAVES_TEXTOS_OBRIGATORIOS;
  api.formatarPrazo = formatarPrazo;
  api.preencherModelo = preencherModelo;
  api.montarTextoCanais = montarTextoCanais;
  api.politicaLink = politicaLink;
  api.resolverModo = resolverModo;
  api.textosValidos = textosValidos;

  // Chamado, payload e serialização
  api.CAMPOS_PAYLOAD = CAMPOS_PAYLOAD;
  api.montarChamado = montarChamado;
  api.montarPayload = montarPayload;
  api.serializar = serializar;
  api.desserializar = desserializar;
  api.formatarIsoComFuso = formatarIsoComFuso;

  // Repositorio_de_Chamados
  api.CHAVE_REPOSITORIO = CHAVE_REPOSITORIO;
  api.lerLista = lerLista;
  api.adicionarComLimite = adicionarComLimite;
  api.criarRepositorio = criarRepositorio;

  // Camada de envio
  api.interpretarRespostaApi = interpretarRespostaApi;
  api.criarPontoDeIntegracao = criarPontoDeIntegracao;

  // Métricas
  api.resumirEventos = resumirEventos;
  api.eventoChamado = eventoChamado;
  api.eventoAvaliacao = eventoAvaliacao;

  return api;
});
