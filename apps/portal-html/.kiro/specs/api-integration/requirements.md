# Requirements Document

## Introduction

Hoje o Autoatendimento TRES funciona só no navegador: o conteúdo dos 13 problemas fica em `js/data.js`, o chamado é simulado no `localStorage` (ou enviado a uma URL genérica, `API_CHAMADOS_URL`) e o comentário da tela de problema resolvido segue o mesmo caminho (`API_FEEDBACK_URL`). Em paralelo, existe um back end real, o repositório `ViniMac3do/prjFacilita-` (referência somente leitura, clonada em `C:\Users\labsfiap\AppData\Local\Temp\prjFacilita-ref`), com uma API pública em `/api/pub` que modela a **jornada** (criar, associar modelo, eventos do guia, resolução, escalada em chamado, avaliação) e o **chamado** (contato, mensagens). O pedido do usuário foi: "Aplique todo esse front as apis desse git".

O usuário escolheu a abordagem **"Adaptar o front à API, sem mexer no back end"**. Em resumo:

- o conteúdo oficial dos 13 problemas **continua local** (`js/data.js`); a API é usada **só para a jornada** (nenhuma instrução, modelo ou foto vem dela);
- o telefone vai para `/contato`, junto do aceite dos termos (que vira `consentimento: true`); a descrição vai para `/mensagens`;
- **nome e e-mail deixam de ser pedidos** quando a API está ligada (a API não tem esses campos);
- a estrela e o comentário passam a ir **juntos em um único envio**, com **nota obrigatória**;
- "Não, ainda não" passa a criar o chamado na API (`/resolucao` com `resolvido: false`), e o protocolo, o prazo e o próximo passo exibidos vêm **da resposta da API**, não mais do front.

A integração é ligada por uma única configuração, `TRES_DATA.API.BASE_URL`. **Vazia** (padrão do repositório) = **Modo_Prototipo**: o comportamento atual, inteiro, sem uma requisição nova e com todos os testes atuais passando. **Preenchida** com uma URL válida = **Modo_API da jornada**. Um módulo novo, `js/api.js` (`window.TRESApi`), concentra o cliente HTTP e a lógica da jornada, sem DOM e com tudo do mundo externo por injeção, como `js/chamado.js` e `js/feedback.js`.

O projeto continua em HTML, CSS e JS puros, sem build, mobile primeiro. O repositório da API **não é alterado**. Para desenvolver sem CORS, um script Node sem dependências (`dev/servir-com-api.js`) serve o site e repassa `/api` e `/midia` para a API local deles.

### Escopo

Dentro do escopo:
- a configuração `TRES_DATA.API` e a regra de modo (Modo_Prototipo e Modo_API) com precedência sobre `API_CHAMADOS_URL` e `API_FEEDBACK_URL`;
- `js/api.js`: cliente HTTP (timeout, cabeçalhos, erro padronizado), ULID e idempotência, corpos e rotas de cada chamada, e o gerente da jornada (criação preguiçosa, modelo, eventos do guia, resolução, avaliação e envio do chamado);
- as mudanças de tela em `index.html`, `css/styles.css` e `js/app.js`: eventos do guia, "Sim" e "Não", Tela_de_Chamado (sem nome e e-mail, com CEP), Tela_de_Confirmacao (número, prioridade, prazo e próximo passo da API) e avaliação única na Tela_de_Resolvido;
- a API falsa dos testes de interface (`tests/ui/servidor-teste.js`), os testes do núcleo (fast-check), os cenários de UI, a atualização dos testes existentes afetados e do roteiro manual;
- `dev/servir-com-api.js` e a documentação de como subir a API local;
- a atualização do `CONTEXTO-PROJETO.md`.

Fora do escopo:
- qualquer alteração no repositório da API (back end, banco, infraestrutura, CloudFront);
- consumir `GET /modelos`, `GET /modelos/{id}` e `GET /jornadas/{id}/instrucao`: o conteúdo oficial continua local (conteúdo de exemplo da API não substitui o oficial);
- fotos do chamado (`/anexos`, `pedir_anexo`, `confirmar_anexo`), vazamento (`/vazamento`) e escalada explícita (`/escalar`), alerta de risco e o envelope `jornada.risco`;
- avaliação pelo chamado (`POST /chamados/{numero}/avaliacao`, só para chamado `encerrado`): a avaliação do consumidor usa sempre `POST /jornadas/{id}/avaliacao`;
- painel de atendimento (Painel_CS), autenticação e sessões do back end;
- PWA, fila persistente de eventos offline e reenvio entre recargas da página;
- alteração de `material/`, de `img/*.png` originais e do `.glb` original.

A tela de acompanhamento do chamado (`GET /chamados/{numero}`) **não faz parte do núcleo**. Ela está descrita como funcionalidade **opcional** no requisito 20 e nas tarefas marcadas com `*`.

## Premissas e pontos em aberto

Cada item traz o **padrão adotado nesta spec**. A abordagem geral (adaptar o front, sem mexer no back end) é *decisão do usuário*.

