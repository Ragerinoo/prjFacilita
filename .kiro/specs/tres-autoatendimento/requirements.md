# Requirements Document

**Documento de Requisitos — TRES Autoatendimento**

## Introduction

O TRES Autoatendimento é um canal web único e padronizado para consumidores de máquinas de café TRES (3corações) resolverem sozinhos o que não é defeito e chegarem ao atendimento humano só quando realmente precisam. Hoje, mais de 70% dos chamados técnicos são falsos defeitos (limpeza simples ou dúvida de uso).

A solução tem 5 camadas, todas na mesma landing page, sem troca de canal e com o contexto preservado:

1. **Encontra o modelo**: QR code colado na máquina ou busca por modelo/foto.
2. **Resolve o comum**: guia determinístico com os 13 falsos defeitos mais comuns, seletor visual de sintoma e instruções animadas.
3. **Pergunta à IA**: assistente com IA (Amazon Bedrock AgentCore) que responde só com base nos manuais, para texto livre fora dos 13 problemas.
4. **Fala com alguém**: repasse inteligente ao CS com pacote estruturado, prioridade e canal definidos por regras determinísticas.
5. **Mede o resultado**: deflexão por camada, precisão da escalada, tempo e custo por dúvida resolvida.

Princípio de "IA sustentável": a IA entra só quando o guia determinístico não cobre o caso, respostas repetidas são reaproveitadas por cache e o custo de cada dúvida resolvida é medido.

Personas: **Renata** (consumidora frustrada, sem manual, quer resolver em poucos passos pelo celular) e **Bruno** (atendente de CS que quer dedicar tempo aos casos que precisam de uma pessoa).

Contexto do hackathon: 2 dias de duração, com o protótipo demonstrado ao vivo, banco de dados real na AWS e agente construído com Amazon Bedrock AgentCore. Cada requisito tem uma marcação de escopo:

- **[MVP]**: essencial para a demo em 2 dias.
- **[MVP-simplificado]**: entra na demo em versão reduzida, com a versão completa descrita na seção "Fora do escopo do MVP".

Convenção EARS em português: QUANDO (event-driven), ENQUANTO (state-driven), SE … ENTÃO (unwanted event), ONDE (optional feature), O <Sistema> DEVE (ubiquitous).

## Glossary

- **Portal_TRES**: landing page web mobile-first usada pelo Consumidor; reúne as camadas 1 a 4 do lado do cliente.
- **Consumidor**: pessoa dona/usuária de uma máquina TRES que acessa o Portal_TRES.
- **Atendente**: colaborador do CS da 3corações que usa o Painel_CS.
- **Gestor**: usuário do Painel_CS com acesso ao Painel_Metricas.
- **Catalogo_Maquinas**: cadastro de modelos TRES com nome, foto, voltagens e manual associado.
- **Codigo_QR**: QR code colado na máquina contendo o identificador do modelo e, quando disponível, o número de série.
- **Pagina_Maquina**: página do Portal_TRES específica de um modelo, ponto de partida da jornada guiada.
- **Jornada**: sessão de atendimento de um Consumidor, identificada por um `jornada_id`, que registra a máquina, a origem (qr/busca), os passos executados e os resultados em todas as camadas.
- **Problema_Catalogado**: um dos 13 problemas do mapa da jornada (ver Requisito 3), cada um com instrução própria.
- **Guia_Diagnostico**: componente determinístico (árvore de decisão, sem IA) que apresenta os Problemas_Catalogados e as respectivas instruções.
- **Seletor_Visual**: imagem interativa da máquina em que o Consumidor toca na luz/tecla que observa para identificar o sintoma.
- **Assistente_IA**: agente conversacional construído com Amazon Bedrock AgentCore que faz triagem e responde com base na Base_Conhecimento.
- **Base_Conhecimento**: conjunto indexado dos manuais oficiais TRES usado pelo Assistente_IA para recuperação (RAG).
- **Pontuacao_Relevancia**: valor numérico de 0 a 1 retornado pela busca na Base_Conhecimento para cada trecho recuperado.
- **Limiar_Relevancia**: valor configurável de Pontuacao_Relevancia abaixo do qual a resposta é considerada sem embasamento (padrão 0,5).
- **Cache_Respostas**: repositório de pares pergunta normalizada → resposta aprovada, consultado antes de acionar o modelo de linguagem.
- **Detector_Risco**: componente determinístico que identifica termos de risco de segurança (cheiro de queimado, fumaça, choque, faísca, vazamento interno) na Jornada.
- **Motor_Escalada**: componente de regras determinísticas que decide quando escalar, a prioridade e o canal recomendado.
- **Pacote_Repasse**: registro estruturado entregue ao CS ao escalar uma Jornada (ver Requisito 10).
- **Chamado**: registro de atendimento humano criado a partir de um Pacote_Repasse, identificado por um número de chamado legível pelo Consumidor.
- **Ordem_Servico**: registro interno de solicitação de assistência técnica vinculado a um Chamado.
- **Painel_CS**: aplicação web autenticada usada pelo Atendente para tratar Chamados.
- **Painel_Metricas**: visão do Painel_CS com os indicadores da camada 5.
- **Servico_Metricas**: componente que registra eventos de resolução por camada e calcula os indicadores.
- **Desfecho**: classificação final de um Chamado marcada pelo Atendente: falso defeito ou defeito real, mais a solução usada.
- **Dados_Pessoais**: telefone, CEP e qualquer outro dado que identifique o Consumidor.

## Requirements

### Requirement 1: Acesso pelo QR code [MVP]

**User Story:** Como Consumidor, quero escanear o QR code da minha máquina e cair direto na página dela, para não precisar descobrir qual é o meu modelo.

#### Acceptance Criteria

1. QUANDO o Consumidor abre a URL de um Codigo_QR válido (identificador de modelo presente no Catalogo_Maquinas), O Portal_TRES DEVE exibir a Pagina_Maquina do modelo correspondente em até 3 segundos, sem nenhuma tela intermediária, formulário, login ou ação adicional do Consumidor, em conexão móvel 4G.
2. QUANDO o Codigo_QR contém número de série de 1 a 30 caracteres alfanuméricos, O Portal_TRES DEVE registrar o número de série na Jornada, associado ao `jornada_id`, no mesmo acesso em que a Pagina_Maquina é exibida.
3. QUANDO uma Jornada é iniciada a partir de um Codigo_QR, O Portal_TRES DEVE criar a Jornada com um `jornada_id` único e registrar a origem "qr" e o modelo da máquina na Jornada.
4. SE o Codigo_QR referencia um modelo inexistente no Catalogo_Maquinas, ENTÃO O Portal_TRES DEVE exibir a busca de máquinas (Requisito 2) com uma mensagem visível informando que o modelo não foi reconhecido, criar a Jornada com origem "qr" sem modelo associado e manter o Consumidor na busca, sem exibir nenhuma Pagina_Maquina.
5. SE o Codigo_QR contém número de série fora do formato (vazio, com mais de 30 caracteres ou com caracteres não alfanuméricos) e identificador de modelo válido, ENTÃO O Portal_TRES DEVE exibir a Pagina_Maquina do modelo normalmente e criar a Jornada sem número de série, sem exibir erro ao Consumidor.
6. SE a URL aberta não contém identificador de modelo legível (ausente ou malformado), ENTÃO O Portal_TRES DEVE exibir a busca de máquinas (Requisito 2) com uma mensagem visível informando que o código não pôde ser lido, sem exibir nenhuma Pagina_Maquina.
7. SE o Catalogo_Maquinas não responde em até 5 segundos ao ser consultado para um Codigo_QR, ENTÃO O Portal_TRES DEVE exibir uma mensagem de erro informando indisponibilidade temporária, oferecer ao Consumidor a ação de tentar novamente e não criar a Jornada até que o modelo seja resolvido.

### Requirement 2: Busca da máquina por modelo [MVP]

**User Story:** Como Consumidor sem QR code, quero encontrar minha máquina pelo nome ou pela foto, para chegar ao guia certo.

#### Acceptance Criteria

