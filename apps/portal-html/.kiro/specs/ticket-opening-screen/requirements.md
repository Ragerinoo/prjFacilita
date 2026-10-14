# Requirements Document

## Introduction

Hoje, quando o consumidor responde "Não, ainda não" em "O problema foi solucionado?", a jornada do Autoatendimento TRES termina na rota `#/suporte/ID`, que aponta para o atendimento humano: telefone 0800, horários, e-mail, "o que ter em mãos" e avaliação por estrelas.

Esta funcionalidade substitui esse desfecho por uma **tela de abertura de chamado**. Em vez de mandar o cliente procurar o atendimento, a página:

- comunica que um chamado será aberto;
- mostra o resumo do que o cliente já fez na jornada (modelo, problema e passos percorridos);
- pede apenas nome, e-mail, telefone (que será usado como número de WhatsApp) e uma breve descrição do que acontece com a máquina, mais o aceite dos termos para envio dos dados;
- informa que o time responsável receberá o chamado, que o problema será analisado, e qual é o prazo de retorno e por quais canais (WhatsApp e e-mail) o contato será feito;
- ao enviar, mostra uma confirmação com número de protocolo, prazo de retorno, canais de retorno e a avaliação por estrelas.

O projeto é uma landing page em HTML, CSS e JS puros, sem build, mobile primeiro. Um back end está sendo desenvolvido em paralelo e o banco de dados será implementado depois. Por isso o envio do chamado passa por uma **camada de envio** (Ponto_de_Integracao) com contrato claro e dois modos de operação:

- **Modo_Prototipo** (padrão, enquanto `API_CHAMADOS_URL` não estiver configurada): grava o chamado no `localStorage` e exibe o aviso de protótipo;
- **Modo_API** (quando `API_CHAMADOS_URL` estiver configurada): envia um `POST` com JSON ao back end, trata falhas com retentativa manual e usa o protocolo devolvido pelo back end.

O que ainda depende de decisão externa (prazo real, texto jurídico dos termos, esquema do banco, autenticação e CORS do back end) está descrito na seção "Premissas e pontos em aberto".

### Escopo

Dentro do escopo:
- a tela de abertura de chamado (rota `#/suporte/ID`), com aceite dos termos e botão ilustrativo "Ler os termos";
- a tela de confirmação com protocolo, prazo de retorno, canais de retorno e avaliação por estrelas;
- o registro de passos percorridos na jornada;
- a camada de envio (contrato do payload, Modo_Prototipo, Modo_API, idempotência), o registro local do chamado em Modo_Prototipo e as métricas de deflexão;
- a configuração em `js/data.js` de `API_CHAMADOS_URL`, do prazo de retorno e de todos os textos novos.

Fora do escopo:
- implementação do back end e do banco de dados, autenticação e CORS do back end (apenas o cliente e o contrato do payload);
- envio real de WhatsApp ou de e-mail ao consumidor;
- texto jurídico dos termos de uso e da política de privacidade;
- painel de acompanhamento do chamado;
- alteração do cabeçalho ("Falar com a gente"), do rodapé e da rota `#/contato`;
- alteração de `material/`, de `img/*.png` originais e do `.glb` original;
- criação de conteúdo novo de instruções de máquina.

## Premissas e pontos em aberto

Estas premissas precisam ser validadas pelo time de Customer Success, pelo time de back end e pelo time responsável pelo atendimento antes de uma prova de conceito (POC) real.

- **P1. Dois modos de envio (premissa principal).** O envio passa pelo Ponto_de_Integracao. Em **Modo_Prototipo**, "abrir o chamado" significa gravar o registro no `localStorage` do navegador e exibir um protocolo gerado localmente; nenhum time recebe o chamado de fato e a confirmação exibe o aviso de protótipo. Em **Modo_API**, o chamado é enviado ao back end e a confirmação não exibe o aviso de protótipo.
- **P2. Protocolo.** Em Modo_Prototipo, o protocolo é gerado no navegador e não vem de um sistema oficial. Em Modo_API, o protocolo é o devolvido pelo back end; o protocolo local nunca é usado como substituto em Modo_API.
- **P3. "Passos percorridos" significa passos exibidos.** A página sabe quais passos foram mostrados ao cliente, mas não sabe se o cliente os executou. O texto da tela deve refletir isso.
- **P4. Prazo e canais de retorno (prazo ilustrativo).** O usuário autorizou um prazo **fictício** de **2 dias úteis**, configurável em `js/data.js` por `PRAZO_RETORNO_DIAS_UTEIS`. O valor é **ilustrativo e `PENDENTE` de validação pelo Customer Success**. Os canais de retorno são WhatsApp (no número informado em Telefone) e e-mail. Que o time consegue, de fato, cumprir esse prazo e usar esses canais também é `PENDENTE`. Antes de ativar o Modo_API em produção, o prazo precisa ser validado, pois deixa de ser ilustrativo.
- **P5. Termos e consentimento.** Não existe texto jurídico dos termos. A tela usa um controle de aceite obrigatório e um botão "Ler os termos" **meramente ilustrativo, que não abre texto algum**. O controlador dos dados, o contato do titular e a URL da política de privacidade ficam `PENDENTE` em `js/data.js`. A base legal e a adequação à LGPD dependem de validação jurídica.
- **P6. Avaliação por estrelas.** A avaliação sai da Tela_de_Chamado e passa a ficar na Tela_de_Confirmacao, reaproveitando o mesmo componente e o mesmo registro no Registro_de_Metricas usados na tela de problema resolvido.
- **P7. Estado em memória.** A máquina escolhida, os passos exibidos, os valores do formulário e o chamado aberto ficam só em memória. Se o cliente recarregar a página, o modelo aparece como "Não informado", nenhum passo é listado e o formulário volta vazio. Persistir a jornada em `sessionStorage` é uma possível evolução, fora deste escopo.
- **P8. Contato de fallback.** Se o registro do chamado falhar, a tela indica o telefone e o e-mail já existentes em `CONTATO` como alternativa. Este é o único caso em que a Tela_de_Chamado aponta para o atendimento.
- **P9. Back end em desenvolvimento paralelo (a alinhar com o time de back end).** O contrato do Payload_do_Chamado definido aqui é **do lado do cliente** e não depende do esquema do banco. Ficam como pontos em aberto, sem definição neste documento:
  - esquema do banco de dados (será implementado depois);
  - autenticação e autorização do endpoint (o front end não guarda segredo, token nem chave de API);
  - política de CORS do endpoint e URL do endpoint por ambiente;
  - formato exato da resposta de sucesso (o cliente espera o campo `protocolo`) e códigos HTTP de erro;
  - tratamento de chave de idempotência repetida (por exemplo, devolver o mesmo protocolo);
  - se o back end também quer a chave de idempotência em cabeçalho HTTP, além do campo do payload;
  - formato do telefone (o cliente envia somente dígitos, sem DDI; o back end pode exigir E.164);
  - se o número de WhatsApp deve ser restrito a celular (11 dígitos); o cliente aceita 10 ou 11 dígitos;
  - limites de tamanho, limitação de taxa e prazo de retenção dos dados;
  - valor do tempo limite de envio (`TIMEOUT_ENVIO_MS`, inicialmente 10 000 ms, ilustrativo).
- **P10. Dados pessoais em trânsito.** Em Modo_API, os dados pessoais trafegam do navegador ao back end. O cliente aceita somente endpoint `https`, ou `http` em `localhost` e `127.0.0.1` para desenvolvimento.

## Glossary

