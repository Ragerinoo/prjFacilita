# Implementation Plan: Integração com a API da jornada (api-integration)

## Overview

O plano segue a ordem do design: primeiro a configuração e os textos em `js/data.js` (`TRES_DATA.API`), depois o núcleo sem DOM em `js/api.js` (cliente HTTP, ULID, erros, corpos, Gerente_de_Jornada), o HTML e o CSS, a lógica de tela em `js/app.js` e a API falsa dos testes de interface. Em seguida vêm os testes do núcleo em Node (fast-check só em `tests/`, fora do site), os cenários de interface no Edge headless, a atualização dos testes existentes que ficarem vermelhos, o `dev/servir-com-api.js` com a documentação, os testes estáticos, de fumaça e o roteiro manual, o `CONTEXTO-PROJETO.md` e a verificação final.

Cada tarefa é pequena e autocontida, para um subagente executar sozinho: ela diz quais arquivos mexer e o critério de pronto. A pasta com o repositório de referência do back end (somente leitura) é `C:\Users\labsfiap\AppData\Local\Temp\prjFacilita-ref`; ela serve só para conferir contratos e nunca é alterada.

Regras que valem para todas as tarefas:

- O site continua HTML, CSS e JS puros, sem build e sem pacotes na raiz. Nenhuma biblioteca, fonte ou script de terceiros novo em produção (`js/vendor` não ganha arquivos).
- `TRES_DATA.API.BASE_URL` fica **vazia** no repositório (Modo_Prototipo); `API_CHAMADOS_URL` e `API_FEEDBACK_URL` também continuam vazias. Com `BASE_URL` vazia, nenhuma requisição nova existe e todos os testes atuais passam.
- Nenhum texto novo da integração é escrito em `index.html`, `js/app.js` nem `js/api.js`; tudo vem de `TRES_DATA.API.textos` em `js/data.js` e entra na página por `data-texto-api` e `textContent`. Prazo, prioridade e próximo passo vêm da API e não são escritos no front. Os textos novos são `ILUSTRATIVO` e o que depende do back end é marcado `PENDENTE`.
- O código novo não usa `console.*` e não usa `innerHTML`, `insertAdjacentHTML`, `outerHTML` nem `document.write` com dados do consumidor, da API ou de `data.js`. Texto da API e do consumidor entra na página só por `textContent` ou `value`.
- `js/api.js` é um módulo UMD com fábrica `criar(base)` (em que `base` é o `TRESChamado`): não usa `require(`, `import(`, DOM, `window`, `localStorage`, `sessionStorage`, `fetch` direto nem relógio direto dentro das funções do núcleo (tudo entra por injeção). No navegador define `window.TRESApi = window.TRESChamado ? criar(window.TRESChamado) : null`.
- `jornada_id`, número do chamado, `dados_solicitados` e Evento_Ids ficam só em memória. Telefone, CEP, descrição e comentário nunca vão para a URL, cabeçalhos, console, `localStorage`, `sessionStorage`, cookies nem para o Registro_de_Metricas. A falha da API nunca mostra texto, código ou status do back end: só textos de `data.js`.
- Alterações em `js/chamado.js` e `js/feedback.js` só se forem aditivas e necessárias (o design não prevê nenhuma). Nenhuma regra CSS existente é editada; as regras novas ficam depois do marcador das regras novas já usado pelo teste estático.
- O repositório da API não é alterado. Não alterar `material/`, `img/*.png` originais nem o `.glb` original. Não criar, mover nem excluir arquivos em `material/`.
- Testes de interface: o Edge headless recarrega a aba depois de uns 5 s. Cada cenário é curto (menos de 4 s) e começa em carga nova. NUNCA rodar duas execuções de `node tests/ui/rodar.js` ao mesmo tempo (uma encerra o Edge da outra); para rodar cenários em paralelo, usar `node --test` direto nos arquivos de `tests/ui/cenarios/`.
- Subagentes não devem ler arquivos gigantes inteiros sem necessidade (`js/app.js`, `js/data.js`, `css/styles.css`, `tests/estatico.js`, `tests/ui/servidor-teste.js`, `tests/ui/cenarios.js`, `tests/geradores.js`): usar busca por texto e ler só os trechos necessários.
- A porta padrão do proxy de desenvolvimento é 8080 e NUNCA a 8000.
- Não fazer commits.

## Tasks

- [ ] 1. Linha de base e configuração em `js/data.js`
  - [ ] 1.1 Conferir a linha de base dos arquivos protegidos antes de qualquer alteração
    - Rodar `node tests/verificar-protegidos.js --conferir` e confirmar que passa; NÃO rodar `--gerar` (a linha de base `tests/baseline-protegidos.json` já existe e não deve ser regravada)
    - _Requirements: 16.6_

  - [ ] 1.2 Acrescentar o objeto `API` em `js/data.js` e exportá-lo em `window.TRES_DATA`
    - Ler só o trecho de `FEEDBACK` e do `window.TRES_DATA = {...}` final como modelo de estilo e de comentários
    - `BASE_URL: ''` com comentário sobre a precedência sobre `API_CHAMADOS_URL` e `API_FEEDBACK_URL`, a regra de validade (`https`, ou `http` em `localhost`/`127.0.0.1`; caminho relativo não vale) e `PENDENTE` do ambiente; `TIMEOUT_MS: 5000` (`ILUSTRATIVO / PENDENTE`); `ACOMPANHAMENTO_HABILITADO: false`
    - `MODELOS_API`: `{ passione: 'tres-passione', lov: null, modo: null, luna: null, touch: null }`, cada `null` com comentário `PENDENTE`
    - `textos` com todas as chaves do design (`tituloChamadoApi`, `introChamadoApi`, `rotuloPrioridade`, `rotuloPrazoApi`, `rotuloProximoPasso`, `rotuloCep`, `ajudaCep`, `erroCep`, `botaoEnviarContato`, `canaisConfirmacaoApi`, `anuncioRegistrandoResposta`, `falhaPergunta`, `botaoTentarDeNovo`, `botaoEnviarAvaliacao`, `botaoEnviandoAvaliacao`, `erroSemNota`, `anuncioErroSemNota`, `agradecimentoAvaliacao`, `falhaAvaliacao`), em português do Brasil, sem palavras vagas ("rapidamente", "adequado"), cada texto marcado `ILUSTRATIVO`
    - Manter intactas todas as chaves e valores atuais de `TRES_DATA`, inclusive `CHAMADO` e `FEEDBACK`
    - _Requirements: 1.1, 1.2, 1.7, 9.9, 12.2, 19.4_