- **P1. `BASE_URL` é a URL completa do prefixo público.** Exemplo: `https://dominio.exemplo/api/pub` ou, em desenvolvimento, `http://localhost:8080/api/pub`. A regra de validade é a mesma de `resolverModo` de `js/chamado.js`: `https`, ou `http` em `localhost` ou `127.0.0.1`. Um caminho relativo (`/api/pub`) **não** é aceito (viraria Modo_Prototipo). Em produção o site e a API ficam no **mesmo domínio** (CloudFront do back end), então não há CORS; em desenvolvimento o `dev/servir-com-api.js` cria essa mesma origem.
- **P2. Precedência.** Com `BASE_URL` válida, `CHAMADO.config.API_CHAMADOS_URL` e `FEEDBACK.config.API_FEEDBACK_URL` ficam **inutilizadas** (as duas devem continuar vazias). Com `BASE_URL` vazia, elas continuam funcionando como hoje.
- **P3. Mapeamento de modelos.** Os modelos da API são `tres-passione`, `tres-circo` e `tres-mimo` (conteúdo de exemplo). O front tem LOV, Modo, Passione, Luna e Touch. Só a Passione tem equivalente. Para os outros quatro a jornada é criada **sem modelo** (a API aceita). O mapeamento fica em `TRES_DATA.API.MODELOS_API` (`{ passione: 'tres-passione', lov: null, modo: null, luna: null, touch: null }`); cada `null` é marcado `PENDENTE`.
- **P4. A jornada nasce quando é preciso.** A jornada na API é criada na primeira necessidade (escolha do problema, "Sim", "Não" ou avaliação), nunca ao abrir a página. O `jornada_id` e o número do chamado ficam **só em memória**. Falha da API na jornada **não** bloqueia o guia.
- **P5. Eventos do guia são "dispare e esqueça".** Nunca bloqueiam a tela, nunca mostram erro e nunca levam dado pessoal. Não há fila persistente: o que falhar é descartado (exceto a recuperação de 409, requisito 6).
- **P6. "Não" cria o chamado antes do formulário.** O chamado nasce em "Não, ainda não" (a API escala a jornada). É a resposta que diz quais dados pedir (`dados_solicitados`: `["telefone"]` em P1, `["telefone","cep"]` em P2, `[]` em P3), então o formulário só aparece depois dela. Na prática, "Não" no guia gera P2 (ou P1 se a API marcar risco).
- **P7. Contato e mensagem em dois envios.** O formulário envia primeiro o contato (telefone e/ou CEP, com `consentimento: true`) e depois a mensagem (a descrição). A falha parcial não duplica o que a API já aceitou. O contato é um *upsert* idempotente na API; a mensagem usa `Idempotency-Key`. Se o consumidor **editar** a descrição depois de uma falha, a mensagem recebe uma chave nova (senão a API ignoraria o texto novo).
- **P8. Estrelas na Tela_de_Confirmacao.** Padrão adotado: o toque na estrela **envia na hora** (sem comentário) e, depois de aceito, as estrelas ficam travadas mostrando a nota enviada, porque a API guarda **uma avaliação por jornada** e não sobrescreve. É uma decisão de design que o usuário pode reverter para o padrão "selecionar e enviar" da Tela_de_Resolvido.
- **P9. Textos da integração ficam em `data.js`.** Todo texto novo (rótulo do CEP, "Enviar avaliação", mensagens de falha) vive em `TRES_DATA.API.textos` e entra na página por `data-texto-api` e `textContent`. São `ILUSTRATIVO` até validação do time de Customer Success. Textos de prazo, prioridade e próximo passo **não** são escritos no front: vêm da API.
- **P10. Anexos, vazamento e escalada explícita ficam fora.** O problema 10 (vazamento) do front não tem a pergunta "externo ou interno" do back end; ligar isso depende de decisão de conteúdo.

### Pontos em aberto (pendentes, registrar como `PENDENTE`/não verificado)

- **Back end real:** nada desta spec é verificado contra o back end real; só contra a API falsa dos testes e, manualmente, contra o `dev_local.py` deles.
- **CORS e autorização de origem na AWS** (cabeçalho `x-origem-cloudfront` só existe na AWS): `PENDENTE`.
- **Mapeamento dos 4 modelos sem equivalente** (LOV, Modo, Luna e Touch): `PENDENTE`.
- **Conteúdo de exemplo da API vs. conteúdo oficial local:** a API traz instruções só para `tres-passione`; o conteúdo oficial continua o local.
- **Tela de acompanhamento do chamado** (mensagens do atendente, resposta do consumidor): fora do núcleo, opcional (requisito 20).
- **Comportamento de "Sim" depois de "Não"** na mesma jornada (a API já escalou): não verificado.
- **LGPD:** o texto dos termos e o aviso de privacidade continuam provisórios; a API mascara dados pessoais nas mensagens, mas o front não confia nisso como controle.

## Glossary

- **Sistema**: a página Autoatendimento TRES (HTML, CSS e JS puros) executada no navegador do consumidor.
- **Consumidor**: a pessoa que usa a jornada, em geral em pé na frente da máquina, com o celular.
- **Back_end**: a API pública do repositório `ViniMac3do/prjFacilita-`, prefixo `/api/pub`, mesma origem do site.
- **BASE_URL**: `TRES_DATA.API.BASE_URL`, a URL completa do prefixo público da API. Vazia por padrão.
- **Modo_Prototipo**: o comportamento atual, ativo quando a BASE_URL está ausente, vazia ou inválida. Nenhuma requisição ao Back_end.
- **Modo_API**: o modo ativo quando a BASE_URL é `https`, ou `http` em `localhost` ou `127.0.0.1`.
- **Cliente_API**: o módulo `js/api.js`, exposto como `window.TRESApi` (fábrica `criar(base)`, em que `base` é o `TRESChamado`), sem DOM.
- **Erro_Padronizado**: o objeto de erro do Cliente_API: `{ tipo: 'timeout' | 'rede' | 'http' | 'resposta', status, codigo, campos }`.
- **Evento_Id**: identificador ULID (26 caracteres, alfabeto Crockford) gerado no navegador para um ato do Consumidor; vai no campo `evento_id` do corpo e no cabeçalho `Idempotency-Key`.
- **Jornada_API**: o registro de jornada no Back_end, identificado por `jornada_id`.
- **Gerente_de_Jornada**: a parte do Cliente_API que mantém em memória a Jornada_API, o modelo, os eventos enviados, a resolução, o Chamado_API e o estado do envio do chamado.
- **Mapeamento_de_Modelos**: `TRES_DATA.API.MODELOS_API`, que liga o id do modelo do front ao `modelo_id` da API (ou `null`).
- **Evento_do_Guia**: evento `selecionado`, `exibido` ou `concluido` enviado ao Back_end em `/jornadas/{id}/eventos`.
- **Chamado_API**: o chamado criado pela resolução "Não": `numero`, `prioridade_rotulo`, `prazo`, `proximo_passo`, `classificacao` e `dados_solicitados`.
- **Dados_Solicitados**: lista, vinda do Chamado_API, dos dados que o Back_end pede ao Consumidor (`telefone`, `cep`).
- **Prazo_da_API**: o texto de `prazo` do Chamado_API (por exemplo, "contato em até 4 horas úteis"), exibido como veio.
- **Tela_de_Pergunta_Final**: a tela `#/confirma/ID`, "O problema foi solucionado?".
- **Tela_de_Resolvido**: a tela `#/resolvido/ID`.
- **Tela_de_Chamado**: a tela `#/suporte/ID`, com o formulário de contato.
- **Tela_de_Confirmacao**: a tela `#/chamado/ID`, exibida depois do envio do formulário.
- **Avaliacao_Unica**: o envio único de nota e comentário opcional da Tela_de_Resolvido em Modo_API.
- **Proxy_de_Desenvolvimento**: o script `dev/servir-com-api.js`.
- **API_Falsa**: a implementação das rotas `/api/pub/...` dentro de `tests/ui/servidor-teste.js`, usada pelos testes de interface.
- **Dados_Pessoais**: nome, e-mail, telefone, CEP e o texto livre digitado pelo Consumidor (descrição e comentário).
- **Registro_de_Metricas**: o armazenamento de eventos no `localStorage`, chave `tres-autoatendimento-eventos`, até 500 eventos.

## Requirements

### Requirement 1: Escolher o modo pela BASE_URL e definir a precedência

**User Story:** Como desenvolvedor, quero ligar a integração com uma única configuração e manter o protótipo intacto quando ela estiver vazia, para que a entrega do hackathon continue funcionando sem back end.

#### Acceptance Criteria