- **Sistema**: a página Autoatendimento TRES (HTML, CSS e JS puros) executada no navegador do consumidor.
- **Tela_de_Chamado**: a tela exibida na rota `#/suporte/ID` quando o consumidor responde "Não, ainda não" em "O problema foi solucionado?". Substitui a antiga tela de assistência técnica.
- **Tela_de_Confirmacao**: a tela exibida depois que o chamado é registrado com sucesso, com o protocolo, o prazo de retorno, os canais de retorno e a avaliação por estrelas.
- **Consumidor**: a pessoa que usa a jornada, em geral em pé na frente da máquina, com o celular.
- **Jornada**: o percurso modelo, problema, passos e confirmação "O problema foi solucionado?".
- **Resumo_da_Jornada**: bloco da Tela_de_Chamado com modelo da máquina, problema selecionado e passos percorridos.
- **Passo_Percorrido**: passo da solução do problema selecionado que o Sistema exibiu ao Consumidor durante a Jornada.
- **Formulario_de_Chamado**: formulário da Tela_de_Chamado com os campos Nome, Email, Telefone e Descricao e o Aceite_dos_Termos.
- **Nome**: campo de texto com o nome do Consumidor.
- **Email**: campo com o endereço de e-mail do Consumidor.
- **Telefone**: campo com o telefone do Consumidor, com DDD, de rótulo "Telefone (WhatsApp)". O número informado é tratado como o número de WhatsApp do Consumidor.
- **Descricao**: campo de texto livre com a breve descrição do que está acontecendo com a máquina.
- **Aceite_dos_Termos**: caixa de seleção (`checkbox`) obrigatória, de rótulo "Li e concordo com os termos para envio dos meus dados". Não é um campo de dados pessoais.
- **Botao_Ler_Termos**: botão "Ler os termos", meramente ilustrativo, que não abre texto de termos.
- **Mensagem_de_Termos_em_Elaboracao**: texto curto "Texto dos termos em elaboração", exibido quando o Botao_Ler_Termos é acionado.
- **Chamado**: registro com os dados do Formulario_de_Chamado, o aceite dos termos, o Resumo_da_Jornada, a Chave_de_Idempotencia, a data e hora de abertura e, depois do sucesso do envio, o Protocolo.
- **Protocolo**: identificador do Chamado. Em Modo_Prototipo, tem o formato `TRES-AAAAMMDD-XXXXXX`, em que `AAAAMMDD` é a data de abertura e `XXXXXX` são 6 caracteres alfanuméricos maiúsculos. Em Modo_API, é o valor devolvido pelo Back_end.
- **Chave_de_Idempotencia**: identificador único gerado no navegador para uma tentativa de abrir um Chamado, reutilizado em todas as retentativas dela, para evitar Chamados duplicados.
- **Payload_do_Chamado**: o objeto JSON enviado ao Back_end em Modo_API, conforme o requisito 10, independente do esquema do banco de dados.
- **Back_end**: o serviço em desenvolvimento paralelo que recebe o Payload_do_Chamado.
- **API_CHAMADOS_URL**: constante de `js/data.js` com a URL do endpoint do Back_end, vazia por padrão.
- **Modo_Prototipo**: modo de envio ativo quando `API_CHAMADOS_URL` está ausente, vazia ou inválida; o envio é simulado e gravado no Repositorio_de_Chamados.
- **Modo_API**: modo de envio ativo quando `API_CHAMADOS_URL` é uma URL válida conforme o requisito 7; o Chamado é enviado ao Back_end por `POST` com JSON.
- **Prazo_de_Retorno**: prazo em dias úteis para o time responsável retornar ao Consumidor, definido por `PRAZO_RETORNO_DIAS_UTEIS` em `js/data.js` (inicialmente 2, ilustrativo).
- **Canais_de_Retorno**: os canais pelos quais o Consumidor será contatado: WhatsApp, no número de Telefone, e e-mail, no endereço de Email.
- **Aviso_de_Prototipo**: texto exibido na Tela_de_Confirmacao somente em Modo_Prototipo, informando que o chamado foi simulado.
- **Repositorio_de_Chamados**: o armazenamento dos Chamados no `localStorage`, na chave `tres-autoatendimento-chamados`, com no máximo 50 registros, usado somente em Modo_Prototipo.
- **Registro_de_Metricas**: o armazenamento de eventos existente no `localStorage`, na chave `tres-autoatendimento-eventos`, com no máximo 500 eventos, consultado por `TRESMetricas`.
- **Ponto_de_Integracao**: a camada de envio do Sistema: função única e substituível que entrega o Chamado ao destino conforme o modo ativo (Modo_Prototipo ou Modo_API) e devolve, de forma assíncrona, o Protocolo ou uma falha.
- **Aviso_de_Privacidade**: texto curto exibido na Tela_de_Chamado sobre a finalidade do uso dos dados pessoais informados.
- **Componente_de_Avaliacao**: o componente de avaliação por estrelas (5 botões de 1 a 5) já existente na tela de problema resolvido.
- **Alvo_de_Toque**: área clicável ou tocável de um controle.
- **Leitor_de_Tela**: tecnologia assistiva que lê o conteúdo da página em voz alta.

## Requirements

### Requirement 1: Comunicar que um chamado será aberto

**User Story:** Como consumidor que não resolveu o problema, quero ver que um chamado será aberto para mim, para que eu entenda o próximo passo sem precisar ligar para ninguém.

#### Acceptance Criteria

1. WHEN o Consumidor responde "Não, ainda não" em "O problema foi solucionado?", THE Sistema SHALL exibir a Tela_de_Chamado na rota `#/suporte/ID`, em que `ID` é o identificador do problema selecionado, e SHALL ocultar a tela de confirmação "O problema foi solucionado?".
2. THE Tela_de_Chamado SHALL exibir um título em `h1`, com 1 a 80 caracteres, cujo texto contém os termos "chamado" e "aberto" e informa que um chamado será aberto.
3. THE Tela_de_Chamado SHALL exibir um texto com 1 a 300 caracteres que informa, ao mesmo tempo, que o time responsável receberá o chamado e que o problema será analisado.
4. THE Tela_de_Chamado SHALL apresentar uma única instância do Formulario_de_Chamado e SHALL omitir da área de conteúdo principal qualquer outro link ou botão de contato com o atendimento, seja por telefone, por e-mail ou para a tela de contato.
5. THE Tela_de_Chamado SHALL omitir da área de conteúdo principal, tanto visualmente quanto para leitores de tela, o telefone 0800, os horários de atendimento, o e-mail de atendimento de `CONTATO`, a lista "o que ter em mãos" e a avaliação por estrelas, com a única exceção do contato de alternativa exibido em caso de falha de registro (requisito 7, critério 14).
6. WHEN a Tela_de_Chamado é exibida por qualquer meio de navegação (resposta do Consumidor, botão voltar ou avançar do navegador, ou abertura direta da URL), THE Sistema SHALL mover o foco do teclado para o título (`h1`) da Tela_de_Chamado em até 300 ms, sem nenhuma ação adicional do Consumidor.
7. IF o `ID` da rota `#/suporte/ID` está ausente ou não corresponde a nenhum problema existente, THEN THE Sistema SHALL redirecionar o Consumidor para `#/problemas`, SHALL exibir a tela de problemas e SHALL NOT exibir nenhum conteúdo da Tela_de_Chamado.
8. THE Tela_de_Chamado SHALL exibir, acima do Aviso_de_Privacidade, uma linha de resumo com o Prazo_de_Retorno e os Canais_de_Retorno (WhatsApp e e-mail), formada pelos mesmos textos-base da Tela_de_Confirmacao e sujeita à regra de prazo ausente ou inválido do requisito 8, critério 9.

### Requirement 2: Mostrar o resumo do que o Consumidor já fez

**User Story:** Como consumidor, quero ver o que já fiz na jornada, para que eu confirme que meu esforço foi considerado e não precise repetir nada.