1. O Portal_TRES DEVE exibir na página inicial um campo de busca por nome de modelo, com limite de 50 caracteres, e uma grade com a foto e o nome de cada modelo do Catalogo_Maquinas, em ordem alfabética de nome e sem paginação.
2. QUANDO o Consumidor digita ao menos 2 caracteres no campo de busca, desconsiderados os espaços no início e no fim do texto, O Portal_TRES DEVE filtrar a grade em até 1 segundo para os modelos cujo nome contém o texto digitado, sem diferenciar maiúsculas, minúsculas e acentos.
3. QUANDO o campo de busca passa a ter menos de 2 caracteres, inclusive quando o Consumidor apaga o texto digitado, O Portal_TRES DEVE exibir a grade completa de modelos do Catalogo_Maquinas.
4. QUANDO o Consumidor seleciona um modelo, O Portal_TRES DEVE exibir a Pagina_Maquina desse modelo e registrar na Jornada a origem "busca" e o modelo selecionado.
5. SE a busca não retorna nenhum modelo, ENTÃO O Portal_TRES DEVE exibir a grade completa de modelos, manter o texto digitado no campo de busca e exibir a mensagem "Não encontramos esse nome. Escolha sua máquina pela foto."
6. SE a foto de um modelo não carrega, ENTÃO O Portal_TRES DEVE exibir uma imagem substituta no lugar da foto, manter o nome do modelo visível e manter o modelo selecionável.
7. SE o Catalogo_Maquinas não pode ser carregado, ENTÃO O Portal_TRES DEVE exibir uma mensagem informando que a lista de máquinas está indisponível e um botão para tentar novamente, e DEVE desabilitar o campo de busca até que o carregamento seja bem-sucedido.

### Requirement 3: Guia de diagnóstico dos 13 problemas [MVP]

**User Story:** Como Consumidor, quero escolher meu sintoma numa lista curta e seguir uma instrução clara, para resolver sozinho em poucos passos.

#### Acceptance Criteria

1. QUANDO o Consumidor abre a Pagina_Maquina, A Pagina_Maquina DEVE exibir os 13 Problemas_Catalogados, cada um com título de no máximo 40 caracteres, sem termos técnicos de manutenção, e ícone com texto alternativo, na seguinte ordem: (1) Máquina não está ligando; (2) Luz vermelha fixa; (3) Alerta vermelho piscando; (4) Teclas das xícaras e sensor vermelho piscando; (5) Luz amarela acesa; (6) Não extrai bebidas; (7) Bebida aguada; (8) Bebida fria; (9) Alavanca travada; (10) Vazamento; (11) Não puxa água; (12) Bico entupido; (13) Alavanca não fecha com cápsula.
2. A Pagina_Maquina DEVE exibir a opção "Meu problema não está na lista / Não sei qual é" após os 13 Problemas_Catalogados. QUANDO o Consumidor seleciona essa opção, A Pagina_Maquina DEVE abrir o Assistente_IA (Requisito 6) mantendo a Jornada atual.
3. QUANDO o Consumidor seleciona um Problema_Catalogado, O Guia_Diagnostico DEVE exibir a instrução correspondente ao modelo da Jornada em passos numerados a partir de 1, com uma ação por passo, no máximo 10 passos por instrução e no máximo 140 caracteres de texto por passo.
4. O Guia_Diagnostico DEVE exibir, para cada passo da instrução, uma animação ou ilustração da ação a executar e um texto alternativo descritivo de no máximo 125 caracteres. SE a animação ou ilustração de um passo não carregar em até 5 segundos, ENTÃO O Guia_Diagnostico DEVE exibir o texto do passo e o texto alternativo no lugar da mídia, sem bloquear o avanço para o passo seguinte.
5. QUANDO o Consumidor seleciona um Problema_Catalogado diferente de "Vazamento", O Guia_Diagnostico DEVE exibir o primeiro passo da instrução em no máximo 2 toques a partir da Pagina_Maquina, contando o toque de seleção do problema. QUANDO o Consumidor seleciona "Vazamento", O Guia_Diagnostico DEVE exibir o primeiro passo da instrução em no máximo 3 toques, incluindo a resposta à pergunta do critério 7.
6. O Guia_Diagnostico DEVE selecionar instruções e próximos passos apenas por regras determinísticas, de modo que a mesma combinação de Problema_Catalogado, modelo e respostas do Consumidor produza sempre a mesma instrução e a mesma sequência de passos, sem acionar o Assistente_IA.
7. QUANDO o Consumidor seleciona o Problema_Catalogado "Vazamento", O Guia_Diagnostico DEVE perguntar se o vazamento é externo ou interno, com exatamente duas opções de resposta, antes de exibir qualquer passo da instrução.
8. QUANDO o Consumidor informa vazamento interno, O Guia_Diagnostico DEVE acionar o Motor_Escalada com risco de segurança (Requisito 9) e DEVE deixar de exibir passos de autoatendimento para esse vazamento.
9. QUANDO o Consumidor seleciona um Problema_Catalogado, exibe um passo ou conclui um passo, O Guia_Diagnostico DEVE registrar na Jornada o Problema_Catalogado, o número do passo, o tipo do evento (selecionado ou concluído) e o horário com data, hora e segundos.
10. SE não existir instrução cadastrada para a combinação do Problema_Catalogado selecionado com o modelo da Jornada, ENTÃO O Guia_Diagnostico DEVE exibir uma mensagem informando que não há instrução disponível para esse modelo, oferecer as opções de abrir o Assistente_IA (Requisito 6) e de voltar à Pagina_Maquina, e preservar a Jornada sem alterações.
11. QUANDO o Consumidor informa vazamento externo, O Guia_Diagnostico DEVE exibir a instrução de vazamento externo correspondente ao modelo da Jornada, conforme o critério 3.
12. SE o registro na Jornada falhar, ENTÃO O Guia_Diagnostico DEVE manter o passo exibido e o avanço liberado, reter o registro pendente e tentar gravá-lo novamente até 3 vezes em intervalos de 5 segundos, sem exibir ao Consumidor mensagem que interrompa o fluxo.

### Requirement 4: Seletor visual de sintoma [MVP-simplificado]

**User Story:** Como Consumidor que não sabe nomear o sintoma, quero tocar na luz ou tecla que está piscando numa imagem da minha máquina, para identificar o problema sem ler termos técnicos.

#### Acceptance Criteria

1. ONDE o modelo da Jornada possui imagem mapeada, A Pagina_Maquina DEVE exibir o Seletor_Visual com áreas tocáveis para luzes, teclas, alavanca, reservatório e bico, sendo que cada área mapeada para o modelo corresponde a um único componente físico e não se sobrepõe a outra área.
2. QUANDO o Consumidor toca uma área do Seletor_Visual, O Seletor_Visual DEVE destacar visualmente a área tocada e exibir, em até 1 segundo, a pergunta sobre o estado observado com no mínimo 2 e no máximo 5 opções entre acesa fixa, piscando, apagada, travada e vazando, sendo apresentadas apenas as opções que o mapeamento do modelo define como aplicáveis àquela área.
3. QUANDO o Consumidor informa área e estado que correspondem a exatamente um Problema_Catalogado, O Seletor_Visual DEVE abrir a instrução desse Problema_Catalogado no Guia_Diagnostico em até 2 segundos e registrar a área e o estado informados na Jornada.
4. SE a combinação de área e estado não corresponde a nenhum Problema_Catalogado, ENTÃO O Seletor_Visual DEVE encaminhar o Consumidor ao Assistente_IA com área e estado registrados na Jornada, exibindo ao Consumidor uma indicação de que o problema não foi encontrado no catálogo e preservando a área e o estado informados.
5. O Seletor_Visual DEVE apresentar cada área tocável com tamanho mínimo de 44×44 pixels CSS, rótulo acessível em português do Brasil que identifique o componente (por exemplo, o nome da luz, tecla, alavanca, reservatório ou bico) para leitores de tela, e permitir o acionamento da área também por teclado.
6. SE a combinação de área e estado corresponde a mais de um Problema_Catalogado, ENTÃO O Seletor_Visual DEVE listar até 5 Problemas_Catalogados correspondentes para o Consumidor escolher um, abrindo a instrução do escolhido no Guia_Diagnostico e registrando área, estado e escolha na Jornada.
7. SE o modelo da Jornada não possui imagem mapeada OU a imagem do Seletor_Visual não carrega em até 5 segundos, ENTÃO A Pagina_Maquina DEVE exibir uma mensagem indicando que o seletor visual está indisponível e oferecer o acesso ao Assistente_IA, preservando os dados já registrados na Jornada.
8. QUANDO o Consumidor aciona a opção de voltar enquanto a pergunta de estado está exibida, O Seletor_Visual DEVE fechar a pergunta sem registrar área ou estado na Jornada e permitir a escolha de outra área.