1. THE Sistema SHALL ler a configuração `TRES_DATA.API` de `js/data.js`, com `BASE_URL` (texto), `TIMEOUT_MS` (número), `MODELOS_API` (objeto) e `textos` (objeto), e SHALL exportá-la em `window.TRES_DATA` junto das chaves atuais.
2. THE `js/data.js` SHALL conter `TRES_DATA.API.BASE_URL` igual a texto vazio no repositório.
3. WHERE a BASE_URL é uma URL `https`, ou `http` em `localhost` ou `127.0.0.1`, THE Sistema SHALL operar em Modo_API.
4. IF a BASE_URL está ausente, vazia ou inválida, THEN THE Sistema SHALL operar em Modo_Prototipo e SHALL NOT realizar nenhuma requisição ao Back_end.
5. WHILE o Modo_API está ativo, THE Sistema SHALL ignorar `CHAMADO.config.API_CHAMADOS_URL` e `FEEDBACK.config.API_FEEDBACK_URL`, sem realizar requisição a elas, e SHALL NOT gravar chamado, comentário ou avaliação nas chaves `tres-autoatendimento-chamados` e `tres-autoatendimento-feedbacks`.
6. WHILE o Modo_Prototipo está ativo, THE Sistema SHALL manter o comportamento atual de `API_CHAMADOS_URL` e `API_FEEDBACK_URL`, inclusive quando elas estiverem preenchidas.
7. THE `js/data.js` SHALL documentar, em comentário junto da BASE_URL, a precedência sobre as duas URLs antigas, a regra de validade da URL e a marcação `PENDENTE` do ambiente.
8. WHEN a BASE_URL termina com uma ou mais barras, THE Cliente_API SHALL removê-las antes de montar as URLs das requisições.
9. IF `TIMEOUT_MS` está ausente ou não é um número finito maior que zero, THEN THE Cliente_API SHALL usar 5000 ms.

### Requirement 2: Falar com o Back_end pelo Cliente_API

**User Story:** Como desenvolvedor, quero um cliente HTTP único, testável sem navegador, que fale com a API como o cliente de referência dela, para que as telas só chamem funções.

#### Acceptance Criteria

1. THE Cliente_API SHALL receber por injeção a configuração, `fetch`, `AbortController`, `setTimeout`, `clearTimeout`, o relógio e o sorteio, e SHALL NOT acessar DOM, `window`, `localStorage`, `sessionStorage` nem `console`.
2. THE Cliente_API SHALL montar a URL de cada requisição como BASE_URL (sem barra final) seguida do caminho, e SHALL aplicar `encodeURIComponent` a todo segmento dinâmico do caminho.
3. THE Cliente_API SHALL enviar o cabeçalho `Accept: application/json` em todas as requisições.
4. WHERE a requisição tem corpo, THE Cliente_API SHALL enviar `Content-Type: application/json` e o corpo serializado em JSON.
5. WHERE o método da requisição não é `GET`, THE Cliente_API SHALL enviar `X-Requested-With: tres-portal`.
6. WHERE a requisição tem chave de idempotência, THE Cliente_API SHALL enviar o cabeçalho `Idempotency-Key` com o valor da chave.
7. THE Cliente_API SHALL enviar `credentials: 'same-origin'`, `cache: 'no-store'` e `referrerPolicy: 'no-referrer'`, e SHALL NOT enviar cabeçalho de autorização, cookie, token nem o cabeçalho `x-origem-cloudfront`.
8. THE Cliente_API SHALL aplicar o tempo limite por `AbortController`; WHERE o ambiente não tem `AbortController`, THE Cliente_API SHALL aplicar o tempo limite por corrida com temporizador; THE Cliente_API SHALL limpar o temporizador ao concluir qualquer requisição.
9. WHEN o Back_end responde com status 2xx e corpo JSON, THE Cliente_API SHALL resolver com o objeto interpretado; WHEN responde 204, THE Cliente_API SHALL resolver sem valor.
10. THE Cliente_API SHALL oferecer as funções `criarJornada`, `associarModelo`, `registrarEvento`, `registrarResolucao`, `registrarAvaliacao`, `obterChamado`, `enviarContato` e `enviarMensagem`, cada uma com o método, o caminho e o corpo definidos no design, e nenhuma outra rota do Back_end.

### Requirement 3: Padronizar os erros

**User Story:** Como desenvolvedor, quero um formato único de erro, para que as telas decidam o que mostrar sem ler texto técnico.

#### Acceptance Criteria

1. IF o tempo limite expira, THEN THE Cliente_API SHALL rejeitar com Erro_Padronizado de `tipo` igual a `timeout`.
2. IF a chamada a `fetch` falha sem expirar o tempo limite, THEN THE Cliente_API SHALL rejeitar com Erro_Padronizado de `tipo` igual a `rede`.
3. IF o Back_end responde com status fora de 2xx, THEN THE Cliente_API SHALL rejeitar com Erro_Padronizado de `tipo` igual a `http`, com `status` igual ao status recebido, `codigo` igual a `erro.codigo` quando for texto e `campos` igual à lista de `{ campo, motivo }` de `erro.campos` quando o corpo seguir o formato `{ erro: { codigo, mensagem, campos? } }`.
4. IF o Back_end responde com status fora de 2xx e o corpo está ausente ou fora do formato, THEN THE Cliente_API SHALL rejeitar com Erro_Padronizado de `tipo` igual a `http`, `codigo` igual a `null` e `campos` igual a lista vazia, sem lançar outra exceção.
5. IF o Back_end responde com status 2xx e o corpo não é JSON válido, ou o corpo não tem a forma esperada pela função chamada, THEN THE Cliente_API SHALL rejeitar com Erro_Padronizado de `tipo` igual a `resposta`.
6. THE Erro_Padronizado SHALL NOT conter o corpo bruto da resposta nem a mensagem de texto do Back_end, e o Sistema SHALL NOT exibir ao Consumidor nenhum texto vindo de `erro.mensagem`.
7. THE Cliente_API SHALL oferecer a função `classificarErro`, que devolve `conflito` para `tipo` `http` com status 409, `definitivo` para os demais status 4xx exceto 408 e 429, e `transitorio` para `timeout`, `rede`, `resposta`, status 5xx, 408 e 429.
8. THE Cliente_API SHALL rejeitar toda chamada que falhe exclusivamente com Erro_Padronizado, sem deixar escapar outra exceção.

### Requirement 4: Gerar identificadores e aplicar idempotência

**User Story:** Como desenvolvedor, quero identificadores únicos por ato do Consumidor, para que reenvios não dupliquem efeitos no Back_end.

#### Acceptance Criteria

