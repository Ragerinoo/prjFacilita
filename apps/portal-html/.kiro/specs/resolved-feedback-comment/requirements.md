# Requirements Document

## Introduction

Hoje, quando o consumidor responde "Sim" em "O problema foi solucionado?", a jornada do Autoatendimento TRES termina na rota `#/resolvido/ID`: mensagem "Que bom! Seu café está de volta.", avaliação por estrelas ("Como foi a ajuda?") e os links "Tenho outro problema" e "Voltar ao início". A nota gera o evento `avaliacao` no Registro_de_Metricas, e só isso. Quem quer explicar o que achou da ajuda não tem onde escrever.

Esta funcionalidade acrescenta, na Tela_de_Resolvido e junto das estrelas, um **campo de comentário opcional** para coleta de feedback. Ele segue o mesmo padrão do campo Descricao da Tela_de_Chamado (rótulo visível, limite de 500 caracteres, contador "N de 500 caracteres", validação, textos vindos de `js/data.js`, acessibilidade e alvos de toque), com uma diferença central: **não pede nenhum dado do consumidor**. Não há nome, e-mail, telefone nem aceite de termos. A identificação continua existindo somente na abertura de chamado.

Pontos principais:

- o comentário é opcional e independe das estrelas: o consumidor pode enviar só a nota (como hoje), só o comentário, ou os dois;
- o texto é sempre tratado como texto puro e nunca entra no Registro_de_Metricas; as métricas guardam apenas a **contagem** de comentários;
- o envio passa por uma camada própria e isolada (Ponto_de_Integracao_de_Feedback), com dois modos, como no chamado: **Modo_Prototipo** (grava no `localStorage`, em chave separada) e **Modo_API** (POST JSON, ainda sem contrato definido com o back end);
- a Tela_de_Confirmacao do chamado e a Tela_de_Chamado **não mudam**.

O projeto continua em HTML, CSS e JS puros, sem build, mobile primeiro.

### Escopo

Dentro do escopo:
- o bloco de comentário na Tela_de_Resolvido (rota `#/resolvido/ID`), com contador, validação, envio, agradecimento e tratamento de falha;
- o Payload_do_Feedback, o Repositorio_de_Feedbacks (Modo_Prototipo) e o Ponto_de_Integracao_de_Feedback (Modo_Prototipo e Modo_API), incluindo idempotência e tempo limite;
- o evento de métrica `comentario` (sem o texto) e o campo `comentarios` em `TRESMetricas.resumo()`;
- os textos e a configuração do feedback em `js/data.js`;
- a atualização dos testes existentes que verificam a Tela_de_Resolvido e a criação de testes para o que for novo.

Fora do escopo:
- implementação do back end e do banco de dados, autenticação, CORS e retenção dos dados (apenas o cliente e o contrato provisório do payload);
- comentário na Tela_de_Confirmacao do chamado, na Tela_de_Chamado ou em qualquer outra rota;
- identificação do consumidor no feedback (nome, e-mail, telefone, aceite de termos, Botao_Ler_Termos);
- detecção ou remoção automática de dados pessoais digitados pelo consumidor no comentário;
- painel de leitura dos comentários, moderação, resposta ao consumidor e análise de sentimento;
- alteração de `material/`, de `img/*.png` originais e do `.glb` original;
- criação de conteúdo novo de instruções de máquina.

## Premissas e pontos em aberto

Cada item traz o **padrão adotado nesta spec**. As perguntas 1 a 5 abertas na primeira versão foram **respondidas pelo usuário** (marcadas abaixo como *Decisão do usuário*). Restam como pontos em aberto somente a avaliação jurídica (LGPD) e o contrato com o back end, listados no fim desta seção.