#### Acceptance Criteria

1. THE Tela_de_Chamado SHALL exibir o Resumo_da_Jornada imediatamente antes do Formulario_de_Chamado, de forma que o Resumo_da_Jornada apareça acima do Formulario_de_Chamado na ordem visual e na ordem de leitura, em qualquer largura de tela.
2. THE Resumo_da_Jornada SHALL exibir o nome do modelo da máquina escolhido pelo Consumidor, exatamente como definido em `js/data.js`.
3. IF o Consumidor não escolheu um modelo, THEN THE Resumo_da_Jornada SHALL exibir o texto "Não informado" no lugar do nome do modelo.
4. THE Resumo_da_Jornada SHALL exibir o título do problema selecionado, exatamente como definido em `js/data.js`.
5. THE Resumo_da_Jornada SHALL exibir cada Passo_Percorrido como um item distinto de uma lista, na mesma ordem em que os passos aparecem na solução do problema em `js/data.js`, usando o texto do passo sem alteração e sem truncá-lo.
6. IF nenhum Passo_Percorrido foi registrado, THEN THE Resumo_da_Jornada SHALL exibir o texto "Nenhum passo registrado nesta visita" no lugar da lista de Passos_Percorridos.
7. THE Resumo_da_Jornada SHALL exibir a quantidade de Passos_Percorridos em relação ao total de passos do problema no formato "X de Y passos", em que X é um número inteiro de 0 até Y e Y é o total de passos do problema em `js/data.js`, inclusive quando X for 0.
8. THE Resumo_da_Jornada SHALL exibir, acima da lista de Passos_Percorridos, um rótulo que descreva os itens como passos apresentados ao Consumidor, sem usar palavras que afirmem execução pelo Consumidor, como "feito", "executado", "realizado" ou "concluído".
9. WHILE a largura da viewport é de até 480 px, THE Resumo_da_Jornada SHALL exibir a lista de Passos_Percorridos recolhida ao carregar a Tela_de_Chamado, mantendo visíveis o nome do modelo, o título do problema e o texto "X de Y passos".
10. THE Sistema SHALL exibir no Resumo_da_Jornada somente conteúdo já existente em `js/data.js`, sem criar nem reescrever instruções de máquina e sem exibir o conteúdo dos guias "Como fazer" vinculados aos passos.
11. WHILE a largura da viewport é de até 480 px, WHEN o Consumidor aciona o controle de expandir ou recolher a lista de Passos_Percorridos, THE Resumo_da_Jornada SHALL alternar a lista entre recolhida e expandida em até 300 ms, mantendo o controle operável por toque (alvo de pelo menos 44 px de altura e de largura) e por teclado (teclas Enter e Espaço).
12. WHILE a largura da viewport é maior que 480 px, THE Resumo_da_Jornada SHALL exibir a lista de Passos_Percorridos sempre expandida, sem controle de expandir ou recolher.
13. IF o Consumidor chega à Tela_de_Chamado sem um problema selecionado ou com um problema que não existe em `js/data.js`, THEN THE Resumo_da_Jornada SHALL exibir o texto "Não informado" no lugar do título do problema, o texto "Nenhum passo registrado nesta visita" no lugar da lista e o texto "0 de 0 passos", sem exibir erro técnico e sem bloquear o Formulario_de_Chamado.

### Requirement 3: Registrar os passos percorridos

**User Story:** Como time de atendimento, quero saber quais passos o consumidor viu, para que eu não peça que ele repita o que já foi apresentado.

#### Acceptance Criteria

1. WHEN o Sistema exibe um passo da solução de um problema (inclusive o primeiro passo ao abrir a tela de solução), THE Sistema SHALL registrar esse passo como Passo_Percorrido do problema selecionado, identificado pelo problema e pela posição do passo (de 1 até o total de passos do problema).
2. WHEN o Consumidor usa "Anterior" ou "Rever os passos", THE Sistema SHALL manter todos os Passos_Percorridos já registrados do mesmo problema, sem remover nem reordenar nenhum deles.
3. WHEN o Consumidor seleciona um problema diferente do problema selecionado anteriormente, THE Sistema SHALL descartar os Passos_Percorridos do problema anterior e iniciar uma lista vazia de Passos_Percorridos para o novo problema, antes de registrar o primeiro passo exibido dele.
4. THE Sistema SHALL registrar cada passo no máximo uma vez por problema selecionado, de modo que a lista de Passos_Percorridos de um problema tenha no máximo tantas entradas quanto o total de passos desse problema, mesmo que o Consumidor exiba o mesmo passo mais de uma vez.
5. WHEN o Consumidor segue o link "Ver solução de" para outro problema, THE Sistema SHALL tratar o problema de destino como o problema selecionado, descartar os Passos_Percorridos do problema anterior e iniciar uma lista vazia de Passos_Percorridos para ele, antes de registrar o primeiro passo exibido do problema de destino.
6. WHEN o Consumidor seleciona na lista de problemas o mesmo problema que já está selecionado, THE Sistema SHALL manter os Passos_Percorridos já registrados desse problema.
7. WHEN a página é recarregada ou o Consumidor reinicia a jornada de atendimento, THE Sistema SHALL iniciar com a lista de Passos_Percorridos vazia, sem reaproveitar registros de jornadas anteriores.

### Requirement 4: Coletar apenas os dados necessários

**User Story:** Como consumidor, quero informar só o essencial, para que abrir o chamado seja rápido no celular.

#### Acceptance Criteria

1. THE Formulario_de_Chamado SHALL conter exatamente quatro campos de dados (Nome, Email, Telefone e Descricao) mais o Aceite_dos_Termos, sem nenhum outro campo visível ou editável pelo Consumidor.
2. THE Formulario_de_Chamado SHALL exibir a indicação escrita "obrigatório" dentro do rótulo de cada um dos quatro campos de dados e do Aceite_dos_Termos, e SHALL tratar esses cinco controles como obrigatórios.
3. THE Formulario_de_Chamado SHALL exibir, para cada campo de dados, um rótulo de texto permanentemente visível, associado programaticamente ao campo, de modo que o rótulo continue visível enquanto o campo estiver preenchido ou com foco.
4. THE Formulario_de_Chamado SHALL apresentar os controles, de cima para baixo, na ordem Nome, Email, Telefone, Descricao, Aceite_dos_Termos e botão "Abrir meu chamado", e essa ordem SHALL ser a mesma ordem de navegação por teclado (Tab), com o Botao_Ler_Termos entre o Aceite_dos_Termos e o botão "Abrir meu chamado".
5. THE Campo Email SHALL usar o tipo de entrada de e-mail, para que o teclado do celular exiba os caracteres de e-mail.
6. THE Campo Telefone SHALL usar o tipo de entrada de telefone, para que o teclado do celular exiba o teclado numérico de telefone.
7. THE Formulario_de_Chamado SHALL declarar o atributo de preenchimento automático correspondente aos campos Nome (nome), Email (e-mail) e Telefone (telefone), e SHALL NOT declarar preenchimento automático para o campo Descricao.
8. THE Campo Nome SHALL aceitar no máximo 100 caracteres, THE Campo Email SHALL aceitar no máximo 254 caracteres e THE Campo Telefone SHALL aceitar no máximo 20 caracteres.
9. THE Campo Descricao SHALL exibir, abaixo do campo, um contador de caracteres no formato "N de 500 caracteres", em que N é o número de caracteres digitados, iniciando em "0 de 500 caracteres" e sendo atualizado a cada alteração do conteúdo, em até 100 ms.
10. IF o conteúdo do campo Descricao atingir 500 caracteres, THEN THE Formulario_de_Chamado SHALL impedir a inclusão de novos caracteres, truncar em 500 caracteres qualquer texto colado que exceda o limite, manter o contador em "500 de 500 caracteres" e preservar o texto já digitado.
11. THE Formulario_de_Chamado SHALL exibir um único botão de envio com o texto "Abrir meu chamado".
12. WHILE o Consumidor permanece na Tela_de_Chamado, THE Sistema SHALL manter em memória os valores já digitados nos quatro campos e o estado (marcado ou desmarcado) do Aceite_dos_Termos, inclusive após uma tentativa de envio rejeitada por validação ou por falha de registro e após mudança de orientação do dispositivo, sem apagar ou alterar nenhum valor.
13. THE Campo Telefone SHALL exibir o rótulo "Telefone (WhatsApp)" e, abaixo do campo, um texto de ajuda visível, associado ao campo por `aria-describedby`, que informa que o número deve ser informado com DDD e que será usado para o contato pelo WhatsApp.
14. WHEN a Tela_de_Chamado é exibida para uma nova Jornada, THE Aceite_dos_Termos SHALL estar desmarcado.