1. THE Cliente_API SHALL gerar o Evento_Id como ULID de exatamente 26 caracteres do alfabeto `0123456789ABCDEFGHJKMNPQRSTVWXYZ`.
2. THE Cliente_API SHALL codificar nos 10 primeiros caracteres do Evento_Id o instante do relógio em milissegundos, em base 32, e SHALL preencher os 16 caracteres restantes com valores do sorteio injetado.
3. FOR ALL pares de instantes `t1 < t2`, o Evento_Id gerado em `t1` SHALL ser menor que o gerado em `t2` pela ordem lexicográfica dos 10 primeiros caracteres.
4. WHERE o sorteio injetado é determinístico, THE Cliente_API SHALL gerar o mesmo Evento_Id para o mesmo instante e a mesma sequência de sorteio.
5. WHERE o ambiente não fornece sorteio injetado, THE Cliente_API SHALL usar `crypto.getRandomValues` quando existir e, na falta dele, `Math.random`.
6. WHEN o Cliente_API envia um Evento_Id, THE Cliente_API SHALL enviá-lo no campo `evento_id` do corpo e no cabeçalho `Idempotency-Key` com o mesmo valor, nas chamadas `registrarEvento`, `registrarResolucao`, `registrarAvaliacao`, `enviarContato` e `enviarMensagem`.
7. WHERE `criarJornada` recebe uma chave, THE Cliente_API SHALL enviá-la em `Idempotency-Key` e SHALL NOT incluí-la no corpo.
8. WHEN o Sistema repete um mesmo ato por causa de falha, THE Sistema SHALL reutilizar o mesmo Evento_Id; WHEN o ato é novo, THE Sistema SHALL gerar um Evento_Id novo.

### Requirement 5: Criar a jornada na API quando for preciso e associar o modelo

**User Story:** Como time de Customer Success, quero que cada jornada do consumidor exista na API, para medir a deflexão por camada, sem que uma falha da API atrapalhe quem está resolvendo a máquina.

#### Acceptance Criteria

1. WHILE o Modo_API está ativo, WHEN a primeira necessidade de Jornada_API ocorre (escolha do problema, resposta "Sim" ou "Não", ou envio da avaliação) e não há Jornada_API ativa em memória, THE Gerente_de_Jornada SHALL criar a Jornada_API por `POST /jornadas` com `origem` igual a `busca`.
2. THE Gerente_de_Jornada SHALL NOT criar Jornada_API ao carregar a página, ao escolher apenas o modelo, nem em Modo_Prototipo.
3. WHEN o Mapeamento_de_Modelos devolve um texto não vazio para o modelo escolhido, THE Gerente_de_Jornada SHALL incluir `modelo_id` no corpo; IF o mapeamento devolve `null`, ou o Consumidor não escolheu modelo, THEN THE Gerente_de_Jornada SHALL omitir `modelo_id` do corpo e criar a Jornada_API sem modelo.
4. WHEN várias necessidades de Jornada_API ocorrem enquanto uma criação está em andamento, THE Gerente_de_Jornada SHALL compartilhar a mesma criação e SHALL enviar no máximo um `POST /jornadas` para elas.
5. THE Gerente_de_Jornada SHALL guardar o `jornada_id` somente em memória, e SHALL NOT gravá-lo em `localStorage`, `sessionStorage`, cookies nem na URL.
6. IF a criação da Jornada_API falha, THEN THE Sistema SHALL NOT exibir mensagem de erro, SHALL NOT bloquear nem atrasar o guia, e SHALL tentar criar de novo somente na próxima necessidade de Jornada_API, sem temporizador de repetição.
7. WHEN o modelo escolhido muda depois de a Jornada_API existir, THE Gerente_de_Jornada SHALL, se o novo modelo mapeado é um texto diferente do registrado, enviar `PUT /jornadas/{id}/modelo` com o novo `modelo_id`; IF o novo modelo é `null` ou não escolhido e a Jornada_API tem modelo, THEN THE Gerente_de_Jornada SHALL descartar a Jornada_API e criar outra na próxima necessidade; IF o modelo mapeado é igual ao registrado, THEN THE Gerente_de_Jornada SHALL NOT enviar nenhuma requisição.
8. IF o Back_end responde 409 a uma requisição da Jornada_API (jornada encerrada), THEN THE Gerente_de_Jornada SHALL descartar a Jornada_API em memória e criar outra na próxima necessidade.
9. WHEN o Consumidor escolhe um problema na lista depois de a Jornada_API ter sido encerrada por "Sim" ou por "Não", THE Gerente_de_Jornada SHALL criar uma Jornada_API nova para esse problema.
10. WHEN o Consumidor muda de problema sem que a Jornada_API tenha sido encerrada, THE Gerente_de_Jornada SHALL reaproveitar a mesma Jornada_API.

### Requirement 6: Enviar os eventos do guia sem bloquear a tela

**User Story:** Como time de Customer Success, quero saber quais problemas e passos os consumidores percorrem, para entender onde o guia resolve e onde falha, sem que isso deixe a tela lenta.

#### Acceptance Criteria

1. WHILE o Modo_API está ativo, WHEN o Consumidor escolhe um problema, THE Gerente_de_Jornada SHALL registrar o Evento_do_Guia `selecionado` com `problema_id`.
2. WHILE o Modo_API está ativo, WHEN um passo da solução é exibido pela primeira vez para a combinação de Jornada_API, problema e passo, THE Gerente_de_Jornada SHALL registrar o Evento_do_Guia `exibido` com `problema_id` e `passo`.
3. WHILE o Modo_API está ativo, WHEN o Consumidor avança de um passo (por "Próximo passo" ou "Terminei os passos"), THE Gerente_de_Jornada SHALL registrar o Evento_do_Guia `concluido` com `problema_id` e o número desse passo, uma vez por combinação de Jornada_API, problema e passo.
4. THE Gerente_de_Jornada SHALL enviar cada Evento_do_Guia com `ocorrido_em` em ISO 8601 com fuso horário e com um Evento_Id novo, e o corpo SHALL conter somente `tipo`, `problema_id`, `passo` (quando houver), `ocorrido_em` e `evento_id`.
5. THE Sistema SHALL tratar o envio de Evento_do_Guia como "dispare e esqueça": a tela SHALL NOT esperar a resposta, SHALL NOT exibir erro e SHALL NOT mudar de comportamento se o envio falhar.
6. THE Gerente_de_Jornada SHALL enviar os Eventos_do_Guia de uma mesma Jornada_API um de cada vez, na ordem em que ocorreram.
7. WHEN o Consumidor volta a um passo já exibido, THE Gerente_de_Jornada SHALL NOT enviar de novo o Evento_do_Guia `exibido` desse passo.
8. IF o Back_end responde 409 a um Evento_do_Guia, THEN THE Gerente_de_Jornada SHALL descartar a Jornada_API, criar uma nova, registrar nela o `selecionado` do problema atual e depois o Evento_do_Guia original, uma única vez, e SHALL NOT tentar mais nenhuma vez.
9. THE Gerente_de_Jornada SHALL NOT enviar Evento_do_Guia cujo `passo` esteja fora de 1 a 10 ou cujo `problema_id` não seja um inteiro maior ou igual a 1.
10. THE Gerente_de_Jornada SHALL NOT incluir nos Eventos_do_Guia nome, e-mail, telefone, CEP, texto digitado, modelo nem protocolo.