### Requirement 5: Confirmação "Resolveu?" e roteamento após a instrução [MVP]

**User Story:** Como Consumidor, quero dizer se a instrução resolveu, para encerrar logo ou ser levado ao próximo nível de ajuda sem repetir nada.

#### Acceptance Criteria

1. QUANDO o Consumidor conclui o último passo de uma instrução de um Problema_Catalogado, O Guia_Diagnostico DEVE exibir, em até 1 segundo, a pergunta "O problema foi solucionado?" com exatamente duas opções, "Sim" e "Não", e DEVE manter a Jornada sem resposta registrada até que o Consumidor selecione uma das opções.
2. QUANDO o Consumidor responde "Sim", O Portal_TRES DEVE, em até 2 segundos, marcar a Jornada como resolvida na camada "guia" e exibir uma avaliação com seleção de 1 a 5 estrelas (valores inteiros) e um campo de comentário opcional com no máximo 500 caracteres.
3. QUANDO o Consumidor responde "Não" para a instrução de um Problema_Catalogado, O Motor_Escalada DEVE, em até 2 segundos, classificar a Jornada como provável defeito e iniciar o repasse ao CS com prioridade P2, sem passar pelo Assistente_IA, preservando na Jornada a máquina, o Problema_Catalogado e os passos executados.
4. QUANDO o repasse de um Problema_Catalogado é iniciado, O Portal_TRES DEVE exibir, junto à confirmação do repasse, a opção "Prefiro descrever ao assistente", e, QUANDO o Consumidor seleciona essa opção, O Portal_TRES DEVE abrir o Assistente_IA em até 2 segundos com o mesmo jornada_id, sem solicitar novamente o modelo da máquina nem o problema selecionado.
5. QUANDO o Consumidor envia uma avaliação com nota entre 1 e 5, O Servico_Metricas DEVE registrar a nota (e o comentário, se informado) associada ao jornada_id e à camada em que a Jornada foi encerrada, aceitando no máximo 1 avaliação por Jornada, e O Portal_TRES DEVE exibir uma confirmação de envio ao Consumidor.
6. SE o Motor_Escalada falhar ao iniciar o repasse ao CS após a resposta "Não", ENTÃO O Portal_TRES DEVE manter a Jornada e seus dados preservados, exibir uma mensagem de erro indicando que o repasse não foi iniciado e oferecer a ação "Tentar novamente" (até 3 tentativas) e a opção "Prefiro descrever ao assistente".
7. SE o Servico_Metricas falhar ao registrar a avaliação, ENTÃO O Portal_TRES DEVE reter a nota e o comentário informados, tentar o registro novamente até 3 vezes e, persistindo a falha, exibir ao Consumidor uma mensagem indicando que a avaliação não foi registrada, sem reabrir a Jornada nem alterar seu estado de resolvida.

### Requirement 6: Assistente com IA baseado nos manuais [MVP]

**User Story:** Como Consumidor com um problema fora da lista, quero descrever o que acontece em texto livre e receber uma resposta confiável, para resolver sem ligar para ninguém.

#### Acceptance Criteria

1. QUANDO o Consumidor abre o Assistente_IA, O Portal_TRES DEVE exibir o chat na mesma página, sem navegar para outra página, em até 2 segundos, e repassar ao Assistente_IA o modelo, o número de série e a lista completa dos passos já registrados na Jornada.
2. QUANDO o Consumidor envia uma mensagem válida, O Assistente_IA DEVE responder usando exclusivamente trechos da Base_Conhecimento do modelo da Jornada, sem usar trechos de outros modelos.
3. QUANDO o Assistente_IA apresenta uma instrução, O Assistente_IA DEVE indicar na mesma resposta o nome do manual e a seção de origem de cada instrução apresentada.
4. SE nenhum trecho foi recuperado ou todos os trechos recuperados têm Pontuacao_Relevancia abaixo do Limiar_Relevancia, ENTÃO O Assistente_IA DEVE exibir uma mensagem informando que não encontrou orientação no manual e acionar o Motor_Escalada, sem gerar nenhuma instrução.
5. QUANDO a descrição do Consumidor corresponde a um Problema_Catalogado, O Assistente_IA DEVE oferecer a instrução do Guia_Diagnostico correspondente, com a indicação do manual e da seção de origem, em vez de gerar uma nova resposta.
6. QUANDO o Assistente_IA apresenta uma solução, O Assistente_IA DEVE perguntar "Isso resolveu?" com as opções "Sim" e "Não" na mesma resposta, e manter as duas opções disponíveis até o Consumidor escolher uma delas.
7. QUANDO o Consumidor responde "Sim" a uma solução do Assistente_IA, O Portal_TRES DEVE marcar a Jornada como resolvida na camada "ia" e exibir a avaliação do Requisito 5 em até 2 segundos.
8. QUANDO o Consumidor envia uma mensagem válida, O Assistente_IA DEVE exibir o início da resposta em até 10 segundos em pelo menos 90% das mensagens (percentil 90), medidos do envio da mensagem até a exibição do primeiro conteúdo da resposta.
9. QUANDO ocorre uma mensagem do Consumidor, uma solução sugerida pelo Assistente_IA ou uma resposta do Consumidor a "Isso resolveu?", O Assistente_IA DEVE registrar o evento na Jornada, em ordem cronológica e com data e hora, antes de apresentar a próxima interação ao Consumidor.
10. QUANDO o Consumidor responde "Não" à primeira solução do Assistente_IA na Jornada, O Assistente_IA DEVE oferecer uma segunda solução baseada na Base_Conhecimento. QUANDO o Consumidor responde "Não" à segunda solução, O Motor_Escalada DEVE escalar a Jornada (Requisito 9, critério 2) e o Assistente_IA DEVE informar ao Consumidor que o atendimento será encaminhado a uma pessoa.
11. SE a mensagem do Consumidor estiver vazia, contiver apenas espaços ou tiver mais de 1.000 caracteres, ENTÃO O Assistente_IA DEVE rejeitar o envio, exibir um aviso indicando o motivo da rejeição e manter o texto digitado no campo de entrada, sem registrar a mensagem na Jornada.
12. SE o Assistente_IA ficar indisponível ou não exibir resposta em até 30 segundos após o envio da mensagem, ENTÃO O Portal_TRES DEVE exibir um aviso de falha, preservar a mensagem enviada e o histórico da conversa, oferecer ao Consumidor as opções "Tentar novamente" e "Falar com uma pessoa" (que aciona o Motor_Escalada), e registrar a falha na Jornada.

### Requirement 7: IA sustentável — cache e controle de custo [MVP-simplificado]

**User Story:** Como Gestor, quero que perguntas repetidas sejam respondidas sem novo custo de IA, para manter o custo por dúvida resolvida baixo.

#### Acceptance Criteria

1. QUANDO o Consumidor envia uma mensagem ao Assistente_IA, O Assistente_IA DEVE consultar o Cache_Respostas pelo par formado pelo modelo da máquina e pela pergunta normalizada (conversão para minúsculas, remoção de acentos, remoção de pontuação, substituição de sequências de espaços por um único espaço e remoção de espaços nas extremidades) antes de acionar o modelo de linguagem.
2. QUANDO existe uma entrada no Cache_Respostas com o mesmo modelo de máquina e a mesma pergunta normalizada, O Assistente_IA DEVE retornar a resposta em cache ao Consumidor em até 2 segundos e registrar na Jornada a origem "cache" com tokens de entrada, tokens de saída e custo estimado iguais a zero.
3. QUANDO o Assistente_IA aciona o modelo de linguagem e recebe a resposta, O Assistente_IA DEVE registrar na Jornada a origem "modelo", a quantidade de tokens de entrada, a quantidade de tokens de saída (inteiros maiores ou iguais a zero) e o custo estimado da chamada em reais (BRL) com 4 casas decimais.
4. O Assistente_IA DEVE limitar cada Jornada a no máximo 10 mensagens do Consumidor processadas pelo modelo de linguagem, sendo que respostas servidas pelo Cache_Respostas não contam para esse limite.
5. QUANDO uma Jornada atinge o limite de 10 mensagens processadas pelo modelo de linguagem do critério 4, O Motor_Escalada DEVE iniciar o repasse ao CS, informar ao Consumidor que o atendimento será continuado pelo CS, preservar o histórico da Jornada e impedir que novas mensagens dessa Jornada acionem o modelo de linguagem.
6. O Cache_Respostas DEVE aceitar novas entradas apenas a partir de respostas aprovadas por um Atendente (Requisito 16).
7. SE uma tentativa de inserir no Cache_Respostas uma resposta não aprovada por um Atendente é feita, ENTÃO O Cache_Respostas DEVE rejeitar a inserção, manter o conteúdo existente inalterado e registrar a rejeição na Jornada.
8. SE o Cache_Respostas está indisponível ou não responde em até 2 segundos durante a consulta do critério 1, ENTÃO O Assistente_IA DEVE tratar a consulta como ausência de entrada correspondente, acionar o modelo de linguagem e registrar na Jornada a origem "modelo".
9. SE o modelo de linguagem retorna erro ou não responde em até 30 segundos, ENTÃO O Assistente_IA DEVE informar ao Consumidor que não foi possível responder naquele momento, não contar a mensagem para o limite do critério 4, preservar a mensagem na Jornada e aplicar o tratamento de indisponibilidade do Requisito 6, critério 12.