### Requirement 5: Validar os campos

**User Story:** Como consumidor, quero ser avisado de forma clara quando algum dado estiver incorreto, para que eu corrija e consiga enviar o chamado.

#### Acceptance Criteria

1. THE Sistema SHALL considerar o Nome válido quando, após remover espaços no início e no fim e reduzir sequências de espaços a um único espaço, o texto tiver de 3 a 100 caracteres e contiver ao menos uma letra (incluindo letras acentuadas).
2. THE Sistema SHALL considerar o Email válido quando, após remover espaços no início e no fim, o texto tiver no máximo 254 caracteres, contiver exatamente um caractere `@`, tiver parte local não vazia, não contiver espaços, e tiver domínio com ao menos um ponto, sem rótulos vazios (sem ponto no início ou no fim do domínio e sem dois pontos consecutivos) e com terminação de 2 ou mais letras, sem distinção entre maiúsculas e minúsculas.
3. THE Sistema SHALL considerar o Telefone válido quando, após remover os separadores permitidos no critério 4, o número tiver 10 ou 11 dígitos, o DDD (dois primeiros dígitos) estiver entre 11 e 99 e, no caso de 11 dígitos, o terceiro dígito for 9; o prefixo `55` SHALL ser removido somente quando o número tiver 12 ou 13 dígitos e começar com `55`, e um número de 12 ou 13 dígitos que não comece com `55` é inválido.
4. THE Sistema SHALL aceitar no Telefone apenas dígitos e os separadores parênteses, espaço, hífen, ponto e o sinal `+` no início; IF o Telefone contiver qualquer outro caractere (incluindo letras), THEN THE Sistema SHALL considerá-lo inválido.
5. THE Sistema SHALL considerar a Descricao válida quando, após remover espaços no início e no fim, o texto tiver de 10 a 500 caracteres.
6. WHEN o Consumidor aciona "Abrir meu chamado" e ao menos um dos campos Nome, Email, Telefone ou Descricao é inválido ou está vazio (inclusive contendo apenas espaços), ou o Aceite_dos_Termos está desmarcado, THE Sistema SHALL impedir o registro do Chamado, não gravar nenhum Chamado, não enviar nenhuma requisição ao Back_end e manter o Consumidor na tela de abertura.
7. WHEN o registro do Chamado é impedido por validação, THE Sistema SHALL exibir, em texto visível adjacente a cada controle inválido, uma mensagem de erro em português que indica o motivo (campo vazio ou formato inválido, ou aceite não marcado) e, para Nome e Descricao, os limites mínimo e máximo de caracteres.
8. WHEN o registro do Chamado é impedido por validação, THE Sistema SHALL mover o foco do teclado para o primeiro controle inválido, seguindo a ordem Nome, Email, Telefone, Descricao, Aceite_dos_Termos.
9. WHEN o registro do Chamado é impedido por validação, THE Sistema SHALL, em até 1 segundo, anunciar em uma região `aria-live` um texto em português que informa o número de itens com erro (de 1 a 5).
10. WHILE a mensagem de erro de um controle está exibida, THE Sistema SHALL manter nesse controle `aria-invalid="true"` e `aria-describedby` referenciando o elemento dessa mensagem (podendo referenciar também o texto de ajuda do controle).
11. WHEN o Consumidor sai de um dos quatro campos de dados (evento de perda de foco) cujo valor está vazio ou inválido, THE Sistema SHALL exibir a mensagem de erro desse campo.
12. WHEN o Consumidor altera o valor de um campo com erro exibido e o novo valor é válido, THE Sistema SHALL, em até 200 ms após a alteração, remover a mensagem de erro, o `aria-invalid` e a referência à mensagem em `aria-describedby` desse campo.
13. WHEN o Consumidor digita ou cola texto que faz a Descricao exceder 500 caracteres, THE Sistema SHALL manter somente os primeiros 500 caracteres no campo.
14. IF a validação impede o registro do Chamado, THEN THE Sistema SHALL manter em todos os campos exatamente os valores digitados pelo Consumidor, sem remover espaços nem alterar máscaras ou separadores, e SHALL manter o estado do Aceite_dos_Termos.
15. WHEN o Consumidor aciona "Abrir meu chamado", todos os campos são válidos e o Aceite_dos_Termos está marcado, THE Sistema SHALL prosseguir com o registro do Chamado sem exibir mensagens de erro de validação e sem anunciar contagem de erros.
16. IF o Aceite_dos_Termos está desmarcado quando o Consumidor aciona "Abrir meu chamado", THEN THE Sistema SHALL exibir, adjacente ao Aceite_dos_Termos, uma mensagem de erro em português informando que é preciso marcar que leu e concorda com os termos para enviar o chamado, e SHALL manter no Aceite_dos_Termos `aria-invalid="true"` e `aria-describedby` referenciando essa mensagem.
17. WHEN o Consumidor marca o Aceite_dos_Termos que está com erro exibido, THE Sistema SHALL, em até 200 ms após a marcação, remover a mensagem de erro, o `aria-invalid` e a referência à mensagem em `aria-describedby` desse controle.

### Requirement 6: Consentir com os termos e informar o uso dos dados pessoais

**User Story:** Como consumidor, quero saber para que meus dados serão usados e concordar de forma explícita antes de enviá-los, para que eu me sinta seguro ao informá-los.

#### Acceptance Criteria

