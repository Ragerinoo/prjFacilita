# Implementation Plan: Comentário opcional na tela de problema resolvido (resolved-feedback-comment)

## Overview

O plano segue a ordem do design: primeiro configuração e textos em `js/data.js`, depois as mudanças aditivas em `js/chamado.js`, o núcleo sem DOM em `js/feedback.js`, o HTML (`index.html`), o CSS (`css/styles.css`) e a lógica de tela (`js/app.js`). Em seguida vêm os testes do núcleo em Node (fast-check só em `tests/`, fora do site), os testes de interface em Edge headless, a atualização do `CONTEXTO-PROJETO.md` e a verificação final.

Regras que valem para todas as tarefas:

- O site continua HTML, CSS e JS puros, sem build e sem pacotes na raiz. Nenhuma biblioteca, fonte ou script de terceiros novo em produção.
- Nenhum texto novo do feedback é escrito em `index.html`, `js/app.js`, `js/chamado.js` ou `js/feedback.js`; tudo vem de `TRES_DATA.FEEDBACK` em `js/data.js` e entra na página por `data-texto-feedback` e `textContent`.
- O código novo não usa `console.*` e não usa `innerHTML`, `insertAdjacentHTML`, `outerHTML` nem `document.write` com dados do consumidor, do back end ou de `data.js`. O comentário entra na página só por `value` ou `textContent`.
- `js/feedback.js` é um módulo UMD com fábrica `criar(base)`: não usa `require(`, `import(`, DOM, `window`, `localStorage`, `fetch` nem relógio direto dentro das funções do núcleo (tudo entra por parâmetro). No navegador usa `window.TRESChamado` já carregado.
- O texto do comentário nunca vai para `tres-autoatendimento-eventos`, para `tres-autoatendimento-chamados`, para o console, para a URL, para cookies nem para `sessionStorage`. Em Modo_Prototipo vai só para `tres-autoatendimento-feedbacks` (máximo de 50 registros); em Modo_API vai só no corpo da requisição.
- `API_FEEDBACK_URL` e `API_CHAMADOS_URL` ficam vazias no repositório (Modo_Prototipo). O contrato do Payload_do_Feedback (versão `"1"`) é provisório; o que depende do back end ou do jurídico fica marcado `PENDENTE` ou `ILUSTRATIVO`.
- O formulário do chamado, a Tela_de_Chamado e a Tela_de_Confirmacao não mudam. Nenhuma regra CSS existente é editada.
- Não alterar `material/`, `img/*.png` originais nem o `.glb` original. Não criar, mover nem excluir arquivos em `material/`.
- Testes de interface: o Edge headless recarrega a aba depois de uns 5 s. Cada cenário é curto (menos de 4 s) e começa em carga nova. NUNCA rodar duas execuções de `node tests/ui/rodar.js` ao mesmo tempo (uma encerra o Edge da outra); para rodar cenários em paralelo, usar `node --test` direto nos arquivos de `tests/ui/cenarios/`.
- Não fazer commits.

## Tasks

- [x] 1. Linha de base e configuração/textos em `js/data.js`
  - [x] 1.1 Conferir a linha de base dos arquivos protegidos antes de qualquer alteração
    - Rodar `node tests/verificar-protegidos.js --conferir` e confirmar que passa; NÃO rodar `--gerar` (a linha de base `tests/baseline-protegidos.json` já existe e não deve ser regravada)
    - _Requirements: 14.7_

  - [x] 1.2 Acrescentar o objeto `FEEDBACK` em `js/data.js` e exportá-lo em `window.TRES_DATA`
    - `config`: `API_FEEDBACK_URL: ''`, `TIMEOUT_FEEDBACK_MS: 10000`, `VERSAO_CONTRATO_FEEDBACK: '1'`, cada valor com comentário `PENDENTE` ou `ILUSTRATIVO`; comentário `PENDENTE (back end)` listando URL por ambiente, autenticação e autorização, CORS, esquema do banco, formato da resposta, chave repetida, cabeçalho de idempotência, limites, limitação de taxa e retenção
    - `textos`: `rotulo`, `opcional`, `avisoNaoIdentificacao` (1 a 200 caracteres, pede para não escrever nome, e-mail, telefone nem outros dados pessoais; `ILUSTRATIVO / PENDENTE` jurídico/LGPD), `contador` (`'{n} de {max} caracteres'`), `botaoEnviar`, `botaoEnviando`, `erroVazio`, `anuncioErroVazio`, `agradecimento`, `falha`, em português do Brasil, sem palavras vagas como "rapidamente" ou "adequado"
    - Não criar texto de título novo do bloco (o `h2` "Como foi a ajuda?" já existe) nem texto de aviso de protótipo
    - Manter intactas todas as chaves e valores atuais de `TRES_DATA`, inclusive `TRES_DATA.CHAMADO`
    - _Requirements: 2.3, 4.2, 10.3, 10.16, 13.1, 13.2, 13.5, 13.6, 14.8_

- [x] 2. Mudanças aditivas em `js/chamado.js`
  - [x] 2.1 Fazer `resumirEventos` contar eventos `comentario`
    - Acrescentar o campo `comentarios` ao resultado (quantidade de eventos com `tipo === 'comentario'`, ou 0)
    - Eventos `comentario` são ignorados nos cálculos de `resolvidos`, `encaminhadosAoSuporte`, `deflexaoPercentual`, `porProblema` e `chamadosAbertos`, como já acontece com `chamado` e `avaliacao`
    - Não alterar mais nada do arquivo nesta tarefa; observação: o teste existente `tests/nucleo/textos-metricas.test.js` passa a falhar nos `deepEqual` até a tarefa 8.24
    - _Requirements: 11.5, 11.6_

  - [x] 2.2 Exportar `formatarIsoComFuso` em `js/chamado.js`
    - Incluir `formatarIsoComFuso` na API exportada (hoje é privada), sem alterar o comportamento nem as assinaturas existentes
    - _Requirements: 10.12, 14.4_