### Requirement 7: Registrar "Sim, resolvi" sem atrapalhar o sucesso

**User Story:** Como consumidor que resolveu o problema, quero ver a tela de sucesso na hora, para não esperar uma resposta de rede.

#### Acceptance Criteria

1. WHILE o Modo_API está ativo, WHEN o Consumidor aciona "Sim, resolvi", THE Sistema SHALL registrar o evento local `resolvido` como hoje, navegar para `#/resolvido/ID` sem esperar nenhuma resposta de rede e enviar `POST /jornadas/{id}/resolucao` com `resolvido` igual a `true`, `problema_id` e `evento_id`.
2. IF o envio da resolução falha, THEN THE Sistema SHALL manter a Tela_de_Resolvido e SHALL NOT exibir mensagem de erro.
3. WHEN o Back_end aceita a resolução `true`, ou responde 409 por jornada já encerrada, THE Gerente_de_Jornada SHALL marcar a Jornada_API como encerrada em memória.
4. WHEN o Consumidor volta e aciona "Sim, resolvi" de novo para o mesmo problema na mesma Jornada_API, THE Sistema SHALL reutilizar o mesmo Evento_Id da resolução.
5. THE Gerente_de_Jornada SHALL tornar a resolução pendente aguardável, de modo que o envio da avaliação espere o fim da resolução, bem-sucedida ou não, antes de enviar.

### Requirement 8: Registrar "Não, ainda não" e criar o chamado

**User Story:** Como consumidor que não resolveu o problema, quero que meu chamado seja aberto com o prazo real de retorno, para saber o que esperar.

#### Acceptance Criteria

1. WHILE o Modo_API está ativo, WHEN o Consumidor aciona "Não, ainda não", THE Sistema SHALL registrar o evento local `suporte` como hoje, desabilitar o botão, marcar a Tela_de_Pergunta_Final com `aria-busy="true"`, anunciar o andamento e enviar `POST /jornadas/{id}/resolucao` com `resolvido` igual a `false`, `problema_id` e `evento_id`.
2. WHEN o Back_end responde com o chamado, THE Gerente_de_Jornada SHALL guardar em memória `numero`, `prazo`, `prioridade_rotulo`, `proximo_passo` e `dados_solicitados`, marcar a Jornada_API como encerrada para as próximas escolhas de problema e THE Sistema SHALL navegar para `#/suporte/ID`.
3. IF o envio falha (rede, tempo limite, status 5xx, 4xx, 409 ou resposta inválida), THEN THE Sistema SHALL permanecer na Tela_de_Pergunta_Final, exibir o bloco de falha em `role="alert"` com o telefone e o e-mail de contato direto, mover o foco para o bloco, anunciar a falha em até 1 segundo e reabilitar os botões.
4. WHEN o Consumidor aciona "Tentar de novo" depois de uma falha que não foi 409, THE Sistema SHALL repetir a resolução com o mesmo Evento_Id.
5. IF a falha foi 409, THEN THE Gerente_de_Jornada SHALL descartar a Jornada_API, e a nova tentativa SHALL criar uma Jornada_API nova e usar um Evento_Id novo.
6. WHEN o Consumidor aciona "Não, ainda não" duas ou mais vezes em sequência rápida, THE Sistema SHALL ter no máximo uma requisição de resolução em andamento.
7. WHEN o Consumidor volta à Tela_de_Pergunta_Final e aciona "Não, ainda não" para o mesmo problema da mesma Jornada_API que já tem Chamado_API em memória, THE Sistema SHALL navegar para `#/suporte/ID` sem nova requisição.
8. WHEN o Consumidor escolhe outro problema, THE Sistema SHALL descartar o Chamado_API e o estado do envio em memória.
9. IF a resposta da resolução `false` não traz `numero` em texto não vazio, THEN THE Gerente_de_Jornada SHALL tratá-la como falha de `tipo` `resposta`.
10. THE Gerente_de_Jornada SHALL descartar de `dados_solicitados` qualquer valor que não seja `telefone` ou `cep`.

### Requirement 9: Adaptar a Tela_de_Chamado ao Modo_API

**User Story:** Como consumidor, quero informar só o que a assistência precisa (telefone e, se pedido, CEP), para não repetir dados que a API não usa.

#### Acceptance Criteria

1. WHILE o Modo_API está ativo, THE Tela_de_Chamado SHALL ocultar os campos nome e e-mail, e o Sistema SHALL NOT validá-los, focá-los, incluí-los em `aria-describedby`, nem enviá-los.
2. WHILE o Modo_API está ativo e `telefone` está em Dados_Solicitados, THE Tela_de_Chamado SHALL exibir o campo telefone (WhatsApp) como obrigatório.
3. WHILE o Modo_API está ativo e `cep` está em Dados_Solicitados, THE Tela_de_Chamado SHALL exibir o campo CEP como obrigatório, e WHILE `cep` não está em Dados_Solicitados, THE Tela_de_Chamado SHALL ocultá-lo.
4. THE Sistema SHALL considerar válido o CEP que tenha apenas dígitos, espaços, parênteses e hífen e exatamente 8 dígitos, e SHALL enviar ao Back_end somente os 8 dígitos.
5. THE Sistema SHALL enviar o telefone ao Back_end somente com dígitos, em 10 ou 11 dígitos, depois de validado pela regra atual do Sistema.
6. THE Tela_de_Chamado SHALL manter o campo descrição com as regras atuais (de 10 a 500 caracteres, contador "N de 500 caracteres").
7. WHERE a Tela_de_Chamado exibe ao menos um campo de contato, THE Tela_de_Chamado SHALL exibir o aceite dos termos como obrigatório; WHERE não exibe nenhum campo de contato (Dados_Solicitados vazio), THE Tela_de_Chamado SHALL ocultar o aceite e o botão "Ler os termos".
8. WHILE o Modo_API está ativo, THE Tela_de_Chamado SHALL exibir o Prazo_da_API e o rótulo de prioridade no lugar da frase de prazo ilustrativo (`PRAZO_RETORNO_DIAS_UTEIS`).
9. WHILE o Modo_API está ativo, THE Tela_de_Chamado SHALL usar o título e o texto do botão de envio de `TRES_DATA.API.textos`, que não afirmam que o chamado "será aberto" nem pedem nome e e-mail.
10. WHILE o Modo_Prototipo está ativo, THE Tela_de_Chamado SHALL manter os campos, os textos e as validações atuais, com o campo CEP oculto.
11. IF a rota `#/suporte/ID` é aberta em Modo_API sem Chamado_API em memória (por exemplo, depois de recarregar a página), THEN THE Sistema SHALL redirecionar para `#/confirma/ID`.