- [ ] 2. Núcleo sem DOM em `js/api.js`
  - [ ] 2.1 Criar o módulo UMD com constantes, modo, ULID e erros
    - Criar `js/api.js` com `'use strict'`; em Node exporta `{ criar }`; no navegador define `window.TRESApi = window.TRESChamado ? criar(window.TRESChamado) : null`; sem `require(`, sem `console.*`
    - Constantes: `ALFABETO_ULID`, `LIMITES` (nota 1 a 5, comentário máx. 500, mensagem 1 a 2000, passo 1 a 10, telefone 10 a 11 dígitos, CEP 8 dígitos, `timeoutPadraoMs: 5000`), `TIPOS_ERRO`, `CHAVES_TEXTOS_OBRIGATORIAS`
    - Funções: `modoDaApi(config)` (usa `base.resolverModo(config.BASE_URL)`; config inválida = `'prototipo'`), `normalizarBaseUrl`, `timeoutDaApi`, `modeloApiDe(config, id)`, `gerarUlid(agora, sorteio)` (10 caracteres de tempo em base 32 e 16 de sorteio) e `ehUlid`, `novoErro(tipo, detalhes)` (Erro_Padronizado `{ tipo, status, codigo, campos }`) e `classificarErro`
    - Sorteio padrão: `crypto.getRandomValues` quando existir; senão `Math.random` (a função recebe o sorteio por parâmetro; o padrão é resolvido fora das funções puras)
    - _Requirements: 1.3, 1.4, 1.8, 1.9, 2.1, 3.7, 4.1, 4.2, 4.3, 4.4, 4.5, 5.3, 15.7_

  - [ ] 2.2 Implementar validações e montadores de corpo puros
    - `normalizarCep`, `validarCep` (`null` | `'vazio'` | `'formato'` | `'tamanho'`: só dígitos, espaços, parênteses e hífen, exatamente 8 dígitos), `telefoneParaApi(s)` (só dígitos, 10 ou 11, via `base.normalizarTelefone`)
    - `prepararAvaliacao({ nota, texto })` (`{ ok:false, codigo:'nota'|'tamanho' }` ou `{ ok:true, nota, comentario }` com `comentario` ausente quando vazio; texto normalizado por `base.normalizarTexto` ou equivalente já exportado, conferindo o nome no `js/chamado.js`), `filtrarDadosSolicitados`, `textosValidos(dadosApi)`
    - `montarCorpoJornada`, `montarCorpoModelo`, `montarCorpoEvento` (só `tipo`, `problema_id`, `passo` quando houver, `ocorrido_em` por `base.formatarIsoComFuso`, `evento_id`), `montarCorpoResolucao`, `montarCorpoAvaliacao`, `montarCorpoContato` (`consentimento: true`, só campos preenchidos), `montarCorpoMensagem`; nunca `null` nem `undefined` em campo opcional
    - _Requirements: 4.6, 4.7, 5.3, 6.4, 6.10, 8.10, 9.4, 9.5, 10.2, 10.3, 12.4, 12.5_

  - [ ] 2.3 Implementar o Cliente_API (`criarApi`)
    - `criarApi(deps)` devolve `null` em Modo_Prototipo; senão `{ criarJornada, associarModelo, registrarEvento, registrarResolucao, registrarAvaliacao, obterChamado, enviarContato, enviarMensagem }`, com métodos e caminhos exatos da tabela do design e nenhuma outra rota
    - Uma função interna de requisição: URL = BASE_URL normalizada + caminho com `encodeURIComponent` em todo segmento dinâmico; cabeçalhos `Accept`, `Content-Type` (se houver corpo), `X-Requested-With: tres-portal` (não `GET`), `Idempotency-Key` (se houver chave); `credentials: 'same-origin'`, `cache: 'no-store'`, `referrerPolicy: 'no-referrer'`; nenhum cabeçalho de autorização, cookie, token nem `x-origem-cloudfront`
    - Tempo limite por `AbortController` ou por `Promise.race` com temporizador (sem `AbortController`); `clearTimeout` sempre; 204 resolve sem valor; erros padronizados (`timeout`, `rede`, `http` com `status`, `codigo` e `campos` válidos, `resposta` para JSON inválido ou fora da forma esperada); o erro nunca leva a mensagem nem o corpo bruto da API; nenhuma outra exceção escapa
    - Validar a forma de cada resposta como no design (`jornada_id` em texto; `registrado` e `registrada` booleanos; `chamado.numero` em texto não vazio de até 64 caracteres com letras, dígitos, hífen e sublinhado; `prazo`, `prioridade_rotulo` e `proximo_passo` em texto ou ausentes; `dados_solicitados` como lista filtrada)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8, 8.9, 15.5, 15.7_

  - [ ] 2.4 Implementar o Gerente_de_Jornada: criação, modelo, eventos do guia e recuperação de 409
    - `criarGerente({ api, config, agora, sorteio })` com o estado interno do design (somente memória): `definirModelo`, `garantir` (compartilha a criação em andamento; chave de criação reaproveitada até dar certo; falha devolve `null` sem rejeitar), `selecionarProblema`, `mostrarPasso`, `concluirPasso`, `descartar`, sincronização de modelo (`PUT` quando muda; descarta a jornada se o modelo mapeado vira `null`; nenhuma requisição se igual)
    - Eventos em fila serial, "dispare e esqueça", sem rejeitar, uma vez por combinação jornada/tipo/problema/passo, com validação (`passo` de 1 a 10; `problema_id` inteiro maior ou igual a 1); em 409: descartar, criar jornada nova, enviar `selecionado` do problema atual (quando o evento original não é esse) e depois o evento original com o mesmo Evento_Id, sem nova tentativa
    - Escolha de problema depois de jornada encerrada cria jornada nova; sem encerramento reaproveita a mesma; trocar de problema descarta Chamado_API e estado de envio de outro problema
    - _Requirements: 5.1, 5.2, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 8.8, 15.4_

  - [ ] 2.5 Implementar no Gerente: `resolver`, `aguardarResolucao` e `chamado`
    - `resolver({ resolvido, problemaId })` nunca rejeita (`{ ok:true, resultado }` ou `{ ok:false, erro }`); garante a jornada; Evento_Id reutilizado para a mesma jornada, mesmo problema e mesma resposta (e novo em outro caso, inclusive depois de 409); `true` ou 409 marca a jornada como encerrada; `false` válido guarda em memória `numero`, `prazo`, `prioridadeRotulo`, `proximoPasso`, `classificacao` e `dadosSolicitados` filtrados; resposta `false` sem `numero` válido vira falha `resposta`; 409 descarta a jornada
    - `aguardarResolucao()` (sempre resolve) e `chamado(problemaId)` (Chamado_API em memória do problema, ou `null`); no máximo uma resolução em andamento por vez
    - _Requirements: 4.8, 7.1, 7.3, 7.4, 7.5, 8.1, 8.2, 8.4, 8.5, 8.6, 8.7, 8.9, 8.10_

  - [ ] 2.6 Implementar no Gerente: `enviarDadosDoChamado`
    - `enviarDadosDoChamado({ telefone, cep, texto })` devolve `{ ok:true }` ou `{ ok:false, etapa:'contato'|'mensagem', erro }`, nunca rejeita; com `dadosSolicitados` não vazio envia primeiro o contato (`consentimento: true`, só campos solicitados e preenchidos, com dígitos) e depois a mensagem; com lista vazia envia só a mensagem
    - Falha parcial: contato aceito com os mesmos valores nunca é reenviado; falha no contato impede a mensagem; Evento_Id do contato reutilizado com os mesmos valores; Evento_Id da mensagem reutilizado com o mesmo texto normalizado e novo quando o texto muda; mensagem aceita com 201, ou 200 e `registrada: false`
    - _Requirements: 4.8, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_

  - [ ] 2.7 Implementar no Gerente: `avaliar`, `estado`, `reiniciar` e fechar a API pública
    - `avaliar({ nota, comentario })` nunca rejeita: aguarda a resolução pendente, tenta criar a jornada se não há ativa (falha se não conseguir), Evento_Id reutilizado para mesma jornada/nota/comentário e novo em qualquer diferença; `registrada: true` (201) e `registrada: false` (200) contam como aceito
    - `estado()` devolve um instantâneo sem dados pessoais (sem telefone, CEP, texto, nome nem e-mail); `reiniciar()`; conferir que a API exportada contém todas as funções e constantes do design
    - _Requirements: 4.8, 12.8, 12.9, 12.10, 13.1, 13.2, 13.3, 13.4, 15.4_