- [x] 3. Implementar o núcleo sem DOM em `js/feedback.js`
  - [x] 3.1 Criar o módulo UMD com fábrica `criar(base)`, constantes e funções de texto
    - Criar `js/feedback.js` com `'use strict'`; em Node exporta `{ criar }`; no navegador define `window.TRESFeedback = window.TRESChamado ? criar(window.TRESChamado) : null`; sem `require(`
    - Constantes: `LIMITES` (`{ comentario: { min: 1, max: 500 }, maxFeedbacks: 50 }`), `CHAVE_REPOSITORIO` (`'tres-autoatendimento-feedbacks'`), `CAMPOS_PAYLOAD` (os 7 campos), `CHAVES_TEXTOS_OBRIGATORIAS`
    - `normalizarComentario(s)` (`String(s).trim()`, `null`/`undefined` viram `''`, preserva quebras de linha e espaços internos), `validarComentario(s)` (`null`, `'vazio'`, `'tamanho'`), `limitarComentario(s)` (`slice(0, 500)`), `formatarContador(modelo, s)` (substituição literal de `{n}` e `{max}` via `base.preencherModelo`)
    - Contar caracteres com `String.length`, igual ao `maxlength` do navegador
    - _Requirements: 2.5, 4.1, 4.2, 4.3, 5.2, 5.3, 6.1, 6.2, 6.5, 13.3_

  - [x] 3.2 Implementar estado do formulário, payload e serialização
    - `novoEstado(problemaId)`, `garantirEstado(estado, problemaId)`, `aoExibir(estado, problemaId)` (zera `texto`, `chave` e `nota` quando `'ocioso'`; mantém `'enviando'` e `'enviado'`), `editarTexto(estado, s)` (só em `'ocioso'`, com `limitarComentario`), `escolherNota(estado, n)` (inteiro de 1 a 5, senão `null`)
    - `prepararEnvio(estado, entrada)` (recusa `'ocupado'` fora de `'ocioso'`, recusa `'vazio'`/`'tamanho'` sem alterar o estado, cria a chave com `base.gerarChaveIdempotencia` só no primeiro envio válido e a reutiliza, devolve `{ ok: true, estado: 'enviando', payload }`) e `concluirEnvio(estado, resultado, payload)` (sucesso → `'enviado'` com `enviado.comentario`; falha → `'ocioso'` mantendo `texto` e `chave`)
    - `montarPayload(entrada)` com exatamente os 7 campos (`versaoContrato`, `chaveIdempotencia`, `enviadoEm` via `base.formatarIsoComFuso`, `comentario` normalizado, `nota` 1 a 5 ou `null`, `problemaId`, `modelo` texto ou `null`), ignorando qualquer outro campo recebido; `serializar` e `desserializar` delegando a `base`
    - _Requirements: 2.4, 3.2, 3.3, 4.5, 5.1, 5.6, 7.1, 7.2, 7.3, 7.8, 7.9, 7.10, 8.2, 8.5, 8.6, 10.11, 10.12, 10.13, 10.14, 10.15_

  - [x] 3.3 Implementar `modoDoFeedback` e o Ponto_de_Integracao_de_Feedback
    - `modoDoFeedback(config)` usa `base.resolverModo(config.API_FEEDBACK_URL)`; nunca usa `API_CHAMADOS_URL`
    - `criarPontoDeIntegracao(deps)` (deps: `config`, `fetch`, `AbortController`, `setTimeout`, `clearTimeout`, `storage`) devolve `{ enviar(payload) }`, que sempre resolve com `{ ok: true, modo }` ou `{ ok: false, categoria, status? }` (`'rede'`, `'timeout'`, `'http'`, `'armazenamento'`)
    - Modo_API: um único `fetch` `POST` com `Content-Type: application/json`, corpo `base.serializar(payload)`, `AbortController` e `TIMEOUT_FEEDBACK_MS` (padrão 10 000 se inválido), `credentials: 'omit'`, `cache: 'no-store'`, `referrerPolicy: 'no-referrer'`; qualquer status 2xx é sucesso sem ler o corpo; fora de 2xx → `'http'` com só o número do status; sem retentativa; sem `AbortController` usa `Promise.race` com temporizador; sempre `clearTimeout`; não toca no armazenamento
    - Modo_Prototipo: ler `storage.getItem` diretamente (exceção → `'armazenamento'`), `base.lerLista`, se a mesma `chaveIdempotencia` já existe devolver sucesso sem gravar de novo, senão gravar o payload (exatamente o payload, sem campos extras) com `base.adicionarComLimite(..., 50)` na chave `tres-autoatendimento-feedbacks`; exceção na gravação → `'armazenamento'` sem alterar o que existia; nenhuma requisição de rede
    - Sem `console.*`; o corpo da resposta nunca aparece no resultado
    - _Requirements: 8.1, 9.1, 9.2, 9.3, 9.6, 9.7, 9.8, 10.1, 10.2, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10_

  - [x] 3.4 Implementar `eventoComentario`, `textosValidos` e fechar a API pública
    - `eventoComentario(payload, em)` → `{ tipo: 'comentario', em, problema, modelo }` (modelo `null` vira `'nao-informado'`), sem texto, nota, tamanho nem chave
    - `textosValidos(dadosFeedback)` → `true` só se `config` e `textos` existem e todas as chaves de `CHAVES_TEXTOS_OBRIGATORIAS` são texto não vazio após `trim`
    - Conferir que a API exportada contém todas as funções e constantes do design
    - _Requirements: 11.1, 11.2, 11.4, 13.4_