1. WHILE a Tela_de_Chamado está aberta, THE Tela_de_Chamado SHALL exibir o Aviso_de_Privacidade no mesmo bloco do botão "Abrir meu chamado", acima do Aceite_dos_Termos e do botão, com o texto visível sem clique, toque, foco, hover ou expansão e com tamanho de fonte mínimo de 14 px.
2. THE Aviso_de_Privacidade SHALL informar que nome, e-mail, telefone e descrição são usados somente para abrir, analisar e responder ao chamado.
3. THE Aviso_de_Privacidade SHALL informar que o resumo da jornada percorrida pelo Consumidor será enviado junto ao chamado.
4. THE Aviso_de_Privacidade SHALL informar o nome do controlador dos dados e um contato (e-mail ou telefone) para o Consumidor exercer os direitos do titular.
5. WHERE existe uma URL de política de privacidade configurada em `js/data.js` com protocolo http ou https, THE Aviso_de_Privacidade SHALL exibir um link para essa política, que abre em nova aba com `rel="noopener noreferrer"`.
6. THE Formulario_de_Chamado SHALL exibir o Aceite_dos_Termos como uma caixa de seleção nativa (`input type="checkbox"`), desmarcada ao carregar, com o rótulo visível "Li e concordo com os termos para envio dos meus dados", associado programaticamente ao controle.
7. THE Formulario_de_Chamado SHALL exibir o Botao_Ler_Termos, com o texto "Ler os termos", imediatamente depois do Aceite_dos_Termos.
8. WHEN o Consumidor aciona o Botao_Ler_Termos, THE Sistema SHALL exibir a Mensagem_de_Termos_em_Elaboracao ("Texto dos termos em elaboração") adjacente ao botão, em uma região `role="status"` (`aria-live` educado), mantendo o foco no Botao_Ler_Termos e o estado do Aceite_dos_Termos inalterado.
9. WHEN o Botao_Ler_Termos é acionado, THE Sistema SHALL NOT navegar para outra rota, SHALL NOT abrir nova aba, nova janela ou diálogo modal e SHALL NOT alterar a URL da página.
10. WHEN o Botao_Ler_Termos é acionado mais de uma vez, THE Sistema SHALL manter uma única Mensagem_de_Termos_em_Elaboracao exibida, sem duplicá-la.
11. THE Sistema SHALL limitar o conteúdo relacionado aos termos ao rótulo do Aceite_dos_Termos, ao rótulo do Botao_Ler_Termos e à Mensagem_de_Termos_em_Elaboracao, sem exibir texto jurídico.
12. WHEN o Chamado é criado, THE Sistema SHALL registrar nele o aceite do Consumidor como o valor booleano `true` e a data e hora do aceite em formato ISO 8601 com data, hora e fuso horário, tomados no instante em que o envio válido é iniciado.
13. THE Sistema SHALL manter os dados pessoais (Nome, Email, Telefone e Descricao) fora de todos os campos do Registro_de_Metricas.
14. THE Sistema SHALL abster-se de gravar dados pessoais (Nome, Email, Telefone e Descricao) em qualquer local além do Repositorio_de_Chamados (somente em Modo_Prototipo) e do corpo da requisição ao Back_end (somente em Modo_API), incluindo outras chaves de localStorage, sessionStorage, cookies, IndexedDB, URL e console do navegador, inclusive quando o Consumidor sai da Tela_de_Chamado sem enviar o chamado.
15. THE Sistema SHALL manter o texto do Aviso_de_Privacidade, o rótulo do Aceite_dos_Termos, o rótulo do Botao_Ler_Termos, a Mensagem_de_Termos_em_Elaboracao, o controlador, o contato e a URL da política em `js/data.js`, com cada valor ainda não validado juridicamente marcado como `PENDENTE`.
16. IF o texto do Aviso_de_Privacidade, o controlador ou o contato estiver ausente ou vazio em `js/data.js`, THEN THE Aviso_de_Privacidade SHALL exibir o marcador `PENDENTE` no lugar do valor ausente, sem deixar nenhum campo do aviso em branco.
17. IF a URL da política de privacidade em `js/data.js` estiver ausente, vazia ou sem protocolo http ou https, THEN THE Aviso_de_Privacidade SHALL ser exibido sem o link para a política, sem link vazio ou quebrado.

### Requirement 7: Registrar e enviar o chamado (Modo_Prototipo e Modo_API)

**User Story:** Como consumidor, quero que meu chamado seja registrado com tudo o que informei, para que o time responsável tenha o contexto completo.

#### Acceptance Criteria

1. WHEN o Consumidor aciona "Abrir meu chamado", todos os campos passam na validação e o Aceite_dos_Termos está marcado, THE Sistema SHALL criar um Chamado e entregá-lo ao Ponto_de_Integracao.
2. THE Chamado SHALL conter Nome, Email, Telefone, Descricao, o aceite dos termos (booleano) e a data e hora do aceite, o modelo, o identificador e o título do problema, a lista de Passos_Percorridos (na ordem em que foram percorridos), o total de passos do problema, a Chave_de_Idempotencia, a data e hora de abertura em formato ISO 8601 com data, hora e fuso horário e, depois do sucesso do envio, o Protocolo.
3. THE Sistema SHALL gravar no Chamado o Nome sem espaços no início e no fim e com cada sequência de espaços internos reduzida a um único espaço, o Email com todos os caracteres em minúsculas e o Telefone contendo somente os dígitos de 0 a 9, sem nenhum outro caractere.
4. THE Sistema SHALL operar em Modo_API quando `API_CHAMADOS_URL` em `js/data.js` for um texto de URL com protocolo `https`, ou com protocolo `http` e host `localhost` ou `127.0.0.1`, e SHALL operar em Modo_Prototipo quando `API_CHAMADOS_URL` estiver ausente, vazia ou fora desse formato; THE Sistema SHALL entregar `API_CHAMADOS_URL` vazia por padrão.
5. WHILE Modo_Prototipo está ativo, THE Ponto_de_Integracao SHALL gerar o Protocolo localmente, gravar o Chamado no Repositorio_de_Chamados, preservando os Chamados já gravados, e só sinalizar sucesso ao Sistema depois que a gravação for concluída.
6. WHEN a gravação de um novo Chamado faria o Repositorio_de_Chamados ultrapassar 50 Chamados, THE Repositorio_de_Chamados SHALL descartar o Chamado de data e hora de abertura mais antiga, de modo que mantenha no máximo os 50 Chamados mais recentes.
7. THE Sistema SHALL expor o Ponto_de_Integracao como uma única função substituível que recebe o Chamado e devolve, de forma assíncrona, o Protocolo em caso de sucesso ou uma falha classificada em rede, tempo limite, resposta HTTP de erro, resposta inválida ou armazenamento, de modo que a troca dessa função por uma integração futura não exija alterar a lógica da tela.
8. WHILE Modo_API está ativo, WHEN o Ponto_de_Integracao recebe um Chamado, THE Ponto_de_Integracao SHALL enviar ao endereço `API_CHAMADOS_URL` uma requisição `POST` com o cabeçalho `Content-Type: application/json` e, no corpo, o Payload_do_Chamado serializado em JSON conforme o requisito 10.
9. WHILE Modo_API está ativo, IF o Back_end não responde dentro de `TIMEOUT_ENVIO_MS` milissegundos (valor de `js/data.js`, inicialmente 10 000), THEN THE Ponto_de_Integracao SHALL abortar a requisição e tratar a situação como falha de registro.
10. WHILE Modo_API está ativo, IF ocorre falha de rede, o Back_end responde com status HTTP fora da faixa 200 a 299, ou a resposta de status 200 a 299 não contém o campo `protocolo` com texto não vazio de até 64 caracteres, THEN THE Ponto_de_Integracao SHALL tratar a situação como falha de registro e SHALL NOT repetir a requisição automaticamente.
11. WHILE Modo_API está ativo, WHEN o Back_end responde com status 200 a 299 e o campo `protocolo` com texto não vazio de até 64 caracteres, THE Sistema SHALL usar esse valor como Protocolo do Chamado, e SHALL NOT gerar Protocolo local em Modo_API.
12. THE Sistema SHALL gerar a Chave_de_Idempotencia no navegador, uma única vez, no primeiro envio válido de uma Jornada, no formato de UUID versão 4 (36 caracteres), reutilizá-la em todas as retentativas até que o envio seja concluído com sucesso e gerar uma nova chave para o Chamado de uma nova Jornada.
13. WHEN o Consumidor aciona "Abrir meu chamado" mais de uma vez para a mesma Jornada, enquanto o registro está em andamento ou depois de concluído com sucesso, THE Sistema SHALL registrar um único Chamado, com um único Protocolo, e ignorar as ativações adicionais; WHILE o Chamado está sendo registrado, THE Sistema SHALL desabilitar o botão "Abrir meu chamado" e exibir o texto "Enviando", anunciado a leitores de tela em uma região `aria-live`.
14. IF o registro do Chamado falhar, THEN THE Sistema SHALL não gravar nenhum Chamado parcial, não exibir Protocolo como sucesso, exibir uma mensagem de erro em uma região `aria-live`, manter os valores digitados em Nome, Email, Telefone e Descricao e o estado do Aceite_dos_Termos, reabilitar o botão "Abrir meu chamado" para retentativa manual com a mesma Chave_de_Idempotencia e exibir o telefone e o e-mail de `CONTATO` como alternativa.
15. IF, em Modo_Prototipo, o `localStorage` estiver indisponível, bloquear o acesso ou rejeitar a gravação (inclusive por limite de armazenamento excedido), THEN THE Sistema SHALL tratar a situação como falha de registro do Chamado, conforme o critério 14.
16. IF o conteúdo existente no Repositorio_de_Chamados não puder ser lido como uma lista de Chamados, THEN THE Ponto_de_Integracao SHALL tratar o Repositorio_de_Chamados como vazio e gravar o novo Chamado como único item.
17. WHILE Modo_API está ativo, THE Sistema SHALL NOT gravar o Chamado no Repositorio_de_Chamados, SHALL NOT exibir o Aviso_de_Prototipo e SHALL NOT incluir no front end nenhum segredo, token ou chave de API.