- [ ] 3. Estrutura HTML e estilos
  - [ ] 3.1 Atualizar `index.html`
    - Incluir `<script src="js/api.js"></script>` entre `js/feedback.js` e `js/app.js`
    - `#view-confirma`: `<div id="confirma-falha-area"></div>` depois do bloco `.confirma`
    - `#view-suporte`: `<p id="chamado-prioridade-resumo" class="envio__prazo" hidden></p>` ao lado de `#chamado-prazo-resumo`; novo `div.campo[data-campo="cep"]` (`hidden`) depois do campo telefone, com `label for="c-cep"` (texto por `data-texto-api="rotuloCep"`), `input#c-cep` (`name="cep"`, `type="text"`, `inputmode="numeric"`, `maxlength="9"`, `autocomplete="postal-code"`, `aria-describedby="c-cep-ajuda"`), `p#c-cep-ajuda.campo__ajuda` e `p#c-cep-erro.campo__erro` (`hidden`); atributo `data-so-prototipo` nos campos nome e e-mail
    - `#view-chamado`: ids `chamado-linha-email`, `<p id="chamado-prioridade" hidden>` e `<p id="chamado-proximo-passo" hidden>` dentro de `.retorno`, com rótulos por `data-texto-api`
    - `#view-resolvido`: `<p class="campo__erro" id="nota-erro" hidden></p>` logo depois de `#status-aval`; `#estrelas` ganha `tabindex="-1"`
    - Nenhum texto escrito no HTML; nenhuma mudança em `h1`, cabeçalho, barra de etapas, rodapé nem textos existentes; Modo_Prototipo continua visualmente idêntico
    - _Requirements: 9.1, 9.3, 11.2, 12.3, 15.1, 16.1, 16.2_

  - [ ] 3.2 Acrescentar as regras novas em `css/styles.css`
    - Ler só o final do arquivo e o marcador das regras novas; acrescentar depois dele (sem editar regra existente, sem transição nem animação, só tokens semânticos, sem cor literal): `.campo[hidden]`, `.aceite[hidden]`, `.envio__prazo[hidden]`, `.retorno [hidden]` com `display: none`; `#c-cep` com `font-size: 1rem` e alvo de 44 px; `.estrelas--travada .estrela { cursor: default; }`; texto de estado das estrelas com contraste mínimo de 4,5:1
    - Reaproveitar `.msg-falha`, `.btn` e `.campo__erro` sem editá-los
    - _Requirements: 16.4, 9.1_

