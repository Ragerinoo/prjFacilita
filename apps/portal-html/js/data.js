/*
 * Conteúdo da jornada de autoatendimento TRES.
 *
 * FONTES (nada aqui foi inventado):
 *  - 13 problemas: "Mapa da Jornada de Atendimento" (PDF do desafio), reescritos
 *    da voz do atendente para a voz direta com o consumidor.
 *  - Cuidados por modelo, botões/volumes e retrolavagem: guias rápidos oficiais
 *    (LOV, Modo, Passione, Luna e Touch) em escolhatres.com.br.
 *  - Contatos: escolhatres.com.br/central-de-ajuda/.
 *
 * Itens marcados com PENDENTE precisam de validação com o time de Customer Success.
 */
(function () {
  'use strict';

  const CONTATO = {
    telefone: '0800 979 2021',
    telefoneLink: 'tel:08009792021',
    horarios: ['Segunda à sexta, das 08h às 18h', 'Sábado, das 08h às 12h'],
    email: 'atendimento@3coracoes.com.br',
    centralAjuda: 'https://www.escolhatres.com.br/central-de-ajuda/'
  };

  /* Procedimentos reutilizados em várias fichas. */
  const COMO_FAZER = {
    reset: {
      titulo: 'Como fazer o reset (zerar o contador)',
      passos: [
        'Desligue a máquina no botão lateral e levante a alavanca.',
        'Pressione as teclas de xícara azul e verde e, com elas pressionadas, ligue a máquina sem soltar.',
        'A máquina vai emitir 3 bips seguidos.',
        'Desligue a máquina e abaixe a alavanca.',
        'Ligue a máquina novamente.'
      ]
    },
    passagem: {
      titulo: 'Como fazer uma passagem de água',
      passos: [
        'Mantenha o reservatório com água potável, sem gás.',
        'Coloque um recipiente embaixo do bico, sem cápsula.',
        'Aperte a tecla azul e espere a máquina terminar sozinha.'
      ]
    },
    retrolavagem: {
      titulo: 'Como fazer a retrolavagem',
      passos: [
        'Confira se a máquina está ligada e o reservatório está cheio.',
        'Coloque um recipiente embaixo do bico.',
        'Levante a alavanca, encaixe a cápsula de retrolavagem e volte a alavanca para a posição original.',
        'Aperte a tecla azul e aguarde o enxágue completo.'
      ],
      aviso: 'A cápsula de retrolavagem é reutilizável. Não jogue fora.'
    }
  };

  /* Categorias exibidas como filtros na tela de problemas. */
  const CATEGORIAS = [
    { id: 'todos', nome: 'Todos' },
    { id: 'bebida', nome: 'Bebida' },
    { id: 'agua', nome: 'Água e vazamento' },
    { id: 'alertas', nome: 'Luzes e alertas' },
    { id: 'energia', nome: 'Não liga' },
    { id: 'alavanca', nome: 'Alavanca' }
  ];

  /*
   * tipo do passo: 'checar' (conferir algo) | 'acao' (fazer algo) | 'aviso'
   * ref: chave de COMO_FAZER para abrir o "como fazer" embutido no passo
   * porModelo: texto extra exibido só para o modelo escolhido
   * topo: um dos 4 motivos mais frequentes de chamado (segundo o briefing)
   */
  const PROBLEMAS = [
    {
      id: 1, slug: 'nao-liga', icone: '🔌', categoria: 'energia',
      titulo: 'A máquina não liga',
      resumo: 'Confira tomada, adaptadores e voltagem.',
      passos: [
        { tipo: 'checar', texto: 'A máquina está ligada direto na tomada?', detalhe: 'Sem adaptadores, transformadores, filtro de linha ou estabilizador.' },
        { tipo: 'acao', texto: 'Ligue a máquina em outra tomada.' },
        { tipo: 'checar', texto: 'Confira a voltagem.', detalhe: 'A voltagem da máquina e a da rede elétrica precisam ser compatíveis.' }
      ]
    },
    {
      id: 2, slug: 'luz-vermelha-fixa', icone: '🔴', categoria: 'alertas',
      titulo: 'Luz vermelha fixa',
      resumo: 'O alerta vermelho não pisca, fica aceso direto.',
      passos: [
        { tipo: 'acao', texto: 'Ligue a máquina e aguarde as teclas pararem de piscar.' },
        { tipo: 'acao', texto: 'Se o alerta vermelho continuar fixo, ligue em outra tomada de mesma voltagem.' }
      ]
    },
    {
      id: 3, slug: 'alerta-vermelho-piscando', icone: '🚨', categoria: 'alertas',
      titulo: 'Alerta vermelho piscando',
      resumo: 'Geralmente falta água no reservatório.',
      passos: [
        { tipo: 'checar', texto: 'O reservatório tem água?' },
        { tipo: 'acao', texto: 'Se não tiver, encha até o nível máximo e aperte a tecla azul.', detalhe: 'Use apenas água potável, em temperatura ambiente e sem gás.', visual: { vista: 'teclas', destaques: ['teclas'], legenda: 'As teclas das xícaras ficam no painel do topo. A azul é a que você aperta.' } },
        { tipo: 'acao', texto: 'Aguarde a passagem de água terminar sozinha.' }
      ]
    },
    {
      id: 4, slug: 'teclas-piscando', icone: '✨', categoria: 'alertas',
      titulo: 'Teclas das xícaras e sensor vermelho piscando',
      resumo: 'Teclas amarela, azul e verde piscando junto com o sensor vermelho.',
      passos: [
        { tipo: 'acao', texto: 'Faça uma passagem de água.', ref: 'passagem', visual: { vista: 'frente', destaques: ['teclas', 'bico', 'apoio'], legenda: 'Coloque o recipiente no apoio, embaixo do bico, e aperte a tecla azul.' } },
        { tipo: 'acao', texto: 'Aguarde o processo terminar sozinho.' }
      ],
      obs: 'Provavelmente o reset foi feito, mas sem finalizar com a passagem de água.'
    },
    {
      id: 5, slug: 'luz-amarela', icone: '🟡', categoria: 'alertas',
      titulo: 'Luz amarela acesa',
      resumo: 'É preciso zerar o contador da máquina.',
      passos: [
        { tipo: 'acao', texto: 'Zere o contador volumétrico seguindo o passo a passo.', ref: 'reset', visual: { vista: 'teclas', destaques: ['teclas'], legenda: 'Com a máquina desligada, mantenha apertadas as teclas azul e verde e ligue sem soltar.' } }
      ],
      obs: 'O reset também serve para desativar o alerta, porque ele zera o contador volumétrico.'
    },
    {
      id: 6, slug: 'nao-extrai', icone: '☕', categoria: 'bebida', topo: true,
      titulo: 'A máquina não extrai bebida',
      resumo: 'Você aperta e o café não sai.',
      passos: [
        { tipo: 'checar', texto: 'Com o tanque cheio, o alerta vermelho acende durante o preparo?' },
        { tipo: 'checar', texto: 'O problema acontece com outras cápsulas também?' },
        { tipo: 'acao', texto: 'Faça o reset e 2 passagens de água.', detalhe: 'De preferência com a cápsula de retrolavagem.', ref: 'reset', visual: { vista: 'frente', destaques: ['teclas', 'bico'], legenda: 'As teclas azul e verde fazem o reset. Depois, faça as passagens de água com um recipiente embaixo do bico.' } },
        { tipo: 'acao', texto: 'Repita o teste com uma cápsula de bebida.' }
      ]
    },
    {
      id: 7, slug: 'bebida-aguada', icone: '💧', categoria: 'bebida',
      titulo: 'Bebida aguada',
      resumo: 'O café saiu fraco ou com pouco sabor.',
      passos: [
        { tipo: 'checar', texto: 'A tecla que você aperta é a mesma indicada na cápsula?', visual: { vista: 'teclas', destaques: ['teclas'], legenda: 'A cor da tecla que você aperta deve ser a mesma indicada na cápsula.' } },
        { tipo: 'acao', texto: 'Se não for, use a cor certa para o tipo de bebida.' },
        {
          tipo: 'checar', texto: 'O volume da bebida está dentro do padrão?',
          detalhe: 'Espresso: 50 mL. Cappuccino, chocolatto e bebidas cremosas: 80 mL. Café filtrado e chás: 100 mL.',
          porModelo: { modo: 'Na Modo, o volume pode ter sido reprogramado (de 30 mL até 250 mL). Veja "Cuidados com a sua máquina" abaixo para reprogramar.' }
        }
      ]
    },
    {
      id: 8, slug: 'bebida-fria', icone: '🧊', categoria: 'bebida',
      titulo: 'Bebida fria',
      resumo: 'O café sai morno ou frio.',
      passos: [
        // PENDENTE: o mapa pede "aumentar a temperatura", mas não descreve como. Validar com o CS.
        { tipo: 'acao', texto: 'Faça o reset da máquina e aumente a temperatura para regular.', ref: 'reset', visual: { vista: 'teclas', destaques: ['teclas'], legenda: 'Com a máquina desligada, mantenha apertadas as teclas azul e verde e ligue sem soltar.' } },
        { tipo: 'acao', texto: 'Se precisar, pré-aqueça a xícara: coloque-a embaixo do bico e faça uma passagem de água na tecla azul.', visual: { vista: 'frente', destaques: ['teclas', 'bico', 'apoio'], legenda: 'Coloque a xícara no apoio, embaixo do bico, e faça uma passagem de água na tecla azul.' } }
      ]
    },
    {
      id: 9, slug: 'alavanca-travada', icone: '🔒', categoria: 'alavanca',
      titulo: 'Alavanca travada',
      resumo: 'A alavanca não levanta nem abaixa.',
      passos: [
        { tipo: 'acao', texto: 'Posicione a máquina de costas para você.' },
        { tipo: 'acao', texto: 'Com uma mão, segure firme o corpo da máquina. Com a outra, puxe a alavanca para trás com firmeza.' },
        { tipo: 'acao', texto: 'Quando liberar, retire a cápsula e feche a alavanca.' },
        { tipo: 'acao', texto: 'Ligue a máquina com a água do reservatório acima da metade.' },
        { tipo: 'acao', texto: 'Toque uma vez na tecla da xícara do meio.', detalhe: 'A máquina vai liberar um pouco de água pelo bico e voltar ao funcionamento normal.' }
      ]
    },
    {
      id: 10, slug: 'vazamento', icone: '🌊', categoria: 'agua', topo: true,
      titulo: 'Vazamento',
      resumo: 'Tem água escorrendo ou acumulada.',
      passos: [
        { tipo: 'checar', texto: 'O vazamento é por fora ou por dentro da máquina?' },
        // PENDENTE: o mapa manda seguir a "resposta de e-mail 37" (conteúdo não fornecido).
        // O texto abaixo vem apenas dos guias rápidos (esvaziar a gaveta de cápsulas usadas).
        { tipo: 'checar', texto: 'É só a água que fica no compartimento de cápsulas usadas?', detalhe: 'Remova as cápsulas usadas logo após o uso e esvazie a gaveta para manter o compartimento limpo.' },
        { tipo: 'checar', texto: 'Será que não é entupimento?', detalhe: 'Se o bico estiver entupido, veja a solução de "Bico entupido".', link: 12 },
        { tipo: 'checar', texto: 'A água chega a molhar a superfície onde a máquina está?' }
      ]
    },
    {
      id: 11, slug: 'nao-puxa-agua', icone: '🚰', categoria: 'agua', topo: true,
      titulo: 'A máquina não puxa água',
      resumo: 'O reservatório tem água, mas ela não chega.',
      passos: [
        { tipo: 'checar', texto: 'O reservatório está bem encaixado e com água?' },
        { tipo: 'acao', texto: 'Se não estiver, retire e recoloque o reservatório. Depois aperte a tecla azul e aguarde terminar.' },
        { tipo: 'acao', texto: 'Se não resolver, repita o processo.' }
      ]
    },
    {
      id: 12, slug: 'bico-entupido', icone: '🧯', categoria: 'bebida', topo: true,
      titulo: 'Bico entupido',
      resumo: 'A bebida sai fraca, falha ou não passa pelo bico.',
      passos: [
        { tipo: 'checar', texto: 'A bebida saiu na bandeja de descarte de cápsulas?' },
        { tipo: 'acao', texto: 'Se saiu, faça a retrolavagem 5 vezes.', ref: 'retrolavagem', visual: { vista: 'frente', destaques: ['teclas', 'bico'], legenda: 'Com a cápsula de retrolavagem encaixada, aperte a tecla azul e aguarde o enxágue completo.' } },
        { tipo: 'acao', texto: 'Em seguida, tente extrair uma bebida novamente.' }
      ]
    },
    {
      id: 13, slug: 'alavanca-nao-fecha', icone: '🔓', categoria: 'alavanca',
      titulo: 'A alavanca não fecha com a cápsula',
      resumo: 'Com a cápsula dentro, a alavanca não desce.',
      passos: [
        { tipo: 'checar', texto: 'O porta-cápsulas está cheio?' },
        { tipo: 'acao', texto: 'Se estiver, esvazie e limpe o porta-cápsulas.', detalhe: 'Lave as peças com água fria e esponja não abrasiva.' }
      ]
    }
  ];

  const MODELOS = [
    {
      id: 'lov', nome: 'LOV',
      imagem: 'img/web/lov.png', dica: 'Alta e arredondada, teclas no topo',
      guia: 'https://www.escolhatres.com.br/wp-content/uploads/2020/01/Guia_Rapido_LOV.pdf',
      cuidados: [
        { titulo: 'Limpeza diária', itens: [
          'Máquina ligada e reservatório cheio.',
          'Coloque um recipiente embaixo do bico.',
          'Levante a alavanca, encaixe a cápsula de retrolavagem e volte a alavanca.',
          'Aperte a tecla azul e aguarde o enxágue completo.',
          'Retire o porta-cápsulas e a cápsula de retrolavagem e lave-os.',
          'Limpe a parte interna com um pano úmido, com cuidado.'
        ] },
        { titulo: 'Limpeza completa', itens: [
          'Retire o recipiente de recolhimento de gotas e a grade. Lave com água fria e esponja não abrasiva.',
          'Esvazie o reservatório de água e enxágue-o.'
        ] }
      ],
      alertas: ['O guia da LOV indica que a limpeza deve ser feita todos os dias.']
    },
    {
      id: 'modo', nome: 'Modo',
      imagem: 'img/web/modo.png', dica: 'Prata e vermelha, painel redondo na frente',
      guia: 'https://www.escolhatres.com.br/wp-content/uploads/2020/01/guia_modo.pdf',
      cuidados: [
        { titulo: 'Depois de usar', itens: [
          'Remova as cápsulas usadas do compartimento.',
          'Máquina ligada e reservatório cheio, com um recipiente embaixo do bico.',
          'Encaixe a cápsula de retrolavagem, volte a alavanca e aperte a tecla azul. Aguarde o enxágue.',
          'Repita a operação 2 vezes e desligue a máquina.',
          'Lave a gaveta de cápsulas com água fria e esponja não abrasiva.',
          'Esvazie e enxágue o reservatório de água.'
        ] },
        { titulo: 'Programar a quantidade da bebida', itens: [
          'Pressione e mantenha pressionada a tecla que deseja reprogramar.',
          'Quando a xícara atingir a quantidade desejada, solte a tecla.',
          'Repita para as outras teclas. O volume pode ir de 30 mL até 250 mL.'
        ] }
      ],
      alertas: ['A limpeza é essencial, principalmente depois de bebidas que levam leite na composição.']
    },
    {
      id: 'passione', nome: 'Passione',
      imagem: 'img/web/passione.png', dica: 'Estreita, com frisos na lateral',
      guia: 'https://www.escolhatres.com.br/wp-content/uploads/2021/05/201125_TRES_169_Guia_Rapido_Passione_16x16_V3.pdf',
      cuidados: [
        { titulo: 'Limpeza diária', itens: [
          'Máquina ligada e reservatório cheio, com um recipiente embaixo do bico.',
          'Encaixe a cápsula de retrolavagem e volte a alavanca.',
          'Aperte a tecla azul e aguarde o enxágue. Repita 2 vezes.',
          'Retire a gaveta e limpe com água fria.'
        ] },
        { titulo: 'Limpeza completa (a cada 15 dias)', itens: [
          'Faça a retrolavagem 2 vezes.',
          'Retire as cápsulas usadas e a gaveta, e lave com água fria.',
          'Retire a grade, esvazie o recipiente de gotas e enxágue.',
          'Esvazie e enxágue o reservatório de água.'
        ] }
      ],
      botoes: true
    },
    {
      id: 'luna', nome: 'Luna',
      imagem: 'img/web/luna.png', dica: 'Preta, com coração branco na frente',
      guia: 'https://www.escolhatres.com.br/wp-content/uploads/2023/12/230405_1086_TRES_Guia_Unico_NOVA_LUNA.pdf',
      cuidados: [
        { titulo: 'Limpeza diária', itens: [
          'Máquina ligada e reservatório cheio, com um recipiente embaixo do bico.',
          'Encaixe a cápsula de retrolavagem e volte a alavanca.',
          'Aperte a tecla azul e aguarde o enxágue. Repita 2 vezes.',
          'Retire a gaveta e limpe com água fria.'
        ] },
        { titulo: 'Limpeza semanal do bico de extração', itens: [
          'Pressione as abas internas do bico, puxando para baixo.',
          'Gire a parte superior no sentido contrário ao da inferior para separar as duas partes.',
          'Enxágue as peças e monte novamente (só existe uma maneira de encaixar).',
          'Recoloque na máquina até ouvir o clique.'
        ] }
      ],
      alertas: [
        'Depois de bebidas cremosas, limpe o bico logo após o uso.',
        'Levante a alavanca depois do preparo, para a cápsula cair na gaveta e não ficar presa.',
        'A cápsula de retrolavagem é exclusiva da Luna.'
      ],
      botoes: true
    },
    {
      id: 'touch', nome: 'Touch',
      imagem: 'img/web/touch.png', dica: 'Painel touch com ícone de ligar',
      guia: 'https://www.escolhatres.com.br/wp-content/uploads/2020/10/200624_TRES_169_Guia_Rapido_G2_Touch_18x18_AF.pdf',
      cuidados: [
        { titulo: 'Limpeza diária', itens: [
          'Máquina ligada e reservatório cheio, com um recipiente embaixo do bico.',
          'Encaixe a cápsula de retrolavagem e volte a alavanca.',
          'Aperte a tecla azul e aguarde o enxágue. Repita 2 vezes.',
          'Retire a gaveta e limpe com água fria.'
        ] },
        { titulo: 'Limpeza completa (a cada 15 dias)', itens: [
          'Faça a retrolavagem e retire as cápsulas usadas.',
          'Retire a gaveta e a grade; esvazie o recipiente de gotas e enxágue.',
          'Esvazie e enxágue o reservatório de água.'
        ] }
      ],
      botoes: true
    }
  ];

  const BOTOES_BEBIDA = [
    { bebida: 'Cafés espressos', volume: '50 mL' },
    { bebida: 'Cappuccino, chocolatto e bebidas cremosas', volume: '80 mL' },
    { bebida: 'Cafés filtrados e chás', volume: '100 mL' }
  ];

  const AVISOS_GERAIS = [
    'Use somente água potável, em temperatura ambiente e sem gás.',
    'Não use leite nem outros líquidos no reservatório.',
    'Não use jatos de água nem palha de aço ou esponja abrasiva para limpar.'
  ];

  /*
   * Ilustração 3D do passo (apenas a Touch, a única máquina com modelo 3D).
   * O modelo é uma peça única: não há animação, só câmera e rótulos.
   * Posições medidas no próprio modelo (em metros). Revisar se o arquivo .glb for trocado.
   * "visual" nos passos escolhe a vista da câmera e quais rótulos aparecem.
   */
  const MODELO_3D = {
    modelo: 'touch',
    arquivo: 'modelos3d/maquina-web.glb',
    poster: 'img/web/touch.png',
    alt: 'Modelo 3D da máquina TRES Touch',
    biblioteca: 'js/vendor/model-viewer-umd.min.js',
    vistas: {
      teclas: { alvo: '0.008m 0.74m 0.03m', orbita: '0deg 35deg 0.7m' },
      frente: { alvo: '0m 0.38m 0.1m', orbita: '15deg 72deg 2.1m' }
    },
    pontos: {
      teclas: { rotulo: 'Teclas das xícaras', posicao: '0.008m 0.7533m 0.0318m', normal: '-0.009m 0.988m 0.157m' },
      bico: { rotulo: 'Bico', posicao: '-0.0004m 0.4914m 0.3108m', normal: '-0.012m 0m 1m' },
      apoio: { rotulo: 'Apoio da xícara', posicao: '-0.0085m 0.144m 0.2916m', normal: '-0.041m 0.996m -0.079m' }
    }
  };

  /*
   * Tela de abertura de chamado (rota #/suporte/ID) e confirmação (rota #/chamado/ID).
   * Todo texto novo dessas telas mora aqui: index.html e app.js só preenchem.
   *
   * PENDENTE (valor ainda não validado):
   *  - prazo de retorno: ilustrativo, depende do Customer Success;
   *  - controlador dos dados, contato do titular e URL da política: dependem do jurídico;
   *  - URL da API, tempo limite e contrato: dependem do time de back end.
   * Os termos de uso não têm texto jurídico: o botão "Ler os termos" é ilustrativo.
   *
   * Marcadores {chave} dentro dos textos são trocados por texto literal em js/chamado.js
   * e js/app.js (nunca por HTML).
   */
  const CHAMADO = {
    config: {
      // Vazia = Modo_Prototipo (envio simulado, gravado no localStorage).
      // ILUSTRATIVO / PENDENTE (back end): URL do endpoint por ambiente.
      API_CHAMADOS_URL: '',
      // ILUSTRATIVO / PENDENTE (back end): tempo limite do envio, em milissegundos.
      TIMEOUT_ENVIO_MS: 10000,
      // ILUSTRATIVO / PENDENTE (Customer Success): prazo de retorno, em dias úteis.
      PRAZO_RETORNO_DIAS_UTEIS: 2,
      // ILUSTRATIVO / PENDENTE (Customer Success): vira true só depois da validação do prazo.
      PRAZO_RETORNO_VALIDADO: false,
      // ILUSTRATIVO / PENDENTE (back end): versão do contrato do payload.
      VERSAO_CONTRATO: '1'
    },

    privacidade: {
      // PENDENTE (jurídico): nome do controlador dos dados.
      controlador: 'PENDENTE',
      // PENDENTE (jurídico): e-mail ou telefone para o titular exercer seus direitos.
      contato: 'PENDENTE',
      // PENDENTE (jurídico): URL da política de privacidade. Vazia = o aviso não mostra link.
      politicaUrl: ''
    },

    textos: {
      /* Abertura da tela */
      tituloChamado: 'Seu chamado será aberto. Falta pouco.',
      introChamado: 'Você já fez a sua parte. O time responsável vai receber o seu chamado e analisar o problema. Preencha os dados abaixo para a gente poder te responder.',

      /* Resumo da jornada */
      resumoTitulo: 'O que você já viu',
      resumoRotuloModelo: 'Máquina',
      resumoRotuloProblema: 'Problema',
      resumoRotuloPassos: 'Passos',
      resumoContagem: '{x} de {y} passos',
      resumoLegendaPassos: 'Passos que apresentamos para você nesta visita, na ordem da solução.',
      resumoSemPassos: 'Nenhum passo registrado nesta visita',
      resumoVer: 'Ver os passos',
      resumoOcultar: 'Ocultar os passos',
      naoInformado: 'Não informado',

      /* Formulário */
      formTitulo: 'Dados para abrir o chamado',
      rotuloNome: 'Nome',
      rotuloEmail: 'E-mail',
      rotuloTelefone: 'Telefone (WhatsApp)',
      rotuloDescricao: 'O que está acontecendo com a máquina',
      obrigatorio: 'obrigatório',
      ajudaTelefone: 'Informe com DDD. Vamos usar este número para falar com você pelo WhatsApp.',
      contadorDescricao: '{n} de 500 caracteres',

      /* Aviso de privacidade, aceite e termos.
         PENDENTE (jurídico): texto do aviso e base legal. Sem links jurídicos aqui. */
      privacidade: 'Usamos seu nome, e-mail, telefone e a descrição só para abrir, analisar e responder ao chamado. O resumo da jornada que você percorreu vai junto. Controlador dos dados: {controlador}. Contato para seus direitos de titular: {contato}.',
      privacidadePolitica: 'Política de privacidade',
      rotuloAceite: 'Li e concordo com os termos para envio dos meus dados',
      botaoLerTermos: 'Ler os termos',
      // PENDENTE (jurídico): não existe texto dos termos. O botão é só ilustrativo.
      termosEmElaboracao: 'Texto dos termos em elaboração',

      /* Erros de validação */
      erroAceite: 'Para enviar, marque que você leu e concorda com os termos.',
      erroVazio: 'Preencha este campo.',
      erroNome: 'O nome deve ter de {min} a {max} caracteres, com ao menos uma letra.',
      erroEmail: 'Informe um e-mail válido, como nome@exemplo.com.',
      erroTelefone: 'Informe um telefone com DDD, com 10 ou 11 números.',
      erroDescricao: 'A descrição deve ter de {min} a {max} caracteres.',
      anuncioErros: 'Não foi possível enviar. {n} itens precisam de correção.',
      anuncioErrosSingular: 'Não foi possível enviar. 1 item precisa de correção.',

      /* Prazo e canais de retorno.
         ILUSTRATIVO / PENDENTE (Customer Success): o prazo vem de config.PRAZO_RETORNO_DIAS_UTEIS. */
      prazoFrase: 'O prazo de retorno é de até {prazo}.',
      canaisFormulario: 'Vamos falar com você por WhatsApp e por e-mail.',
      canaisConfirmacao: 'Vamos falar com você pelo WhatsApp, no número {telefone}, e por e-mail, em {email}.',

      /* Envio, falha e conteúdo indisponível */
      botaoAbrirChamado: 'Abrir meu chamado',
      botaoEnviando: 'Enviando',
      anuncioEnviando: 'Enviando o seu chamado.',
      anuncioSucesso: 'Chamado aberto. Seu protocolo é {protocolo}.',
      falha: 'Não conseguimos abrir o chamado agora. Seus dados continuam preenchidos. Tente de novo em instantes.',
      falhaAlternativa: 'Se preferir, fale com a gente: {telefone} ou {email}.',
      conteudoIndisponivel: 'Esta tela está indisponível no momento. Tente novamente mais tarde.',

      /* Confirmação */
      tituloConfirmacao: 'Chamado aberto',
      confirmacaoRecebido: 'O time responsável recebeu o seu chamado e vai analisar o problema.',
      confirmacaoConferir: 'Confira se os seus dados de contato estão corretos:',
      protocoloRotulo: 'Número do protocolo',
      rotuloEmailConfirmacao: 'E-mail',
      rotuloTelefoneConfirmacao: 'Telefone (WhatsApp)',
      // ILUSTRATIVO: aparece só em Modo_Prototipo (sem back end).
      avisoPrototipo: 'Este é um protótipo. O chamado foi simulado e não foi enviado a um sistema de atendimento. O prazo informado é ilustrativo.',
      avaliacaoTitulo: 'Como foi a ajuda até aqui?',

      /* Botões de navegação */
      botaoRever: 'Rever os passos',
      botaoEscolherOutro: 'Escolher outro problema',
      botaoOutroProblema: 'Tenho outro problema',
      botaoVoltarInicio: 'Voltar ao início'
    }
  };

  /*
   * Comentário opcional na tela de problema resolvido (rota #/resolvido/ID).
   * Configuração e textos próprios, separados de CHAMADO. Todo texto novo do feedback
   * mora aqui: index.html e app.js só preenchem (data-texto-feedback + textContent).
   *
   * PENDENTE (valor ainda não validado):
   *  - URL da API de feedback, tempo limite e contrato: dependem do time de back end;
   *  - texto do aviso de não identificação: depende da revisão jurídica (LGPD).
   *
   * Marcadores {chave} dentro dos textos são trocados por texto literal (nunca por HTML).
   */
  const FEEDBACK = {
    config: {
      // Vazia = Modo_Prototipo (grava em tres-autoatendimento-feedbacks).
      // Independente de CHAMADO.config.API_CHAMADOS_URL: o feedback nunca usa a URL do chamado.
      // ILUSTRATIVO / PENDENTE (back end): URL do endpoint de feedback por ambiente.
      API_FEEDBACK_URL: '',
      // ILUSTRATIVO / PENDENTE (back end): tempo limite do envio do feedback, em milissegundos.
      TIMEOUT_FEEDBACK_MS: 10000,
      // ILUSTRATIVO / PENDENTE (back end): versão do contrato do Payload_do_Feedback.
      VERSAO_CONTRATO_FEEDBACK: '1'
      // PENDENTE (back end): URL por ambiente, autenticação e autorização, CORS, esquema do banco,
      // formato da resposta de sucesso, tratamento de chave de idempotência repetida,
      // cabeçalho de idempotência, limites de tamanho, limitação de taxa e prazo de retenção.
    },

    textos: {
      rotulo: 'Deixe um comentário sobre a ajuda',
      opcional: '(opcional)',
      // ILUSTRATIVO / PENDENTE (jurídico/LGPD): texto do aviso de não identificação.
      avisoNaoIdentificacao: 'Não escreva nome, e-mail, telefone nem outros dados pessoais aqui.',
      contador: '{n} de {max} caracteres',
      botaoEnviar: 'Enviar comentário',
      botaoEnviando: 'Enviando',
      erroVazio: 'Escreva um comentário antes de enviar.',
      anuncioErroVazio: 'Comentário vazio. Escreva um comentário antes de enviar.',
      agradecimento: 'Obrigado pelo seu comentário! Ele ajuda a melhorar o autoatendimento.',
      falha: 'Não conseguimos enviar o seu comentário agora. O texto continua aqui. Tente de novo em instantes.'
    }
  };

  window.TRES_DATA = { CONTATO, COMO_FAZER, CATEGORIAS, PROBLEMAS, MODELOS, BOTOES_BEBIDA, AVISOS_GERAIS, MODELO_3D, CHAMADO, FEEDBACK };
})();