- **P1. Comentário opcional e independente das estrelas.** Padrão: o comentário pode ser enviado sem nenhuma estrela, e as estrelas continuam gravando o evento `avaliacao` no clique, exatamente como hoje. O comentário tem o próprio botão de envio. Quando existir uma nota escolhida no momento do envio, ela acompanha o comentário no Payload_do_Feedback; senão o campo `nota` vai como `null`. *Decisão do usuário (pergunta 1): a nota NÃO é obrigatória para enviar o comentário; o padrão acima foi mantido.*
- **P2. Limite de 500 caracteres e contador.** Padrão: o mesmo limite e o mesmo formato do campo Descricao ("N de 500 caracteres"). Não há mínimo além de 1 caractere não vazio depois de remover espaços das pontas, porque um comentário curto como "ótimo" é válido. *Decisão do usuário (pergunta 2): o limite de 500 caracteres foi mantido.*
- **P3. Um comentário por resposta "Sim".** Padrão: depois de um envio bem-sucedido, o campo e o botão ficam travados e a Mensagem_de_Agradecimento é exibida. O estado "já enviado" fica só em memória e é zerado quando o consumidor escolhe outro problema ou recarrega a página. Voltar a `#/resolvido/ID` pelo botão voltar do navegador na mesma jornada mostra o estado "já enviado". *Decisão do usuário (pergunta 3): um único comentário por jornada; o padrão acima foi mantido.*
- **P4. Sem identificação e aviso de não incluir dados pessoais.** Padrão: nenhum campo de identificação e nenhum aceite de termos. O bloco exibe um Aviso_de_Nao_Identificacao pedindo para não escrever nome, e-mail, telefone ou outros dados pessoais no comentário. O Sistema não detecta nem apaga dados pessoais digitados; a prevenção é só o aviso. O comentário em si não tem identificador do consumidor, mas o texto livre pode conter dado pessoal digitado por ele. A avaliação jurídica (LGPD) desse risco é `PENDENTE`.
- **P5. Vínculo opcional ao problema e ao modelo, sem identificar o cliente.** O Payload_do_Feedback leva `problemaId` (da rota) e `modelo` (identificador escolhido ou `null`). Esses dados descrevem a máquina e o problema, não a pessoa. Nenhum outro dado de contexto (agente de usuário, IP, geolocalização, protocolo) é coletado pelo cliente.
- **P6. Modo_Prototipo.** Padrão: o comentário é gravado no `localStorage`, na chave `tres-autoatendimento-feedbacks`, com no máximo 50 registros, separada de `tres-autoatendimento-eventos` e de `tres-autoatendimento-chamados`. Nenhum time recebe o comentário de fato. A Mensagem_de_Agradecimento é a mesma nos dois modos, sem aviso de protótipo. *Decisão do usuário (pergunta 4): o aviso de protótipo no agradecimento foi removido por completo; o agradecimento é igual em Modo_Prototipo e em Modo_API.*
- **P7. Modo_API é ponto em aberto com o back end.** Não existe contrato nem endpoint de feedback. Padrão: o feedback tem **configuração própria**, `API_FEEDBACK_URL`, vazia por padrão e **independente** de `API_CHAMADOS_URL`. Com `API_FEEDBACK_URL` vazia, o feedback opera em Modo_Prototipo mesmo que `API_CHAMADOS_URL` esteja preenchida, e o Sistema não envia comentário ao endpoint de chamados. O Payload_do_Feedback desta spec é **provisório** (versão `"1"`) e do lado do cliente. Ficam sem definição, para alinhar com o back end: URL por ambiente, autenticação e autorização, CORS, esquema do banco, formato da resposta de sucesso (o cliente aceita qualquer status 2xx, sem exigir corpo), tratamento de chave de idempotência repetida, se a chave também vai em cabeçalho HTTP, limites de tamanho, limitação de taxa e prazo de retenção. A URL deve continuar vazia no repositório do protótipo. *Decisão do usuário (pergunta 5): o contrato do back end é mantido como provisório; os itens sem definição acima seguem `PENDENTE`.*
- **P8. Falha de envio.** Padrão: mensagem de falha com nova tentativa manual, texto preservado e a mesma Chave_de_Idempotencia nas tentativas. Sem contato alternativo (telefone ou e-mail), porque o comentário é opcional e o consumidor já resolveu o problema.
- **P9. Métricas.** Padrão: um evento `comentario` por envio bem-sucedido, com problema, modelo e instante, sem o texto, sem a nota e sem o tamanho. `TRESMetricas.resumo()` ganha `comentarios` (contagem). Os eventos `comentario` não alteram resolvidos, encaminhados ao suporte, deflexão nem por problema. A leitura do texto dos comentários, em Modo_Prototipo, é feita diretamente no `localStorage`; não há painel.
- **P10. Estado em memória.** O texto digitado fica só em memória enquanto o consumidor está na Tela_de_Resolvido. Se ele sair da rota sem enviar e voltar, o campo aparece vazio. Recarregar a página também zera o campo.
- **P11. Posição do bloco.** "Ao lado das estrelas" é interpretado como **no mesmo bloco de avaliação**, logo abaixo das estrelas e acima de "Cuidados com a sua máquina". Em telas estreitas e largas o campo ocupa a largura do bloco, sem colunas.
- **P12. Ajuste em requisito anterior.** Esta funcionalidade altera, de forma deliberada, o requisito 12, critério 1, da spec `ticket-opening-screen`, que exigia a Tela_de_Resolvido idêntica à anterior: ela ganha o bloco de comentário e mais nada.

### Pontos em aberto (pendentes)

- **Avaliação jurídica (LGPD)** do risco de o texto livre conter dado pessoal digitado pelo Consumidor, do texto do Aviso_de_Nao_Identificacao e da política de retenção: `PENDENTE` (ver P4).
- **Contrato com o Back_end** do Payload_do_Feedback e do endpoint (URL por ambiente, autenticação e autorização, CORS, esquema do banco, resposta, idempotência repetida, limites, limitação de taxa e retenção): `PENDENTE`; o usuário confirmou manter o contrato provisório (ver P7).

## Glossary