### Requirement 8: Detecção de risco de segurança [MVP]

**User Story:** Como 3corações, quero que qualquer sinal de risco à segurança vá direto para uma pessoa, para proteger o Consumidor.

#### Acceptance Criteria

1. QUANDO uma mensagem do Consumidor contém termo da lista de risco (queimado, fumaça, choque, faísca, vazamento interno e sinônimos configurados), O Detector_Risco DEVE marcar a Jornada com risco de segurança em até 1 segundo após o recebimento da mensagem e antes de enviá-la ao modelo de linguagem, comparando os termos sem diferenciar maiúsculas, minúsculas e acentos, marcando também quando a mensagem contém o termo precedido de negação (exemplo: "não sai fumaça"), e registrando na Jornada o horário e a origem "lista" da marcação.
2. QUANDO o Assistente_IA classifica uma mensagem como risco de segurança, O Detector_Risco DEVE marcar a Jornada com risco de segurança em até 1 segundo após a classificação, registrando na Jornada o horário e a origem "ia" da marcação.
3. QUANDO uma Jornada é marcada com risco de segurança, O Portal_TRES DEVE exibir em até 2 segundos a orientação "Desligue a máquina da tomada e não a utilize" em um bloco de alerta posicionado no topo da área de conteúdo, anunciado por leitores de tela como alerta, e mantê-lo visível em todas as telas do Portal_TRES até o encerramento da Jornada.
4. ENQUANTO uma Jornada está marcada com risco de segurança, O Assistente_IA DEVE encerrar a tentativa de solução para essa Jornada, descartando qualquer resposta em andamento, sem gerar nem exibir novas instruções de solução, e O Detector_Risco DEVE manter a marcação até o encerramento da Jornada, sem que o Consumidor possa removê-la.
5. QUANDO uma Jornada é marcada com risco de segurança, O Portal_TRES DEVE iniciar em até 5 segundos o repasse ao CS com prioridade P1, uma única vez por Jornada, mesmo que a marcação seja repetida por outra origem.
6. SE o repasse ao CS de uma Jornada com risco de segurança falha ou não é confirmado em até 10 segundos, ENTÃO O Portal_TRES DEVE manter a orientação do critério 3 visível, informar ao Consumidor que o contato com o CS ainda não foi registrado, oferecer a ação "Tentar novamente" e preservar a marcação e os dados da Jornada.
7. QUANDO o Guia_Diagnostico registra vazamento interno informado pelo Consumidor (Requisito 3, critério 8), O Detector_Risco DEVE marcar a Jornada com risco de segurança em até 1 segundo, registrando na Jornada o horário e a origem "guia" da marcação.

### Requirement 9: Gatilhos de escalada [MVP]

**User Story:** Como Atendente, quero receber só os casos que precisam de uma pessoa, e recebê-los no momento certo, para não gastar tempo com dúvidas simples nem deixar o Consumidor preso no robô.

#### Acceptance Criteria

1. QUANDO uma Jornada é marcada com risco de segurança, O Motor_Escalada DEVE escalar a Jornada em até 2 segundos após a marcação, sem depender de resposta do Assistente_IA ou de confirmação do Consumidor.
2. QUANDO o Consumidor responde "Não" à pergunta "Isso resolveu?" do Assistente_IA (Requisito 6, critério 6) pela segunda vez na mesma Jornada, O Motor_Escalada DEVE escalar a Jornada em até 2 segundos, contando as respostas "Não" consecutivas ou não e desconsiderando as respostas "Não" do Guia_Diagnostico (tratadas no Requisito 5, critério 3).
3. QUANDO o Consumidor aciona o botão "Falar com uma pessoa" ou envia uma mensagem que contém uma expressão da lista configurável de pedidos de atendimento humano (por exemplo "atendente", "falar com uma pessoa", "humano"), sem diferenciar maiúsculas, minúsculas e acentos, O Motor_Escalada DEVE escalar a Jornada em até 2 segundos.
4. QUANDO o Assistente_IA reporta resposta sem embasamento (Requisito 6, critério 4), O Motor_Escalada DEVE escalar a Jornada em até 2 segundos.
5. QUANDO o Assistente_IA classifica o sentimento de 2 mensagens consecutivas do Consumidor como "frustração alta" (escala de 3 níveis: baixa, média, alta), O Motor_Escalada DEVE escalar a Jornada em até 2 segundos, reiniciando a contagem sempre que uma mensagem for classificada em nível diferente de "alta".
6. ENQUANTO o Consumidor está em qualquer tela do Assistente_IA, O Portal_TRES DEVE exibir o botão "Falar com uma pessoa", visível sem rolagem da página e com tamanho mínimo de 44×44 pixels CSS e rótulo acessível para leitores de tela.
7. QUANDO o Motor_Escalada escala uma Jornada, O Motor_Escalada DEVE registrar na Jornada, junto com o horário da escalada, o gatilho que causou a escalada, escolhido entre: risco de segurança, duas negativas ao Assistente_IA, pedido de atendimento humano, resposta sem embasamento, frustração alta, limite de mensagens (Requisito 7, critério 5) e instrução de Problema_Catalogado sem solução (Requisito 5, critério 3).
8. QUANDO o Motor_Escalada escala uma Jornada, O Portal_TRES DEVE informar ao Consumidor em até 2 segundos que o caso será encaminhado a uma pessoa e dar continuidade ao repasse (Requisitos 10 a 12) com a Jornada preservada, sem solicitar novamente modelo, número de série ou passos já executados.
9. SE um gatilho de escalada ocorre em uma Jornada já escalada, ENTÃO O Motor_Escalada DEVE manter o repasse existente sem criar novo Pacote_Repasse ou novo Chamado e DEVE registrar o gatilho adicional na Jornada.
10. SE o Motor_Escalada não consegue registrar o gatilho na Jornada, ENTÃO O Motor_Escalada DEVE escalar a Jornada mesmo assim, marcar o gatilho como "não registrado" no Pacote_Repasse e preservar os dados já registrados na Jornada.

### Requirement 10: Pacote de repasse estruturado [MVP]

**User Story:** Como Atendente, quero receber um resumo completo do caso, para atender sem repetir perguntas ao Consumidor.

#### Acceptance Criteria