- [ ] 4. Lógica de tela em `js/app.js`
  - [ ] 4.1 Inicialização, gerente e eventos do guia
    - Buscar por texto os pontos de `iniciarModelos`, `cartaoProblema`, `renderSolucao` e `iniciarSolucao`; não ler o arquivo inteiro
    - Acrescentar `const TRESApi = window.TRESApi || null;`, `let gerente = null;` e `obterGerente()` (cria `TRESApi.criarApi({...})` e `TRESApi.criarGerente(...)` com as dependências reais só quando `modoDaApi(D.API) === 'api'` e `TRESApi.textosValidos(D.API)`; senão devolve `null` e o app fica em Modo_Prototipo; `window.TRESApi` ausente também vira Modo_Prototipo sem erro)
    - Preencher `[data-texto-api]` por `textContent` com `D.API.textos`; acrescentar `jornada`, `jornadaId`, `eventoId` e `evento_id` a `CHAVES_EXTRAS_PROIBIDAS` dos eventos de métrica
    - Chamar `gerente.definirModelo(...)` ao escolher modelo (e `null` em "Continuar sem escolher"), `gerente.selecionarProblema(p.id)` ao escolher problema, `gerente.mostrarPasso(...)` em `renderSolucao` e `gerente.concluirPasso(...)` em "Próximo passo" e "Terminei os passos"; tudo sem `await`, sem erro na tela, sem foco nem anúncio
    - Tudo guardado por `if (gerente)`; em Modo_Prototipo o comportamento e as chamadas ficam idênticos
    - _Requirements: 1.4, 1.5, 1.6, 5.1, 5.2, 5.7, 6.1, 6.2, 6.3, 6.5, 14.1, 15.1, 15.8, 16.1_

  - [ ] 4.2 "Sim, resolvi" e "Não, ainda não" na Tela_de_Pergunta_Final
    - "Sim": registrar o evento local `resolvido`, navegar para `#/resolvido/ID` sem esperar e chamar `gerente.resolver({ resolvido: true, problemaId })` sem `await`; falha da resolução não mostra nada
    - `aoNaoEncerrou()` (novo): registrar o evento local `suporte`, desabilitar os botões, `aria-busy="true"`, anunciar `anuncioRegistrandoResposta`, `await gerente.resolver({ resolvido: false, ... })`; sucesso navega para `#/suporte/ID`; já existindo Chamado_API do mesmo problema, navega direto sem nova requisição; no máximo uma requisição em andamento
    - `mostrarFalhaPergunta()`: bloco `role="alert"` com `tabindex="-1"` em `#confirma-falha-area` com o texto `falhaPergunta`, os contatos diretos (`D.CONTATO` e `CHAMADO.textos.falhaAlternativa`, links `tel:` e `mailto:`) e o botão "Tentar de novo", foco no bloco, anúncio em até 1 s, botões reabilitados e `aria-busy` removido; nova tentativa reusa o Evento_Id (e um novo após 409); em Modo_Prototipo o fluxo atual não muda
    - _Requirements: 7.1, 7.2, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 14.1, 15.6_

  - [ ] 4.3 Tela_de_Chamado em Modo_API: formulário e guarda de rota
    - `aplicarModoApiNoFormulario()` (novo): ocultar por `hidden` os campos `[data-so-prototipo]` (nome e e-mail); mostrar telefone e CEP conforme `dadosSolicitados`; ocultar aceite e "Ler os termos" quando `dadosSolicitados` está vazio; trocar título, introdução e botão por `API.textos`; mostrar prioridade (`prioridade_rotulo`) e `prazo` da API no lugar da frase ilustrativa, por `textContent`
    - `camposAtivos()` no lugar da lista fixa `CAMPOS` quando em Modo_API (sem `nome` e `email`, com `cep` quando pedido, `telefone` só quando pedido); CEP validado por `TRESApi.validarCep` com `erroCep` e `aria-describedby`/`aria-invalid` como os outros campos; descrição mantém 10 a 500 caracteres e contador
    - Guarda em `aoMudarRota`: `#/suporte/ID` em Modo_API sem Chamado_API em memória faz `location.replace('#/confirma/ID')`; em Modo_Prototipo o formulário, os textos, as validações e o campo CEP oculto ficam como hoje
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.6, 9.7, 9.8, 9.9, 9.10, 9.11_

  - [ ] 4.4 Envio do formulário do chamado em Modo_API
    - `aoEnviarApi()` (novo, chamado por `aoEnviar` quando há gerente): validar os campos ativos, mudar para "enviando" antes do primeiro `await`, desabilitar o botão e marcar `aria-busy`, chamar `gerente.enviarDadosDoChamado({ telefone, cep, texto })` com telefone e CEP só em dígitos
    - Falha: reutilizar `mostrarFalha()` existente (mesmo bloco, mesmos contatos, valores preservados, formulário reabilitado); 422 com `campos` que apontam `telefone`, `cep` ou `consentimento`: erro de validação padrão do campo (texto de `data.js`) e foco no primeiro campo com erro; qualquer outra falha usa a mensagem única de `data.js`
    - `concluirSucessoApi()` (novo): preencher `sessao.aberto` com `{ problemaId, protocolo: numero, modo: 'api', telefone, email: null, prazo, prioridadeRotulo, proximoPasso }`, gravar o evento local `chamado` com `protocolo` igual ao número da API e `modo: 'api'` e fazer `location.replace('#/chamado/ID')`; nada de telefone, CEP ou descrição na URL, no console, em storage ou nas métricas
    - _Requirements: 10.1, 10.4, 10.5, 10.6, 10.8, 10.9, 10.10, 14.2, 15.3_

  - [ ] 4.5 Tela_de_Confirmacao e estrelas em Modo_API
    - `renderConfirmacao`: em Modo_API mostrar o `numero`, `prioridade_rotulo`, `prazo` e `proximo_passo` da API como texto literal (ocultar o elemento de valor ausente ou vazio), o telefone como WhatsApp (`canaisConfirmacaoApi`), manter título de sucesso e contatos diretos; ocultar frase de prazo ilustrativo, aviso de protótipo e linha do e-mail; nunca exibir `undefined`, `null` nem `[object Object]`
    - `montarEstrelasApi` (novo): o toque envia na hora `gerente.avaliar({ nota })` sem comentário; sucesso trava as estrelas mostrando a nota enviada (`aria-disabled`/`disabled`), agradecimento em `role="status"` e anúncio; falha mostra mensagem visível (`falhaAvaliacao`) e mantém as estrelas habilitadas com o mesmo Evento_Id para a mesma nota; novos toques são ignorados durante o envio; o evento local `avaliacao` (com `desfecho: 'chamado'`) só é gravado depois de `registrada: true`
    - Em Modo_Prototipo continua `montarEstrelas` com `avaliacao` gravada ao toque
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 13.1, 13.2, 13.3, 13.4, 13.5, 14.3_

  - [ ] 4.6 Avaliação única na Tela_de_Resolvido em Modo_API
    - `renderAvaliacaoApi()` (novo) no lugar de `montarEstrelas` + `renderFeedback()` quando há gerente: estrelas só marcam a nota (`aria-pressed`), sem requisição nem evento local; comentário opcional (até 500 caracteres, contador e aviso de não identificação, reaproveitando `state.feedback`, `TRESFeedback.aoExibir`, `editarTexto` e `escolherNota`); botão com `botaoEnviarAvaliacao`
    - `aoEnviarAvaliacao()` (novo): sem nota, nada enviado, mensagem visível em `#nota-erro`, foco em `#estrelas`, anúncio em até 1 s; comentário normalizado com mais de 500 caracteres, nada enviado e erro de tamanho; enviar `gerente.avaliar({ nota, comentario })` com `comentario` só quando não vazio; durante o envio `aria-busy`, botão e estrelas desabilitados e novas ativações ignoradas; sucesso mostra o mesmo agradecimento em `role="status"`, desabilita nota, comentário e botão e move o foco para o agradecimento; falha mostra bloco `role="alert"` preservando nota e texto e reusando o Evento_Id
    - Depois do envio aceito, voltar a `#/resolvido/ID` na mesma jornada mostra o estado "já enviado"; os eventos locais `avaliacao` e `comentario` (sem texto, sem nota) só são gravados depois de `registrada: true`; em Modo_Prototipo a tela continua exatamente como está
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10, 12.11, 14.3_

  - [ ]* 4.7 Acompanhamento do chamado (opcional, fora do núcleo)
    - Só com `D.API.ACOMPANHAMENTO_HABILITADO === true` e Modo_API: rota `#/acompanhar/NUMERO` que consulta `gerente`/`api.obterChamado` e exibe status, prioridade, `prazo`/agendamento quando houver e a lista de mensagens com autor e data, tudo por `textContent`; permite enviar resposta de 1 a 2000 caracteres com Evento_Id reutilizado na retentativa; 404 ou falha mostra mensagem de `data.js` com os contatos diretos
    - Acrescentar em `data.js` os textos próprios do acompanhamento (`ILUSTRATIVO`), a `section` em `index.html` e as regras novas em `css/styles.css`; com a flag `false` (padrão) a rota não é registrada e volta a `#/` como rota desconhecida
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5_

- [ ] 5. Checkpoint - Telas integradas
  - Conferir pelo servidor de teste (sem deixar servidor aberto) que, com `BASE_URL` vazia, o site carrega sem erro de script e a jornada em Modo_Prototipo segue igual. Falhas esperadas de testes existentes (ordem dos scripts em `tests/estatico.test.js`) são corrigidas na tarefa 9.1. Pergunte ao usuário se houver dúvidas.

- [ ] 6. API falsa e opções dos cenários de interface
  - [ ]* 6.1 Implementar as rotas `/api/pub/...` em `tests/ui/servidor-teste.js`
    - Ler só os trechos necessários (rota `api/chamados`, troca em memória de `js/data.js`); acrescentar as rotas sob `<sessão>/api/pub/...` com estado por sessão e os contratos da tabela do design: `POST /jornadas` (201, mesma `Idempotency-Key` = 200 com a mesma jornada), `PUT /jornadas/{id}/modelo`, `POST /eventos` (repetido = 200 `registrado: false`), `POST /resolucao` (`true` encerra; `false` devolve chamado com `numero 'TRES-...'`, `prioridade_rotulo`, `prazo`, `proximo_passo`, `classificacao`, `dados_solicitados`), `POST /avaliacao` (2ª = 200 `registrada: false`), `POST /chamados/{n}/contato` (telefone 10/11 dígitos, CEP 8, `consentimento === true`), `POST /chamados/{n}/mensagens` (201; mesma chave = 200 `registrada: false`), e `GET /chamados/{n}` mínimo para o acompanhamento opcional
    - Modos de falha por rota (`sucesso`, `erro500`, `conflito409`, `lento`, `sem-resposta`, `corpo-invalido`; um modo ou lista de modos consumidos em ordem), `prioridade: 'P1'|'P2'|'P3'` (muda prioridade, prazo e `dados_solicitados`) e `atraso`; registro de método, rota, `Idempotency-Key`, `X-Requested-With`, `Content-Type` e corpo, só para o teste
    - Nova opção de sessão `modoApiPub` que troca `BASE_URL: ''` em memória por `http://127.0.0.1:<porta>/__t/<id>/api/pub` (sem escrever em `js/data.js`), independente de `modoApi` e `modoApiFeedback`
    - _Requirements: 18.2_

  - [ ]* 6.2 Expor `ctx.apiPub` e as opções em `tests/ui/cenarios.js`
    - Ler só o trecho que monta o contexto do cenário; acrescentar as opções `modoApiPub` e `apiPub: { falhas, prioridade, atraso }` e o objeto `ctx.apiPub` com `requisicoes(rota?)`, `cabecalhos(rota?)`, `definirApi(cfg)` e `baseUrl`, mais `ctx.jornadaApi()` para ler o estado da API falsa; os cenários atuais não mudam
    - _Requirements: 18.2, 18.3_