- **Sistema**: a página Autoatendimento TRES (HTML, CSS e JS puros) executada no navegador do consumidor.
- **Consumidor**: a pessoa que usa a jornada, em geral em pé na frente da máquina, com o celular.
- **Jornada**: o percurso modelo, problema, passos e confirmação "O problema foi solucionado?".
- **Tela_de_Resolvido**: a tela da rota `#/resolvido/ID`, exibida quando o Consumidor responde "Sim" em "O problema foi solucionado?".
- **Tela_de_Chamado**: a tela da rota `#/suporte/ID`, com o formulário de abertura de chamado. Não muda nesta funcionalidade.
- **Tela_de_Confirmacao**: a tela da rota `#/chamado/ID`, exibida depois do registro do chamado. Não muda nesta funcionalidade.
- **Componente_de_Avaliacao**: os 5 botões de estrela (1 a 5) da avaliação, já existentes na Tela_de_Resolvido.
- **Bloco_de_Feedback**: a área da Tela_de_Resolvido que reúne o Componente_de_Avaliacao e o Formulario_de_Feedback.
- **Formulario_de_Feedback**: a parte do Bloco_de_Feedback com o Campo_de_Comentario, o contador, o Aviso_de_Nao_Identificacao e o Botao_Enviar_Comentario.
- **Campo_de_Comentario**: campo de texto de várias linhas (`textarea`) para as considerações do Consumidor, opcional.
- **Comentario**: o texto digitado no Campo_de_Comentario, depois da normalização.
- **Botao_Enviar_Comentario**: o botão que envia o Comentario.
- **Aviso_de_Nao_Identificacao**: texto curto visível no Formulario_de_Feedback que pede para o Consumidor não escrever dados pessoais no Comentario.
- **Mensagem_de_Agradecimento**: texto exibido depois do envio bem-sucedido do Comentario.
- **Mensagem_de_Falha_de_Feedback**: texto exibido quando o envio do Comentario falha.
- **Feedback**: registro com o Comentario, a nota (quando houver), o problema, o modelo, o instante do envio, a Chave_de_Idempotencia e a versão do contrato. Não contém dado de identificação do Consumidor.
- **Payload_do_Feedback**: o objeto JSON do Feedback, com os campos definidos no requisito 10, independente do esquema do banco de dados.
- **Chave_de_Idempotencia**: identificador único (UUID versão 4) gerado no navegador para uma tentativa de enviar um Feedback e reutilizado em todas as retentativas dela.
- **Back_end**: o serviço em desenvolvimento paralelo que poderá receber o Payload_do_Feedback.
- **API_FEEDBACK_URL**: constante de `js/data.js` com a URL do endpoint de feedback, vazia por padrão e independente de `API_CHAMADOS_URL`.
- **Modo_Prototipo**: modo de envio do feedback ativo quando `API_FEEDBACK_URL` está ausente, vazia ou inválida; o envio é simulado e gravado no Repositorio_de_Feedbacks.
- **Modo_API**: modo de envio do feedback ativo quando `API_FEEDBACK_URL` é uma URL válida conforme o requisito 10; o Feedback é enviado ao Back_end por `POST` com JSON.
- **Repositorio_de_Feedbacks**: o armazenamento dos Feedbacks no `localStorage`, na chave `tres-autoatendimento-feedbacks`, com no máximo 50 registros, usado somente em Modo_Prototipo.
- **Ponto_de_Integracao_de_Feedback**: a camada de envio do Feedback, função única e substituível, isolada em `js/chamado.js` ou em módulo equivalente de `js/`, que entrega o Feedback ao destino conforme o modo ativo e devolve, de forma assíncrona, sucesso ou falha.
- **Registro_de_Metricas**: o armazenamento de eventos existente no `localStorage`, na chave `tres-autoatendimento-eventos`, com no máximo 500 eventos, consultado por `TRESMetricas`.
- **Evento_Comentario**: evento do tipo `comentario` gravado no Registro_de_Metricas, sem o texto do Comentario.
- **Alvo_de_Toque**: área clicável ou tocável de um controle.
- **Leitor_de_Tela**: tecnologia assistiva que lê o conteúdo da página em voz alta.

## Requirements

### Requirement 1: Oferecer um campo de comentário opcional na tela de problema resolvido

**User Story:** Como consumidor que resolveu o problema, quero escrever o que achei da ajuda junto da avaliação, para que o time de Customer Success entenda minha experiência além da nota.

#### Acceptance Criteria

1. WHEN a Tela_de_Resolvido é exibida para um `ID` de problema existente, THE Sistema SHALL exibir o Formulario_de_Feedback dentro do Bloco_de_Feedback, imediatamente abaixo do Componente_de_Avaliacao e acima do bloco "Cuidados com a sua máquina", na ordem visual e na ordem de leitura.
2. THE Formulario_de_Feedback SHALL conter exatamente um Campo_de_Comentario, um contador de caracteres, o Aviso_de_Nao_Identificacao e um Botao_Enviar_Comentario, sem nenhum outro campo editável.
3. THE Campo_de_Comentario SHALL exibir um rótulo de texto permanentemente visível, associado programaticamente ao campo, que contém a indicação escrita "opcional", de modo que o rótulo continue visível com o campo preenchido ou com foco.
4. THE Campo_de_Comentario SHALL ser um campo de texto de várias linhas, com 4 linhas visíveis, sem preenchimento automático (`autocomplete="off"`).
5. THE Campo_de_Comentario SHALL NOT ser tratado como obrigatório: o Consumidor SHALL poder sair da Tela_de_Resolvido pelos links "Tenho outro problema" e "Voltar ao início" sem preencher nem enviar o Comentario.
6. WHEN o Componente_de_Avaliacao e o Formulario_de_Feedback são exibidos, THE Sistema SHALL exibir o Aviso_de_Nao_Identificacao em texto visível, associado ao Campo_de_Comentario por `aria-describedby`, junto do contador.
7. WHEN a Tela_de_Resolvido é exibida por qualquer meio de navegação (resposta "Sim", botão voltar ou avançar do navegador, ou abertura direta da URL), THE Sistema SHALL manter o foco do teclado no título (`h1`) da tela em até 300 ms, sem mover o foco para o Campo_de_Comentario.
8. IF o `ID` da rota `#/resolvido/ID` está ausente ou não corresponde a nenhum problema existente, THEN THE Sistema SHALL redirecionar o Consumidor para `#/problemas`, como já faz hoje, e SHALL NOT exibir o Formulario_de_Feedback.

### Requirement 2: Dispensar identificação e aceite de termos no feedback

**User Story:** Como consumidor, quero comentar sem informar quem sou, para que dar minha opinião seja rápido e não exija meus dados.

#### Acceptance Criteria