1. QUANDO o Motor_Escalada escala uma Jornada, O Sistema de repasse DEVE gerar um Pacote_Repasse com os seguintes campos obrigatórios: número do Chamado; modelo; número de série (texto, ou "não informado" quando ausente na Jornada); origem ("qr" ou "busca"); categoria do sintoma (um dos 13 Problemas_Catalogados ou "outro"); resumo de 1 a 300 caracteres; lista "já tentado" (zero ou mais itens em ordem cronológica, cada um com passo, camada "guia" ou "ia", e resultado "sim", "não" ou "sem resposta"); classificação ("provável defeito" ou "provável uso"); prioridade (P1, P2 ou P3); canal recomendado (um dos canais definidos no Requisito 11); sentimento ("neutro", "frustração moderada" ou "frustração alta"); anexos (lista com 0 a 3 fotos); e sugestão de próxima ação (texto de 1 a 200 caracteres).
2. QUANDO o Sistema de repasse gera um Pacote_Repasse, O Sistema de repasse DEVE preencher número do Chamado, modelo, número de série, origem, categoria, lista "já tentado", anexos, classificação, prioridade e canal recomendado a partir dos dados registrados na Jornada e dos valores atribuídos pelo Motor_Escalada (Requisito 11), sem uso do modelo de linguagem.
3. QUANDO o Sistema de repasse gera um Pacote_Repasse, O Sistema de repasse DEVE preencher resumo, sentimento e sugestão de próxima ação a partir do Assistente_IA.
4. SE o Assistente_IA retorna erro, não responde em até 10 segundos, ou retorna resumo vazio ou com mais de 300 caracteres ao gerar os campos do critério 3, ENTÃO O Sistema de repasse DEVE criar o Pacote_Repasse com os campos determinísticos do critério 2, o resumo "Resumo indisponível — ver histórico da Jornada", o sentimento "neutro" e a sugestão de próxima ação "Revisar o histórico da Jornada", sem bloquear a criação do Chamado.
5. O Pacote_Repasse DEVE ser serializado em JSON (codificação UTF-8) conforme um esquema que contém um identificador de versão, com todos os campos obrigatórios do critério 1 presentes.
6. PARA TODO Pacote_Repasse válido, serializar em JSON e desserializar DEVE produzir um Pacote_Repasse equivalente ao original, com os mesmos valores em todos os campos, os mesmos itens da lista "já tentado" na mesma ordem e os caracteres acentuados preservados (propriedade de ida e volta).
7. SE um Pacote_Repasse recebido pelo Painel_CS não atende ao esquema (campo obrigatório ausente, tipo ou valor fora do domínio do critério 1, resumo com mais de 300 caracteres ou versão de esquema não suportada), ENTÃO O Painel_CS DEVE rejeitar o registro sem criar nem alterar nenhum Chamado e retornar um erro que indique cada campo inválido e o motivo da invalidade.
8. QUANDO o Motor_Escalada escala uma Jornada, O Sistema de repasse DEVE disponibilizar o Pacote_Repasse ao Painel_CS em até 15 segundos, inclusive quando o fallback do critério 4 é aplicado.
9. SE a Jornada escalada não possui número de série ou anexos, ENTÃO O Sistema de repasse DEVE gerar um Pacote_Repasse válido com número de série "não informado" e lista de anexos vazia, sem rejeitar o registro no critério 7.

### Requirement 11: Prioridade e canal por regras determinísticas [MVP]

**User Story:** Como Gestor de CS, quero que prioridade e canal sejam definidos por regras claras e auditáveis, para garantir que casos graves sejam atendidos primeiro.

#### Acceptance Criteria

1. QUANDO a Jornada escalada tem risco de segurança, O Motor_Escalada DEVE atribuir prioridade P1, classificação "provável defeito" e canal recomendado "ligação imediata".
2. QUANDO a Jornada escalada não tem risco de segurança e o Consumidor respondeu "Não" à pergunta de confirmação de resolução após concluir a instrução de ao menos um Problema_Catalogado no Guia_Diagnostico, O Motor_Escalada DEVE atribuir prioridade P2, classificação "provável defeito" e canal recomendado "chat ou ligação, à escolha do Consumidor".
3. QUANDO a Jornada escalada não tem risco de segurança e nenhuma instrução de Problema_Catalogado foi respondida com "Não" (inclui Jornadas sem Problema_Catalogado identificado), O Motor_Escalada DEVE atribuir prioridade P3, classificação "provável uso" e canal recomendado "chat assíncrono".
4. QUANDO uma Jornada recebe prioridade P2, O Painel_CS DEVE criar, em até 5 segundos após a criação do Chamado, uma única Ordem_Servico com status "rascunho" vinculada ao Chamado, preenchida com modelo, número de série, categoria do sintoma e lista "já tentado" da Jornada, sem enviá-la para assistência técnica até confirmação do Atendente.
5. O Motor_Escalada DEVE produzir a mesma prioridade, a mesma classificação e o mesmo canal para Jornadas com os mesmos fatos registrados (risco de segurança, Problema_Catalogado e resultado das instruções), independentemente de horário, sentimento, ordem dos gatilhos ou saída do modelo de linguagem.
6. QUANDO uma Jornada tem mais de um gatilho de escalada registrado (Requisito 9), O Motor_Escalada DEVE avaliar os critérios 1 a 3 uma única vez sobre os fatos consolidados da Jornada e atribuir a prioridade mais alta entre os critérios atendidos (P1 > P2 > P3), com a classificação e o canal correspondentes a essa prioridade.
7. QUANDO o Motor_Escalada atribui prioridade, classificação e canal a uma Jornada, O Motor_Escalada DEVE registrar na Jornada os valores atribuídos, o número do critério (1, 2 ou 3) que determinou a atribuição e a data e hora da decisão, e O Painel_CS DEVE disponibilizar esse registro para consulta pelo Gestor.
8. SE a criação da Ordem_Servico em rascunho do critério 4 falha, ENTÃO O Painel_CS DEVE manter o Chamado com a prioridade P2, a classificação e o canal já atribuídos, exibir ao Atendente uma indicação de falha na criação da Ordem_Servico e permitir nova tentativa sem criar Ordem_Servico duplicada.

### Requirement 12: Abertura do chamado pelo Consumidor [MVP]

**User Story:** Como Consumidor, quero saber o número do meu chamado e o que acontece em seguida, informando só o que falta, para não ficar no escuro nem repetir informações.

#### Acceptance Criteria

1. QUANDO um Chamado é criado, O Portal_TRES DEVE exibir ao Consumidor, em até 3 segundos, o número único do Chamado, a prioridade como rótulo textual em linguagem simples (sem exibir as siglas P1, P2 ou P3 nem termos técnicos) e o próximo passo esperado com prazo de contato (P1: ligação em até 15 minutos; P2: contato em até 4 horas úteis; P3: resposta em até 1 dia útil).
2. QUANDO um Chamado P1 ou P2 é criado e o telefone do Consumidor não foi informado durante a Jornada, O Portal_TRES DEVE solicitar o telefone do Consumidor.
3. QUANDO um Chamado P2 é criado e o CEP do Consumidor não foi informado durante a Jornada, O Portal_TRES DEVE solicitar o CEP do Consumidor.
4. O Portal_TRES DEVE solicitar apenas os Dados_Pessoais exigidos para a prioridade do Chamado (P1: telefone; P2: telefone e CEP; P3: nenhum) que não tenham sido informados na Jornada, sem solicitar novamente nenhum dado já informado.
5. QUANDO o Portal_TRES solicita Dados_Pessoais, O Portal_TRES DEVE exibir a finalidade do uso junto ao campo e obter o consentimento explícito do Consumidor, por meio de uma opção que inicia desmarcada, e DEVE manter o envio dos Dados_Pessoais bloqueado até que o Consumidor marque essa opção.
6. SE o telefone informado não tem 10 ou 11 dígitos (DDD incluído), ou o CEP informado não tem 8 dígitos, ou o campo contém caracteres que não sejam dígitos, espaço, parênteses ou hífen, ENTÃO O Portal_TRES DEVE rejeitar o envio, exibir uma mensagem de erro junto ao campo indicando o formato esperado e manter todos os dados já digitados.
7. ONDE o Consumidor deseja anexar evidência, O Portal_TRES DEVE aceitar até 3 fotos por Chamado, nos formatos JPEG ou PNG, com até 5 MB cada, vinculadas ao Chamado.
8. QUANDO o Consumidor acessa o Portal_TRES com o número de um Chamado existente, O Portal_TRES DEVE exibir, em até 3 segundos, o status atual do Chamado e as mensagens do Atendente em ordem cronológica, cada uma com data e hora.
9. SE o Consumidor não fornece o telefone solicitado para um Chamado P1 ou P2, ou não concede o consentimento, ou deixa de informar o CEP solicitado para um Chamado P2, ENTÃO O Portal_TRES DEVE manter o Chamado registrado, manter o número do Chamado visível e informar que o contato no prazo indicado não é garantido sem esse dado, permitindo ao Consumidor informá-lo posteriormente pelo acompanhamento do Chamado.
10. SE o Consumidor seleciona uma foto em formato diferente de JPEG ou PNG, com mais de 5 MB, ou além do limite de 3 fotos, ou se o envio da foto falha, ENTÃO O Portal_TRES DEVE rejeitar apenas essa foto, exibir uma mensagem indicando o motivo da rejeição e manter o Chamado e as fotos já anexadas com sucesso.
11. SE o Consumidor informa um número de Chamado inexistente, ENTÃO O Portal_TRES DEVE exibir uma mensagem de erro indicando que o Chamado não foi encontrado, sem exibir dados de nenhum Chamado, e manter o campo disponível para nova tentativa.