### Requirement 8: Confirmar a abertura com protocolo, prazo, canais e avaliação

**User Story:** Como consumidor, quero receber a confirmação com um protocolo, saber em quanto tempo e por onde terei retorno e poder avaliar a ajuda, para que eu tenha certeza de que o chamado foi aberto e possa citá-lo depois.

#### Acceptance Criteria

1. WHEN o Chamado é registrado com sucesso, THE Sistema SHALL exibir a Tela_de_Confirmacao em até 1 segundo após o registro.
2. WHILE Modo_Prototipo está ativo, WHEN o Chamado é registrado, THE Sistema SHALL gerar o Protocolo no formato `TRES-AAAAMMDD-XXXXXX`, onde `AAAAMMDD` é a data local do dispositivo no momento do registro (AAAA com 4 dígitos, MM de 01 a 12, DD de 01 a 31) e `XXXXXX` são exatamente 6 caracteres, cada um sendo uma letra maiúscula de A a Z ou um dígito de 0 a 9.
3. WHILE Modo_Prototipo está ativo, WHEN o Sistema gera um Protocolo, THE Sistema SHALL garantir que ele seja diferente de todos os Protocolos já existentes no Repositorio_de_Chamados, gerando um novo valor para `XXXXXX` até 10 vezes caso o valor gerado já exista.
4. THE Tela_de_Confirmacao SHALL exibir o Protocolo em texto selecionável (não como imagem), com tamanho de fonte de no mínimo 24 px e maior que o do texto restante da tela, e em peso de fonte diferente do texto do corpo.
5. THE Tela_de_Confirmacao SHALL exibir uma mensagem informando que o time responsável recebeu o chamado e que o problema será analisado.
6. THE Tela_de_Confirmacao SHALL exibir o e-mail e o telefone do Chamado exatamente como foram armazenados a partir do que o Consumidor informou, junto com um texto convidando o Consumidor a conferir os dados de contato.
7. THE Tela_de_Confirmacao SHALL exibir o Prazo_de_Retorno no formato "N dias úteis" (ou "1 dia útil" quando N for 1), em que N é o valor inteiro de `PRAZO_RETORNO_DIAS_UTEIS` em `js/data.js`, sem calcular nem exibir data limite de retorno.
8. THE Tela_de_Confirmacao SHALL informar que o contato será feito pelos Canais_de_Retorno, WhatsApp no número de Telefone do Chamado e e-mail no endereço de Email do Chamado.
9. IF `PRAZO_RETORNO_DIAS_UTEIS` estiver ausente ou não for um número inteiro de 1 a 30, THEN THE Sistema SHALL omitir a frase do Prazo_de_Retorno (na Tela_de_Confirmacao e na linha de resumo da Tela_de_Chamado), SHALL manter a frase dos Canais_de_Retorno e SHALL NOT exibir texto de erro técnico.
10. WHILE Modo_Prototipo está ativo, THE Tela_de_Confirmacao SHALL exibir o Aviso_de_Prototipo, visível sem rolagem adicional além da necessária para ver o Protocolo, informando que o chamado foi simulado neste protótipo, que não foi enviado a um sistema de atendimento e que o prazo informado é ilustrativo.
11. WHILE Modo_API está ativo, THE Tela_de_Confirmacao SHALL omitir o Aviso_de_Prototipo, tanto visualmente quanto para leitores de tela.
12. WHEN a Tela_de_Confirmacao é exibida, THE Sistema SHALL mover o foco do teclado para o título (`h1`) da Tela_de_Confirmacao em até 500 milissegundos, de modo que `document.activeElement` seja esse `h1`.
13. THE Tela_de_Confirmacao SHALL exibir exatamente duas ações de navegação, rotuladas "Tenho outro problema" e "Voltar ao início", ambas acessíveis por teclado.
14. WHEN o Consumidor navega de volta à Tela_de_Chamado do mesmo problema depois de abrir o Chamado, THE Sistema SHALL exibir a Tela_de_Confirmacao com o mesmo Protocolo, o mesmo e-mail e o mesmo telefone do Chamado já aberto, sem apresentar o formulário vazio e sem criar nem enviar um novo Chamado.
15. WHEN o Consumidor seleciona um problema diferente depois de abrir um Chamado, THE Sistema SHALL tratar a nova jornada como independente da anterior, exibindo a Tela_de_Chamado com o formulário vazio e o Aceite_dos_Termos desmarcado, sem exibir o Protocolo anterior, e gerando uma nova Chave_de_Idempotencia e um novo Protocolo, diferente do anterior, ao registrar o novo Chamado, sem alterar o Chamado já aberto.
16. WHILE Modo_Prototipo está ativo, IF o Sistema não consegue gerar um Protocolo único após 10 tentativas, THEN THE Sistema SHALL não registrar o Chamado, não exibir a Tela_de_Confirmacao, exibir uma mensagem de erro informando que não foi possível abrir o chamado e que o Consumidor pode tentar novamente, e manter na Tela_de_Chamado todos os dados já preenchidos no formulário.
17. WHEN o Consumidor aciona "Tenho outro problema" na Tela_de_Confirmacao, THE Sistema SHALL exibir a tela de seleção de problemas, sem apagar o Chamado já registrado.
18. WHEN o Consumidor aciona "Voltar ao início" na Tela_de_Confirmacao, THE Sistema SHALL exibir a tela inicial do Autoatendimento, sem apagar o Chamado já registrado.
19. THE Tela_de_Confirmacao SHALL exibir o Componente_de_Avaliacao, com a mesma aparência, as mesmas opções de nota (1 a 5 estrelas) e o mesmo comportamento da avaliação da tela de problema resolvido, sob um título em texto visível, mantendo a avaliação opcional e sem bloquear as ações de navegação.

### Requirement 9: Preservar as métricas de deflexão

**User Story:** Como time de Customer Success, quero manter a medição de deflexão, saber quantos encaminhamentos viraram chamado e ver a avaliação da confirmação, para que o pitch e a POC tenham números confiáveis.

#### Acceptance Criteria