1. THE Formulario_de_Feedback SHALL omitir campos de nome, e-mail e telefone, a caixa de seleção de aceite dos termos e o botão "Ler os termos".
2. THE Sistema SHALL permitir o envio do Comentario sem que o Consumidor tenha preenchido qualquer dado de identificação ou marcado qualquer aceite.
3. THE Aviso_de_Nao_Identificacao SHALL pedir ao Consumidor que não escreva nome, e-mail, telefone nem outros dados pessoais no Comentario, e SHALL conter entre 1 e 200 caracteres.
4. THE Sistema SHALL NOT incluir, no Feedback, no Payload_do_Feedback, no Repositorio_de_Feedbacks ou no Evento_Comentario, valores digitados em campos de identificação do Formulario_de_Chamado, mesmo que existam em memória na mesma sessão.
5. THE Sistema SHALL NOT impedir o envio do Comentario por detectar nele nome, e-mail ou telefone, e SHALL NOT alterar o texto digitado pelo Consumidor para remover tais dados.
6. THE Sistema SHALL manter o Formulario_de_Chamado, o Aceite_dos_Termos e a coleta de identificação exclusivamente na Tela_de_Chamado.

### Requirement 3: Manter o comentário independente das estrelas

**User Story:** Como consumidor, quero escolher se avalio com estrelas, comento ou faço os dois, para que eu responda do jeito que me for mais fácil.

#### Acceptance Criteria

1. WHEN o Consumidor escolhe uma nota no Componente_de_Avaliacao, THE Sistema SHALL registrar o evento `avaliacao` com `desfecho` igual a `resolvido` e SHALL exibir o texto de agradecimento da avaliação, com o mesmo comportamento anterior a esta funcionalidade, sem exigir nem enviar o Comentario.
2. WHEN o Consumidor aciona o Botao_Enviar_Comentario sem ter escolhido nenhuma nota, THE Sistema SHALL enviar o Comentario com `nota` igual a `null` e SHALL NOT registrar nenhum evento `avaliacao`.
3. WHEN o Consumidor aciona o Botao_Enviar_Comentario depois de ter escolhido uma nota de 1 a 5 na mesma exibição da Tela_de_Resolvido, THE Sistema SHALL enviar o Comentario com `nota` igual à nota escolhida mais recentemente e SHALL NOT registrar um novo evento `avaliacao`.
4. WHEN o Consumidor escolhe uma nota depois de o Comentario já ter sido enviado, THE Sistema SHALL registrar o evento `avaliacao` normalmente e SHALL NOT alterar o Feedback já enviado.
5. THE Sistema SHALL tratar o envio do Comentario e o registro da nota como operações independentes: a falha de uma SHALL NOT impedir nem desfazer a outra.
6. WHILE o Consumidor não escolheu nenhuma nota, THE Sistema SHALL manter o Botao_Enviar_Comentario operável, sem exibir mensagem que exija a nota.

### Requirement 4: Limitar o comentário e mostrar o contador de caracteres

**User Story:** Como consumidor, quero saber quanto ainda posso escrever, para que eu não perca texto ao enviar.

#### Acceptance Criteria

1. THE Campo_de_Comentario SHALL aceitar no máximo 500 caracteres.
2. THE Formulario_de_Feedback SHALL exibir, abaixo do Campo_de_Comentario, um contador no formato "N de 500 caracteres", em que N é o número de caracteres digitados, iniciando em "0 de 500 caracteres" e atualizado a cada alteração do conteúdo em até 100 ms.
3. IF o conteúdo do Campo_de_Comentario atingir 500 caracteres, THEN THE Formulario_de_Feedback SHALL impedir a inclusão de novos caracteres, truncar em 500 caracteres qualquer texto colado que exceda o limite, manter o contador em "500 de 500 caracteres" e preservar o texto já digitado.
4. THE contador SHALL ser associado ao Campo_de_Comentario por `aria-describedby` e SHALL NOT anunciar cada alteração por região `aria-live`.
5. WHEN a Tela_de_Resolvido é exibida, THE Sistema SHALL iniciar o Campo_de_Comentario vazio e o contador em "0 de 500 caracteres", exceto no estado "já enviado" descrito no requisito 7, critério 8.

### Requirement 5: Validar o comentário antes do envio

**User Story:** Como consumidor, quero ser avisado de forma clara quando tentar enviar um comentário vazio, para que eu corrija sem perder o que já escrevi.

#### Acceptance Criteria

1. WHEN o Consumidor aciona o Botao_Enviar_Comentario, THE Sistema SHALL validar o Comentario antes de qualquer envio ou gravação.
2. THE Sistema SHALL considerar válido o Comentario que tenha, depois de remover espaços e quebras de linha das pontas, entre 1 e 500 caracteres.
3. IF o Campo_de_Comentario está vazio ou contém somente espaços e quebras de linha, THEN THE Sistema SHALL NOT enviar nem gravar nada, SHALL exibir abaixo do campo uma mensagem de erro em texto visível, SHALL marcar o campo com `aria-invalid="true"` e SHALL associar a mensagem ao campo por `aria-describedby`.
4. IF o Comentario é inválido, THEN THE Sistema SHALL mover o foco para o Campo_de_Comentario e SHALL anunciar o erro, em até 1 segundo, por região `aria-live` compatível com Leitores_de_Tela.
5. WHEN o Consumidor altera o conteúdo do Campo_de_Comentario que exibe erro, THE Sistema SHALL remover, em até 200 ms, a mensagem de erro, o `aria-invalid` e a referência à mensagem em `aria-describedby`, mantendo a referência ao contador e ao Aviso_de_Nao_Identificacao.
6. THE Sistema SHALL preservar o texto digitado, sem alteração, após qualquer tentativa de envio rejeitada por validação.
7. WHEN o Consumidor pressiona a tecla Enter no Campo_de_Comentario, THE Sistema SHALL inserir uma quebra de linha e SHALL NOT enviar o Comentario.

### Requirement 6: Normalizar o comentário e tratá-lo como texto puro