### Requirement 13: Autenticação do Painel do CS [MVP]

**User Story:** Como 3corações, quero que só atendentes autorizados acessem o Painel_CS, para proteger os dados dos consumidores.

#### Acceptance Criteria

1. ENQUANTO o usuário não estiver autenticado, O Painel_CS DEVE exibir somente a tela de login com campos de usuário e senha e DEVE não exibir nenhum Chamado nem Dado_Pessoal.
2. SE uma requisição à API do Painel_CS não contém credencial válida (ausente, malformada, expirada ou de sessão encerrada), ENTÃO O Painel_CS DEVE recusar a requisição com status HTTP 401 e DEVE não retornar nenhum Chamado nem Dado_Pessoal na resposta.
3. ENQUANTO a sessão estiver autenticada com o perfil Atendente, O Painel_CS DEVE ocultar o acesso ao Painel_Metricas e DEVE recusar qualquer requisição ao Painel_Metricas, retornando um indicativo de permissão insuficiente sem expor dados de métricas.
4. ENQUANTO a sessão estiver autenticada com o perfil Gestor, O Painel_CS DEVE liberar o acesso ao Painel_Metricas.
5. ENQUANTO uma sessão do Painel_CS permanecer sem nenhuma interação do usuário nem requisição à API por mais de 30 minutos, O Painel_CS DEVE encerrar a sessão, redirecionar o usuário para a tela de login, DEVE não exibir nenhum Chamado nem Dado_Pessoal e DEVE exigir nova autenticação.
6. QUANDO o usuário envia usuário e senha válidos, O Painel_CS DEVE iniciar uma sessão associada ao perfil Atendente ou Gestor cadastrado para o usuário e DEVE exibir o Painel_CS em até 3 segundos.
7. SE o usuário envia usuário ou senha inválidos, ENTÃO O Painel_CS DEVE recusar o login, DEVE não iniciar sessão, DEVE exibir uma mensagem de erro que não indica qual dos dois campos está incorreto e DEVE manter o usuário na tela de login.
8. SE ocorrerem 5 tentativas de login consecutivas com falha para o mesmo usuário em um intervalo de 15 minutos, ENTÃO O Painel_CS DEVE bloquear novas tentativas de login desse usuário por 15 minutos e DEVE exibir uma mensagem informando o bloqueio temporário.

### Requirement 14: Fila e card do Chamado no Painel do CS [MVP]

**User Story:** Como Atendente, quero ver os chamados ordenados por prioridade, com o resumo e o que já foi tentado no topo, para agir rápido nos casos mais graves.

#### Acceptance Criteria

1. O Painel_CS DEVE exibir a fila de Chamados abertos (todos os Chamados que ainda não foram encerrados, incluindo os já assumidos por um Atendente) ordenada por prioridade (P1, P2, P3) e, dentro da mesma prioridade, por horário de criação crescente, usando o número do Chamado crescente como desempate quando o horário de criação for idêntico.
2. QUANDO um Chamado P1 entra na fila, O Painel_CS DEVE exibir, em até 10 segundos e sem recarregamento manual da página, o Chamado na posição correta da fila com um alerta visual que permaneça visível até que um Atendente abra o Chamado.
3. QUANDO o Atendente abre um Chamado, O Painel_CS DEVE exibir no topo do card, acima do histórico da Jornada, o resumo, a lista "já tentado" (passo, camada guia/ia, resultado), a classificação, a prioridade e o canal recomendado, e DEVE exibir o card completo em até 3 segundos.
4. QUANDO o Atendente abre um Chamado, O Painel_CS DEVE exibir o histórico completo da Jornada em ordem cronológica crescente, incluindo as mensagens do Assistente_IA, as mensagens do Consumidor e os anexos (até 3 fotos), permitindo ao Atendente visualizar cada anexo.
5. QUANDO o Atendente assume um Chamado que não possui responsável, O Painel_CS DEVE registrar o Atendente responsável e o horário de início do atendimento, alterar o status do Chamado para "em atendimento" e exibir o nome do responsável na fila e no card.
6. SE o Atendente tenta assumir um Chamado que já possui outro Atendente responsável, ENTÃO O Painel_CS DEVE recusar a ação, manter o responsável e o horário de início originais e exibir uma mensagem que indique o nome do Atendente responsável.
7. SE não há Chamados abertos, ENTÃO O Painel_CS DEVE exibir na fila uma mensagem indicando que não há Chamados abertos.
8. SE o Painel_CS falha ao carregar a fila ou o card de um Chamado, ENTÃO O Painel_CS DEVE exibir uma mensagem de erro que indique a falha de carregamento, oferecer a ação "Tentar novamente" e manter exibida a última fila carregada com sucesso, sem alterar o estado de nenhum Chamado.

### Requirement 15: Ações e comunicação do Atendente [MVP-simplificado]

**User Story:** Como Atendente, quero agir com um clique e conversar com o Consumidor no mesmo sistema, para resolver sem trocar de ferramenta.

#### Acceptance Criteria

1. O Painel_CS DEVE oferecer no card do Chamado as ações "Abrir Ordem_Servico", "Enviar instrução do manual" e "Agendar ligação", cada uma acionável com um único clique a partir do card, sem navegar para outra tela.
2. QUANDO o Atendente abre um Chamado, O Assistente_IA DEVE gerar, em até 10 segundos, uma sugestão de resposta com base no Pacote_Repasse e na Base_Conhecimento e o Painel_CS DEVE exibi-la em um campo editável, sem enviá-la ao Consumidor.
3. QUANDO o Atendente confirma explicitamente o envio da sugestão aprovada ou editada (texto final de 1 a 2000 caracteres), O Painel_CS DEVE enviar o texto final ao Consumidor, e O Painel_CS NÃO DEVE enviar nenhum texto antes dessa confirmação.
4. QUANDO o Atendente envia uma mensagem, O Portal_TRES DEVE exibir a mensagem, com data e horário de envio, na página de acompanhamento do Chamado em até 10 segundos.
5. QUANDO o Consumidor responde (texto de 1 a 2000 caracteres) na página de acompanhamento do Chamado, O Painel_CS DEVE exibir a resposta, com data e horário de recebimento, no card do Chamado em até 10 segundos e DEVE sinalizar o card como contendo resposta não lida até que o Atendente o abra.
6. QUANDO o Atendente aciona "Agendar ligação" e informa uma data e um horário válidos (futuros, no fuso horário de Brasília, em até 30 dias a partir do momento do agendamento), O Painel_CS DEVE registrar data e horário da ligação no Chamado e O Portal_TRES DEVE exibir o agendamento ao Consumidor na página de acompanhamento do Chamado em até 10 segundos.
7. SE o Assistente_IA falhar ou não gerar a sugestão de resposta em até 10 segundos, ENTÃO O Painel_CS DEVE exibir uma indicação de que a sugestão está indisponível e DEVE manter o campo de resposta vazio e editável, permitindo ao Atendente redigir e enviar a mensagem manualmente, com o Chamado e o Pacote_Repasse preservados.
8. SE o envio de uma mensagem ao Consumidor falhar ou o texto estiver vazio ou acima de 2000 caracteres, ENTÃO O Painel_CS DEVE exibir uma indicação do motivo da falha, DEVE manter o texto digitado no campo de resposta sem alteração, DEVE permitir novo envio e NÃO DEVE exibir a mensagem como enviada na página de acompanhamento do Chamado.
9. SE o Atendente informar data e horário de ligação no passado, fora do limite de 30 dias ou incompletos, ENTÃO O Painel_CS DEVE rejeitar o agendamento, exibir uma indicação do campo inválido e preservar os valores informados, sem registrar nem exibir agendamento ao Consumidor.

### Requirement 16: Fechamento do ciclo e retroalimentação [MVP]