1. WHEN o Consumidor aciona "Não, ainda não", THE Sistema SHALL registrar no Registro_de_Metricas exatamente um evento do tipo `suporte` contendo o problema, o modelo e o instante do registro, mantendo o formato atual do evento.
2. WHEN o Chamado é registrado com sucesso, THE Sistema SHALL registrar no Registro_de_Metricas exatamente um evento do tipo `chamado` contendo o problema, o modelo, o Protocolo, o modo de envio (`prototipo` ou `api`), a quantidade de Passos_Percorridos (número inteiro maior ou igual a 0) e o instante do registro.
3. THE Sistema SHALL omitir Nome, Email, Telefone e Descricao de todo evento do tipo `chamado` e de todo evento do tipo `avaliacao` gravado no Registro_de_Metricas.
4. IF o envio do Chamado falhar, THEN THE Sistema SHALL não registrar nenhum evento do tipo `chamado` no Registro_de_Metricas e SHALL manter inalterados os eventos já registrados.
5. THE Sistema SHALL manter em `TRESMetricas.resumo()` o cálculo atual de `resolvidos` (quantidade de eventos `resolvido`), `encaminhadosAoSuporte` (quantidade de eventos `suporte`), `deflexaoPercentual` (percentual inteiro arredondado de `resolvidos` sobre a soma de `resolvidos` e `encaminhadosAoSuporte`, ou `null` quando essa soma for 0) e `porProblema`, de modo que eventos do tipo `chamado` e `avaliacao` não alterem nenhum desses quatro valores.
6. THE Sistema SHALL incluir em `TRESMetricas.resumo()` o campo `chamadosAbertos`, igual à quantidade de eventos do tipo `chamado` presentes no Registro_de_Metricas, ou 0 quando não houver nenhum.
7. IF o Registro_de_Metricas estiver indisponível ou a gravação de um evento falhar, THEN THE Sistema SHALL continuar a Jornada normalmente, SHALL exibir ao Consumidor a mesma tela que exibiria se o registro tivesse sucesso (incluindo o Protocolo, no caso de Chamado) e SHALL não exibir mensagem de erro relacionada ao registro.
8. THE Sistema SHALL manter a avaliação por estrelas da tela de problema resolvido com a mesma aparência, as mesmas opções de nota e o mesmo comportamento anteriores à introdução da tela de abertura de chamado, gravando o evento `avaliacao` com `desfecho` igual a `resolvido`.
9. WHEN o Consumidor escolhe uma nota no Componente_de_Avaliacao da Tela_de_Confirmacao, THE Sistema SHALL registrar no Registro_de_Metricas um evento do tipo `avaliacao` contendo a nota (1 a 5), o `desfecho` igual a `chamado`, o problema, o modelo, o Protocolo do Chamado e o instante do registro, e SHALL exibir o texto de agradecimento do Componente_de_Avaliacao em uma região `aria-live`.
10. THE Sistema SHALL omitir o Componente_de_Avaliacao da Tela_de_Chamado, de modo que nenhum evento `avaliacao` com `desfecho` igual a `suporte` ou `chamado` seja gravado antes do sucesso do envio.

### Requirement 10: Contrato do Chamado, serialização e consistência

**User Story:** Como desenvolvedor, quero que o Chamado e o payload sejam definidos por um contrato claro e sejam gravados e lidos sem perda de dados, para que o back end receba exatamente o que o Consumidor informou, sem depender do esquema do banco.

#### Acceptance Criteria

1. WHEN um Chamado for registrado em Modo_Prototipo, THE Repositorio_de_Chamados SHALL serializar todos os campos do Chamado (Nome, Telefone, Email, Descricao, aceite, Chave_de_Idempotencia, Protocolo e demais campos do Chamado) em um único texto JSON válido e gravá-lo.
2. WHEN o Sistema solicitar a leitura de Chamados, THE Sistema SHALL ler o JSON gravado no Repositorio_de_Chamados e reconstruir cada Chamado com os mesmos campos e valores gravados.
3. FOR ALL Chamados válidos, serializar, gravar, ler e desserializar SHALL produzir um Chamado equivalente ao original, isto é, com todos os campos presentes e com valores idênticos caractere a caractere, incluindo letras acentuadas, emojis, quebras de linha, aspas, barras invertidas e os caracteres `<`, `>` e `&` (propriedade de ida e volta).
4. FOR ALL textos de Nome, Descricao e Email aceitos pela validação, a normalização aplicada duas vezes SHALL produzir exatamente o mesmo texto que a normalização aplicada uma vez (idempotência).
5. FOR ALL textos de Telefone válidos, a normalização para dígitos SHALL produzir uma sequência composta somente pelos caracteres de 0 a 9, com 10 ou 11 dígitos.
6. FOR ALL Protocolos gerados em Modo_Prototipo, o Protocolo SHALL corresponder ao formato `TRES-AAAAMMDD-XXXXXX`, em que `AAAAMMDD` é uma data válida do calendário correspondente ao dia da geração e `XXXXXX` é uma sequência de exatamente 6 caracteres alfanuméricos maiúsculos (A-Z e 0-9).
7. IF o conteúdo gravado no Repositorio_de_Chamados não puder ser interpretado como JSON ou, sendo JSON válido, não tiver a estrutura esperada de uma lista de Chamados, THEN THE Sistema SHALL tratar o Repositorio_de_Chamados como vazio (0 Chamados), continuar a operação sem lançar exceção não tratada e sem exibir mensagem de erro técnica ao Consumidor.
8. IF a gravação do Chamado no Repositorio_de_Chamados falhar, THEN THE Sistema SHALL exibir ao Consumidor uma mensagem de erro indicando que o chamado não foi registrado, SHALL NOT exibir o Protocolo como confirmação de sucesso e SHALL manter preenchidos os dados digitados no formulário.
9. WHEN o Sistema exibir qualquer dado digitado pelo Consumidor (Nome, Telefone, Email ou Descricao), THE Sistema SHALL apresentá-lo como texto literal, de modo que um valor como `<b>x</b>` ou `<img src=x>` apareça na tela exatamente como digitado e nenhum elemento HTML seja criado a partir dele.
10. THE Payload_do_Chamado SHALL ser um objeto JSON com exatamente os campos `versaoContrato` (texto, inicialmente `"1"`), `chaveIdempotencia`, `abertoEm`, `nome`, `email`, `telefone`, `descricao`, `aceiteTermos`, `aceiteEm`, `modelo`, `problemaId`, `problemaTitulo`, `passosPercorridos` e `totalPassos`, sem nenhum outro campo.
11. THE Payload_do_Chamado SHALL ter `nome`, `email` e `telefone` normalizados conforme o requisito 7, critério 3; `aceiteTermos` igual a `true`; `abertoEm` e `aceiteEm` em ISO 8601 com fuso horário; `modelo` igual ao identificador do modelo escolhido ou `null` quando não informado; `problemaId` inteiro; `passosPercorridos` como lista, na ordem percorrida, de objetos com `posicao` (inteiro de 1 a `totalPassos`) e `texto`; e `totalPassos` inteiro maior ou igual a 1.
12. THE Payload_do_Chamado SHALL ser definido somente pelo contrato deste requisito, sem identificadores, nomes de tabela, nem estruturas do banco de dados, e SHALL NOT conter o Protocolo, nem dados do Registro_de_Metricas.
13. FOR ALL Payloads_do_Chamado válidos, serializar para JSON e desserializar SHALL produzir um objeto equivalente ao original, com os mesmos campos e valores idênticos caractere a caractere (propriedade de ida e volta).
14. FOR ALL Chaves_de_Idempotencia geradas, a chave SHALL corresponder ao formato de UUID versão 4 e SHALL ser diferente das chaves geradas para outros Chamados na mesma execução.

### Requirement 11: Acessibilidade e uso no celular

**User Story:** Como consumidor, inclusive com deficiência, quero abrir o chamado com facilidade no celular, para que ninguém fique sem atendimento por barreira de uso.

#### Acceptance Criteria