- [x] 4. Estrutura HTML em `index.html`
  - [x] 4.1 Incluir o script do núcleo do feedback
    - Acrescentar `<script src="js/feedback.js"></script>` entre `js/chamado.js` e `js/app.js`
    - _Requirements: 14.6_

  - [x] 4.2 Incluir o `#form-feedback` dentro de `#view-resolvido`
    - No `div.avaliacao` já existente (`role="group"`, `aria-labelledby="titulo-aval"`), logo depois de `#status-aval` e antes de `#cuidados-resolvido`, incluir o esqueleto do design: `<form id="form-feedback" class="feedback" novalidate hidden>` com `.campo` contendo `label for="f-comentario"` (com "opcional" dentro do rótulo), `textarea#f-comentario` (`name="comentario"`, `rows="4"`, `maxlength="500"`, `autocomplete="off"`, `aria-describedby="f-comentario-aviso f-comentario-contador"`), `p#f-comentario-aviso`, `p#f-comentario-contador` (sem `aria-live`), `p#f-comentario-erro.campo__erro` com `hidden`, `button#btn-enviar-comentario.btn` (`type="submit"`), `div#feedback-agradecimento` (`role="status"`, `aria-live="polite"`, `tabindex="-1"`, vazia) e `div#feedback-falha-area`
    - Todos os textos por `data-texto-feedback="chave"`; nenhum texto escrito no HTML; nenhum campo de nome, e-mail, telefone, aceite nem botão "Ler os termos"
    - Não alterar o `h1`, o `h2` "Como foi a ajuda?", as estrelas, `#status-aval`, `#cuidados-resolvido`, os links finais, `#view-suporte`, `#view-chamado`, o cabeçalho, a barra de etapas nem o rodapé
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6, 2.1, 4.4, 7.4, 8.1, 12.10, 13.1, 14.2, 14.3_

- [x] 5. Estilos em `css/styles.css`
  - [x] 5.1 Acrescentar o token e o bloco "Comentário opcional (Tela_de_Resolvido)"
    - No `:root`, um token novo: `--campo-fundo-desabilitado: var(--creme)` (sem alterar as variáveis existentes)
    - Ao final do arquivo, depois do marcador das regras novas já usado pelo teste estático, acrescentar `.feedback` (largura máxima de 640 px, alinhado à esquerda, sem colunas), `.feedback__agradecimento` (fundo `--sucesso-fundo`, borda e ícone "✓" por pseudo-elemento com texto alternativo vazio; vazia não ocupa espaço) e `.campo textarea:disabled` / `[readonly]` (texto `--texto` sobre `--campo-fundo-desabilitado`); reaproveitar `.campo`, `.campo__rotulo`, `.campo__obrig`, `.campo__ajuda`, `.campo__erro`, `.msg-falha` e `.btn` sem editá-los
    - Só tokens semânticos, sem cor, raio, sombra nem fonte literal; sem transição nem animação; `font-size: 1rem` na textarea; espaçamento de pelo menos 8 px entre campo, botão e estrelas; foco visível não cortado por `overflow`
    - _Requirements: 1.1, 7.8, 12.1, 12.2, 12.3, 12.5, 12.6, 12.8_

  - [x] 5.2 Acrescentar o override do botão desabilitado só no bloco novo
    - Regra `.feedback .btn[disabled]` com `opacity: 1`, texto `--texto` sobre `--campo-fundo-desabilitado` e borda `--campo-borda`, sem editar a regra global `.btn[disabled]`
    - Garantir que o estado "Enviando" e o botão travado depois do envio mantêm contraste mínimo de 4,5:1
    - _Requirements: 7.2, 7.6, 12.6, 12.7_