### Requirement 10: Enviar contato e mensagem sem duplicar

**User Story:** Como consumidor, quero que meu contato e minha descrição cheguem uma só vez ao atendimento, mesmo que a rede falhe no meio, para não ser chamado em duplicidade nem perder o texto.

#### Acceptance Criteria

1. WHEN o Consumidor aciona "enviar" com o formulário válido em Modo_API, THE Sistema SHALL mudar o estado para "enviando" antes de qualquer espera, de modo que cliques repetidos gerem no máximo um envio.
2. WHILE Dados_Solicitados não está vazio e o contato ainda não foi aceito com os valores atuais, THE Gerente_de_Jornada SHALL enviar `POST /chamados/{numero}/contato` com `consentimento` igual a `true`, `evento_id` e somente os campos solicitados e preenchidos (`telefone` e `cep`, com dígitos).
3. WHEN o contato é aceito, ou Dados_Solicitados está vazio, THE Gerente_de_Jornada SHALL enviar `POST /chamados/{numero}/mensagens` com `texto` igual à descrição normalizada e `evento_id`.
4. WHEN a mensagem é aceita (status 201, ou 200 com `registrada` igual a `false`), THE Sistema SHALL guardar o chamado aberto em memória e navegar, por `location.replace`, para `#/chamado/ID`.
5. IF o contato é aceito e a mensagem falha, THEN THE Sistema SHALL exibir o bloco de falha com os contatos diretos, preservar todos os valores digitados e, na nova tentativa, SHALL NOT reenviar o contato enquanto telefone e CEP forem os mesmos já aceitos.
6. IF o contato falha, THEN THE Gerente_de_Jornada SHALL NOT enviar a mensagem, e a nova tentativa SHALL reenviar o contato.
7. WHEN a nova tentativa da mensagem ocorre com o mesmo texto normalizado, THE Gerente_de_Jornada SHALL reutilizar o Evento_Id da mensagem; WHEN o texto normalizado mudou desde a tentativa anterior, THE Gerente_de_Jornada SHALL usar um Evento_Id novo.
8. IF o Back_end responde 422 ao contato com `campos` que apontam `telefone`, `cep` ou `consentimento`, THEN THE Sistema SHALL mostrar o erro de validação padrão do campo correspondente (texto de `data.js`, nunca o texto do Back_end) e mover o foco para o primeiro campo com erro.
9. THE Sistema SHALL NOT incluir telefone, CEP ou texto da descrição na URL, nos cabeçalhos, no console, no `localStorage`, no `sessionStorage`, em cookies nem no Registro_de_Metricas.
10. IF a requisição falha por qualquer outro motivo, THEN THE Sistema SHALL exibir a mensagem de falha única de `data.js`, sem detalhe técnico, e reabilitar o formulário.

### Requirement 11: Mostrar a confirmação com os dados da API

**User Story:** Como consumidor, quero ver o número do chamado, o prazo e o próximo passo informados pelo atendimento, para ter uma expectativa real.

#### Acceptance Criteria

1. WHILE o Modo_API está ativo, THE Tela_de_Confirmacao SHALL exibir o `numero` do Chamado_API no lugar do protocolo local.
2. WHILE o Modo_API está ativo, THE Tela_de_Confirmacao SHALL exibir o `prioridade_rotulo`, o Prazo_da_API e o `proximo_passo`, cada um como texto literal, e SHALL ocultar o elemento de um valor ausente ou vazio.
3. WHILE o Modo_API está ativo, THE Tela_de_Confirmacao SHALL NOT exibir a frase de prazo ilustrativo (`PRAZO_RETORNO_DIAS_UTEIS`), o aviso de protótipo nem o e-mail.
4. WHILE o Modo_API está ativo e o telefone foi enviado, THE Tela_de_Confirmacao SHALL exibir o telefone informado como contato de WhatsApp.
5. THE Tela_de_Confirmacao SHALL manter os canais de contato direto (telefone e e-mail da 3corações) e o título de sucesso.
6. WHILE o Modo_Prototipo está ativo, THE Tela_de_Confirmacao SHALL manter protocolo local, prazo ilustrativo, aviso de protótipo e e-mail como hoje.
7. THE Sistema SHALL NOT exibir o texto `undefined`, `null` ou `[object Object]` em nenhum campo da Tela_de_Confirmacao.

### Requirement 12: Enviar nota e comentário em um único envio na Tela_de_Resolvido

**User Story:** Como consumidor que resolveu o problema, quero dar minha nota e, se quiser, um comentário, de uma vez, para que a avaliação chegue completa ao time.

#### Acceptance Criteria

1. WHILE o Modo_API está ativo, WHEN o Consumidor toca uma estrela na Tela_de_Resolvido, THE Sistema SHALL apenas marcar a nota (`aria-pressed`), sem requisição de rede e sem evento local, até o envio.
2. WHILE o Modo_API está ativo, THE Tela_de_Resolvido SHALL manter o campo de comentário opcional (até 500 caracteres, contador e aviso de não identificação) e SHALL exibir o botão com o texto "Enviar avaliação" de `TRES_DATA.API.textos`.
3. IF o Consumidor aciona "Enviar avaliação" sem nota escolhida, THEN THE Sistema SHALL NOT enviar nada, SHALL exibir mensagem de erro em texto visível associada às estrelas, SHALL mover o foco para o grupo de estrelas e SHALL anunciar o erro em até 1 segundo.
4. WHEN o Consumidor aciona "Enviar avaliação" com nota de 1 a 5, THE Sistema SHALL enviar `POST /jornadas/{id}/avaliacao` com `nota`, `evento_id` e `comentario` somente quando o comentário normalizado não está vazio.
5. IF o comentário normalizado tem mais de 500 caracteres, THEN THE Sistema SHALL NOT enviar nada e SHALL exibir o erro de tamanho; THE campo SHALL truncar em 500 caracteres o texto digitado ou colado, como hoje.
6. WHILE o envio está em andamento, THE Sistema SHALL marcar o formulário com `aria-busy="true"`, desabilitar o botão e as estrelas, e ignorar novas ativações.
7. WHEN o Back_end responde 201 com `registrada` igual a `true`, ou 200 com `registrada` igual a `false`, THE Sistema SHALL exibir o mesmo agradecimento em `role="status"`, desabilitar nota, comentário e botão, e mover o foco para o agradecimento, sem mensagem de erro.
8. IF o envio falha, THEN THE Sistema SHALL exibir o bloco de falha em `role="alert"`, preservar a nota e o texto, reabilitar o formulário e usar o mesmo Evento_Id na nova tentativa.
9. THE Sistema SHALL aceitar uma avaliação por Jornada_API: depois do envio aceito, voltar a `#/resolvido/ID` na mesma Jornada_API SHALL mostrar o estado "já enviado".
10. WHEN o envio da avaliação é solicitado, THE Gerente_de_Jornada SHALL aguardar a resolução pendente e, se não há Jornada_API ativa, tentar criá-la; IF não consegue, THEN THE Sistema SHALL tratar como falha de envio (critério 8).
11. WHILE o Modo_Prototipo está ativo, THE Tela_de_Resolvido SHALL manter estrelas que gravam `avaliacao` ao toque e o comentário opcional independente da nota, como hoje.