- [ ] 7. Testes do núcleo em Node (somente desenvolvimento, fora do site)
  - [ ]* 7.1 Acrescentar geradores em `tests/geradores.js` e a API falsa em `tests/falsos.js`
    - Geradores: `baseUrlBruta`, `timeoutBruto`, `mapaModelos`, `instanteMs`, `sequenciaSorteio`, `segmentoDinamico`, `corpoErroHttp`, `respostaInesperada`, `dadosSolicitadosBrutos`, `telefoneBruto`, `cepBruto`, `notaBruta`, `acaoDoGerente`, `falhaDeRede`, `caminhoDeRequisicao`, `hostEPorta`
    - `tests/falsos.js` ganha um `fetch` falso de API que implementa em memória os contratos da API falsa (sem rede) e registra requisições; não alterar o contrato dos falsos existentes nem criar `package.json` na raiz
    - _Requirements: 18.1_

  - [ ]* 7.2 Escrever o teste de propriedade do modo e da normalização da configuração
    - **Property 1: Modo e normalização da configuração**
    - Arquivo `tests/nucleo/api-config.test.js`, carregando o núcleo com `require('../../js/api.js').criar(require('../../js/chamado.js'))`, `numRuns` mínimo 100, com o comentário `// Feature: api-integration, Property 1: Modo e normalização da configuração`
    - **Validates: Requirements 1.3, 1.4, 1.8, 1.9**

  - [ ]* 7.3 Escrever o teste de propriedade do corpo da jornada e do mapeamento de modelo
    - **Property 2: Corpo da jornada e mapeamento de modelo**
    - Arquivo `tests/nucleo/api-config.test.js` (depois da propriedade 1)
    - **Validates: Requirements 5.3**

  - [ ]* 7.4 Escrever o teste de propriedade do ULID
    - **Property 3: ULID: formato, ordem e determinismo**
    - Arquivo `tests/nucleo/api-ulid.test.js`
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**

  - [ ]* 7.5 Escrever o teste de propriedade da requisição do cliente
    - **Property 4: Requisição do cliente**
    - Arquivo `tests/nucleo/api-cliente-req.test.js`, com `fetch` falso espião e as 8 funções
    - **Validates: Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.10, 4.6, 4.7**

  - [ ]* 7.6 Escrever o teste de propriedade dos erros de transporte e do tempo limite
    - **Property 5: Erros de transporte e tempo limite**
    - Arquivo `tests/nucleo/api-cliente-req.test.js` (depois da propriedade 4), com temporizador falso, com e sem `AbortController`
    - **Validates: Requirements 2.8, 3.1, 3.2**

  - [ ]* 7.7 Escrever o teste de propriedade do erro HTTP padronizado
    - **Property 6: Erro HTTP padronizado sem texto do back end**
    - Arquivo `tests/nucleo/api-cliente-erro.test.js`
    - **Validates: Requirements 3.3, 3.4, 3.6, 3.8**

  - [ ]* 7.8 Escrever o teste de propriedade da resposta inesperada
    - **Property 7: Resposta inesperada**
    - Arquivo `tests/nucleo/api-cliente-erro.test.js` (depois da propriedade 6)
    - **Validates: Requirements 3.5, 8.9, 15.5**

  - [ ]* 7.9 Escrever o teste de propriedade da classificação de erro
    - **Property 8: Classificação de erro**
    - Arquivo `tests/nucleo/api-cliente-erro.test.js` (depois da propriedade 7)
    - **Validates: Requirements 3.7**

  - [ ]* 7.10 Escrever o teste de propriedade da validação de CEP e telefone
    - **Property 9: Validação e normalização de CEP e telefone**
    - Arquivo `tests/nucleo/api-validacao.test.js`
    - **Validates: Requirements 9.4, 9.5**

  - [ ]* 7.11 Escrever o teste de propriedade da preparação da avaliação
    - **Property 10: Preparação da avaliação**
    - Arquivo `tests/nucleo/api-validacao.test.js` (depois da propriedade 9)
    - **Validates: Requirements 12.4, 12.5**

  - [ ]* 7.12 Escrever o teste de propriedade do filtro de Dados_Solicitados
    - **Property 11: Filtro de Dados_Solicitados**
    - Arquivo `tests/nucleo/api-filtros.test.js`
    - **Validates: Requirements 8.10**

  - [ ]* 7.13 Escrever o teste de propriedade da criação da jornada sob demanda
    - **Property 12: Criação da jornada sob demanda e sem duplicidade**
    - Arquivo `tests/nucleo/api-jornada.test.js`, com a API falsa de `tests/falsos.js` e `Promise.all` de várias necessidades simultâneas
    - **Validates: Requirements 5.1, 5.2, 5.4, 5.6**

  - [ ]* 7.14 Escrever o teste de propriedade do ciclo de vida do modelo e da jornada
    - **Property 13: Ciclo de vida do modelo e da jornada**
    - Arquivo `tests/nucleo/api-jornada.test.js` (depois da propriedade 12), teste baseado em modelo com o gerador `acaoDoGerente`
    - **Validates: Requirements 5.7, 5.8, 5.9, 5.10**

  - [ ]* 7.15 Escrever o teste de propriedade dos eventos do guia
    - **Property 14: Eventos do guia**
    - Arquivo `tests/nucleo/api-eventos.test.js`
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4, 6.6, 6.7, 6.9, 6.10**

  - [ ]* 7.16 Escrever o teste de propriedade da recuperação de 409 em evento
    - **Property 15: Recuperação de 409 em evento**
    - Arquivo `tests/nucleo/api-eventos.test.js` (depois da propriedade 14)
    - **Validates: Requirements 6.8**

  - [ ]* 7.17 Escrever o teste de propriedade da resolução e do Evento_Id
    - **Property 16: Resolução e reaproveitamento do Evento_Id**
    - Arquivo `tests/nucleo/api-resolucao.test.js`
    - **Validates: Requirements 4.8, 7.3, 7.4, 7.5, 8.2, 8.4, 8.5**

  - [ ]* 7.18 Escrever o teste de propriedade do envio do chamado sem duplicar
    - **Property 17: Envio do chamado sem duplicar o que a API já aceitou**
    - Arquivo `tests/nucleo/api-resolucao.test.js` (depois da propriedade 16)
    - **Validates: Requirements 10.2, 10.3, 10.5, 10.6, 10.7**

  - [ ]* 7.19 Escrever o teste de propriedade da avaliação única
    - **Property 18: Avaliação única e reaproveitamento do Evento_Id**
    - Arquivo `tests/nucleo/api-avaliacao.test.js`
    - **Validates: Requirements 4.8, 12.8, 12.9, 12.10, 13.3**

  - [ ]* 7.20 Escrever o teste de propriedade do estado em memória sem dados pessoais
    - **Property 19: Estado em memória sem dados pessoais**
    - Arquivo `tests/nucleo/api-avaliacao.test.js` (depois da propriedade 18)
    - **Validates: Requirements 14.3, 14.4, 15.3, 15.4**

  - [ ]* 7.21 Escrever o teste de propriedade dos textos obrigatórios
    - **Property 20: Textos obrigatórios do Modo_API**
    - Arquivo `tests/nucleo/api-filtros.test.js` (depois da propriedade 11)
    - **Validates: Requirements 9.9, 19.4**

  - [ ]* 7.22 Escrever os testes de exemplo e de contrato do núcleo (`tests/nucleo/api-exemplos.test.js`)
    - Rota, método, corpo e cabeçalhos exatos de cada uma das 8 funções com valores fixos; 204 resolve sem valor; sem `AbortController` usa a corrida com temporizador; `BASE_URL` com barras finais; `registrada: false` aceito; nenhuma outra rota é chamada (compara com `ROTAS`); promessas do gerente nunca rejeitam
    - _Requirements: 2.8, 2.9, 2.10, 3.8, 6.5, 18.1_