**User Story:** Como mantenedor, quero que o comentário seja guardado e exibido como texto literal, para que ele nunca execute nem altere a página.

#### Acceptance Criteria

1. THE Sistema SHALL normalizar o Comentario removendo espaços e quebras de linha das pontas e preservando as quebras de linha internas e os espaços internos.
2. FOR ALL textos de Comentario aceitos pela validação, a normalização aplicada duas vezes SHALL produzir exatamente o mesmo texto que a normalização aplicada uma vez (idempotência).
3. WHEN o Sistema exibe qualquer parte do Comentario digitado pelo Consumidor na página, THE Sistema SHALL apresentá-lo como texto literal, de modo que um valor como `<b>x</b>` ou `<img src=x>` apareça exatamente como digitado e nenhum elemento HTML seja criado a partir dele.
4. THE Sistema SHALL NOT inserir o Comentario na página por meio de `innerHTML`, `insertAdjacentHTML`, `outerHTML` ou `document.write`.
5. THE Sistema SHALL preservar caracteres acentuados, emojis, aspas, barras invertidas e os caracteres `<`, `>` e `&` do Comentario, sem escapar nem remover nenhum deles ao gravar ou enviar.

### Requirement 7: Enviar o comentário, agradecer e evitar envio duplicado

**User Story:** Como consumidor, quero enviar meu comentário uma vez e saber que foi recebido, para que eu tenha certeza de que minha opinião foi registrada.

#### Acceptance Criteria

1. WHEN o Consumidor aciona o Botao_Enviar_Comentario com um Comentario válido, THE Sistema SHALL gerar uma Chave_de_Idempotencia (UUID versão 4) e SHALL entregar o Feedback ao Ponto_de_Integracao_de_Feedback.
2. WHILE o envio do Feedback está em andamento, THE Sistema SHALL marcar o Formulario_de_Feedback com `aria-busy="true"`, exibir no Botao_Enviar_Comentario o texto de envio em andamento, ignorar novas ativações do botão e manter o Campo_de_Comentario legível e sem possibilidade de edição.
3. WHEN o Consumidor aciona o Botao_Enviar_Comentario duas ou mais vezes em sequência rápida (duplo toque ou clique repetido), THE Sistema SHALL iniciar no máximo um envio e SHALL gravar ou enviar no máximo um Feedback para essa tentativa.
4. WHEN o envio do Feedback é concluído com sucesso, THE Sistema SHALL exibir a Mensagem_de_Agradecimento em até 300 ms, em região `role="status"` com `aria-live="polite"`.
5. WHEN o envio do Feedback é concluído com sucesso, THE Sistema SHALL exibir a mesma Mensagem_de_Agradecimento em Modo_Prototipo e em Modo_API, sem nenhum aviso adicional que indique o modo ativo.
6. WHEN o envio do Feedback é concluído com sucesso, THE Sistema SHALL desabilitar o Campo_de_Comentario e o Botao_Enviar_Comentario, manter o texto enviado visível e mover o foco para a Mensagem_de_Agradecimento em até 300 ms.
7. WHEN o envio do Feedback é concluído com sucesso, THE Sistema SHALL anunciar o agradecimento, em até 1 segundo, por região `aria-live` compatível com Leitores_de_Tela.
8. WHILE o Consumidor permanece na mesma Jornada, WHEN a Tela_de_Resolvido do mesmo problema é exibida novamente depois de um envio bem-sucedido, THE Sistema SHALL exibir o Formulario_de_Feedback no estado "já enviado", com o texto enviado, o Campo_de_Comentario e o Botao_Enviar_Comentario desabilitados e a Mensagem_de_Agradecimento visível.
9. WHEN o Consumidor escolhe um problema para iniciar uma nova Jornada, ou recarrega a página, THE Sistema SHALL descartar o estado "já enviado" e o texto em memória.
10. THE Sistema SHALL manter a Chave_de_Idempotencia de uma tentativa em memória e reutilizá-la em todas as retentativas dessa tentativa, e SHALL gerar uma nova chave somente para um novo Feedback.

### Requirement 8: Tratar falha no envio do comentário

**User Story:** Como consumidor, quero saber quando o comentário não foi enviado e poder tentar de novo sem reescrever, para que eu não perca o que escrevi.

#### Acceptance Criteria

1. IF o envio do Feedback falhar (gravação local indisponível em Modo_Prototipo, ou, em Modo_API, falha de rede, tempo limite, resposta de erro do Back_end ou resposta que não seja 2xx), THEN THE Sistema SHALL exibir a Mensagem_de_Falha_de_Feedback em texto visível, em região `role="alert"`, sem exibir detalhe técnico.
2. IF o envio do Feedback falhar, THEN THE Sistema SHALL preservar o texto digitado, reabilitar o Campo_de_Comentario e o Botao_Enviar_Comentario, remover o `aria-busy` e manter a mesma Chave_de_Idempotencia para a próxima tentativa.
3. IF o envio do Feedback falhar, THEN THE Sistema SHALL mover o foco para a Mensagem_de_Falha_de_Feedback e SHALL anunciar a falha, em até 1 segundo, por região `aria-live` compatível com Leitores_de_Tela.
4. IF o envio do Feedback falhar, THEN THE Sistema SHALL NOT exibir a Mensagem_de_Agradecimento, SHALL NOT gravar o Evento_Comentario no Registro_de_Metricas e SHALL NOT travar o Formulario_de_Feedback.
5. WHEN o Consumidor aciona novamente o Botao_Enviar_Comentario depois de uma falha, THE Sistema SHALL remover a Mensagem_de_Falha_de_Feedback e tentar o envio com o texto atual do Campo_de_Comentario, validado conforme o requisito 5.
6. IF o Consumidor editou o texto depois de uma falha e aciona o envio, THEN THE Sistema SHALL reutilizar a mesma Chave_de_Idempotencia e enviar o texto atualizado.
7. IF o envio do Feedback falhar, THEN THE Sistema SHALL manter funcionando o Componente_de_Avaliacao, o bloco "Cuidados com a sua máquina" e os links "Tenho outro problema" e "Voltar ao início".