- [x] 6. Lógica de tela em `js/app.js`
  - [x] 6.1 Estado, utilitários e ajustes pontuais
    - Acrescentar `const TRESFeedback = window.TRESFeedback || null;` e `state.feedback = TRESFeedback ? TRESFeedback.novoEstado(null) : null`
    - Acrescentar `comentario`, `texto` e `feedback` a `CHAVES_EXTRAS_PROIBIDAS` dos eventos de métrica
    - Em `mostrarView`, acrescentar `resolvido` à lista de exceções do foco na primeira rota, para o foco ir ao `h1` em até 300 ms em qualquer meio de navegação (nunca ao campo)
    - Extrair a escolha do `storage` (com o substituto que lança) para a função `obterStorage()`, usada também pelo chamado e pelo feedback, sem mudar o comportamento do chamado
    - _Requirements: 1.7, 11.3, 14.1, 14.4_

  - [x] 6.2 Estender `montarEstrelas` e zerar o estado ao escolher problema
    - Adicionar o 5º parâmetro opcional `aoEscolher(n)`, chamado depois de gravar o evento `avaliacao`; sem o parâmetro o comportamento fica idêntico ao atual (tela de problema resolvido grava `avaliacao` com `desfecho: 'resolvido'`, sem comentário nem indicação de comentário)
    - No clique de `cartaoProblema` (escolha de problema na lista), chamar `state.feedback = TRESFeedback.novoEstado(p.id)` (quando o módulo existe), descartando texto, chave e "já enviado" de uma jornada anterior
    - _Requirements: 3.1, 3.4, 3.5, 7.9, 11.8_

  - [x] 6.3 Implementar `aplicarTextosFeedback` e `renderFeedback` e ligar na rota `resolvido`
    - `aplicarTextosFeedback(raiz)` preenche `[data-texto-feedback]` com `D.FEEDBACK.textos[chave]` por `textContent`
    - `renderFeedback()`: se `!TRESFeedback || !TRESFeedback.textosValidos(D.FEEDBACK)` mantém o formulário `hidden` (sem erro técnico, estrelas, cuidados e links seguem funcionando); senão `state.feedback = aoExibir(...)`, mostra o formulário, aplica textos, repõe texto e contador (`formatarContador`), limpa erro e falha e aplica o estado `ocioso`, `enviando` ou `enviado`
    - Em `aoMudarRota` (view `resolvido`), depois de `montarEstrelas(...)` (com callback `aoEscolher` que guarda a nota em `state.feedback` por `escolherNota`) e `renderCuidados(...)`, chamar `renderFeedback()`; a nota é zerada a cada exibição; nenhuma outra rota chama `renderFeedback`
    - _Requirements: 1.1, 1.5, 1.8, 3.2, 3.3, 3.6, 4.5, 7.8, 13.3, 13.4, 14.3_

  - [x] 6.4 Implementar `iniciarFeedback`, contador e validação do campo
    - Ligar uma única vez `input`, `submit` e o clique do botão; no `input`, `editarTexto` + atualização do contador em até 100 ms, truncando em 500 (digitado ou colado) e mantendo o texto
    - `mostrarErroComentario` / `limparErroComentario`: mensagem visível abaixo do campo, `aria-invalid="true"` e id do erro em `aria-describedby` junto de aviso e contador; ao editar, remover erro, `aria-invalid` e a referência ao erro em até 200 ms, mantendo aviso e contador
    - Envio com comentário vazio ou só espaços: nada gravado nem enviado, foco no campo, anúncio de `anuncioErroVazio` em `#anuncio` em até 1 s, texto preservado; Enter no `textarea` só insere quebra de linha
    - Botão operável sem nota escolhida, sem mensagem que exija a nota
    - Implementar `definirEnviandoFeedback(bool)` (`aria-busy` no formulário, texto do botão "Enviando", botão `disabled`, campo `readonly`)
    - _Requirements: 3.6, 4.1, 4.2, 4.3, 4.4, 5.1, 5.3, 5.4, 5.5, 5.6, 5.7, 7.2, 12.4_

  - [x] 6.5 Implementar o envio: `pontoDeIntegracaoFeedback`, `aoEnviarFeedback` e `mostrarEnviado`
    - Criar o Ponto_de_Integracao_de_Feedback com `TRESFeedback.criarPontoDeIntegracao` e as dependências reais (`fetch`, `AbortController`, `setTimeout`, `clearTimeout`, `obterStorage()`, `D.FEEDBACK.config`)
    - `aoEnviarFeedback(ev)`: `prepararEnvio` com texto, nota de `state.feedback`, `problemaId` da rota, modelo escolhido (ou `null`) e `agora`; `'ocupado'` ignora o toque; marcar `estado = 'enviando'` antes do primeiro `await` (duplo toque gera no máximo um envio); chamar `enviar(payload)` e `concluirEnvio`
    - Sucesso: gravar um único evento `comentario` com `TRESFeedback.eventoComentario` (falha ao gravar métrica não altera a tela nem exibe erro), `mostrarEnviado` (campo e botão `disabled`, texto enviado visível, `#feedback-agradecimento` preenchido com o texto de `data.js` em até 300 ms, foco nele; mesmo texto em Modo_Prototipo e Modo_API, sem aviso de protótipo; sem chamar `anunciar()` em paralelo)
    - Sem registrar evento `avaliacao` no envio do comentário; sem `console.*`
    - _Requirements: 3.2, 3.3, 7.1, 7.3, 7.4, 7.5, 7.6, 7.7, 7.10, 11.1, 11.2, 11.7_

  - [x] 6.6 Implementar `mostrarFalhaFeedback`, retentativa e saída da rota durante o envio
    - Falha: bloco `role="alert"` com `tabindex="-1"` e o texto `falha` em `#feedback-falha-area`, foco no bloco, anúncio em até 1 s, campo e botão reabilitados, `aria-busy` removido, texto e chave preservados, nenhum evento `comentario`, sem agradecimento
    - Nova tentativa: remover o bloco de falha, validar o texto atual e reenviar com a mesma `chaveIdempotencia`; estrelas, "Cuidados com a sua máquina" e os links continuam funcionando
    - Se o consumidor sair da rota durante o envio: atualizar `state.feedback` apenas se a chave ainda for a da tentativa, gravar a métrica no sucesso e só mexer na tela se a rota ainda for `resolvido`
    - Confirmar que a Tela_de_Chamado e a Tela_de_Confirmacao não exibem o formulário nem enviam Feedback
    - _Requirements: 7.9, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 11.4, 14.3_

- [x] 7. Checkpoint - Telas integradas
  - Conferir pelo servidor de teste (sem deixar servidor aberto) que a Tela_de_Resolvido carrega sem erro de script e que o fluxo envia e agradece uma vez. Falhas esperadas de testes existentes (`textos-metricas.test.js` e `22-regressao-rotas`) são corrigidas nas tarefas 8.24 e 10.7. Pergunte ao usuário se houver dúvidas.