### Requirement 13: Avaliar na Tela_de_Confirmacao pelo mesmo endpoint da jornada

**User Story:** Como consumidor que abriu um chamado, quero avaliar a ajuda até aqui, para que o atendimento saiba como foi.

#### Acceptance Criteria

1. WHILE o Modo_API está ativo, WHEN o Consumidor toca uma estrela na Tela_de_Confirmacao, THE Sistema SHALL enviar `POST /jornadas/{id}/avaliacao` com `nota` e `evento_id`, sem `comentario`, para a Jornada_API que originou o chamado.
2. WHEN o Back_end responde 201 com `registrada` igual a `true`, ou 200 com `registrada` igual a `false`, THE Sistema SHALL exibir o agradecimento de avaliação, travar as estrelas mostrando a nota enviada e anunciar o resultado.
3. IF o envio falha, THEN THE Sistema SHALL exibir mensagem de falha em texto visível, manter as estrelas habilitadas e usar o mesmo Evento_Id na nova tentativa com a mesma nota.
4. WHILE o envio está em andamento, THE Sistema SHALL ignorar novos toques nas estrelas.
5. WHILE o Modo_Prototipo está ativo, THE Tela_de_Confirmacao SHALL manter estrelas que gravam `avaliacao` com `desfecho` igual a `chamado` ao toque, como hoje.

### Requirement 14: Manter métricas locais sem dados pessoais

**User Story:** Como mantenedor, quero que as métricas locais continuem existindo e continuem sem dado pessoal, para medir a deflexão também sem back end.

#### Acceptance Criteria

1. WHILE o Modo_API está ativo, THE Sistema SHALL continuar gravando os eventos locais `modelo`, `problema`, `resolvido` e `suporte` nos mesmos momentos de hoje.
2. WHEN o envio do formulário do chamado é concluído em Modo_API, THE Sistema SHALL gravar o evento local `chamado` com `protocolo` igual ao `numero` do Chamado_API e `modo` igual a `api`.
3. WHEN uma avaliação é aceita pelo Back_end com `registrada` igual a `true`, THE Sistema SHALL gravar o evento local `avaliacao` com a nota e o `desfecho` (`resolvido` ou `chamado`), e, se havia comentário, o evento local `comentario`, sem o texto, sem a nota e sem tamanho.
4. THE Sistema SHALL NOT gravar no Registro_de_Metricas nome, e-mail, telefone, CEP, descrição, comentário, `jornada_id` nem Evento_Id.
5. THE `TRESMetricas.resumo()` SHALL manter `resolvidos`, `encaminhadosAoSuporte`, `deflexaoPercentual`, `porProblema`, `chamadosAbertos` e `comentarios` calculados como hoje.

### Requirement 15: Proteger privacidade e segurança

**User Story:** Como mantenedor, quero que nenhum dado pessoal vaze e que nada vindo da API execute na página, para que a integração seja segura mesmo com um back end que eu não controlo.

#### Acceptance Criteria

1. THE Sistema SHALL inserir na página todo texto vindo do Back_end (`numero`, `prioridade_rotulo`, `prazo`, `proximo_passo`) e do Consumidor somente por `textContent` ou `value`, e SHALL NOT usar `innerHTML`, `insertAdjacentHTML`, `outerHTML` nem `document.write` com esses dados.
2. THE Sistema SHALL NOT incluir no front end segredo, token, chave de API ou credencial; a BASE_URL é pública.
3. THE Sistema SHALL NOT escrever no console, na URL (exceto o número do chamado como segmento de caminho, que não é dado pessoal), em cookies nem no `sessionStorage` dado pessoal, `jornada_id` ou número do chamado.
4. THE Sistema SHALL guardar `jornada_id`, número do chamado, Dados_Solicitados e Evento_Ids somente em memória.
5. THE Sistema SHALL tratar como inválida, e não exibir, qualquer resposta cujo campo esperado não tenha o tipo esperado.
6. THE Sistema SHALL exibir ao Consumidor somente textos de `data.js` em caso de falha, nunca o texto, o status ou o código recebidos do Back_end.
7. THE Cliente_API SHALL NOT registrar log, e o arquivo `js/api.js` SHALL NOT conter `console.*` nem `require(`.
8. IF o `js/api.js` não carregou (`window.TRESApi` ausente), THEN THE Sistema SHALL operar em Modo_Prototipo sem erro de script.

### Requirement 16: Preservar o Modo_Prototipo e os testes atuais

**User Story:** Como mantenedor, quero que ligar a integração não quebre nada do que já existe, para entregar o protótipo mesmo se o back end não estiver disponível.

#### Acceptance Criteria

1. WHILE a BASE_URL está vazia, THE Sistema SHALL manter rotas, telas, textos, eventos locais, chaves de armazenamento e comportamento exatamente como antes desta funcionalidade, sem nenhuma requisição nova.
2. THE `index.html` SHALL carregar os scripts na ordem `js/data.js`, `js/chamado.js`, `js/feedback.js`, `js/api.js`, `js/app.js`.
3. THE Sistema SHALL NOT alterar o comportamento de `js/chamado.js` e de `js/feedback.js`; mudanças nesses arquivos SHALL ser apenas aditivas e só quando necessárias.
4. THE Sistema SHALL NOT alterar nenhuma regra de `css/styles.css` existente; as regras novas SHALL ficar depois do marcador das regras novas já usado pelo teste estático.
5. THE Sistema SHALL NOT adicionar dependência, biblioteca, fonte, script de terceiros nem `package.json` na raiz do site.
6. THE Sistema SHALL NOT alterar `material/`, `img/*.png` originais nem o `.glb` original.
7. WHEN os testes atuais rodam com a BASE_URL vazia, THE suíte atual SHALL passar sem mudança, exceto as asserções que dependem da lista de scripts do `index.html`, da lista de arquivos do núcleo e do formato de `TRES_DATA`, que são atualizadas por tarefas próprias.
8. THE spec SHALL registrar como mudanças deliberadas em requisitos anteriores, válidas só em Modo_API: nome e e-mail deixam de ser pedidos (ticket-opening-screen); protocolo, prazo e aviso passam a vir da API (ticket-opening-screen); estrela e comentário passam a um único envio, com nota obrigatória (resolved-feedback-comment).

### Requirement 17: Desenvolver localmente sem CORS

**User Story:** Como desenvolvedor, quero subir o site e a API local deles na mesma origem, para testar a integração sem configurar CORS.