### Requirement 9: Gravar o feedback em Modo_Prototipo

**User Story:** Como desenvolvedor, quero que o protótipo guarde os comentários localmente em um lugar separado, para demonstrar a coleta sem back end e sem contaminar as métricas.

#### Acceptance Criteria

1. WHILE Modo_Prototipo está ativo, WHEN um Feedback válido é enviado, THE Repositorio_de_Feedbacks SHALL serializar o Payload_do_Feedback em JSON válido e gravá-lo na chave `tres-autoatendimento-feedbacks` do `localStorage`, sem realizar nenhuma requisição de rede.
2. THE Repositorio_de_Feedbacks SHALL manter no máximo 50 registros, descartando os mais antigos quando o limite for excedido.
3. THE Sistema SHALL NOT gravar o Comentario nas chaves `tres-autoatendimento-eventos` e `tres-autoatendimento-chamados`, nem gravar nelas qualquer registro do Repositorio_de_Feedbacks.
4. WHEN o Sistema lê o Repositorio_de_Feedbacks, THE Sistema SHALL reconstruir cada registro com os mesmos campos e valores gravados.
5. FOR ALL Payloads_do_Feedback válidos, serializar, gravar, ler e desserializar SHALL produzir um objeto equivalente ao original, com todos os campos presentes e valores idênticos caractere a caractere, incluindo letras acentuadas, emojis, quebras de linha, aspas, barras invertidas e os caracteres `<`, `>` e `&` (propriedade de ida e volta).
6. IF o conteúdo gravado no Repositorio_de_Feedbacks não puder ser interpretado como JSON ou, sendo JSON válido, não tiver a estrutura de uma lista de registros, THEN THE Sistema SHALL tratá-lo como vazio (0 registros), continuar a operação sem lançar exceção não tratada e sem exibir mensagem técnica ao Consumidor.
7. IF a gravação no Repositorio_de_Feedbacks falhar (por exemplo, armazenamento cheio ou bloqueado), THEN THE Sistema SHALL tratar o envio como falha conforme o requisito 8.
8. WHEN o mesmo Feedback é entregue ao Repositorio_de_Feedbacks mais de uma vez com a mesma Chave_de_Idempotencia, THE Repositorio_de_Feedbacks SHALL manter um único registro para essa chave.

### Requirement 10: Isolar o envio e definir o contrato provisório para o Modo_API

**User Story:** Como desenvolvedor, quero que o envio do feedback fique isolado e tenha um contrato provisório, para que o back end possa se alinhar depois sem mudar a tela.

#### Acceptance Criteria

1. THE Sistema SHALL implementar o envio do Feedback no Ponto_de_Integracao_de_Feedback, separado do Ponto_de_Integracao do chamado, de modo que a tela chame uma única função e não saiba qual modo está ativo.
2. THE Ponto_de_Integracao_de_Feedback SHALL receber como parâmetros as dependências do ambiente (configuração, `fetch`, `AbortController`, temporizadores, armazenamento e relógio), sem depender do DOM, para ser testável sem navegador.
3. THE Sistema SHALL carregar de `js/data.js` a configuração do feedback: `API_FEEDBACK_URL` (vazia por padrão) e o tempo limite de envio em milissegundos (inicialmente 10 000), ambos independentes dos valores de `API_CHAMADOS_URL` e `TIMEOUT_ENVIO_MS` do chamado.
4. WHERE `API_FEEDBACK_URL` é uma URL `https`, ou `http` em `localhost` ou `127.0.0.1`, THE Ponto_de_Integracao_de_Feedback SHALL operar em Modo_API.
5. IF `API_FEEDBACK_URL` está ausente, vazia ou inválida, THEN THE Ponto_de_Integracao_de_Feedback SHALL operar em Modo_Prototipo e SHALL NOT realizar nenhuma requisição de rede, mesmo que `API_CHAMADOS_URL` esteja preenchida.
6. THE Sistema SHALL NOT enviar Feedback para `API_CHAMADOS_URL`.
7. WHILE Modo_API está ativo, WHEN um Feedback válido é enviado, THE Ponto_de_Integracao_de_Feedback SHALL enviar um `POST` com `Content-Type: application/json` e corpo igual ao Payload_do_Feedback serializado, com tempo limite de envio aplicado por `AbortController`.
8. WHILE Modo_API está ativo, THE Sistema SHALL NOT gravar o Feedback no Repositorio_de_Feedbacks e SHALL NOT incluir no front end nenhum segredo, token ou chave de API.
9. WHILE Modo_API está ativo, WHEN o Back_end responde com status HTTP 2xx, THE Ponto_de_Integracao_de_Feedback SHALL considerar o envio bem-sucedido, sem exigir corpo de resposta nem protocolo.
10. IF, em Modo_API, o Back_end responde com status fora de 2xx, a requisição falha por rede ou o tempo limite é excedido, THEN THE Ponto_de_Integracao_de_Feedback SHALL devolver falha com a categoria correspondente (resposta, rede ou tempo limite), sem lançar exceção não tratada.
11. THE Payload_do_Feedback SHALL ser um objeto JSON com exatamente os campos `versaoContrato` (texto, inicialmente `"1"`), `chaveIdempotencia`, `enviadoEm`, `comentario`, `nota`, `problemaId` e `modelo`, sem nenhum outro campo.
12. THE Payload_do_Feedback SHALL ter `chaveIdempotencia` no formato de UUID versão 4; `enviadoEm` em ISO 8601 com fuso horário; `comentario` normalizado conforme o requisito 6, com 1 a 500 caracteres; `nota` inteiro de 1 a 5 ou `null`; `problemaId` inteiro igual ao `ID` da rota; e `modelo` igual ao identificador do modelo escolhido ou `null` quando não informado.
13. THE Payload_do_Feedback SHALL NOT conter nome, e-mail, telefone, protocolo, título do problema, dados do Registro_de_Metricas nem identificadores do banco de dados.
14. FOR ALL Payloads_do_Feedback válidos, serializar para JSON e desserializar SHALL produzir um objeto equivalente ao original, com os mesmos campos e valores idênticos caractere a caractere (propriedade de ida e volta).
15. FOR ALL Chaves_de_Idempotencia geradas para Feedbacks, a chave SHALL corresponder ao formato de UUID versão 4 e SHALL ser diferente das chaves geradas para outros Feedbacks na mesma execução.
16. THE Sistema SHALL manter a lista de pontos em aberto com o Back_end (URL por ambiente, autenticação, CORS, esquema do banco, resposta, idempotência repetida, limites e retenção) registrada como `PENDENTE` nos comentários de `js/data.js` junto da configuração do feedback.