1. THE Tela_de_Chamado SHALL exibir todo o seu conteúdo e todos os seus controles, sem rolagem horizontal e sem sobreposição ou corte de texto, em larguras de viewport de 360 px a 1024 px, tendo 360 px como largura de projeto de referência.
2. THE Sistema SHALL garantir Alvos_de_Toque de no mínimo 44 px por 44 px, com espaçamento de no mínimo 8 px entre Alvos_de_Toque adjacentes, em todos os botões, links, campos e na caixa de seleção do Aceite_dos_Termos da Tela_de_Chamado e da Tela_de_Confirmacao.
3. THE Sistema SHALL usar fonte de no mínimo 16 px em todos os campos do Formulario_de_Chamado, incluindo o texto digitado e o texto de orientação exibido dentro do campo.
4. THE Tela_de_Chamado SHALL permitir que todas as ações do Formulario_de_Chamado, incluindo o aceite, o Botao_Ler_Termos, o envio e as ações "Rever os passos" e "Escolher outro problema", sejam executadas somente com o teclado (Tab e Shift+Tab para mover o foco; Enter ou Espaço para ativar), seguindo a ordem visual dos controles, sem armadilha de foco.
5. WHEN um controle da Tela_de_Chamado ou da Tela_de_Confirmacao recebe o foco do teclado, THE Sistema SHALL exibir um indicador de foco com espessura mínima de 2 px e contraste mínimo de 3:1 em relação às cores adjacentes, sem ficar oculto ou cortado por outro elemento.
6. WHEN o envio do chamado é concluído com sucesso, THE Sistema SHALL anunciar a conclusão, em até 1 segundo, por região `aria-live` compatível com Leitores_de_Tela.
7. WHERE o sistema do Consumidor sinaliza `prefers-reduced-motion: reduce`, THE Sistema SHALL suprimir todas as transições, animações e rolagens suaves na Tela_de_Chamado e na Tela_de_Confirmacao, de modo que a mudança de estado seja imediata (duração de 0 ms).
8. THE Sistema SHALL manter a relação de contraste mínima de 4,5:1 entre texto e fundo, em todos os estados (normal, foco, erro), para todo texto da Tela_de_Chamado e da Tela_de_Confirmacao, incluindo rótulos, texto de orientação dentro dos campos, texto de ajuda, mensagens de erro e a Mensagem_de_Termos_em_Elaboracao.
9. THE Sistema SHALL manter a barra de etapas indicando a etapa 3 ("A solução") como etapa atual na Tela_de_Chamado e na Tela_de_Confirmacao, com a indicação perceptível por meio de texto ou forma (não apenas por cor) e identificável por Leitores_de_Tela.
10. THE Tela_de_Chamado SHALL oferecer, visíveis sem rolagem adicional além da própria tela e operáveis conforme os critérios 2 e 4, as ações "Rever os passos" e "Escolher outro problema".
11. IF o envio é impedido por erro de validação ou por falha no registro do chamado (inclusive tempo limite, falha de rede ou resposta de erro do Back_end), THEN THE Sistema SHALL anunciar o erro, em até 1 segundo, por região `aria-live` compatível com Leitores_de_Tela, identificando o controle com erro quando o erro for de validação, mover o foco para o primeiro controle com erro (ou para a mensagem de erro, quando a falha não for de campo) e preservar os valores já digitados e o estado do Aceite_dos_Termos.
12. WHEN o Consumidor ativa "Rever os passos" na Tela_de_Chamado, THE Sistema SHALL exibir novamente os passos de solução do problema já escolhido e preservar os valores já digitados no Formulario_de_Chamado.
13. WHEN o Consumidor ativa "Escolher outro problema" na Tela_de_Chamado, THE Sistema SHALL exibir a lista de problemas para nova escolha.
14. THE Aceite_dos_Termos SHALL ser operável por teclado (tecla Espaço para marcar e desmarcar), SHALL ter nome acessível igual ao seu rótulo visível e SHALL ser identificado por Leitores_de_Tela como caixa de seleção obrigatória.
15. THE Componente_de_Avaliacao da Tela_de_Confirmacao SHALL manter Alvos_de_Toque de no mínimo 44 px por 44 px, nome acessível por botão no formato "N estrela(s) de 5", estado `aria-pressed` e operação por teclado (Enter ou Espaço).

### Requirement 12: Preservar o conteúdo e os arquivos existentes

**User Story:** Como mantenedor do projeto, quero que a mudança não afete o restante da jornada nem os materiais originais, para que o protótipo continue estável.

#### Acceptance Criteria

1. WHEN o usuário acessa cada uma das rotas existentes, exceto `#/suporte/ID` (`#/`, `#/problemas`, `#/solucao/ID`, `#/confirma/ID`, `#/resolvido/ID` e `#/contato`), THE Sistema SHALL exibir, para as etapas "Sua máquina", "O problema", "A solução", "O problema foi solucionado?", "Resolvido" e "Contato", a mesma tela da versão anterior à mudança, com os mesmos textos, a mesma ordem de elementos, os mesmos destinos de botões e links, a mesma barra de etapas com 3 itens e o mesmo comportamento do botão voltar do navegador. A rota `#/suporte/ID` e a rota da Tela_de_Confirmacao são as únicas que mudam ou surgem, conforme os requisitos 1 a 11.
2. THE Sistema SHALL manter o cabeçalho com o link "Falar com a gente" (destino `#/contato`) e o rodapé com os canais de atendimento (telefone, horários e e-mail) com os mesmos textos, valores e destinos da versão anterior à mudança.
3. THE Sistema SHALL carregar a partir de `js/data.js` todos os textos novos desta funcionalidade (título, avisos, mensagens de erro, Aviso_de_Privacidade, rótulos do Aceite_dos_Termos e do Botao_Ler_Termos, Mensagem_de_Termos_em_Elaboracao, textos de prazo e canais, Aviso_de_Prototipo e título da avaliação), sem que nenhum deles esteja escrito diretamente em `index.html` ou `js/app.js`, e SHALL carregar de `js/data.js` as configurações `API_CHAMADOS_URL`, `PRAZO_RETORNO_DIAS_UTEIS` e `TIMEOUT_ENVIO_MS`.
4. THE Sistema SHALL funcionar quando servido por um servidor HTTP estático, sem etapa de build, sem etapa de instalação de pacotes e sem adicionar bibliotecas, fontes ou scripts de terceiros além dos já existentes em `js/vendor`.
5. THE Sistema SHALL manter inalterados, byte a byte, todos os arquivos existentes em `material/`, as imagens originais `img/LOV.png`, `img/Luna.png`, `img/Modo.png`, `img/Passione.png` e `img/TOUCH.png`, e o arquivo `.glb` original, sem renomear, mover, excluir nem criar arquivos dentro de `material/`.
6. IF os textos novos ou o Aviso_de_Privacidade estiverem ausentes ou vazios em `js/data.js`, THEN THE Sistema SHALL exibir na tela de abertura de chamado uma mensagem indicando que o conteúdo está indisponível, desabilitar o envio do chamado e manter as demais telas funcionando conforme o critério 1.
7. WHILE Modo_Prototipo está ativo, WHEN um chamado simulado é gravado no `localStorage`, THE Sistema SHALL gravar o Chamado completo em uma chave diferente de `tres-autoatendimento-eventos`, SHALL NOT gravar nessa chave nenhum dado do Chamado além dos eventos `chamado` e `avaliacao` previstos no requisito 9, e SHALL manter inalterado o resultado de `resolvidos`, `encaminhadosAoSuporte`, `deflexaoPercentual` e `porProblema` em `TRESMetricas.resumo()`.
8. WHILE `API_CHAMADOS_URL` está vazia, THE Sistema SHALL NOT realizar nenhuma requisição de rede para o envio de Chamados.