- [ ] 8. Cenários de interface no Edge headless (cenários curtos, com a API falsa)
  - [ ]* 8.1 Criar `tests/ui/cenarios/26-api-jornada.test.js`
    - Com `modoApiPub: true`: a jornada só é criada ao escolher o problema (nenhuma requisição ao carregar); eventos `selecionado`, `exibido` e `concluido` na ordem, sem erro nem foco na tela; "Sim" navega na hora para `#/resolvido/ID` e a resolução `true` chega à API; falha da API na jornada não bloqueia o guia; corpos dos eventos sem dados pessoais
    - _Requirements: 5.1, 5.2, 6.1, 6.2, 6.3, 6.5, 7.1, 7.2, 15.3_

  - [ ]* 8.2 Criar `tests/ui/cenarios/27-api-chamado.test.js`
    - "Não, ainda não" cria o chamado e leva ao formulário; prioridades P1 (só telefone), P2 (telefone e CEP) e P3 (sem campos, sem aceite nem "Ler os termos"); nome e e-mail ocultos e nunca enviados; CEP validado e enviado só com 8 dígitos; contato e depois mensagem; confirmação com número, prioridade, prazo e próximo passo da API como texto literal, sem aviso de protótipo, sem e-mail e sem `undefined`; evento local `chamado` com `modo: 'api'` e sem dados pessoais; `#/suporte/ID` recarregada volta a `#/confirma/ID`
    - _Requirements: 8.1, 8.2, 9.1, 9.2, 9.3, 9.4, 9.5, 9.7, 9.8, 9.11, 10.2, 10.3, 10.4, 11.1, 11.2, 11.3, 11.7, 14.2_

  - [ ]* 8.3 Criar `tests/ui/cenarios/28-api-avaliacao.test.js`
    - Resolvido: estrelas só marcam (nenhuma requisição até o envio), "Enviar avaliação" sem nota mostra erro visível com foco em `#estrelas`, envio com nota e comentário em uma requisição (`comentario` só quando não vazio), agradecimento em `role="status"`, "já enviado" ao voltar; Confirmação: toque na estrela envia e trava, falha mantém habilitado e reenvia com o mesmo `Idempotency-Key`; eventos locais `avaliacao` e `comentario` só depois de `registrada: true`
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.6, 12.7, 12.8, 12.9, 13.1, 13.2, 13.3, 13.4, 14.3_

  - [ ]* 8.4 Criar `tests/ui/cenarios/29-api-falhas.test.js`
    - Falha em "Não" (500, rede, tempo limite, 409): bloco `role="alert"` com contatos e "Tentar de novo" (mesmo `Idempotency-Key`, e novo após 409); falha parcial (contato aceito, mensagem falha): valores preservados, contato não reenviado e mesma chave da mensagem na nova tentativa, chave nova se a descrição mudou; 422 do contato mostra erro do campo com texto de `data.js`; texto vindo da API (mensagem de erro) nunca aparece; duplo toque gera no máximo uma requisição; `BASE_URL` vazia ou `window.TRESApi` ausente = Modo_Prototipo sem nenhuma requisição `/api/pub`
    - _Requirements: 8.3, 8.4, 8.5, 8.6, 10.1, 10.5, 10.6, 10.7, 10.8, 10.10, 15.6, 15.8, 16.1_

  - [ ]* 8.5 Criar `tests/ui/cenarios/30-api-acompanhar.test.js` (opcional, junto da tarefa 4.7)
    - Com a flag `ACOMPANHAMENTO_HABILITADO` ligada em memória: consulta de `#/acompanhar/NUMERO`, lista de mensagens por `textContent`, resposta com Evento_Id reutilizado, 404 com contatos diretos; com a flag desligada a rota volta a `#/`
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5_

- [ ] 9. Atualizar os testes existentes afetados
  - [ ]* 9.1 Atualizar `tests/estatico.test.js` para a nova lista de scripts
    - O teste da lista de scripts do `index.html` passa a esperar `['js/data.js', 'js/chamado.js', 'js/feedback.js', 'js/api.js', 'js/app.js']`; `NUCLEOS` (em `tests/estatico.js`, só essa constante) ganha `js/api.js` para os testes de núcleo puro
    - _Requirements: 16.2, 16.7, 18.4_

  - [ ]* 9.2 Atualizar `tests/ui/cenarios/23-dados-pessoais.test.js`
    - `exigirMetricasLimpas` passa a proibir também `jornada`, `jornadaId`, `eventoId`, `evento_id` nos eventos; novo cenário em `modoApiPub`: nada de telefone, CEP, descrição ou comentário em `localStorage`, `sessionStorage`, cookies, URL, console nem métricas, e `jornada_id` e número do chamado ausentes de qualquer storage
    - _Requirements: 10.9, 14.4, 15.3, 15.4_

  - [ ]* 9.3 Atualizar `tests/ui/cenarios/22-regressao-rotas.test.js` e demais cenários que ficarem vermelhos
    - Conferir com `BASE_URL` vazia que rotas, textos, ids, eventos e chaves de armazenamento são os de antes e que nenhuma requisição a `/api/pub` ocorre; ajustar apenas asserções que fixavam a lista de scripts ou o formato de `TRES_DATA`; nunca enfraquecer uma verificação existente
    - _Requirements: 16.1, 16.7_