### Requirement 11: Medir comentários sem guardar o texto

**User Story:** Como time de Customer Success, quero saber quantos consumidores comentaram, para que eu veja o engajamento do feedback sem que o texto fique nas métricas.

#### Acceptance Criteria

1. WHEN um Feedback é enviado com sucesso, THE Sistema SHALL registrar no Registro_de_Metricas exatamente um Evento_Comentario, contendo somente o tipo `comentario`, o instante do registro, o problema e o modelo (ou `nao-informado`).
2. THE Sistema SHALL omitir o texto do Comentario, a nota, o tamanho do texto, a Chave_de_Idempotencia e qualquer dado pessoal de todo evento gravado no Registro_de_Metricas.
3. THE Sistema SHALL incluir a chave `comentario` e as chaves de texto livre equivalentes (`texto`, `feedback`) na lista de chaves proibidas de `extras` dos eventos de métrica, de modo que nenhum evento aceite essas chaves.
4. IF o envio do Feedback falhar, THEN THE Sistema SHALL NOT registrar o Evento_Comentario.
5. THE Sistema SHALL incluir em `TRESMetricas.resumo()` o campo `comentarios`, igual à quantidade de Eventos_Comentario presentes no Registro_de_Metricas, ou 0 quando não houver nenhum.
6. THE Sistema SHALL manter em `TRESMetricas.resumo()` o cálculo atual de `resolvidos`, `encaminhadosAoSuporte`, `deflexaoPercentual`, `porProblema` e `chamadosAbertos`, de modo que Eventos_Comentario não alterem nenhum desses valores.
7. IF o Registro_de_Metricas estiver indisponível ou a gravação do Evento_Comentario falhar, THEN THE Sistema SHALL tratar o envio do Feedback como bem-sucedido, exibir a Mensagem_de_Agradecimento e não exibir mensagem de erro relacionada às métricas.
8. THE Sistema SHALL manter o evento `avaliacao` com `desfecho` igual a `resolvido` no mesmo formato anterior a esta funcionalidade, sem acrescentar a ele o Comentario nem qualquer indicação de que há comentário.

### Requirement 12: Acessibilidade e uso no celular

**User Story:** Como consumidor, inclusive com deficiência, quero comentar com facilidade no celular, para que ninguém fique sem poder dar sua opinião por barreira de uso.

#### Acceptance Criteria

1. THE Tela_de_Resolvido SHALL exibir todo o seu conteúdo, incluindo o Formulario_de_Feedback, sem rolagem horizontal e sem sobreposição ou corte de texto, em larguras de viewport de 360 px a 1024 px, tendo 360 px como largura de projeto de referência.
2. THE Sistema SHALL garantir Alvos_de_Toque de no mínimo 44 px por 44 px, com espaçamento de no mínimo 8 px entre Alvos_de_Toque adjacentes, no Campo_de_Comentario, no Botao_Enviar_Comentario, nas estrelas e nos links da Tela_de_Resolvido.
3. THE Campo_de_Comentario SHALL usar fonte de no mínimo 16 px, incluindo o texto digitado.
4. THE Sistema SHALL permitir que todas as ações do Formulario_de_Feedback (focar o campo, enviar, tentar de novo) sejam executadas somente com o teclado (Tab e Shift+Tab para mover o foco; Enter ou Espaço para ativar o botão), na ordem visual dos controles (estrelas, Campo_de_Comentario, Botao_Enviar_Comentario, links), sem armadilha de foco.
5. WHEN um controle do Formulario_de_Feedback recebe o foco do teclado, THE Sistema SHALL exibir um indicador de foco com espessura mínima de 2 px e contraste mínimo de 3:1 em relação às cores adjacentes, sem ficar oculto ou cortado.
6. THE Sistema SHALL manter relação de contraste mínima de 4,5:1 entre texto e fundo, em todos os estados (normal, foco, erro, desabilitado após envio), para o rótulo, o contador, o Aviso_de_Nao_Identificacao, a mensagem de erro, a Mensagem_de_Agradecimento e a Mensagem_de_Falha_de_Feedback.
7. THE Sistema SHALL comunicar o estado de erro, de envio em andamento, de falha e de sucesso por texto, e não apenas por cor, forma ou ícone.
8. WHERE o sistema do Consumidor sinaliza `prefers-reduced-motion: reduce`, THE Sistema SHALL suprimir transições, animações e rolagens suaves do Formulario_de_Feedback, de modo que a mudança de estado seja imediata (duração de 0 ms).
9. THE Sistema SHALL manter o Componente_de_Avaliacao com Alvos_de_Toque de no mínimo 44 px por 44 px, nome acessível por botão no formato "N estrela(s) de 5", estado `aria-pressed` e operação por teclado, sem alteração em relação à versão anterior.
10. THE Bloco_de_Feedback SHALL ser identificado para Leitores_de_Tela como um grupo com nome acessível igual ao título visível da avaliação.
11. THE Sistema SHALL manter a barra de etapas indicando a etapa 3 ("A solução") como etapa atual na Tela_de_Resolvido, como na versão anterior.