#### Acceptance Criteria

1. THE Proxy_de_Desenvolvimento SHALL ser o arquivo `dev/servir-com-api.js`, escrito para Node sem dependências (somente módulos nativos), fora da pasta `js/` e fora do site.
2. THE Proxy_de_Desenvolvimento SHALL servir os arquivos estáticos da raiz do projeto apenas para `GET` e `HEAD`, com o tipo MIME correto, e SHALL recusar com 404 caminhos com `..`, arquivos e pastas iniciados por ponto e as pastas `tests`, `dev`, `.kiro` e `node_modules`.
3. THE Proxy_de_Desenvolvimento SHALL repassar toda requisição cujo caminho começa por `/api` ou `/midia` para a API local, preservando método, caminho, consulta, cabeçalhos úteis e corpo, e devolver status, cabeçalhos e corpo da resposta.
4. IF a API local não responde, THEN THE Proxy_de_Desenvolvimento SHALL responder 502 com um JSON `{ "erro": { "codigo": "api_indisponivel", "mensagem": ... } }` e SHALL continuar em execução.
5. THE Proxy_de_Desenvolvimento SHALL aceitar `--porta` (padrão 8080), `--api-porta` (padrão 8001) e `--host` (padrão 127.0.0.1), e SHALL NOT usar a porta 8000 como padrão.
6. WHERE a opção `--sem-injecao` não é informada, THE Proxy_de_Desenvolvimento SHALL entregar `js/data.js` com `BASE_URL` preenchida, em memória, com `http://<host>:<porta>/api/pub`, sem alterar o arquivo em disco.
7. THE documentação em `dev/LEIAME.md` SHALL explicar como clonar o repositório da API, criar o ambiente virtual, instalar as dependências, subir `python scripts/dev_local.py --porta 8001`, subir o Proxy_de_Desenvolvimento e abrir o site, e SHALL explicar que em produção o site e a API ficam no mesmo domínio.
8. THE Proxy_de_Desenvolvimento SHALL NOT registrar corpo de requisição nem cabeçalhos em log; o log SHALL conter no máximo método, caminho sem consulta e status.
9. THE Proxy_de_Desenvolvimento SHALL encerrar de forma limpa ao receber SIGINT.

### Requirement 18: Cobrir a integração com testes automatizados

**User Story:** Como mantenedor, quero testes que provem o contrato de cada chamada e os fluxos de tela, para mudar o front sem medo de quebrar a integração.

#### Acceptance Criteria

1. THE suíte do núcleo SHALL testar `js/api.js` com `fast-check` e um `fetch` falso: cliente (cabeçalhos, corpo, rotas exatas, tempo limite), ULID, mapeamento de erros, idempotência e o Gerente_de_Jornada.
2. THE `tests/ui/servidor-teste.js` SHALL implementar a API_Falsa das rotas de `/api/pub` usadas por esta spec, com os contratos de sucesso, erro 500, 409, resposta lenta e sem resposta, e com registro das requisições recebidas.
3. THE suíte de interface SHALL cobrir: jornada e eventos do guia; "Sim" encerra e avalia; "Não" cria chamado, contato e mensagem, e confirmação com número e prazo da API; falhas e retentativas; falha parcial; e BASE_URL vazia sem nenhuma requisição nova.
4. THE `tests/estatico.js` SHALL incluir `js/api.js` nas verificações de ausência de `console.*`, de HTML dinâmico, de `require(` e de núcleo puro, e SHALL conferir que nenhuma frase de `API.textos` está escrita fora de `data.js`.
5. THE `tests/smoke.test.js` SHALL carregar `js/api.js` e conferir sua API pública.
6. THE `tests/dados.test.js` SHALL conferir que `API.BASE_URL` é vazia, que as URLs antigas continuam vazias e que cada `null` do Mapeamento_de_Modelos está marcado `PENDENTE`.
7. THE suíte SHALL ser executável com `npm test` (dentro de `tests/`) e com `node tests/ui/rodar.js`, em série.
8. THE `tests/ui/roteiro-manual.md` SHALL ganhar uma seção da integração com os itens não verificados pela automação.

### Requirement 19: Documentar e registrar pendências

**User Story:** Como pessoa que retoma o projeto, quero ler o que mudou e o que ainda não foi verificado, para não assumir que a integração funciona contra o back end real.

#### Acceptance Criteria

1. THE `CONTEXTO-PROJETO.md` SHALL ganhar uma seção da integração com a API: abordagem, modos, precedência, arquivos, mapeamento de modelos, fluxo, métricas, como rodar com o Proxy_de_Desenvolvimento e como rodar os testes.
2. THE `CONTEXTO-PROJETO.md` SHALL registrar como `PENDENTE` ou não verificado: o back end real, CORS e autorização de origem na AWS, o mapeamento dos modelos LOV, Modo, Luna e Touch, o conteúdo de exemplo da API contra o oficial, a tela de acompanhamento e "Sim" depois de "Não".
3. THE `CONTEXTO-PROJETO.md` SHALL registrar as mudanças deliberadas em requisitos anteriores (requisito 16, critério 8).
4. THE `js/data.js` SHALL marcar com `PENDENTE` ou `ILUSTRATIVO` o ambiente da BASE_URL, o tempo limite, cada `null` do mapeamento e cada texto de `API.textos`.
5. THE documentação SHALL NOT afirmar que a integração funciona contra o back end real enquanto isso não tiver sido verificado.

### Requirement 20: Acompanhar o chamado (opcional, fora do núcleo)

**User Story:** Como consumidor com chamado aberto, quero ver as mensagens do atendimento e responder, para acompanhar sem ligar.

#### Acceptance Criteria

1. WHERE `TRES_DATA.API.ACOMPANHAMENTO_HABILITADO` é `true` e o Modo_API está ativo, THE Sistema SHALL oferecer a rota `#/acompanhar/NUMERO` que consulta `GET /chamados/{numero}`.
2. WHERE o acompanhamento está habilitado, THE Tela_de_Acompanhamento SHALL exibir status, prioridade, `prazo`/agendamento quando houver e a lista de mensagens com autor e data, tudo por `textContent`.
3. WHERE o acompanhamento está habilitado, THE Tela_de_Acompanhamento SHALL permitir enviar uma resposta de 1 a 2000 caracteres por `POST /chamados/{numero}/mensagens`, com Evento_Id reutilizado na retentativa.
4. IF o chamado não existe (404 `chamado_nao_encontrado`) ou a consulta falha, THEN THE Tela_de_Acompanhamento SHALL exibir mensagem de `data.js` com os contatos diretos.
5. WHERE `ACOMPANHAMENTO_HABILITADO` é `false` (padrão), THE Sistema SHALL NOT registrar a rota `#/acompanhar/NUMERO` e SHALL tratá-la como rota desconhecida (volta a `#/`).