- [x] 8. Testes do núcleo em Node (somente desenvolvimento, fora do site)
  - [x]* 8.1 Acrescentar os geradores do feedback em `tests/geradores.js`
    - `comentarioBruto` (Unicode completo com `fc.string({ unit: 'binary' })`, emojis, acentos, quebras de linha, tabulações, aspas, `\`, `<`, `>`, `&`, e-mails e telefones no meio, espaços e quebras nas pontas, *surrogates* soltos), `comentarioValido` (1 a 500 caracteres após `trim`), `comentarioLongo` (mais de 500)
    - `payloadFeedback` (7 campos válidos), `listaDeFeedbacks` (0 a 120 itens, chaves distintas), `urlDeConfiguracao` (vazio, inválido, `ftp:`, `javascript:`, `http:` em outros hosts e locais, `https:`), `acaoDoFormulario` (editar, enviar, concluir com sucesso, concluir com falha, reexibir), `eventoComentario` somado ao `eventoMetrica` existente
    - Não alterar o contrato de `tests/falsos.js` nem criar `package.json` na raiz
    - _Requirements: 14.9_

  - [x]* 8.2 Escrever o teste de propriedade da normalização do comentário
    - **Property 1: Normalização do comentário**
    - Arquivo `tests/nucleo/feedback-texto.test.js`, carregando o núcleo com `require('../../js/feedback.js').criar(require('../../js/chamado.js'))`, `numRuns` mínimo 100, com o comentário `// Feature: resolved-feedback-comment, Property 1: Normalização do comentário`
    - **Validates: Requirements 2.5, 6.1, 6.2, 6.5**

  - [x]* 8.3 Escrever o teste de propriedade da validação do comentário
    - **Property 2: Validação do comentário**
    - **Validates: Requirements 5.2, 5.3**

  - [x]* 8.4 Escrever o teste de propriedade do limite e do contador
    - **Property 3: Limite e contador de caracteres**
    - **Validates: Requirements 4.1, 4.2, 4.3**

  - [x]* 8.5 Escrever o teste de propriedade do conteúdo indisponível
    - **Property 20: Conteúdo indisponível**
    - **Validates: Requirements 13.4**

  - [x]* 8.6 Escrever o teste de propriedade do conteúdo do Payload_do_Feedback
    - **Property 4: Conteúdo do Payload_do_Feedback**
    - Arquivo `tests/nucleo/feedback-payload.test.js`, incluindo entradas com campos extras de identificação (`nome`, `email`, `telefone`, `protocolo`, `problemaTitulo`)
    - **Validates: Requirements 2.4, 3.2, 3.3, 10.11, 10.12, 10.13**

  - [x]* 8.7 Escrever o teste de propriedade da ida e volta do Payload em JSON
    - **Property 5: Ida e volta do Payload em JSON**
    - Usar mais de 100 execuções e os geradores Unicode completos
    - **Validates: Requirements 10.14**

  - [x]* 8.8 Escrever o teste de propriedade da chave de idempotência
    - **Property 15: Chave de idempotência**
    - **Validates: Requirements 7.1, 10.15**

  - [x]* 8.9 Escrever o teste de propriedade da ida e volta pelo repositório
    - **Property 6: Ida e volta pelo Repositorio_de_Feedbacks**
    - Arquivo `tests/nucleo/feedback-repositorio.test.js`, com `storage` e `fetch` falsos de `tests/falsos.js` (o `fetch` nunca é chamado em Modo_Prototipo)
    - **Validates: Requirements 9.1, 9.4, 9.5**

  - [x]* 8.10 Escrever o teste de propriedade da leitura tolerante do repositório
    - **Property 7: Leitura tolerante do repositório**
    - **Validates: Requirements 9.6**

  - [x]* 8.11 Escrever o teste de propriedade do limite de 50 registros
    - **Property 8: Limite de 50 registros**
    - **Validates: Requirements 9.2**

  - [x]* 8.12 Escrever o teste de propriedade da idempotência por chave no repositório
    - **Property 9: Idempotência por chave no repositório**
    - **Validates: Requirements 9.8**

  - [x]* 8.13 Escrever o teste de propriedade do armazenamento isolado
    - **Property 11: Armazenamento isolado**
    - **Validates: Requirements 9.3, 10.8**

  - [x]* 8.14 Escrever o teste de propriedade da falha de armazenamento sem rastro
    - **Property 14: Falha de armazenamento não deixa rastro**
    - **Validates: Requirements 8.1, 9.7**

  - [x]* 8.15 Escrever o teste de propriedade da seleção do modo e do destino
    - **Property 10: Seleção do modo e do destino**
    - Arquivo `tests/nucleo/feedback-envio.test.js`, com `fetch` falso espião
    - **Validates: Requirements 10.4, 10.5, 10.6**

  - [x]* 8.16 Escrever o teste de propriedade da requisição em Modo_API
    - **Property 12: Requisição em Modo_API**
    - **Validates: Requirements 10.7**

  - [x]* 8.17 Escrever o teste de propriedade da classificação do resultado do envio
    - **Property 13: Classificação do resultado do envio**
    - **Validates: Requirements 10.9, 10.10**

  - [x]* 8.18 Escrever o teste de propriedade da máquina de estados do envio
    - **Property 16: Máquina de estados do envio**
    - Arquivo `tests/nucleo/feedback-estado.test.js`, teste baseado em modelo com o gerador `acaoDoFormulario`
    - **Validates: Requirements 4.5, 5.1, 5.6, 7.2, 7.3, 7.8, 7.10, 8.2, 8.4, 8.5, 8.6**

  - [x]* 8.19 Escrever o teste de propriedade do reinício por jornada
    - **Property 17: Reinício por jornada**
    - **Validates: Requirements 4.5, 7.9**

  - [x]* 8.20 Escrever o teste de propriedade do evento de métrica sem texto
    - **Property 18: Evento de métrica sem texto**
    - Arquivo `tests/nucleo/feedback-metricas.test.js`
    - **Validates: Requirements 11.1, 11.2**

  - [x]* 8.21 Escrever o teste de propriedade do resumo de métricas com comentários
    - **Property 19: Resumo de métricas com comentários**
    - **Validates: Requirements 11.5, 11.6**

  - [x]* 8.22 Escrever os testes de exemplo e de borda do núcleo (`tests/nucleo/feedback-exemplos.test.js`)
    - Códigos de validação (`vazio`, `tamanho`); `"  ótimo \n"` vira `"ótimo"`; comentário com 500 caracteres aceito e com 501 recusado
    - Tempo limite: `fetch` que nunca responde com temporizador falso → `'timeout'`; sem `AbortController` no ambiente usa a corrida com temporizador
    - Chave `tres-autoatendimento-feedbacks` com 3 ou 4 formatos de lixo conhecidos; sem `API_FEEDBACK_URL` mas com `API_CHAMADOS_URL` válida, o `fetch` falso nunca é chamado
    - _Requirements: 4.1, 5.2, 5.3, 9.6, 10.5, 10.6, 10.10_

  - [x]* 8.23 Escrever os testes de exemplo sobre `TRES_DATA.FEEDBACK` em `tests/dados.test.js`
    - `FEEDBACK.config.API_FEEDBACK_URL === ''` e `CHAMADO.config.API_CHAMADOS_URL === ''`; todas as chaves obrigatórias presentes; aviso de não identificação com 1 a 200 caracteres pedindo para não escrever nome, e-mail, telefone nem dados pessoais; nenhum texto com palavras vagas ("rapidamente", "adequado")
    - Marcação `PENDENTE` ou `ILUSTRATIVO` junto de `API_FEEDBACK_URL`, do tempo limite, da versão do contrato e do aviso; `FEEDBACK.textos` sem chave de aviso de protótipo; `TRES_DATA.CHAMADO` idêntico ao anterior
    - _Requirements: 2.3, 10.16, 13.2, 13.5, 13.6, 14.8_

  - [x]* 8.24 Atualizar `tests/nucleo/textos-metricas.test.js` para incluir `comentarios`
    - Os `deepEqual` que fixam o formato de `resumirEventos` (entrada inválida e exemplo com chamado) passam a incluir `comentarios`; a propriedade do resumo de métricas do chamado passa a incluir eventos `comentario` entre os ignorados
    - _Requirements: 11.5, 11.6, 14.9_

  - [x]* 8.25 Atualizar `tests/smoke.test.js` para o `feedback.js`
    - Carregar `feedback.js` com `criar(chamado)` e conferir a API pública (funções e constantes do design)
    - _Requirements: 10.1, 10.2_

- [x] 9. Checkpoint - Núcleo e testes
  - Garanta que `npm test` (dentro de `tests/`) passa, pergunte ao usuário se houver dúvidas.

- [x] 10. Testes de interface e verificação estática (Edge headless, cenários curtos)
  - [x]* 10.1 Estender `tests/ui/servidor-teste.js` e `tests/ui/cenarios.js` para o feedback
    - Nova opção `modoApiFeedback` (troca em memória de `API_FEEDBACK_URL`, com a mesma técnica de `API_CHAMADOS_URL`, sem escrever em `js/data.js`) e `configNumerica` aceitando `TIMEOUT_FEEDBACK_MS`
    - Nova rota `POST api/feedbacks` na API falsa com modos `sucesso` (201 com corpo vazio), `erro500` e `lento`, registrando as requisições e as `chaveIdempotencia` recebidas
    - `ctx.feedbacksLocais()` análogo a `ctx.chamadosLocais()`, lendo `tres-autoatendimento-feedbacks`; opção para entregar `data.js` sem uma chave de `FEEDBACK.textos`
    - _Requirements: 10.5, 10.7, 13.4_

  - [x]* 10.2 Estender `tests/estatico.js` (e `tests/estatico.test.js`) para o feedback
    - Incluir `js/feedback.js` nos testes de "sem `console.*`", "sem HTML dinâmico", "núcleo puro (sem DOM, `window`, armazenamento direto, `fetch` direto nem relógio)" e "sem `require(`, `import(` nem scripts de terceiros"
    - Teste novo: dentro de `#form-feedback` todo texto vem de `data-texto-feedback`, e todo `data-texto-feedback` aponta para chave existente em `FEEDBACK.textos`; nenhuma frase de `FEEDBACK.textos` escrita em `index.html`, `js/app.js`, `js/chamado.js` nem `js/feedback.js`
    - Conferir que o `h1`, o `h2` "Como foi a ajuda?" e os links finais da Tela_de_Resolvido mantêm os textos
    - CSS: o bloco novo fica depois do marcador das regras novas (sem transição, fonte do campo de 16 px, alvos de 44 px); acrescentar ao teste de contraste os pares novos (texto sobre `--campo-fundo-desabilitado`, texto sobre `--sucesso-fundo`) com mínimo de 4,5:1
    - _Requirements: 6.3, 6.4, 12.3, 12.6, 13.1, 14.2_

  - [x]* 10.3 Criar `tests/ui/cenarios/24-comentario-resolvido.test.js`: fluxos principais (Modo_Prototipo)
    - Fluxo só com comentário: chegar a `#/resolvido/ID`, escrever e enviar; agradecimento em `role="status"`, campo e botão desabilitados, foco no agradecimento, um registro com `nota: null`, evento `comentario`, `resumo().comentarios === 1`, nenhum evento `avaliacao`
    - Nota mais comentário: tocar a estrela 4 e enviar; registro com `nota: 4`; um só evento `avaliacao`. Só nota: nenhum registro novo e `comentarios === 0`
    - _Requirements: 3.1, 3.2, 3.3, 7.4, 7.6, 9.1, 11.1, 11.5, 11.8_

  - [x]* 10.4 Continuar `24-comentario-resolvido.test.js`: validação, contador e limite
    - Enviar vazio e só com espaços: mensagem, `aria-invalid`, `aria-describedby` com aviso, contador e erro, foco no campo, anúncio; editar remove o erro mantendo aviso e contador; Enter não envia
    - Digitar e colar acima de 500: "500 de 500 caracteres" e texto truncado
    - _Requirements: 4.2, 4.3, 5.3, 5.4, 5.5, 5.6, 5.7_

  - [x]* 10.5 Continuar `24-comentario-resolvido.test.js`: falha, estrutura e conteúdo indisponível
    - Falha de gravação local: bloco `role="alert"`, texto preservado, botão reabilitado, nenhuma métrica; reenviar com sucesso usando a mesma chave
    - Sem aviso de protótipo: agradecimento com o texto de `data.js` e nenhum elemento de aviso de protótipo
    - Conteúdo indisponível: `data.js` sem uma chave de `FEEDBACK.textos` → formulário omitido, estrelas e links funcionando
    - Estrutura: ordem estrelas, formulário, cuidados, links; um único campo editável; sem campos de identificação nem "Ler os termos"; `aria-describedby` do campo; foco no `h1` nos quatro meios de navegação (resposta "Sim", voltar, avançar e abertura direta da URL)
    - _Requirements: 1.1, 1.2, 1.7, 2.1, 7.5, 8.1, 8.2, 8.3, 8.4, 13.4_

  - [x]* 10.6 Criar `tests/ui/cenarios/25-comentario-api.test.js` (Modo_API)
    - Sucesso com 201 e corpo vazio: uma requisição `POST` com `Content-Type: application/json`, corpo com os 7 campos, nenhum registro em `tres-autoatendimento-feedbacks`, mesmo agradecimento
    - Falha 500, rede e tempo limite (`TIMEOUT_FEEDBACK_MS: 800`): bloco de falha, texto preservado; nova tentativa com a mesma `chaveIdempotencia`
    - Destino: com `API_CHAMADOS_URL` preenchida e `API_FEEDBACK_URL` vazia, nenhuma requisição a `api/chamados` nem a `api/feedbacks`; a API falsa não recebe nome, e-mail nem telefone digitados no formulário do chamado
    - _Requirements: 2.4, 10.5, 10.6, 10.7, 10.9, 10.10, 8.6_

  - [x]* 10.7 Atualizar `22-regressao-rotas.test.js`
    - O cenário de `#/resolvido/ID` confere a ordem estrelas, `#form-feedback`, `#cuidados-resolvido`, links, mantendo textos e destinos de sempre; `resumo()` passa a trazer `comentarios: 0`; o foco no `h1` ao abrir `#/resolvido/ID` direto passa a ser esperado
    - Cabeçalho, rodapé, barra de etapas (3 itens e etapa 3 atual) e as demais rotas continuam sem mudança
    - _Requirements: 12.11, 14.1, 14.2, 14.5, 14.9_

  - [x]* 10.8 Atualizar `18-estrelas.test.js`
    - O cenário do problema resolvido (nota 5) continua igual e ganha: nenhum registro em `tres-autoatendimento-feedbacks` e nenhum evento `comentario`; novo cenário: a nota escolhida acompanha o comentário e não cria segundo `avaliacao`; estrela tocada depois do envio não altera o feedback gravado
    - Manter a proteção do ajuste `gap: 0.5rem` das estrelas
    - _Requirements: 3.1, 3.3, 3.4, 11.8, 12.9_

  - [x]* 10.9 Atualizar `19-texto-literal.test.js`
    - Novo cenário: `<b>x</b>` e `<img src=x onerror=alert(1)>` no comentário aparecem como texto no campo travado e no armazenamento, e nenhum elemento é criado em `#view-resolvido`
    - _Requirements: 6.3, 6.4, 6.5_

  - [x]* 10.10 Atualizar `20-responsivo.test.js`
    - Novos cenários da Tela_de_Resolvido com o formulário (e depois do envio) em 360, 480, 768 e 1024 px: sem rolagem horizontal, alvos de 44 px, textarea com 16 px, espaçamento de 8 px, sem cortes; `medirLayout` aplicado a `#view-resolvido`; capturas só em pasta temporária
    - _Requirements: 12.1, 12.2, 12.3_

  - [x]* 10.11 Atualizar `21-movimento-reduzido.test.js`
    - Novo cenário: Tela_de_Resolvido com `prefers-reduced-motion: reduce`, sem transição, animação nem rolagem suave
    - _Requirements: 12.8_

  - [x]* 10.12 Atualizar `23-dados-pessoais.test.js`
    - Acrescentar a chave `tres-autoatendimento-feedbacks` à lista de chaves conhecidas; `exigirMetricasLimpas` passa a proibir também `comentario`, `texto` e `feedback` nos eventos
    - Novo cenário: dados digitados no formulário do chamado (sem enviar) não aparecem no feedback, no payload nem no evento `comentario`; o texto do comentário não aparece em `sessionStorage`, cookies, URL, console nem nas chaves de eventos e chamados
    - _Requirements: 2.4, 9.3, 11.2, 11.3_

  - [x]* 10.13 Atualizar `16-duplo-toque.test.js`
    - Novo cenário: dois cliques rápidos em "Enviar comentário" geram um registro (Modo_Prototipo) ou uma requisição (Modo_API)
    - _Requirements: 7.3_

  - [x]* 10.14 Atualizar `17-navegacao.test.js`
    - Novos cenários: voltar a `#/resolvido/ID` depois do envio mostra o estado "já enviado"; escolher um problema (mesmo o mesmo) zera o estado; sair sem enviar e voltar mostra o campo vazio; recarregar a página zera o estado
    - _Requirements: 4.5, 7.8, 7.9_

  - [x]* 10.15 Atualizar `15-modo-api.test.js`
    - Novo cenário: `API_CHAMADOS_URL` preenchida e `API_FEEDBACK_URL` vazia → Modo_Prototipo e nenhuma requisição ao endpoint de chamados
    - _Requirements: 10.5, 10.6_

  - [x]* 10.16 Acrescentar a seção do comentário em `tests/ui/roteiro-manual.md`
    - Checklist curto dos itens que a automação não cobre: leitor de tela real (NVDA, VoiceOver, TalkBack), incluindo a leitura dupla do agradecimento (região `role="status"` mais foco); celular físico; Firefox e Safari; sensação visual do bloco; revisão jurídica (LGPD) do aviso de não identificação
    - Os itens continuam "não verificados" até alguém executá-los; esta tarefa só escreve o roteiro
    - _Requirements: 7.4, 7.6, 7.7, 12.6_

- [x] 11. Checkpoint - Testes de interface
  - Rodar `node tests/ui/rodar.js` (uma única execução, sem nenhum outro processo de teste de interface em paralelo) e garantir que passa, pergunte ao usuário se houver dúvidas.

- [x] 12. Atualizar o `CONTEXTO-PROJETO.md`
  - [x] 12.1 Registrar a funcionalidade no contexto do projeto
    - Descrever o bloco de comentário opcional na Tela_de_Resolvido (sem rota nova), `js/feedback.js` (fábrica `criar(base)`), `TRES_DATA.FEEDBACK` (`API_FEEDBACK_URL`, `TIMEOUT_FEEDBACK_MS`, `VERSAO_CONTRATO_FEEDBACK`), a chave `tres-autoatendimento-feedbacks`, o evento `comentario` (sem o texto) e o campo `comentarios` em `TRESMetricas.resumo()`
    - Registrar a mudança deliberada do requisito 12.1 da spec `ticket-opening-screen` (Tela_de_Resolvido deixa de ser idêntica), a nova exceção de foco no `h1` e a lição do botão desabilitado
    - Pendências: contrato com o back end (URL por ambiente, autenticação, CORS, esquema do banco, resposta, chave repetida, limites, taxa, retenção), avaliação jurídica (LGPD) do texto livre e do aviso, leitura dupla do agradecimento com leitor de tela, itens não verificados (leitor de tela, celular, outros navegadores)
    - Registrar como rodar os testes (`npm test` em `tests/`, `node tests/ui/rodar.js` em série, `node --test` direto para paralelo)
    - _Requirements: 14.1, 14.9_

- [x] 13. Integração e verificação final
  - [x] 13.1 Conferir arquivos protegidos e escopo dos arquivos
    - Rodar `node tests/verificar-protegidos.js --conferir` e confirmar que nada em `material/`, em `img/*.png` originais e no `.glb` original mudou e que nada foi criado, movido nem excluído em `material/`
    - Confirmar que não existe `package.json` na raiz, que `js/vendor` não ganhou arquivos e que `API_FEEDBACK_URL` e `API_CHAMADOS_URL` continuam vazias
    - _Requirements: 14.6, 14.7, 14.8_

  - [x] 13.2 Conferir que nenhum texto de comentário vai para métricas nem para o console
    - Revisar `js/app.js`, `js/feedback.js` e `js/chamado.js`: nenhum `console.*`, nenhum `innerHTML`/`insertAdjacentHTML`/`outerHTML`/`document.write` com dado do consumidor, evento `comentario` só com `tipo`, `em`, `problema` e `modelo`, evento `avaliacao` sem indicação de comentário, e o texto do comentário só em `tres-autoatendimento-feedbacks` (Modo_Prototipo) ou no corpo da requisição (Modo_API)
    - Conferir que `TRESMetricas.resumo()` mantém `resolvidos`, `encaminhadosAoSuporte`, `deflexaoPercentual`, `porProblema` e `chamadosAbertos` inalterados e soma `comentarios`
    - _Requirements: 6.4, 9.3, 11.1, 11.2, 11.3, 11.8_

  - [x] 13.3 Rodar a suíte completa em série
    - Garantir que as tarefas de atualização dos testes existentes (8.24, 10.7 a 10.15) foram feitas; se alguma foi pulada por ser opcional, ajustar essas asserções antes de rodar
    - Rodar `npm test` dentro de `tests/` e, depois, `node tests/ui/rodar.js` (uma única execução por vez; NUNCA duas execuções de `rodar.js` ao mesmo tempo; para rodar em paralelo, usar `node --test` direto nos arquivos de `tests/ui/cenarios/`)
    - Rodar de novo `node tests/verificar-protegidos.js --conferir` e garantir que tudo passa, pergunte ao usuário se houver dúvidas
    - _Requirements: 14.9_

  - [x] 13.4 Limpar temporários
    - Encerrar servidores de teste e processos do Edge, apagar perfis temporários (`tres-ui-edge-*`), capturas e arquivos `tmp-*` que tenham sobrado, e garantir que `tests/node_modules` não é referenciado pelo site
    - Não deixar `rodar.js` nem `servidor-teste.js` em execução
    - _Requirements: 14.6_

## Notes

- Tarefas marcadas com `*` são opcionais (testes) e podem ser puladas para um MVP mais rápido; as tarefas de código, os checkpoints, a documentação e a verificação final não são opcionais. Atenção: pular 8.24 e 10.7 a 10.15 deixa testes existentes falhando (eles fixavam a Tela_de_Resolvido idêntica e o formato antigo de `resumirEventos`), então a tarefa 13.3 exige que essas asserções sejam ajustadas.
- Cada tarefa cita os requisitos específicos que cumpre; cada teste de propriedade cita o número da propriedade do design e o requisito que valida.
- Os testes de propriedade usam fast-check 4.10.2 (já fixado em `tests/package.json`), só em `tests/`, com no mínimo 100 execuções e o comentário `// Feature: resolved-feedback-comment, Property N: <título>`.
- Verificação com leitor de tela real (incluindo a leitura dupla do agradecimento), celular físico, Firefox, Safari e back end real fica fora da automação e continua não verificada até alguém executar o roteiro manual. Avaliação jurídica (LGPD) e contrato com o back end seguem `PENDENTE`.
- As tarefas 6.x alteram o mesmo arquivo (`js/app.js`) e as tarefas 3.x o mesmo arquivo (`js/feedback.js`); por isso são sequenciais no grafo de dependências. O mesmo vale para os cenários 10.3 a 10.5 (mesmo arquivo de teste) e para os arquivos de teste de propriedade agrupados por arquivo.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.1"] },
    { "id": 1, "tasks": ["2.2", "3.1", "4.1", "5.1"] },
    { "id": 2, "tasks": ["3.2", "4.2", "5.2"] },
    { "id": 3, "tasks": ["3.3"] },
    { "id": 4, "tasks": ["3.4"] },
    { "id": 5, "tasks": ["6.1", "8.1"] },
    { "id": 6, "tasks": ["6.2", "8.2", "8.6", "8.9", "8.15", "8.18", "8.20", "8.22", "8.23", "8.24", "8.25"] },
    { "id": 7, "tasks": ["6.3", "8.3", "8.7", "8.10", "8.16", "8.19", "8.21"] },
    { "id": 8, "tasks": ["6.4", "8.4", "8.8", "8.11", "8.17"] },
    { "id": 9, "tasks": ["6.5", "8.5", "8.12"] },
    { "id": 10, "tasks": ["6.6", "8.13"] },
    { "id": 11, "tasks": ["8.14", "10.1", "10.2"] },
    { "id": 12, "tasks": ["10.3", "10.6", "10.7", "10.8", "10.9", "10.10", "10.11", "10.12", "10.13", "10.14", "10.15", "10.16"] },
    { "id": 13, "tasks": ["10.4"] },
    { "id": 14, "tasks": ["10.5"] },
    { "id": 15, "tasks": ["12.1"] },
    { "id": 16, "tasks": ["13.1", "13.2"] },
    { "id": 17, "tasks": ["13.3"] },
    { "id": 18, "tasks": ["13.4"] }
  ]
}
```