### Requirement 13: Carregar textos e configuração de js/data.js

**User Story:** Como mantenedor, quero que todos os textos e a configuração do feedback fiquem em `js/data.js`, para que o conteúdo seja revisado em um só lugar e a tela não quebre se algo faltar.

#### Acceptance Criteria

1. THE Sistema SHALL carregar de `js/data.js` todos os textos novos do feedback (título do bloco, rótulo e indicação "opcional", Aviso_de_Nao_Identificacao, formato do contador, Botao_Enviar_Comentario, texto de envio em andamento, mensagem de erro de comentário vazio, anúncios, Mensagem_de_Agradecimento e Mensagem_de_Falha_de_Feedback), sem que nenhum deles esteja escrito diretamente em `index.html` ou `js/app.js`.
2. THE Sistema SHALL agrupar textos e configuração do feedback em uma estrutura própria de `TRES_DATA`, separada de `TRES_DATA.CHAMADO`, sem alterar as chaves nem os valores já existentes de `TRES_DATA.CHAMADO`.
3. THE Sistema SHALL inserir os textos do feedback na página por `textContent` e SHALL tratar marcadores `{chave}` dos textos como substituição por texto literal.
4. IF algum texto obrigatório do feedback ou a estrutura de configuração do feedback estiver ausente ou vazio (após remover espaços) em `js/data.js`, THEN THE Sistema SHALL omitir o Formulario_de_Feedback, SHALL manter o Componente_de_Avaliacao e os demais blocos da Tela_de_Resolvido funcionando e SHALL NOT exibir erro técnico ao Consumidor.
5. THE Sistema SHALL escrever os textos do feedback em português do Brasil, em tom direto, sem palavras vagas como "rapidamente" ou "adequado", e sem pedir dado pessoal.
6. THE Sistema SHALL marcar como `PENDENTE` ou `ILUSTRATIVO`, nos comentários de `js/data.js`, os valores ainda não validados (URL da API de feedback, tempo limite e texto do aviso de não identificação, sujeito a revisão jurídica).

### Requirement 14: Preservar o restante da jornada e os arquivos existentes

**User Story:** Como mantenedor do projeto, quero que a mudança não afete o resto da jornada nem os materiais originais, para que o protótipo continue estável.

#### Acceptance Criteria

1. WHEN o usuário acessa cada uma das rotas `#/`, `#/problemas`, `#/solucao/ID`, `#/confirma/ID`, `#/suporte/ID`, `#/chamado/ID` e `#/contato`, THE Sistema SHALL exibir a mesma tela da versão anterior a esta funcionalidade, com os mesmos textos, a mesma ordem de elementos, os mesmos destinos de botões e links e o mesmo comportamento do botão voltar do navegador.
2. THE Tela_de_Resolvido SHALL manter o título "Que bom! Seu café está de volta.", o texto de apoio, o título "Como foi a ajuda?", o Componente_de_Avaliacao, o bloco "Cuidados com a sua máquina" e os links "Tenho outro problema" e "Voltar ao início" com os mesmos textos e destinos, acrescentando somente o Formulario_de_Feedback.
3. THE Tela_de_Confirmacao e a Tela_de_Chamado SHALL NOT exibir o Formulario_de_Feedback nem enviar Feedback.
4. THE Sistema SHALL manter o Formulario_de_Chamado, a validação do chamado, o Modo_Prototipo e o Modo_API do chamado, o Repositorio_de_Chamados e o Payload_do_Chamado sem nenhuma alteração de comportamento.
5. THE Sistema SHALL manter o cabeçalho com o link "Falar com a gente" e o rodapé com os canais de atendimento com os mesmos textos, valores e destinos da versão anterior.
6. THE Sistema SHALL funcionar quando servido por um servidor HTTP estático, sem etapa de build, sem etapa de instalação de pacotes e sem adicionar bibliotecas, fontes ou scripts de terceiros além dos já existentes em `js/vendor`.
7. THE Sistema SHALL manter inalterados, byte a byte, todos os arquivos existentes em `material/`, as imagens originais `img/LOV.png`, `img/Luna.png`, `img/Modo.png`, `img/Passione.png` e `img/TOUCH.png`, e o arquivo `.glb` original, sem renomear, mover, excluir nem criar arquivos dentro de `material/`.
8. THE Sistema SHALL manter `API_CHAMADOS_URL` e `API_FEEDBACK_URL` vazias no repositório do protótipo.
9. THE suíte de testes existente (`npm test`, `npm run test:ui` e `node tests/verificar-protegidos.js --conferir`) SHALL continuar passando depois da atualização dos testes que verificam a Tela_de_Resolvido (regressão de rotas, estrelas, texto literal e dados pessoais) para refletir o novo bloco, e SHALL cobrir os requisitos 3 a 11 com testes novos.