**User Story:** Como Gestor, quero que cada chamado encerrado ensine o sistema, para que a próxima pessoa com a mesma dúvida resolva sozinha.

#### Acceptance Criteria

1. QUANDO o Atendente encerra um Chamado, O Painel_CS DEVE exigir o Desfecho (falso defeito ou defeito real) e a solução usada, composta por um tipo ("instrução do manual" ou "outra") e uma descrição de 1 a 500 caracteres.
2. QUANDO o Atendente encerra um Chamado como falso defeito resolvido com instrução do manual, O Painel_CS DEVE oferecer a ação "Adicionar ao Cache_Respostas" com a pergunta (1 a 300 caracteres) preenchida com o relato do Consumidor registrado na Jornada e a resposta (1 a 1000 caracteres) preenchida com a solução usada, ambas editáveis e sem Dados_Pessoais.
3. QUANDO o Atendente confirma "Adicionar ao Cache_Respostas", O Cache_Respostas DEVE armazenar a entrada vinculada ao modelo da máquina, ao Atendente aprovador e à data e hora da aprovação, e DEVE disponibilizá-la para consulta do Assistente_IA (Requisito 7, critério 1) em até 10 segundos.
4. QUANDO um Chamado é encerrado, O Servico_Metricas DEVE marcar a Jornada como resolvida na camada "humano" com o Desfecho registrado, em até 10 segundos após o encerramento.
5. QUANDO um Chamado é encerrado, O Portal_TRES DEVE exibir ao Consumidor, em até 10 segundos e na página de acompanhamento do Chamado, a avaliação de 1 a 5 estrelas com comentário opcional do Requisito 5 (critério 2), e O Servico_Metricas DEVE registrar a nota enviada associada à Jornada e à camada "humano" (Requisito 5, critério 5).
6. SE o Atendente tenta encerrar um Chamado sem Desfecho, ou com descrição de solução vazia ou acima de 500 caracteres, ENTÃO O Painel_CS DEVE recusar o encerramento, manter o Chamado aberto, exibir um erro junto ao campo inválido e preservar os dados já preenchidos.
7. SE a confirmação de "Adicionar ao Cache_Respostas" falha porque a pergunta ou a resposta está vazia ou acima do limite do critério 2, ou porque o armazenamento no Cache_Respostas falha, ENTÃO O Painel_CS DEVE manter o Chamado encerrado, não armazenar a entrada, exibir um erro indicando o motivo e preservar os textos editados para nova tentativa.
8. SE já existe no Cache_Respostas uma entrada com o mesmo modelo de máquina e a mesma pergunta normalizada (Requisito 7, critério 1), ENTÃO O Cache_Respostas DEVE manter a entrada existente sem alterações e O Painel_CS DEVE exibir um aviso indicando que a entrada já existe.

### Requirement 17: Métricas de deflexão e custo [MVP]

**User Story:** Como Gestor, quero medir quanto cada camada resolve e quanto custa cada dúvida resolvida, para comprovar o impacto da solução.

#### Acceptance Criteria

1. QUANDO uma Jornada é encerrada, O Servico_Metricas DEVE registrar a camada de resolução (guia, ia, humano ou abandonada), o Problema_Catalogado ou "outro", o tempo total em segundos (do início da Jornada até o encerramento, ou até a última interação do Consumidor no caso de "abandonada") e o custo em reais com 2 casas decimais. Uma Jornada é considerada encerrada quando é resolvida na camada guia (Requisito 5, critério 2), na camada ia (Requisito 6, critério 7), na camada humano (Requisito 16, critério 4) ou marcada como abandonada (critério 2). Cada Jornada encerrada DEVE ter exatamente uma camada de resolução.
2. QUANDO uma Jornada sem Chamado aberto fica 30 minutos sem interação do Consumidor e sem resolução, O Servico_Metricas DEVE marcar a Jornada como "abandonada" e DEVE manter essa classificação mesmo se o Consumidor interagir depois.
3. O Painel_Metricas DEVE exibir a taxa de deflexão por camada (guia, ia, humano e abandonada), calculada como Jornadas encerradas na camada dividido pelo total de Jornadas encerradas no período, em percentual com 1 casa decimal.
4. O Painel_Metricas DEVE exibir a precisão da escalada: Chamados com Desfecho "defeito real" dividido pelo total de Chamados encerrados no período, em percentual com 1 casa decimal.
5. O Painel_Metricas DEVE exibir o tempo médio de resolução por camada guia, ia e humano, calculado como a média do tempo total das Jornadas resolvidas na camada no período, no formato minutos e segundos. Jornadas "abandonada" NÃO DEVEM entrar nesse cálculo.
6. O Painel_Metricas DEVE exibir o custo médio por dúvida resolvida por camada guia, ia e humano, em reais com 2 casas decimais, calculado sobre as Jornadas resolvidas na camada no período, com guia = 0, ia = soma do custo de tokens registrado na Jornada (Requisito 7, critérios 2 e 3) e humano = minutos de atendimento (do horário de início do atendimento, Requisito 14, critério 5, até o encerramento do Chamado) × custo por minuto configurável. O custo por minuto configurável DEVE aceitar valores de 0,00 a 999,99 reais.
7. O Painel_Metricas DEVE exibir a taxa de acerto do Cache_Respostas: respostas do Assistente_IA servidas pelo cache dividido pelo total de respostas do Assistente_IA no período, em percentual com 1 casa decimal.
8. O Painel_Metricas DEVE exibir o ranking dos 10 Problemas_Catalogados mais acessados no período, em ordem decrescente de Jornadas que selecionaram o Problema_Catalogado (empates ordenados pelo título em ordem alfabética), e a nota média de avaliação (escala de 1 a 5, com 1 casa decimal) e o número de avaliações por camada.
9. PARA TODO período, a soma das Jornadas por camada de resolução (guia, ia, humano e abandonada) DEVE ser igual ao total de Jornadas encerradas no período (invariante). Jornadas ainda não encerradas NÃO DEVEM ser contadas.
10. QUANDO o Gestor abre o Painel_Metricas ou seleciona um período, O Painel_Metricas DEVE calcular todos os indicadores para o período selecionado, com as opções "hoje", "últimos 7 dias" (padrão), "últimos 30 dias" e intervalo personalizado de no máximo 90 dias, considerando a data de encerramento da Jornada ou do Chamado, e DEVE exibir os indicadores em até 3 segundos.
11. SE o denominador de um indicador é zero no período selecionado (por exemplo, nenhuma Jornada encerrada, nenhum Chamado encerrado ou nenhuma avaliação), ENTÃO O Painel_Metricas DEVE exibir "sem dados" nesse indicador, em vez de 0 ou de um erro.
12. SE o Servico_Metricas falha ao registrar o evento de encerramento de uma Jornada, ENTÃO O Servico_Metricas DEVE repetir o registro até 3 vezes, com intervalo de 10 segundos, sem interromper nem alterar o fluxo exibido ao Consumidor; esgotadas as tentativas, O Servico_Metricas DEVE manter os dados da Jornada e sinalizar a falha de registro ao Gestor no Painel_Metricas.
13. SE o Painel_Metricas não consegue carregar os indicadores, ENTÃO O Painel_Metricas DEVE exibir uma mensagem de erro indicando a falha e a ação "Tentar novamente", sem exibir valores parciais ou desatualizados como se fossem do período selecionado.

### Requirement 18: Proteção de dados pessoais (LGPD) [MVP]

**User Story:** Como Consumidor, quero que meus dados sejam usados só para o atendimento, para confiar no canal.

#### Acceptance Criteria