- [ ] 10. Proxy de desenvolvimento e documentação
  - [ ] 10.1 Criar `dev/servir-com-api.js` (Node, somente módulos nativos)
    - Opções `--porta` (padrão 8080, NUNCA 8000), `--api-porta` (padrão 8001), `--host` (padrão 127.0.0.1), `--sem-injecao`; só inicia o servidor quando executado diretamente (`require.main === module`) e exporta as funções puras `resolverCaminho(raiz, caminho)` e `injetarBaseUrl(texto, host, porta)` para teste
    - Estáticos só para `GET` e `HEAD` com MIME correto; 404 para `..`, segmentos iniciados por ponto e pastas `tests`, `dev`, `.kiro`, `node_modules`; `/api` e `/midia` repassados para a API local preservando método, caminho, consulta, cabeçalhos úteis e corpo (`pipe`); erro de conexão = 502 com `{ "erro": { "codigo": "api_indisponivel", "mensagem": ... } }` sem derrubar o processo; `js/data.js` entregue em memória com `BASE_URL` trocada por `http://<host>:<porta>/api/pub` (salvo `--sem-injecao`); log só com método, caminho sem consulta e status; `SIGINT` encerra de forma limpa
    - _Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.6, 17.8, 17.9_

  - [ ] 10.2 Criar `dev/LEIAME.md`
    - Como clonar o repositório da API, criar o ambiente virtual (`python -m venv .venv-demo`), instalar as dependências (`pip install -e packages/dominio argon2-cffi jsonschema boto3`), subir `python scripts/dev_local.py --porta 8001`, subir `node dev/servir-com-api.js`, abrir `http://localhost:8080`; explicar que em produção site e API ficam no mesmo domínio (CloudFront do back end, sem CORS) e que o cabeçalho `x-origem-cloudfront` só existe na AWS; não afirmar que funciona contra o back end real enquanto não for verificado
    - _Requirements: 17.7, 19.5_

  - [ ]* 10.3 Escrever o teste de propriedade da resolução de caminho do proxy
    - **Property 21: Resolução de caminho do Proxy_de_Desenvolvimento**
    - Arquivo `tests/nucleo/dev-caminho.test.js`, carregando `dev/servir-com-api.js` por `require` (sem subir servidor), `numRuns` mínimo 100, com o comentário `// Feature: api-integration, Property 21: Resolução de caminho do Proxy_de_Desenvolvimento`
    - **Validates: Requirements 17.2**

  - [ ]* 10.4 Escrever o teste de propriedade da injeção da BASE_URL
    - **Property 22: Injeção da BASE_URL pelo Proxy_de_Desenvolvimento**
    - Arquivo `tests/nucleo/dev-injecao.test.js`
    - **Validates: Requirements 17.6**

  - [ ]* 10.5 Escrever os testes de exemplo do proxy (`tests/nucleo/dev-exemplos.test.js`)
    - Com uma API local falsa (`http.createServer` em porta efêmera) e o proxy em porta efêmera: repasse de método, caminho, consulta, corpo, status e cabeçalhos em `/api/...` e `/midia/...`; 502 com JSON quando a API não responde e processo continua; 404 para `tests`, `.kiro`, dotfile e `..`; só `GET`/`HEAD` nos estáticos; log sem corpo nem cabeçalhos; valores padrão das opções (8080, 8001, 127.0.0.1, nunca 8000); encerra no fim do teste
    - _Requirements: 17.2, 17.3, 17.4, 17.5, 17.8, 17.9_

- [ ] 11. Checkpoint - Núcleo, proxy e interface
  - Garanta que `npm test` (dentro de `tests/`) passa e rode `node tests/ui/rodar.js` (uma única execução, sem nenhum outro processo de teste de interface em paralelo); pergunte ao usuário se houver dúvidas.

- [ ] 12. Testes estáticos, de fumaça e roteiro manual
  - [ ]* 12.1 Estender `tests/estatico.js` (e `tests/estatico.test.js`) para a integração
    - Incluir `js/api.js` nos testes de "sem `console.*`", "sem HTML dinâmico", "núcleo puro (sem DOM, `window`, armazenamento direto, `fetch` direto nem relógio)" e "sem `require(`, `import(` nem scripts de terceiros"; teste novo: todo `data-texto-api` aponta para chave existente em `API.textos` e nenhuma frase de `API.textos` aparece em `index.html`, `js/app.js`, `js/chamado.js`, `js/feedback.js` nem `js/api.js`; `js/vendor` sem arquivos novos e nenhum `package.json` na raiz
    - CSS: o bloco novo fica depois do marcador das regras novas (sem transição, campo CEP com fonte de 16 px)
    - _Requirements: 15.1, 15.7, 16.4, 16.5, 18.4_

  - [ ]* 12.2 Atualizar `tests/smoke.test.js` para o `js/api.js`
    - Carregar `js/api.js` com `criar(chamado)` e conferir a API pública (funções e constantes do design, as 8 funções do cliente em `criarApi`, os métodos do Gerente_de_Jornada)
    - _Requirements: 18.5_

  - [ ]* 12.3 Acrescentar os testes de exemplo sobre `TRES_DATA.API` em `tests/dados.test.js`
    - `API.BASE_URL === ''`; `CHAMADO.config.API_CHAMADOS_URL === ''` e `FEEDBACK.config.API_FEEDBACK_URL === ''`; todas as chaves obrigatórias de `API.textos` presentes; cada `null` de `MODELOS_API` marcado `PENDENTE` em comentário; `PENDENTE`/`ILUSTRATIVO` junto de `BASE_URL`, `TIMEOUT_MS` e dos textos; `TRES_DATA.CHAMADO` e `TRES_DATA.FEEDBACK` idênticos aos anteriores
    - _Requirements: 1.2, 18.6, 19.4_

  - [ ]* 12.4 Acrescentar a seção da integração em `tests/ui/roteiro-manual.md`
    - Checklist curto dos itens que a automação não cobre: back end real (`dev_local.py` e AWS), CORS e `x-origem-cloudfront`, mapeamento dos modelos LOV, Modo, Luna e Touch, conteúdo oficial local contra o de exemplo da API, "Sim" depois de "Não" na mesma jornada, leitor de tela real (NVDA, VoiceOver, TalkBack), celular físico, Firefox e Safari, revisão jurídica (LGPD) dos textos; os itens continuam "não verificados" até alguém executar
    - _Requirements: 18.8, 19.2_

- [ ] 13. Atualizar o `CONTEXTO-PROJETO.md`
  - [ ] 13.1 Registrar a integração com a API no contexto do projeto
    - Nova seção: abordagem (adaptar o front à API), modos e precedência (`BASE_URL`, `API_CHAMADOS_URL`, `API_FEEDBACK_URL`), arquivos novos (`js/api.js`, `dev/servir-com-api.js`, `dev/LEIAME.md`), mapeamento de modelos, fluxo da jornada, métricas locais, como rodar com o proxy (porta 8080, nunca 8000) e como rodar os testes (`npm test` em `tests/`, `node tests/ui/rodar.js` em série, `node --test` direto para paralelo)
    - Registrar as mudanças deliberadas em requisitos anteriores válidas só em Modo_API (nome e e-mail deixam de ser pedidos; protocolo, prazo e aviso vêm da API; estrela e comentário em um único envio com nota obrigatória)
    - Pendências `PENDENTE`/não verificado: back end real, CORS e autorização de origem na AWS, mapeamento de LOV, Modo, Luna e Touch, conteúdo de exemplo da API contra o oficial, tela de acompanhamento, "Sim" depois de "Não", leitor de tela, celular, outros navegadores, LGPD; sem afirmar que a integração funciona contra o back end real
    - _Requirements: 19.1, 19.2, 19.3, 19.5, 16.8_

