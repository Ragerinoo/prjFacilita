/*
 * Lógica da jornada de autoatendimento TRES.
 * Fluxo: modelo -> problema -> passo a passo -> "resolveu?" -> (solução | suporte técnico)
 * A navegação usa o hash da URL, então o botão "voltar" do navegador funciona.
 */
(function () {
  'use strict';

  const D = window.TRES_DATA;
  const TRESChamado = window.TRESChamado;
  // Núcleo do comentário opcional; null se o script não carregou (a tela omite o formulário).
  const TRESFeedback = window.TRESFeedback || null;
  const CHAVE_EVENTOS = 'tres-autoatendimento-eventos';

  const state = {
    modelo: null,       // id do modelo escolhido (ou null)
    problemaId: null,
    passoIdx: 0,
    filtro: 'todos',
    busca: '',
    primeiraRota: true,
    // Jornada e chamado ficam só em memória: zeram ao recarregar a página ou ao trocar de problema.
    passos: { problemaId: null, posicoes: [] },   // passos exibidos (posições 1..total)
    sessao: TRESChamado.novaSessao(null),         // valores do formulário, aceite, chave e chamado aberto
    feedback: TRESFeedback ? TRESFeedback.novoEstado(null) : null   // comentário opcional (só em memória)
  };

  /* ---------- utilitários ---------- */

  const $ = (sel, raiz) => (raiz || document).querySelector(sel);

  function el(tag, attrs, ...filhos) {
    const n = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => {
      if (v === null || v === undefined) return;
      if (k === 'class') n.className = v;
      else if (k === 'text') n.textContent = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v);
    });
    filhos.flat().forEach((f) => {
      if (f === null || f === undefined || f === false) return;
      n.append(f.nodeType ? f : document.createTextNode(f));
    });
    return n;
  }

  function normalizar(s) {
    return String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  }

  const PALAVRAS_VAZIAS = ['nao', 'que', 'esta', 'com', 'para', 'uma', 'meu', 'minha', 'dos', 'das', 'mas', 'por'];

  const modeloAtual = () => D.MODELOS.find((m) => m.id === state.modelo) || null;
  const problemaAtual = () => D.PROBLEMAS.find((p) => p.id === state.problemaId) || null;

  /* Preenche os elementos [data-texto] com os textos de data.js (sempre por textContent).
     Chave ausente deixa o elemento vazio. Pode ser chamada de novo sem efeito colateral. */
  function aplicarTextos(raiz) {
    const textos = (D.CHAMADO && D.CHAMADO.textos) || {};
    (raiz || document).querySelectorAll('[data-texto]').forEach((n) => {
      const t = textos[n.getAttribute('data-texto')];
      n.textContent = typeof t === 'string' ? t : '';
    });
  }

  /* Região viva global (#anuncio): limpa e preenche logo depois, para o leitor de tela anunciar de novo. */
  let anuncioPendente = null;
  function anunciar(texto) {
    const regiao = $('#anuncio');
    if (!regiao) return;
    regiao.textContent = '';
    if (anuncioPendente) clearTimeout(anuncioPendente);
    anuncioPendente = setTimeout(() => {
      anuncioPendente = null;
      regiao.textContent = String(texto === null || texto === undefined ? '' : texto);
    }, 50);
  }

  /* Mantém a sessão do problema atual; ao trocar de problema o núcleo devolve uma sessão nova. */
  function garantirSessao(problemaId) {
    state.sessao = TRESChamado.garantirSessao(state.sessao, problemaId);
    return state.sessao;
  }

  /* ---------- registro de resultados (base para medir deflexão) ---------- */

  function lerEventos() {
    try { return JSON.parse(localStorage.getItem(CHAVE_EVENTOS)) || []; } catch (e) { return []; }
  }

  /* Grava um evento já pronto, com o limite de 500 eventos. Falha de armazenamento é ignorada. */
  function gravarEvento(evento) {
    try {
      const lista = lerEventos();
      lista.push(evento);
      localStorage.setItem(CHAVE_EVENTOS, JSON.stringify(lista.slice(-500)));
    } catch (e) { /* armazenamento indisponível: a jornada continua normalmente */ }
  }

  function registrar(tipo, dados) {
    gravarEvento(Object.assign({ tipo: tipo, em: new Date().toISOString() }, dados || {}));
  }

  window.TRESMetricas = {
    listar: lerEventos,
    limpar: function () { try { localStorage.removeItem(CHAVE_EVENTOS); } catch (e) { /* ignora */ } },
    // Mesmos quatro campos de antes, mais chamadosAbertos.
    resumo: function () { return TRESChamado.resumirEventos(lerEventos()); }
  };

  /* ---------- navegação ---------- */

  const VIEWS = {
    '': 'modelo', modelo: 'modelo', problemas: 'problema', solucao: 'solucao',
    confirma: 'confirma', resolvido: 'resolvido', suporte: 'suporte', chamado: 'chamado', contato: 'contato'
  };
  const ETAPA_DA_VIEW = { modelo: 1, problema: 2, solucao: 3, confirma: 3, resolvido: 3, suporte: 3, chamado: 3 };

  function lerRota() {
    const partes = location.hash.replace(/^#\/?/, '').split('/');
    return { nome: partes[0] || '', id: Number(partes[1]) || null };
  }

  function ir(hash) { location.hash = hash; }

  function atualizarEtapas(view) {
    const etapa = ETAPA_DA_VIEW[view] || 0;
    const nav = $('.etapas');
    nav.classList.toggle('etapas--oculta', !etapa);
    document.querySelectorAll('#etapas li').forEach((li) => {
      const n = Number(li.dataset.etapa);
      li.classList.toggle('feita', n < etapa);
      if (n === etapa) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
    });
  }

  function mostrarView(view) {
    document.querySelectorAll('.view').forEach((s) => { s.hidden = s.id !== 'view-' + view; });
    atualizarEtapas(view);
    // Na primeira rota o foco não é movido, exceto em suporte, chamado e resolvido (abertura direta da URL leva o foco ao h1).
    if (!state.primeiraRota || view === 'suporte' || view === 'chamado' || view === 'resolvido') {
      const alvo = $('#view-' + view + ' h1');
      if (alvo) { alvo.setAttribute('tabindex', '-1'); alvo.focus({ preventScroll: true }); }
    }
    window.scrollTo(0, 0);
    state.primeiraRota = false;
  }

  function aoMudarRota() {
    const rota = lerRota();
    const view = VIEWS[rota.nome];
    if (!view) { ir('#/'); return; }

    if (['solucao', 'confirma', 'resolvido', 'suporte', 'chamado'].includes(view)) {
      const p = D.PROBLEMAS.find((x) => x.id === rota.id);
      if (!p) { ir('#/problemas'); return; }
      if (state.problemaId !== p.id) { state.problemaId = p.id; state.passoIdx = 0; }
      // Zera o estado do chamado se o problema mudou e aplica as guardas antes de mostrar qualquer tela.
      garantirSessao(p.id);
      if (view === 'suporte' && state.sessao.aberto) { location.replace('#/chamado/' + p.id); return; }
      if (view === 'chamado' && !state.sessao.aberto) { location.replace('#/suporte/' + p.id); return; }
    }

    mostrarView(view);

    if (view === 'problema') renderProblemas();
    if (view === 'solucao') renderSolucao();
    if (view === 'confirma') $('#confirma-problema').textContent = problemaAtual().titulo;
    if (view === 'resolvido') {
      // A nota escolhida fica em memória para acompanhar o comentário (não gera novo evento).
      montarEstrelas($('#estrelas'), $('#status-aval'), 'resolvido', null, (n) => {
        if (TRESFeedback && state.feedback) state.feedback = TRESFeedback.escolherNota(state.feedback, n);
      });
      renderCuidados($('#cuidados-resolvido'));
      renderFeedback();
    }
    if (view === 'suporte') renderChamado();
    if (view === 'chamado') renderConfirmacao();
    if (view === 'contato') renderContato($('#cartao-contato-geral'));
  }

  /* ---------- etapa 1: modelo ---------- */

  const SVG_MAQUINA =
    '<svg viewBox="0 0 64 64" aria-hidden="true" focusable="false">' +
    '<rect x="12" y="6" width="40" height="44" rx="8" fill="#2a1810"/>' +
    '<rect x="18" y="12" width="28" height="10" rx="3" fill="#5b4a42"/>' +
    '<circle cx="24" cy="30" r="3.2" fill="#f2b705"/><circle cx="32" cy="30" r="3.2" fill="#1f5fbf"/><circle cx="40" cy="30" r="3.2" fill="#2e7d32"/>' +
    '<rect x="22" y="38" width="20" height="4" rx="2" fill="#5b4a42"/>' +
    '<rect x="8" y="50" width="48" height="8" rx="4" fill="#c8102e"/>' +
    '</svg>';

  /* Foto do modelo. Se a imagem falhar, volta para o desenho genérico. */
  function fotoModelo(m) {
    const caixa = el('span', { class: 'modelo__icone' });
    const reserva = () => { caixa.innerHTML = SVG_MAQUINA; }; // marcação fixa, sem dados externos
    if (!m.imagem) { reserva(); return caixa; }
    // alt vazio: o nome do modelo já está escrito ao lado, então a foto é só apoio visual.
    const img = el('img', { src: m.imagem, alt: '', loading: 'lazy', decoding: 'async' });
    img.addEventListener('error', reserva);
    caixa.append(img);
    return caixa;
  }

  function iniciarModelos() {
    const ul = $('#lista-modelos');
    D.MODELOS.forEach((m) => {
      const icone = fotoModelo(m);
      const btn = el('button', {
        type: 'button', class: 'modelo',
        onclick: () => {
          state.modelo = m.id;
          registrar('modelo', { modelo: m.id });
          ir('#/problemas');
        }
      }, icone, el('span', { class: 'modelo__nome', text: m.nome }), el('span', { class: 'modelo__dica', text: m.dica || 'Toque para escolher' }));
      ul.append(el('li', null, btn));
    });

    const btnNaoSei = $('#btn-nao-sei');
    btnNaoSei.addEventListener('click', () => {
      const dica = $('#dica-modelo');
      dica.hidden = !dica.hidden;
      btnNaoSei.setAttribute('aria-expanded', String(!dica.hidden));
    });
    $('#btn-pular-modelo').addEventListener('click', () => {
      state.modelo = null;
      registrar('modelo', { modelo: 'nao-informado' });
      ir('#/problemas');
    });
  }

  /* ---------- etapa 2: problema ---------- */

  function iniciarFiltros() {
    const cont = $('#filtros');
    D.CATEGORIAS.forEach((c) => {
      cont.append(el('button', {
        type: 'button', class: 'chip', 'data-cat': c.id, 'aria-pressed': String(c.id === state.filtro), text: c.nome,
        onclick: () => { state.filtro = c.id; renderProblemas(); }
      }));
    });
    $('#campo-busca').addEventListener('input', (e) => { state.busca = e.target.value; renderProblemas(); });
    $('#btn-limpar-busca').addEventListener('click', () => {
      state.busca = ''; state.filtro = 'todos';
      $('#campo-busca').value = '';
      renderProblemas();
      $('#campo-busca').focus();
    });
  }

  function pontuar(p, tokens) {
    const texto = normalizar([p.titulo, p.resumo].concat(p.passos.map((s) => s.texto)).join(' '));
    const titulo = normalizar(p.titulo + ' ' + p.resumo);
    return tokens.reduce((soma, t) => soma + (titulo.includes(t) ? 2 : 0) + (texto.includes(t) ? 1 : 0), 0);
  }

  function cartaoProblema(p) {
    return el('li', null, el('button', {
      type: 'button', class: 'problema',
      onclick: () => {
        state.problemaId = p.id; state.passoIdx = 0;
        if (TRESFeedback) state.feedback = TRESFeedback.novoEstado(p.id);
        registrar('problema', { problema: p.id, modelo: state.modelo || 'nao-informado' });
        ir('#/solucao/' + p.id);
      }
    },
    el('span', { class: 'problema__icone', 'aria-hidden': 'true', text: p.icone }),
    el('span', null,
      el('span', { class: 'problema__titulo', text: p.titulo }),
      el('span', { class: 'problema__resumo', text: p.resumo }),
      p.topo ? el('span', { class: 'problema__selo', text: 'Mais comum' }) : null)));
  }

  function renderProblemas() {
    const m = modeloAtual();
    $('#sub-problema').textContent = (m ? 'Máquina: ' + m.nome + '. ' : '') +
      'Escolha o que mais se parece com o que você está vendo.';

    const faixa = $('#maquina-escolhida');
    faixa.hidden = !m;
    if (m) {
      faixa.replaceChildren(fotoModelo(m), el('span', null,
        el('strong', { text: m.nome }), el('br'), el('span', { class: 'modelo__dica', text: m.dica || '' })));
    }

    document.querySelectorAll('#filtros .chip').forEach((b) => {
      b.setAttribute('aria-pressed', String(b.dataset.cat === state.filtro));
    });

    const tokens = normalizar(state.busca).split(/[^a-z0-9]+/).filter((t) => t.length >= 3 && !PALAVRAS_VAZIAS.includes(t));
    const comBusca = tokens.length > 0;

    let lista = D.PROBLEMAS.filter((p) => state.filtro === 'todos' || p.categoria === state.filtro);
    if (comBusca) {
      lista = lista.map((p) => ({ p: p, s: pontuar(p, tokens) })).filter((x) => x.s > 0)
        .sort((a, b) => b.s - a.s).map((x) => x.p);
    }

    const comuns = comBusca ? [] : lista.filter((p) => p.topo);
    const outros = comBusca ? lista : lista.filter((p) => !p.topo);

    const ulComuns = $('#lista-comuns'); const ulOutros = $('#lista-outros');
    ulComuns.replaceChildren(...comuns.map(cartaoProblema));
    ulOutros.replaceChildren(...outros.map(cartaoProblema));

    $('#bloco-comuns').hidden = comuns.length === 0;
    $('#bloco-outros').hidden = outros.length === 0;
    $('#titulo-outros').textContent = comBusca ? 'Resultados da busca' : (comuns.length ? 'Outros problemas' : 'Problemas');
    $('#vazio').hidden = lista.length > 0;
    $('#status-busca').textContent = (comBusca || state.filtro !== 'todos')
      ? lista.length + (lista.length === 1 ? ' problema encontrado' : ' problemas encontrados') : '';

    renderCuidados($('#cuidados-problema'));
  }

  /* ---------- ilustração 3D do passo (somente Touch) ---------- */

  const M3D = D.MODELO_3D;
  const reduzMovimento = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  let visor = null;            // elemento <model-viewer>, criado uma única vez
  let estado3d = 'parado';     // parado | carregando | pronto | falhou
  let ultimoVisual = null;     // vista pedida pelo passo atual

  function carregarBiblioteca3D() {
    if (window.customElements && customElements.get('model-viewer')) return Promise.resolve();
    return new Promise((ok, falha) => {
      document.head.append(el('script', {
        src: M3D.biblioteca, onload: ok, onerror: () => falha(new Error('biblioteca 3D indisponível'))
      }));
    });
  }

  /* Reserva: se o 3D não carregar, mostra a foto da máquina e a legenda continua valendo. */
  function usarFoto() {
    $('#visual3d-palco').replaceChildren(el('img', { class: 'visual3d__foto', src: M3D.poster, alt: M3D.alt }));
    visor = null;
  }

  function montarVisor() {
    if (visor) return visor;
    visor = el('model-viewer', {
      src: M3D.arquivo, alt: M3D.alt, poster: M3D.poster,
      'camera-controls': '', 'touch-action': 'pan-y', 'interaction-prompt': 'none',
      'environment-image': 'neutral', 'shadow-intensity': '0.6', 'field-of-view': '30deg',
      'min-camera-orbit': 'auto auto 0.3m', 'max-camera-orbit': 'auto auto 3m',
      // Arrasto mais lento e sem deslizar depois de soltar.
      // interpolation-decay é um TEMPO de amortecimento (ms): quanto MAIOR, mais a câmera escorrega.
      'orbit-sensitivity': '0.5', 'zoom-sensitivity': '0.6',
      'interpolation-decay': reduzMovimento ? '1' : '25'
    });
    Object.keys(M3D.pontos).forEach((chave) => {
      const p = M3D.pontos[chave];
      visor.append(el('span', {
        class: 'hotspot', slot: 'hotspot-' + chave, 'data-ponto': chave, 'aria-hidden': 'true',
        'data-position': p.posicao, 'data-normal': p.normal, 'data-visibility-attribute': 'visible', text: p.rotulo
      }));
    });
    visor.addEventListener('error', () => { estado3d = 'falhou'; usarFoto(); });
    $('#visual3d-palco').replaceChildren(visor);
    return visor;
  }

  function aplicarVisual() {
    if (!ultimoVisual || estado3d === 'falhou') return;
    const vista = M3D.vistas[ultimoVisual.vista];
    const mv = montarVisor();
    mv.setAttribute('camera-target', vista.alvo);
    mv.setAttribute('camera-orbit', vista.orbita);
    mv.querySelectorAll('.hotspot').forEach((h) => {
      h.classList.toggle('hotspot--off', !ultimoVisual.destaques.includes(h.dataset.ponto));
    });
  }

  function renderVisual3D(passo) {
    const figura = $('#visual3d');
    const v = passo.visual;
    const aplicavel = !!v && state.modelo === M3D.modelo;
    figura.hidden = !aplicavel;
    if (!aplicavel) return;

    $('#legenda-3d').textContent = v.legenda;
    ultimoVisual = v;
    if (estado3d === 'pronto') { aplicarVisual(); return; }
    if (estado3d === 'falhou') { if (!$('#visual3d-palco').firstChild) usarFoto(); return; }
    if (estado3d === 'carregando') return;

    estado3d = 'carregando';
    carregarBiblioteca3D()
      .then(() => { estado3d = 'pronto'; aplicarVisual(); })
      .catch(() => { estado3d = 'falhou'; usarFoto(); });
  }

  /* ---------- etapa 3: solução passo a passo ---------- */

  function blocoComoFazer(chave) {
    const ref = D.COMO_FAZER[chave];
    if (!ref) return null;
    return el('details', { class: 'passo__ref' },
      el('summary', { text: ref.titulo }),
      el('ol', null, ref.passos.map((t) => el('li', { text: t }))),
      ref.aviso ? el('p', { class: 'passo__aviso', text: ref.aviso }) : null);
  }

  function renderSolucao() {
    const p = problemaAtual();
    const total = p.passos.length;
    state.passoIdx = Math.min(Math.max(state.passoIdx, 0), total - 1);
    const passo = p.passos[state.passoIdx];

    // Cada passo exibido (inclusive o primeiro) entra na lista de passos percorridos.
    // O núcleo zera a lista ao mudar de problema e mantém a ordem e as posições já vistas.
    garantirSessao(p.id);
    state.passos = TRESChamado.registrarPasso(state.passos, p.id, state.passoIdx + 1, total);

    $('#solucao-modelo').textContent = 'Máquina: ' + (modeloAtual() ? modeloAtual().nome : 'qualquer modelo');
    $('#titulo-solucao').textContent = p.titulo;
    $('#contagem-passo').textContent = 'Passo ' + (state.passoIdx + 1) + ' de ' + total;
    $('#barra-passo').style.width = ((state.passoIdx + 1) / total * 100) + '%';

    const extraModelo = passo.porModelo && state.modelo ? passo.porModelo[state.modelo] : null;
    const alvoLink = passo.link ? D.PROBLEMAS.find((x) => x.id === passo.link) : null;

    // filter(Boolean): replaceChildren transformaria cada null em o texto 'null'.
    $('#passo').replaceChildren(...[
      el('span', { class: 'passo__tipo passo__tipo--' + passo.tipo, text: passo.tipo === 'checar' ? 'Confira' : 'Faça' }),
      el('p', { class: 'passo__texto', text: passo.texto }),
      passo.detalhe ? el('p', { class: 'passo__detalhe', text: passo.detalhe }) : null,
      extraModelo ? el('p', { class: 'passo__modelo', text: extraModelo }) : null,
      passo.ref ? blocoComoFazer(passo.ref) : null,
      alvoLink ? el('button', {
        type: 'button', class: 'link-btn',
        onclick: () => { state.passoIdx = 0; ir('#/solucao/' + alvoLink.id); }
      }, 'Ver solução de “' + alvoLink.titulo + '”') : null
    ].filter(Boolean));

    $('#btn-anterior').disabled = state.passoIdx === 0;
    $('#btn-proximo').textContent = state.passoIdx === total - 1 ? 'Terminei os passos' : 'Próximo passo';

    const obs = $('#obs-solucao');
    obs.hidden = !p.obs;
    obs.textContent = p.obs ? 'Bom saber: ' + p.obs : '';

    renderVisual3D(passo);
  }

  function iniciarSolucao() {
    $('#btn-anterior').addEventListener('click', () => { state.passoIdx -= 1; renderSolucao(); });
    $('#btn-proximo').addEventListener('click', () => {
      const p = problemaAtual();
      if (state.passoIdx >= p.passos.length - 1) { ir('#/confirma/' + p.id); return; }
      state.passoIdx += 1;
      renderSolucao();
    });
    $('#btn-sim').addEventListener('click', () => {
      registrar('resolvido', { problema: state.problemaId, modelo: state.modelo || 'nao-informado' });
      ir('#/resolvido/' + state.problemaId);
    });
    $('#btn-nao').addEventListener('click', () => {
      registrar('suporte', { problema: state.problemaId, modelo: state.modelo || 'nao-informado' });
      ir('#/suporte/' + state.problemaId);
    });
    const rever = () => { state.passoIdx = 0; ir('#/solucao/' + state.problemaId); };
    $('#btn-rever').addEventListener('click', rever);
    $('#btn-rever-chamado').addEventListener('click', rever);
    document.querySelectorAll('[data-voltar]').forEach((b) => {
      b.addEventListener('click', () => ir(b.dataset.voltar));
    });
  }

  /* ---------- desfechos ---------- */

  /* Chaves que `extras` nunca pode trazer: as do próprio evento e as de dados pessoais. */
  const CHAVES_EXTRAS_PROIBIDAS = ['tipo', 'em', 'nota', 'desfecho', 'problema', 'modelo',
    '__proto__', 'constructor', 'prototype', 'nome', 'email', 'telefone', 'descricao', 'descrição',
    'comentario', 'texto', 'feedback'];

  /* Copia de `extras` só com chaves permitidas e valores string, number ou boolean.
     Objeto que não é simples (null, array, texto, etc.) resulta em objeto vazio. */
  function extrasSeguros(extras) {
    const seguro = {};
    if (Object.prototype.toString.call(extras) !== '[object Object]') return seguro;
    const proto = Object.getPrototypeOf(extras);
    if (proto !== Object.prototype && proto !== null) return seguro;
    Object.keys(extras).forEach((chave) => {
      if (CHAVES_EXTRAS_PROIBIDAS.indexOf(chave.toLowerCase()) !== -1) return;
      const valor = extras[chave];
      const tipo = typeof valor;
      if (tipo === 'string' || tipo === 'boolean' || (tipo === 'number' && isFinite(valor))) seguro[chave] = valor;
    });
    return seguro;
  }

  /* `aoEscolher(n)` é opcional: chamado depois de gravar o evento `avaliacao`. */
  function montarEstrelas(cont, status, desfecho, extras, aoEscolher) {
    const adicionais = extrasSeguros(extras);
    status.textContent = '';
    cont.replaceChildren(...[1, 2, 3, 4, 5].map((n) => el('button', {
      type: 'button', class: 'estrela', 'aria-pressed': 'false',
      'aria-label': n + (n === 1 ? ' estrela' : ' estrelas') + ' de 5', text: '★',
      onclick: () => {
        cont.querySelectorAll('.estrela').forEach((b, i) => {
          b.classList.toggle('ativa', i < n);
          b.setAttribute('aria-pressed', String(i === n - 1));
        });
        registrar('avaliacao', Object.assign({}, adicionais, { nota: n, desfecho: desfecho, problema: state.problemaId, modelo: state.modelo || 'nao-informado' }));
        status.textContent = 'Obrigado pela sua avaliação!';
        if (typeof aoEscolher === 'function') aoEscolher(n);
      }
    })));
  }

  function renderContato(cont) {
    const c = D.CONTATO;
    cont.replaceChildren(
      el('h2', { text: 'Canais de atendimento' }),
      el('a', { class: 'tel', href: c.telefoneLink, text: c.telefone }),
      el('ul', null, c.horarios.map((h) => el('li', { text: h }))),
      el('p', null, 'Se preferir, envie um e-mail: ', el('a', { href: 'mailto:' + c.email, text: c.email })),
      el('p', null, el('a', { href: c.centralAjuda, target: '_blank', rel: 'noopener noreferrer' }, 'Ver vídeos e perguntas frequentes (abre em nova aba)'))
    );
  }

  /* ---------- Tela_de_Chamado ---------- */

  const TEXTO_PENDENTE = 'PENDENTE';

  /* Valor de privacidade ausente, vazio ou que não é texto vira "PENDENTE". */
  function valorPrivacidade(v) {
    return typeof v === 'string' && v.trim().length > 0 ? v : TEXTO_PENDENTE;
  }

  /* Controle do resumo: recolhe ou expande a lista de passos. O CSS só aplica o recolhimento até 480 px. */
  function definirResumoRecolhido(recolhido) {
    const t = (D.CHAMADO && D.CHAMADO.textos) || {};
    const botao = $('#resumo-toggle');
    $('#resumo-jornada').classList.toggle('resumo--recolhido', recolhido);
    botao.setAttribute('aria-expanded', String(!recolhido));
    const texto = recolhido ? t.resumoVer : t.resumoOcultar;
    botao.textContent = typeof texto === 'string' ? texto : '';
  }

  /* Registrado uma única vez, na inicialização (fora do render). */
  function iniciarResumo() {
    $('#resumo-toggle').addEventListener('click', () => {
      definirResumoRecolhido(!$('#resumo-jornada').classList.contains('resumo--recolhido'));
    });
  }

  function renderResumo() {
    const t = (D.CHAMADO && D.CHAMADO.textos) || {};
    const naoInformado = typeof t.naoInformado === 'string' ? t.naoInformado : '';
    const m = modeloAtual();
    const resumo = TRESChamado.montarResumo({
      modeloNome: m ? m.nome : null,
      problema: problemaAtual(),
      posicoes: state.passos.problemaId === state.problemaId ? state.passos.posicoes : []
    });

    $('#resumo-modelo').textContent = resumo.modelo === null ? naoInformado : resumo.modelo;
    $('#resumo-problema').textContent = resumo.problemaTitulo === null ? naoInformado : resumo.problemaTitulo;
    $('#resumo-contagem').textContent = TRESChamado.preencherModelo(t.resumoContagem, { x: resumo.vistos, y: resumo.total });

    // Um li por passo (só textContent); sem passos, aparece a frase de lista vazia.
    $('#resumo-lista').replaceChildren(...resumo.passos.map((texto) => el('li', { text: texto })));
    $('#resumo-vazio').hidden = resumo.passos.length > 0;

    // Cada vez que a tela abre, o resumo volta recolhido.
    definirResumoRecolhido(true);
  }

  function renderAvisoPrivacidade() {
    const priv = (D.CHAMADO && D.CHAMADO.privacidade) || {};
    const t = (D.CHAMADO && D.CHAMADO.textos) || {};
    const aviso = $('#aviso-privacidade');
    aviso.textContent = TRESChamado.preencherModelo(t.privacidade, {
      controlador: valorPrivacidade(priv.controlador),
      contato: valorPrivacidade(priv.contato)
    });
    // Link da política só quando a URL é http: ou https: válida; nunca um link vazio ou quebrado.
    const url = TRESChamado.politicaLink(priv.politicaUrl);
    if (url) {
      aviso.append(' ', el('a', { href: url, target: '_blank', rel: 'noopener noreferrer', text: t.privacidadePolitica }));
    }
  }

  /* Linha de prazo e canais acima do aviso de privacidade.
     Prazo ausente ou inválido: só a frase de canais. Sem nenhuma das duas: o parágrafo fica oculto. */
  function renderPrazoResumo() {
    const p = $('#chamado-prazo-resumo');
    if (!p) return;
    const t = (D.CHAMADO && D.CHAMADO.textos) || {};
    const cfg = (D.CHAMADO && D.CHAMADO.config) || {};
    const prazo = TRESChamado.formatarPrazo(cfg.PRAZO_RETORNO_DIAS_UTEIS);
    const partes = [];
    if (prazo !== null && typeof t.prazoFrase === 'string' && t.prazoFrase.trim().length > 0) {
      partes.push(TRESChamado.preencherModelo(t.prazoFrase, { prazo: prazo }));
    }
    if (typeof t.canaisFormulario === 'string' && t.canaisFormulario.trim().length > 0) {
      partes.push(t.canaisFormulario);
    }
    p.textContent = partes.join(' ');
    p.hidden = partes.length === 0;
  }

  /* Conteúdo indisponível: mostra a mensagem, esconde o formulário (hidden) e desabilita o envio.
     As demais telas continuam funcionando; "Rever os passos" e "Escolher outro problema" seguem ativos. */
  function renderIndisponivel(indisponivel) {
    const antigo = $('#chamado-indisponivel');
    if (antigo) antigo.remove();
    const form = $('#form-chamado');
    form.hidden = indisponivel;
    $('#btn-abrir-chamado').disabled = indisponivel;
    if (!indisponivel) return;
    const t = (D.CHAMADO && D.CHAMADO.textos) || {};
    const msg = typeof t.conteudoIndisponivel === 'string' && t.conteudoIndisponivel.trim().length > 0
      ? t.conteudoIndisponivel : TRESChamado.FRASE_CONTEUDO_INDISPONIVEL;
    form.before(el('p', { id: 'chamado-indisponivel', class: 'msg-falha', role: 'status', text: msg }));
  }

  function renderChamado() {
    const sessao = garantirSessao(state.problemaId);
    const indisponivel = !TRESChamado.textosValidos(D.CHAMADO);

    aplicarTextos($('#view-suporte'));
    renderResumo();
    renderPrazoResumo();
    renderAvisoPrivacidade();

    // Repõe o que foi digitado e o aceite (ficam em memória, na sessão do problema).
    const v = sessao.valores;
    $('#c-nome').value = v.nome;
    $('#c-email').value = v.email;
    $('#c-telefone').value = v.telefone;
    $('#c-descricao').value = v.descricao;
    $('#c-aceite').checked = sessao.aceite === true;
    $('#c-descricao-contador').textContent = TRESChamado.formatarContador(v.descricao);

    // A mensagem dos termos volta oculta e vazia ao reabrir a tela.
    const termosMsg = $('#termos-msg');
    termosMsg.textContent = '';
    termosMsg.hidden = true;

    limparTodosErros();
    limparFalha();
    renderIndisponivel(indisponivel);
    // Envio ainda em andamento ao reabrir a tela: botão segue desabilitado ("Enviando").
    if (!indisponivel && sessao.estado === 'enviando') definirEnviando(true);
    else if (!indisponivel) $('#form-chamado').removeAttribute('aria-busy');
  }

  /* ---------- formulário: validação por campo ---------- */

  /* Campos validados, na ordem de foco. `ajuda` é o id que continua em aria-describedby
     quando o erro some; `msg` é a chave do texto de erro por código ('vazio' usa erroVazio). */
  const CAMPOS = [
    { chave: 'nome', id: 'c-nome', msg: 'erroNome', validar: (s) => TRESChamado.validarNome(s) },
    { chave: 'email', id: 'c-email', msg: 'erroEmail', validar: (s) => TRESChamado.validarEmail(s) },
    { chave: 'telefone', id: 'c-telefone', msg: 'erroTelefone', ajuda: 'c-telefone-ajuda', validar: (s) => TRESChamado.validarTelefone(s) },
    { chave: 'descricao', id: 'c-descricao', msg: 'erroDescricao', ajuda: 'c-descricao-contador', validar: (s) => TRESChamado.validarDescricao(s) },
    { chave: 'aceite', id: 'c-aceite', msg: 'erroAceite' }
  ];
  const campoPorChave = (chave) => CAMPOS.find((c) => c.chave === chave) || null;
  const campoPorId = (id) => CAMPOS.find((c) => c.id === id) || null;

  /* Texto do erro por código. Só os limites de TRESChamado.LIMITES entram em {min} e {max}. */
  function textoErro(campo, codigo) {
    const t = (D.CHAMADO && D.CHAMADO.textos) || {};
    if (codigo === 'vazio') return typeof t.erroVazio === 'string' ? t.erroVazio : '';
    const lim = TRESChamado.LIMITES[campo.chave] || {};
    return TRESChamado.preencherModelo(t[campo.msg], { min: lim.min, max: lim.max });
  }

  function idsDescricao(controle) {
    return (controle.getAttribute('aria-describedby') || '').split(/\s+/).filter(Boolean);
  }

  function definirDescricao(controle, ids) {
    if (ids.length > 0) controle.setAttribute('aria-describedby', ids.join(' '));
    else controle.removeAttribute('aria-describedby');
  }

  function mostrarErro(campo, codigo) {
    const controle = $('#' + campo.id);
    const erroId = campo.id + '-erro';
    const p = $('#' + erroId);
    p.textContent = textoErro(campo, codigo);
    p.hidden = false;
    controle.setAttribute('aria-invalid', 'true');
    const ids = idsDescricao(controle);
    if (!ids.includes(erroId)) ids.push(erroId);
    definirDescricao(controle, ids);
  }

  /* Tira só o id do erro de aria-describedby; a ajuda ou o contador continuam. */
  function limparErro(campo) {
    const controle = $('#' + campo.id);
    const erroId = campo.id + '-erro';
    const p = $('#' + erroId);
    p.hidden = true;
    p.textContent = '';
    controle.removeAttribute('aria-invalid');
    definirDescricao(controle, idsDescricao(controle).filter((i) => i !== erroId));
  }

  function limparTodosErros() {
    CAMPOS.forEach(limparErro);
  }

  const erroVisivel = (campo) => !$('#' + campo.id + '-erro').hidden;

  /* Valida um campo de texto com o valor atual e mostra ou limpa o erro. Devolve o código (null = válido). */
  function validarCampo(campo) {
    const codigo = campo.validar($('#' + campo.id).value);
    if (codigo === null) limparErro(campo); else mostrarErro(campo, codigo);
    return codigo;
  }

  function aoDigitar(campo, controle) {
    if (campo.chave === 'descricao') {
      // Digitada ou colada: acima de 500 mantém só o início do texto, com o cursor no fim.
      if (controle.value.length > TRESChamado.LIMITES.descricao.max) {
        controle.value = TRESChamado.limitarDescricao(controle.value);
        controle.setSelectionRange(controle.value.length, controle.value.length);
      }
      $('#c-descricao-contador').textContent = TRESChamado.formatarContador(controle.value);
    }
    // Guarda o valor exatamente como foi digitado (sem trim).
    state.sessao.valores[campo.chave] = controle.value;
    // Erro visível some assim que o valor fica válido; se segue inválido, a mensagem acompanha o código atual.
    if (erroVisivel(campo)) validarCampo(campo);
  }

  /* Envio do formulário: valida, monta o Chamado e entrega ao Ponto_de_Integracao. */
  function aoEnviar(ev) {
    if (ev && typeof ev.preventDefault === 'function') ev.preventDefault();
    const form = $('#form-chamado');
    // Estado indisponível (7.4) ou envio já em andamento: nada a fazer.
    if (form.hidden || $('#btn-abrir-chamado').disabled || state.sessao.estado === 'enviando') return;

    const s = state.sessao;
    const resultado = TRESChamado.validarFormulario({
      nome: s.valores.nome, email: s.valores.email, telefone: s.valores.telefone,
      descricao: s.valores.descricao, aceite: s.aceite === true
    });

    if (!resultado.valido) {
      // Nenhuma gravação nem requisição: só mostra os erros, leva o foco ao primeiro e anuncia a contagem.
      const comErro = new Map(resultado.erros.map((e) => [e.campo, e.codigo]));
      CAMPOS.forEach((campo) => {
        if (comErro.has(campo.chave)) mostrarErro(campo, comErro.get(campo.chave));
        else limparErro(campo);
      });
      const primeiro = CAMPOS.find((c) => comErro.has(c.chave));
      if (primeiro) $('#' + primeiro.id).focus();
      const t = (D.CHAMADO && D.CHAMADO.textos) || {};
      const n = resultado.erros.length;
      anunciar(n === 1 ? t.anuncioErrosSingular : TRESChamado.preencherModelo(t.anuncioErros, { n: n }));
      return;
    }

    // Formulário válido: nenhum erro fica visível e o envio começa.
    CAMPOS.forEach(limparErro);

    // O estado muda ANTES de qualquer await: toques, Enter e cliques seguintes caem no retorno acima.
    s.estado = 'enviando';
    limparFalha();
    definirEnviando(true);
    const t = (D.CHAMADO && D.CHAMADO.textos) || {};
    anunciar(t.anuncioEnviando);

    const problema = problemaAtual();
    const problemaId = state.problemaId;
    // A chave nasce no primeiro envio válido da jornada e é reutilizada nas retentativas.
    if (typeof s.chave !== 'string' || s.chave.length === 0) s.chave = TRESChamado.gerarChaveIdempotencia();

    const posicoes = state.passos.problemaId === problemaId ? state.passos.posicoes : [];
    const passosPercorridos = posicoes
      .filter((pos) => problema && problema.passos[pos - 1])
      .map((pos) => ({ posicao: pos, texto: problema.passos[pos - 1].texto }));

    let chamado;
    try {
      chamado = TRESChamado.montarChamado({
        agora: () => new Date(),
        config: D.CHAMADO.config,
        chaveIdempotencia: s.chave,
        nome: s.valores.nome,
        email: s.valores.email,
        telefone: s.valores.telefone,
        descricao: s.valores.descricao,
        modelo: state.modelo,
        problemaId: problemaId,
        problemaTitulo: problema ? problema.titulo : '',
        passosPercorridos: passosPercorridos,
        totalPassos: problema ? problema.passos.length : 0
      });
    } catch (e) {
      concluirFalha(s, 'rede');
      return;
    }

    pontoDeIntegracao().enviar(chamado).then(
      (resultado) => {
        if (resultado && resultado.ok === true) concluirSucesso(s, problemaId, chamado, resultado, passosPercorridos.length);
        else concluirFalha(s, resultado && resultado.categoria);
      },
      () => concluirFalha(s, 'rede')
    );
  }

  /* ---------- envio do chamado ---------- */

  /* Ponto_de_Integracao criado uma vez, na primeira necessidade, com as dependências reais do navegador. */
  let pontoIntegracao = null;

  /* localStorage real ou, se o acesso falhar, um substituto que lança (o núcleo responde "armazenamento"). */
  function obterStorage() {
    let storage;
    try {
      storage = window.localStorage;
      if (!storage) throw new Error('indisponível');
    } catch (e) {
      storage = {
        getItem: () => { throw new Error('indisponível'); },
        setItem: () => { throw new Error('indisponível'); },
        removeItem: () => { throw new Error('indisponível'); }
      };
    }
    return storage;
  }

  function pontoDeIntegracao() {
    if (pontoIntegracao) return pontoIntegracao;
    const storage = obterStorage();
    pontoIntegracao = TRESChamado.criarPontoDeIntegracao({
      config: D.CHAMADO.config,
      fetch: (url, init) => window.fetch(url, init),
      AbortController: window.AbortController,
      setTimeout: (fn, ms) => window.setTimeout(fn, ms),
      clearTimeout: (id) => window.clearTimeout(id),
      storage: storage,
      agora: () => new Date()
    });
    return pontoIntegracao;
  }

  /* Botão, texto e aria-busy do estado "enviando". */
  function definirEnviando(enviando) {
    const t = (D.CHAMADO && D.CHAMADO.textos) || {};
    const botao = $('#btn-abrir-chamado');
    const form = $('#form-chamado');
    botao.disabled = enviando;
    const texto = enviando ? t.botaoEnviando : t.botaoAbrirChamado;
    botao.textContent = typeof texto === 'string' ? texto : '';
    if (enviando) form.setAttribute('aria-busy', 'true'); else form.removeAttribute('aria-busy');
  }

  function limparFalha() {
    const area = $('#chamado-falha-area');
    if (area) area.replaceChildren();
  }

  function concluirSucesso(sessao, problemaId, chamado, resultado, totalPassos) {
    // Grava o chamado aberto na sessão que enviou (mesmo que a tela já tenha mudado).
    sessao.aberto = {
      problemaId: problemaId,
      protocolo: resultado.protocolo,
      email: chamado.email,
      telefone: chamado.telefone,
      modo: resultado.modo
    };
    sessao.estado = 'enviado';
    // Evento de métrica sem dados pessoais; falha de armazenamento é ignorada em gravarEvento.
    try {
      gravarEvento(TRESChamado.eventoChamado(chamado, resultado.protocolo, resultado.modo, totalPassos));
    } catch (e) { /* a métrica nunca altera a tela */ }

    // Só mexe na tela se o consumidor ainda está nela.
    if (state.sessao !== sessao || state.problemaId !== problemaId || lerRota().nome !== 'suporte') return;
    const t = (D.CHAMADO && D.CHAMADO.textos) || {};
    $('#form-chamado').removeAttribute('aria-busy');
    anunciar(TRESChamado.preencherModelo(t.anuncioSucesso, { protocolo: resultado.protocolo }));
    location.replace('#/chamado/' + problemaId);
  }

  function concluirFalha(sessao, categoria) {
    sessao.estado = 'ocioso';
    if (state.sessao !== sessao || lerRota().nome !== 'suporte') return;
    mostrarFalha(categoria);
  }

  /* Texto com {telefone} e {email} trocados por links tel: e mailto:, sem innerHTML. */
  function montarAlternativa(modelo) {
    const c = D.CONTATO;
    const partes = String(modelo === undefined || modelo === null ? '' : modelo).split(/(\{telefone\}|\{email\})/);
    return partes.map((parte) => {
      if (parte === '{telefone}') return el('a', { href: c.telefoneLink, text: c.telefone });
      if (parte === '{email}') return el('a', { href: 'mailto:' + c.email, text: c.email });
      return parte;
    });
  }

  /* Falha de envio: único caso em que a tela aponta para o atendimento.
     A categoria não vira texto técnico: a mensagem é a mesma para qualquer falha. */
  function mostrarFalha(categoria) {
    const t = (D.CHAMADO && D.CHAMADO.textos) || {};
    const area = $('#chamado-falha-area');
    const bloco = el('div', { class: 'msg-falha', role: 'alert', tabindex: '-1' },
      el('p', { text: t.falha }),
      el('p', null, montarAlternativa(t.falhaAlternativa)));
    area.replaceChildren(bloco);

    // Conteúdo indisponível (formulário oculto) mantém o envio desabilitado.
    if ($('#form-chamado').hidden) $('#form-chamado').removeAttribute('aria-busy');
    else definirEnviando(false);
    bloco.focus();
    anunciar(t.falha);
  }

  /* Registrado uma única vez, na inicialização (fora do render). */
  function iniciarFormulario() {
    const form = $('#form-chamado');

    form.addEventListener('input', (ev) => {
      const campo = campoPorId(ev.target.id);
      if (campo && campo.validar) aoDigitar(campo, ev.target);
    });

    // blur não borbulha: focusout cobre o formulário todo.
    form.addEventListener('focusout', (ev) => {
      const campo = campoPorId(ev.target.id);
      if (campo && campo.validar) validarCampo(campo);
    });

    $('#c-aceite').addEventListener('change', (ev) => {
      state.sessao.aceite = ev.target.checked === true;
      if (state.sessao.aceite) limparErro(campoPorChave('aceite'));
    });

    // "Ler os termos": só mostra a mensagem fixa em #termos-msg (sempre o mesmo elemento).
    // Sem navegação, sem aba, janela ou diálogo; o foco e o aceite ficam como estão.
    $('#btn-ler-termos').addEventListener('click', () => {
      const t = (D.CHAMADO && D.CHAMADO.textos) || {};
      const msg = $('#termos-msg');
      msg.textContent = typeof t.termosEmElaboracao === 'string' ? t.termosEmElaboracao : '';
      msg.hidden = false;
    });

    form.addEventListener('submit', aoEnviar);
  }

  /* Tela_de_Confirmacao: mostra o chamado guardado em state.sessao.aberto.
     Tudo entra por textContent. */
  function renderConfirmacao() {
    garantirSessao(state.problemaId);
    const aberto = state.sessao && state.sessao.aberto;
    if (!aberto) return;

    aplicarTextos($('#view-chamado'));
    const t = (D.CHAMADO && D.CHAMADO.textos) || {};

    $('#chamado-protocolo').textContent = aberto.protocolo === undefined || aberto.protocolo === null ? '' : String(aberto.protocolo);
    $('#chamado-email').textContent = aberto.email === undefined || aberto.email === null ? '' : String(aberto.email);
    $('#chamado-telefone').textContent = aberto.telefone === undefined || aberto.telefone === null ? '' : String(aberto.telefone);

    // O aviso existe só no Modo_Prototipo; no modo api fica oculto e vazio.
    const aviso = $('#chamado-aviso-prototipo');
    if (aberto.modo === 'prototipo') {
      aviso.textContent = t.avisoPrototipo === undefined || t.avisoPrototipo === null ? '' : String(t.avisoPrototipo);
      aviso.hidden = false;
    } else {
      aviso.textContent = '';
      aviso.hidden = true;
    }

    renderPrazoCanaisConfirmacao(aberto);

    // Avaliação do atendimento: remonta as estrelas a cada render e limpa o status.
    // O evento leva só protocolo, nota, desfecho, problema e modelo (sem dados pessoais).
    const protocolo = aberto.protocolo === undefined || aberto.protocolo === null ? '' : String(aberto.protocolo);
    montarEstrelas($('#estrelas-chamado'), $('#status-aval-chamado'), 'chamado', { protocolo: protocolo });
  }

  /* Prazo (só "N dias úteis", sem data limite) e canais de retorno na confirmação.
     Prazo ausente ou inválido: a frase de prazo é omitida e os canais continuam. */
  function renderPrazoCanaisConfirmacao(aberto) {
    const t = (D.CHAMADO && D.CHAMADO.textos) || {};
    const cfg = (D.CHAMADO && D.CHAMADO.config) || {};

    const pPrazo = $('#chamado-prazo');
    if (pPrazo) {
      const prazo = TRESChamado.formatarPrazo(cfg.PRAZO_RETORNO_DIAS_UTEIS);
      const temModelo = typeof t.prazoFrase === 'string' && t.prazoFrase.trim().length > 0;
      const frase = prazo !== null && temModelo ? TRESChamado.preencherModelo(t.prazoFrase, { prazo: prazo }) : '';
      pPrazo.textContent = frase;
      pPrazo.hidden = frase.length === 0;
    }

    const pCanais = $('#chamado-canais');
    if (pCanais) {
      const temModelo = typeof t.canaisConfirmacao === 'string' && t.canaisConfirmacao.trim().length > 0;
      const texto = temModelo ? TRESChamado.montarTextoCanais(t.canaisConfirmacao, aberto.telefone, aberto.email) : '';
      pCanais.textContent = texto;
      pCanais.hidden = texto.length === 0;
    }
  }

  /* ---------- comentário opcional na Tela_de_Resolvido ---------- */

  const dadosFeedback = () => (D.FEEDBACK && D.FEEDBACK.textos) || {};

  /* Preenche os elementos [data-texto-feedback] com os textos de data.js (sempre por textContent).
     Chave ausente deixa o elemento vazio. Pode ser chamada de novo sem efeito colateral. */
  function aplicarTextosFeedback(raiz) {
    const textos = dadosFeedback();
    (raiz || document).querySelectorAll('[data-texto-feedback]').forEach((n) => {
      const t = textos[n.getAttribute('data-texto-feedback')];
      n.textContent = typeof t === 'string' ? t : '';
    });
  }

  /* Contador "N de 500 caracteres" a partir do texto exibido no campo. */
  function atualizarContadorFeedback() {
    const campo = $('#f-comentario');
    $('#f-comentario-contador').textContent = TRESFeedback.formatarContador(dadosFeedback().contador, campo.value);
  }

  /* Remove mensagem de erro e aria-invalid; aria-describedby volta a citar só aviso e contador. */
  function limparErroFeedback() {
    const campo = $('#f-comentario');
    const erro = $('#f-comentario-erro');
    erro.textContent = '';
    erro.hidden = true;
    campo.removeAttribute('aria-invalid');
    campo.setAttribute('aria-describedby', 'f-comentario-aviso f-comentario-contador');
  }

  /* Aplica ao DOM o estado 'ocioso', 'enviando' ou 'enviado' de state.feedback.
     Roda DEPOIS de aplicarTextosFeedback, que reescreve o texto do botão. */
  function aplicarEstadoFeedback() {
    const t = dadosFeedback();
    const f = state.feedback;
    const form = $('#form-feedback');
    const campo = $('#f-comentario');
    const botao = $('#btn-enviar-comentario');
    const agradecimento = $('#feedback-agradecimento');
    const enviado = f.estado === 'enviado';
    const enviando = f.estado === 'enviando';
    const textoBotao = enviando ? t.botaoEnviando : t.botaoEnviar;

    campo.value = enviado && f.enviado ? f.enviado.comentario : f.texto;
    campo.readOnly = enviando;
    campo.disabled = enviado;
    botao.disabled = enviando || enviado;
    botao.textContent = typeof textoBotao === 'string' ? textoBotao : '';
    if (enviando) form.setAttribute('aria-busy', 'true'); else form.removeAttribute('aria-busy');
    agradecimento.textContent = enviado && typeof t.agradecimento === 'string' ? t.agradecimento : '';
    atualizarContadorFeedback();
  }

  /* Monta o Formulario_de_Feedback ao exibir a rota resolvido (depois das estrelas e dos cuidados).
     Sem módulo ou com textos incompletos, o formulário fica oculto e o resto da tela segue normal. */
  function renderFeedback() {
    const form = $('#form-feedback');
    if (!form) return;
    if (!TRESFeedback || !TRESFeedback.textosValidos(D.FEEDBACK)) { form.hidden = true; return; }

    state.feedback = TRESFeedback.aoExibir(state.feedback, state.problemaId);
    form.hidden = false;
    aplicarTextosFeedback(form);
    limparErroFeedback();
    $('#feedback-falha-area').replaceChildren();
    aplicarEstadoFeedback();
    // Ganchos: iniciarFeedback (6.4) liga input/submit; 6.5 e 6.6 tratam envio, sucesso e falha.
  }

  /* Mesma operação de limparErroFeedback, com o nome usado pelo fluxo de edição/validação do campo. */
  const limparErroComentario = limparErroFeedback;

  /* Mensagem de erro visível abaixo do campo, aria-invalid e id do erro em aria-describedby
     (junto de aviso e contador). Usa só textos de data.js, por textContent. */
  function mostrarErroComentario() {
    const campo = $('#f-comentario');
    const erro = $('#f-comentario-erro');
    const t = dadosFeedback();
    erro.textContent = typeof t.erroVazio === 'string' ? t.erroVazio : '';
    erro.hidden = false;
    campo.setAttribute('aria-invalid', 'true');
    campo.setAttribute('aria-describedby', 'f-comentario-aviso f-comentario-contador f-comentario-erro');
  }

  /* Estado "enviando" no DOM: aria-busy no formulário, texto "Enviando" e botão desabilitado,
     campo somente leitura (continua legível e focável). Ao sair do envio volta ao repouso. */
  function definirEnviandoFeedback(enviando) {
    const t = dadosFeedback();
    const form = $('#form-feedback');
    const botao = $('#btn-enviar-comentario');
    const texto = enviando ? t.botaoEnviando : t.botaoEnviar;
    botao.disabled = enviando;
    botao.textContent = typeof texto === 'string' ? texto : '';
    $('#f-comentario').readOnly = enviando;
    if (enviando) form.setAttribute('aria-busy', 'true'); else form.removeAttribute('aria-busy');
  }

  /* Ponto_de_Integracao_de_Feedback criado uma vez, na primeira necessidade, com as dependências reais. */
  let pontoIntegracaoFeedback = null;

  function pontoDeIntegracaoFeedback() {
    if (pontoIntegracaoFeedback) return pontoIntegracaoFeedback;
    pontoIntegracaoFeedback = TRESFeedback.criarPontoDeIntegracao({
      config: D.FEEDBACK.config,
      fetch: (url, init) => window.fetch(url, init),
      AbortController: window.AbortController,
      setTimeout: (fn, ms) => window.setTimeout(fn, ms),
      clearTimeout: (id) => window.clearTimeout(id),
      storage: obterStorage()
    });
    return pontoIntegracaoFeedback;
  }

  /* Estado "enviado" no DOM: campo e botão desabilitados, texto enviado visível, agradecimento
     preenchido (mesmo texto em Modo_Prototipo e Modo_API, sem aviso de protótipo) e foco nele.
     O próprio #feedback-agradecimento é role="status": não há anunciar() em paralelo. */
  function mostrarEnviado() {
    limparErroFeedback();
    $('#feedback-falha-area').replaceChildren();
    aplicarEstadoFeedback();
    $('#feedback-agradecimento').focus();
  }

  /* Falha de envio do comentário: bloco role="alert" com o texto "falha" (sempre o mesmo, sem detalhe técnico)
     em #feedback-falha-area e foco no bloco. O alert recém-inserido já é anunciado pelo leitor de tela,
     então não há anunciar() em paralelo. Quem chama já reabilitou campo e botão e removeu aria-busy;
     texto e chave ficam em state.feedback (concluirEnvio volta a 'ocioso'). Sem evento e sem agradecimento. */
  function mostrarFalhaFeedback() {
    const area = $('#feedback-falha-area');
    if (!area) return;
    const t = dadosFeedback();
    const bloco = el('div', { class: 'msg-falha', role: 'alert', tabindex: '-1' },
      el('p', { text: typeof t.falha === 'string' ? t.falha : '' }));
    area.replaceChildren(bloco);
    $('#feedback-agradecimento').textContent = '';
    bloco.focus();
  }

  /* Resultado do envio. Atualiza state.feedback só se a tentativa ainda é a atual (mesma chave, 'enviando'),
     grava a métrica no sucesso (sem texto) e só mexe na tela se a rota ainda é "resolvido". */
  function concluirFeedback(chave, payload, resultado) {
    const atual = state.feedback;
    const mesma = !!atual && atual.chave === chave && atual.estado === 'enviando';
    const ok = !!resultado && resultado.ok === true;
    if (mesma) state.feedback = TRESFeedback.concluirEnvio(atual, resultado, payload);
    if (ok) {
      try { gravarEvento(TRESFeedback.eventoComentario(payload, new Date())); } catch (e) { /* a métrica nunca altera a tela */ }
    }
    if (!mesma || lerRota().nome !== 'resolvido') return;
    if (ok) {
      mostrarEnviado();
    } else {
      definirEnviandoFeedback(false);
      mostrarFalhaFeedback();
    }
  }

  /* Envio do comentário. Chamado só com o comentário já validado (não vazio, até 500 caracteres). */
  function aoEnviarFeedback() {
    if (!TRESFeedback || !state.feedback) return;
    const preparo = TRESFeedback.prepararEnvio(state.feedback, {
      texto: $('#f-comentario').value,
      nota: state.feedback.nota,
      problemaId: lerRota().id,
      modelo: state.modelo || null,
      agora: () => new Date()
    });
    if (!preparo.ok) return; // 'ocupado' (duplo toque) ou inválido: nada é enviado

    // O estado muda ANTES de qualquer espera: toques e cliques seguintes caem no retorno de aoSubmeterFeedback.
    state.feedback = preparo.estado;
    definirEnviandoFeedback(true);

    const chave = preparo.estado.chave;
    const payload = preparo.payload;
    let promessa;
    try {
      promessa = Promise.resolve(pontoDeIntegracaoFeedback().enviar(payload));
    } catch (e) {
      promessa = Promise.resolve({ ok: false, categoria: 'rede' });
    }
    promessa
      .catch(() => ({ ok: false, categoria: 'rede' }))
      .then((resultado) => concluirFeedback(chave, payload, resultado));
  }

  /* Submit do Formulario_de_Feedback: valida antes de qualquer envio ou gravação. */
  function aoSubmeterFeedback(ev) {
    ev.preventDefault();
    const f = state.feedback;
    if (!TRESFeedback || !f || f.estado !== 'ocioso') return; // envio em andamento ou já enviado: ignora o toque

    // Nova tentativa após falha: o bloco de falha sai antes de validar o texto atual.
    $('#feedback-falha-area').replaceChildren();
    const campo = $('#f-comentario');
    if (TRESFeedback.validarComentario(campo.value) !== null) {
      // Vazio ou só espaços/quebras de linha: nada é gravado nem enviado; o texto digitado fica como está.
      mostrarErroComentario();
      campo.focus();
      anunciar(dadosFeedback().anuncioErroVazio);
      return;
    }
    limparErroComentario();
    aoEnviarFeedback();
  }

  /* Registrado uma única vez, na inicialização (fora do render). */
  function iniciarFeedback() {
    const form = $('#form-feedback');
    const campo = $('#f-comentario');
    const botao = $('#btn-enviar-comentario');
    if (!TRESFeedback || !form || !campo || !botao) return;

    campo.addEventListener('input', () => {
      // editarTexto só aceita edição em 'ocioso' e trunca em 500 (digitado ou colado).
      state.feedback = TRESFeedback.editarTexto(state.feedback, campo.value);
      if (state.feedback.estado === 'ocioso' && campo.value !== state.feedback.texto) campo.value = state.feedback.texto;
      atualizarContadorFeedback();
      if (campo.getAttribute('aria-invalid') === 'true') limparErroComentario();
    });

    // O botão é type="submit": Enter no textarea só insere quebra de linha e não envia.
    // O clique só impede ativação enquanto envia ou depois de enviado; a validação roda no submit.
    botao.addEventListener('click', (ev) => {
      if (!state.feedback || state.feedback.estado !== 'ocioso') ev.preventDefault();
    });

    form.addEventListener('submit', aoSubmeterFeedback);
  }

  /* ---------- cuidados por modelo ---------- */

  function renderCuidados(cont) {
    const m = modeloAtual();
    const idTitulo = 'tit-' + cont.id;
    const avisos = el('ul', { class: 'lista-simples' }, D.AVISOS_GERAIS.map((a) => el('li', { text: a })));

    if (!m) {
      cont.replaceChildren(el('section', { class: 'cuidados', 'aria-labelledby': idTitulo },
        el('h2', { id: idTitulo, text: 'Cuidados com a sua máquina' }),
        avisos,
        el('p', null, el('a', { href: '#/' }, 'Escolha o seu modelo'), ' para ver a limpeza e o guia rápido específicos.')));
      return;
    }

    cont.replaceChildren(el('section', { class: 'cuidados', 'aria-labelledby': idTitulo },
      el('h2', { id: idTitulo, text: 'Cuidados com a sua ' + m.nome }),
      m.cuidados.map((g) => el('details', null,
        el('summary', { text: g.titulo }),
        el('ol', null, g.itens.map((i) => el('li', { text: i }))))),
      m.alertas ? el('ul', { class: 'alertas' }, m.alertas.map((a) => el('li', { text: a }))) : null,
      m.botoes ? el('table', null,
        el('caption', { text: 'Volume padrão por tipo de bebida' }),
        el('thead', null, el('tr', null, el('th', { scope: 'col', text: 'Bebida' }), el('th', { scope: 'col', text: 'Volume' }))),
        el('tbody', null, D.BOTOES_BEBIDA.map((b) => el('tr', null, el('td', { text: b.bebida }), el('td', { text: b.volume }))))) : null,
      el('h3', { text: 'Vale lembrar' }),
      avisos,
      el('p', null, el('a', { href: m.guia, target: '_blank', rel: 'noopener noreferrer' }, 'Abrir o guia rápido da ' + m.nome + ' (PDF, abre em nova aba)'))));
  }

  /* ---------- início ---------- */

  iniciarModelos();
  iniciarFiltros();
  iniciarSolucao();
  iniciarResumo();
  iniciarFormulario();
  iniciarFeedback();
  aplicarTextos();
  window.addEventListener('hashchange', aoMudarRota);
  aoMudarRota();
})();