1. O Portal_TRES DEVE permitir que o Consumidor conclua a Jornada no Guia_Diagnostico e no Assistente_IA sem exibir nenhum campo obrigatório de Dados_Pessoais, de modo que Dados_Pessoais só sejam solicitados na etapa de contato com o Atendente.
2. O Sistema DEVE armazenar Dados_Pessoais com criptografia em repouso, de modo que nenhum Dado_Pessoal fique legível em texto puro no armazenamento do Sistema.
3. QUANDO o Consumidor enviar uma mensagem ao Assistente_IA, O Assistente_IA DEVE substituir cada telefone, CPF, e-mail e CEP encontrado no texto por um marcador do tipo correspondente antes de enviar o texto ao modelo de linguagem, de modo que o texto original não chegue ao modelo.
4. O Painel_Metricas DEVE exibir apenas valores agregados por camada, modelo e período, sem exibir registros individuais de Jornada e sem exibir telefone, CPF, e-mail, CEP ou qualquer outro Dado_Pessoal.
5. O Portal_TRES DEVE exibir, em todas as telas que solicitam Dados_Pessoais, um link visível na própria tela, sem necessidade de rolagem ou ação prévia, que abre o aviso de privacidade.
6. QUANDO um Atendente visualizar Dados_Pessoais de um Chamado, O Sistema DEVE gravar um registro de acesso contendo o identificador do Atendente, o número do Chamado e a data e hora do acesso com precisão de segundos, antes de exibir os Dados_Pessoais ao Atendente.
7. SE o Consumidor acessar o Portal_TRES por conexão sem HTTPS, ENTÃO O Sistema DEVE recusar a conexão ou redirecioná-la para HTTPS sem processar nem transmitir nenhum dado da requisição original.
8. SE a substituição de Dados_Pessoais por marcadores falhar, ENTÃO O Assistente_IA DEVE NÃO enviar a mensagem ao modelo de linguagem, DEVE exibir ao Consumidor uma mensagem de erro informando que a mensagem não pôde ser processada e DEVE preservar o texto digitado na tela para novo envio.
9. SE o registro de acesso a Dados_Pessoais falhar, ENTÃO O Sistema DEVE NÃO exibir os Dados_Pessoais ao Atendente e DEVE exibir uma mensagem de erro informando que o acesso não foi autorizado por falha de registro.

### Requirement 19: Acessibilidade e experiência mobile-first [MVP]

**User Story:** Como Consumidor que acessa pelo celular, quero uma página leve, legível e fácil de tocar, para resolver mesmo com pressa e frustrado.

#### Acceptance Criteria

1. O Portal_TRES DEVE apresentar layout funcional, sem rolagem horizontal e sem sobreposição ou corte de texto e controles, em telas com largura de 360 a 1280 pixels CSS e com zoom do navegador de até 200%.
2. QUANDO a Pagina_Maquina é aberta em conexão 4G (vazão de download de 1,6 Mbps e latência de ida e volta de 150 ms), O Portal_TRES DEVE exibir o conteúdo principal (identificação da máquina e a primeira ação de autoatendimento disponível) em até 3 segundos, medidos do início da navegação até a renderização desse conteúdo, em pelo menos 95% das medições de teste.
3. O Portal_TRES DEVE usar contraste mínimo de 4,5:1 para texto comum, contraste mínimo de 3:1 para texto grande (a partir de 24 pixels CSS, ou 18,66 pixels CSS em negrito) e para bordas de controles interativos, e alvos de toque de no mínimo 44×44 pixels CSS com espaçamento mínimo de 8 pixels CSS entre alvos adjacentes.
4. O Portal_TRES DEVE oferecer navegação completa por teclado, com ordem de foco igual à ordem visual, indicador de foco visível com contraste mínimo de 3:1 e sem armadilha de foco, e rótulos acessíveis para leitores de tela em 100% dos controles interativos.
5. O Portal_TRES DEVE oferecer, para toda animação de instrução, texto equivalente com as mesmas etapas da animação, disponível sem necessidade de reproduzir a animação.
6. O Portal_TRES DEVE exibir todo o conteúdo em português do Brasil, com frases de até 20 palavras, sem termos técnicos de TI e sem siglas, exceto as que forem explicadas em linguagem simples na primeira ocorrência na página.
7. ENQUANTO a preferência do sistema de movimento reduzido estiver ativa, O Portal_TRES DEVE substituir toda animação de instrução por imagem estática acompanhada do texto equivalente, sem nenhum movimento iniciado automaticamente.
8. O Portal_TRES DEVE exibir todo texto de conteúdo com tamanho mínimo de 16 pixels CSS.
9. SE o conteúdo principal da Pagina_Maquina não for renderizado em até 10 segundos ou o carregamento falhar, ENTÃO O Portal_TRES DEVE exibir uma mensagem de erro em português do Brasil indicando que a página não carregou, com um controle de "tentar novamente" que recarrega a página sem exigir que o Consumidor reinsira dados já informados.

### Requirement 20: Infraestrutura e persistência na AWS [MVP]

**User Story:** Como equipe do hackathon, quero o sistema rodando na AWS com dados reais, para demonstrar ao vivo uma solução viável.

#### Acceptance Criteria

1. QUANDO o Sistema grava Catalogo_Maquinas, Jornadas, Chamados, Pacotes_Repasse, Cache_Respostas ou eventos de métricas, O Sistema DEVE persistir o registro em banco de dados gerenciado na AWS, de modo que o registro gravado seja recuperado com conteúdo idêntico após o reinício de qualquer componente da aplicação.
2. QUANDO o Assistente_IA recebe uma pergunta do usuário, O Sistema DEVE executar o Assistente_IA no Amazon Bedrock AgentCore, consultando a Base_Conhecimento indexada exclusivamente a partir dos manuais oficiais TRES carregados conforme o critério 3.
3. QUANDO o script de carga é executado, O Sistema DEVE carregar o Catalogo_Maquinas, as instruções dos 13 Problemas_Catalogados e os manuais de ao menos 1 modelo TRES usado na demo, de forma reprodutível: duas execuções consecutivas do script em um ambiente vazio ou já carregado DEVEM resultar no mesmo conjunto de registros, sem duplicatas.
4. SE o Assistente_IA retorna erro ou não responde em até 10 segundos, ENTÃO O Portal_TRES DEVE manter o Guia_Diagnostico funcional e exibir o botão "Falar com uma pessoa" em até 2 segundos após a detecção da indisponibilidade, sem perder as informações já informadas pelo usuário na Jornada atual.
5. O Sistema DEVE manter credenciais e chaves fora do repositório de código, de modo que nenhum arquivo versionado contenha senhas, tokens ou chaves de acesso, armazenando-os em serviço de segredos ou variáveis de ambiente da AWS.
6. SE a gravação no banco de dados falha ou excede 10 segundos, ENTÃO O Sistema DEVE exibir ao usuário mensagem de erro indicando que a operação não foi concluída, DEVE NÃO confirmar sucesso da operação, DEVE preservar os dados informados pelo usuário na tela e DEVE permitir nova tentativa sem reiniciar a Jornada.
7. SE o script de carga falha em qualquer item (Catalogo_Maquinas, Problemas_Catalogados ou manuais), ENTÃO O Sistema DEVE interromper a carga, indicar na saída do script qual item falhou e o motivo, e DEVE NÃO deixar registros parciais desse item no banco de dados.

## Fora do escopo do MVP

Os itens abaixo ficam para as fases de evolução (fase 4, aperfeiçoamento iterativo):

- **WhatsApp**: descartado como canal.
- **Telefonia integrada**: no MVP, "ligação imediata" e "Agendar ligação" são registros no Chamado. Discagem e URA reais ficam para depois.
- **Integração com sistemas legados da 3corações**: CRM, ERP e sistema real de assistência técnica. No MVP, a Ordem_Servico é um registro interno.
- **Cache semântico**: no MVP, o cache casa a pergunta normalizada exata. Busca por similaridade de embeddings fica para evolução.
- **Detecção de frustração por modelo dedicado**: no MVP, o sentimento vem da classificação do Assistente_IA e do pedido explícito.
- **Seletor_Visual para todos os modelos**: no MVP, ele cobre ao menos o modelo da demo. Os demais modelos usam a lista dos 13 Problemas_Catalogados.
- **Identificação da máquina por foto com IA**: o MVP usa a grade de fotos para escolha manual.
- **Vídeo como anexo**: o MVP aceita só fotos.
- **Notificações ativas**: SMS, e-mail e push sobre o status do Chamado.
- **Login do Consumidor e histórico de múltiplas máquinas**.
- **Promoção automática de novos itens ao Guia_Diagnostico**: no MVP, a retroalimentação vai só para o Cache_Respostas com aprovação do Atendente.
- **Outros idiomas**.
- **SSO corporativo e MFA no Painel_CS**: o MVP usa usuário e senha com perfis.
- **Auditoria formal de acessibilidade (WCAG)**: exige testes manuais com tecnologias assistivas.
- **Política formal de retenção e exclusão de Dados_Pessoais**: deve ser definida com o jurídico da 3corações.