- [ ] 14. Integração e verificação final
  - [ ] 14.1 Conferir arquivos protegidos e escopo dos arquivos
    - Rodar `node tests/verificar-protegidos.js --conferir` e confirmar que nada em `material/`, em `img/*.png` originais e no `.glb` original mudou e que nada foi criado, movido nem excluído em `material/`
    - Confirmar que não existe `package.json` na raiz, que `js/vendor` não ganhou arquivos, que `API.BASE_URL`, `API_CHAMADOS_URL` e `API_FEEDBACK_URL` continuam vazias, que `js/chamado.js` e `js/feedback.js` não mudaram de comportamento e que o repositório de referência da API não foi alterado
    - _Requirements: 1.2, 16.3, 16.5, 16.6_

  - [ ] 14.2 Conferir privacidade e segurança do código novo
    - Revisar `js/api.js`, `js/app.js` e `dev/servir-com-api.js`: nenhum `console.*` (exceto o log de método, caminho e status do proxy, que não usa dado pessoal), nenhum `innerHTML`/`insertAdjacentHTML`/`outerHTML`/`document.write` com dado da API ou do consumidor, nenhum segredo, token ou cabeçalho de autorização, `jornada_id` e número do chamado só em memória, falhas mostrando só textos de `data.js`
    - Conferir que `TRESMetricas.resumo()` mantém `resolvidos`, `encaminhadosAoSuporte`, `deflexaoPercentual`, `porProblema`, `chamadosAbertos` e `comentarios` inalterados
    - _Requirements: 14.4, 14.5, 15.1, 15.2, 15.3, 15.4, 15.6, 15.7, 17.8_

  - [ ] 14.3 Rodar a suíte completa em série
    - Garantir que as tarefas de atualização dos testes existentes (9.1 a 9.3) foram feitas; se alguma foi pulada por ser opcional, ajustar essas asserções antes de rodar
    - Rodar `npm test` dentro de `tests/` e, depois, `node tests/ui/rodar.js` (uma única execução por vez; NUNCA duas execuções de `rodar.js` ao mesmo tempo; para rodar em paralelo, usar `node --test` direto nos arquivos de `tests/ui/cenarios/`)
    - Rodar de novo `node tests/verificar-protegidos.js --conferir` e garantir que tudo passa, pergunte ao usuário se houver dúvidas
    - _Requirements: 16.7, 18.7_

  - [ ] 14.4 Limpar temporários
    - Encerrar servidores de teste, o proxy de desenvolvimento e processos do Edge, apagar perfis temporários (`tres-ui-edge-*`), capturas e arquivos `tmp-*` que tenham sobrado, e garantir que `tests/node_modules` não é referenciado pelo site
    - Não deixar `rodar.js`, `servidor-teste.js` nem `dev/servir-com-api.js` em execução
    - _Requirements: 16.5_

## Notes

- Tarefas marcadas com `*` são opcionais (testes, API falsa, documentação de teste e o acompanhamento do requisito 20) e podem ser puladas para um MVP mais rápido; as tarefas de código do site, o proxy e sua documentação, o `CONTEXTO-PROJETO.md`, os checkpoints e a verificação final não são opcionais. Atenção: pular 9.1 deixa `tests/estatico.test.js` falhando (ele fixa a lista de scripts do `index.html`), e pular 9.2 e 9.3 pode deixar cenários de interface vermelhos, então a tarefa 14.3 exige que essas asserções sejam ajustadas antes da suíte final.
- Cada tarefa cita os requisitos específicos que cumpre; cada teste de propriedade cita o número da propriedade do design e o requisito que valida.
- Os testes de propriedade usam fast-check 4.10.2 (já fixado em `tests/package.json`), só em `tests/`, com no mínimo 100 execuções e o comentário `// Feature: api-integration, Property N: <título>`. Cada propriedade é implementada por um único teste de propriedade.
- Verificação contra o back end real, CORS e autorização de origem na AWS, leitor de tela real, celular físico, Firefox e Safari fica fora da automação e continua não verificada até alguém executar o roteiro manual. O mapeamento de LOV, Modo, Luna e Touch, a avaliação jurídica (LGPD) e a tela de acompanhamento seguem `PENDENTE`.
- As tarefas 2.x alteram o mesmo arquivo (`js/api.js`) e as tarefas 4.x o mesmo arquivo (`js/app.js`); por isso são sequenciais no grafo de dependências. O mesmo vale para os testes de propriedade agrupados por arquivo (`api-config`, `api-cliente-req`, `api-cliente-erro`, `api-validacao`, `api-filtros`, `api-jornada`, `api-eventos`, `api-resolucao`, `api-avaliacao`).
- A porta padrão do proxy é 8080 e nunca 8000. O repositório de referência da API (`C:\Users\labsfiap\AppData\Local\Temp\prjFacilita-ref`) é somente leitura.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2"] },
    { "id": 1, "tasks": ["2.1", "3.1", "3.2", "6.1", "7.1", "10.1"] },
    { "id": 2, "tasks": ["2.2", "6.2", "7.2", "7.4", "10.2", "10.3", "10.4", "10.5"] },
    { "id": 3, "tasks": ["2.3", "7.3", "7.10", "7.12"] },
    { "id": 4, "tasks": ["2.4", "7.5", "7.11", "7.21"] },
    { "id": 5, "tasks": ["2.5", "7.6", "7.7", "7.13", "7.15"] },
    { "id": 6, "tasks": ["2.6", "7.8", "7.14", "7.16", "7.17"] },
    { "id": 7, "tasks": ["2.7", "7.9", "7.18"] },
    { "id": 8, "tasks": ["4.1", "7.19", "7.22"] },
    { "id": 9, "tasks": ["4.2", "7.20"] },
    { "id": 10, "tasks": ["4.3"] },
    { "id": 11, "tasks": ["4.4"] },
    { "id": 12, "tasks": ["4.5"] },
    { "id": 13, "tasks": ["4.6"] },
    { "id": 14, "tasks": ["4.7"] },
    { "id": 15, "tasks": ["8.1", "8.2", "8.3", "8.4", "8.5"] },
    { "id": 16, "tasks": ["9.1", "9.2", "9.3"] },
    { "id": 17, "tasks": ["12.1", "12.2", "12.3", "12.4"] },
    { "id": 18, "tasks": ["13.1"] },
    { "id": 19, "tasks": ["14.1", "14.2"] },
    { "id": 20, "tasks": ["14.3"] },
    { "id": 21, "tasks": ["14.4"] }
  ]
}
```
