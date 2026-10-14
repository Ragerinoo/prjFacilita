# Requirements Document

## Introduction

O Painel_CS já tem a tela `MetricasCs` (`/cs/metricas`), que mostra apenas contagens de Chamados por problema, modelo, prioridade e Desfecho. Esta feature adiciona uma tela nova de Insights para o Gestor, em `/cs/insights`, com foco em **atendimento e satisfação**: nota média e distribuição das avaliações, amostra de comentários, tempo até assumir e até encerrar o Chamado, Chamados P1 de risco, falso defeito x defeito real e o ranking dos problemas mais frequentes. O funil da Jornada (QR x busca, abandono, deflexão) aparece só como contexto secundário e opcional.

A tela é alimentada pela nova rota `GET /api/cs/insights?periodo=`, exclusiva do perfil Gestor, com os mesmos códigos 401 e 403 da rota `GET /api/cs/metricas`. A `MetricasCs` e a rota `/api/cs/metricas` continuam como estão.

A feature reaproveita `agregar_metricas` (`packages/dominio/src/dominio/metricas.py`) para os indicadores que ela já calcula (nota média, precisão da escalada, deflexão por camada e contagem de seleções por problema) e segue as regras das tarefas 20.2 e 20.3 da spec `tres-autoatendimento`: períodos Hoje, 7 dias (padrão), 30 dias e personalizado de até 90 dias, "sem dados" quando o denominador é zero, erro único com "Tentar novamente" e apenas valores agregados, sem dados pessoais. Os indicadores ligados à IA (`ia_cache`, `ia_modelo` e custo de IA) ficam ocultos, pois a demo roda sem IA.

Seguindo a spec `persistencia-local-demo`, as consultas de listagem usadas aqui (`listar_todos` de Chamados) só existem no Modo_Local, e o adaptador DynamoDB levanta `ErroIndisponivelForaDoModoLocal`. Esta feature não cria método novo de listagem nos repositórios.

Para a demo ter o que mostrar, o `scripts/dev_local.py` ganha uma Semente_Demo com Jornadas, Chamados e avaliações fictícios distribuídos nos últimos cerca de 30 dias. A semente roda só na primeira subida, respeita o snapshot `.dados-demo/estado.json`, é desligada por `--sem-demo` e nunca existe em código de produção.

Fora do escopo: DynamoDB/AWS, `infra/`, IAM, deploy, agente de IA e `PUT /config`.

**Atualização (Dashboard e navegação).** Hoje a navbar do Painel_CS (`LayoutPainel.tsx`) mostra apenas "Fila de chamados" e, para o Gestor, "Métricas"; a rota índice `/cs` apenas redireciona para `/cs/fila` (`apps/web/src/app/rotas.tsx`), e o login sem destino anterior também cai em `/cs/fila` (`LoginCs.tsx`). Quem digitou `/cs/inshigts` (erro de digitação) viu "Página não encontrada", porque a URL correta é `/cs/insights` e não havia link no menu. Esta atualização acrescenta: (a) o link "Insights" e o link "Dashboard" na navbar; (b) um **Dashboard** como tela principal do Painel_CS em `/cs`, com uma visão geral dos Chamados no topo e duas abas, "Insights" (reaproveita o conteúdo da Tela_Insights) e "Chamados em foco" (Chamados que pedem atenção agora); (c) a rota `GET /api/cs/dashboard`, aberta aos perfis Gestor e Atendente, que alimenta a visão geral e os Chamados em foco sem dados pessoais. O redirecionamento de `/cs` para `/cs/fila` deixa de existir. A Fila (`/cs/fila`, `GET /api/cs/fila`) e a Tela_Insights completa (`/cs/insights`) continuam como estão. O Atendente só vê a aba "Chamados em foco" e nunca chama a API_Insights. Os Requisitos 19 a 26 descrevem essa parte; os Requisitos 1 a 18 continuam valendo, com ajustes pontuais nos itens 15.5, 17.3, 18.5 e 18.6 (e o Requisito 12 complementado pelo Requisito 19).

## Glossary

- **Painel_CS**: front-end de atendimento acessado em `/cs`.
- **Gestor**: usuário do Painel_CS com perfil `gestor`.
- **Atendente**: usuário do Painel_CS com perfil `atendente`.
- **Consumidor**: pessoa que usa o site público (pesquisa, QR, guia e Chamado).
- **Jornada**: sessão do Consumidor (`Jornada` em `repositorios/modelos.py`), com `origem_inicial`, `problema_id`, `risco` e `encerramento`.
- **Chamado**: registro de escalada para atendimento humano (`Chamado` em `repositorios/modelos.py`) com status `aberto`, `em_atendimento` ou `encerrado`.
- **Chamado_Encerrado**: Chamado cujo status é `encerrado`, com `encerramento.em` preenchido.
- **Desfecho**: valor `falso_defeito` ou `defeito_real` gravado em `Chamado.encerramento.desfecho`.
- **Chamado_P1_De_Risco**: Chamado de prioridade P1 cuja Jornada possui `risco` marcado.
- **Avaliacao**: avaliação da Jornada com nota inteira de 1 a 5, camada, data (`em`) e comentário opcional.
- **Comentario**: texto livre do campo `comentario` da Avaliacao, com no máximo 500 caracteres.
- **Tempo_Ate_Assumir**: intervalo entre `Chamado.criado_em` e `Chamado.responsavel.inicio`.
- **Tempo_Ate_Encerrar**: intervalo entre `Chamado.criado_em` e `Chamado.encerramento.em`.
- **Periodo**: intervalo de análise escolhido pelo Gestor: `hoje`, `7d` (padrão), `30d` ou `personalizado` de até 90 dias.
- **Fuso_Referencia**: fuso horário usado para delimitar os dias do Periodo, definido no design e igual para a API e para a Semente_Demo.
- **Sem_Dados**: texto literal `sem dados` (constante `SEM_DADOS` de `dominio.metricas`) exibido quando o denominador de um indicador é zero.
- **API_Insights**: rota `GET /api/cs/insights` da API.
- **Servico_Insights**: função pura em `services/api/servicos/` que monta a resposta da API_Insights a partir de registros já lidos.
- **Tela_Insights**: componente do front-end exibido em `/cs/insights`.
- **MetricasCs**: tela atual `/cs/metricas` e a rota `GET /api/cs/metricas` que a alimenta, que permanecem sem alteração.
- **Agregar_Metricas**: função `agregar_metricas` de `packages/dominio/src/dominio/metricas.py`.
- **Ranking_Problemas**: lista dos problemas mais selecionados no Periodo, com no máximo 10 itens.
- **Solucao_Mais_Registrada**: par (`solucao_tipo`, `solucao`) mais frequente entre os Chamados_Encerrados do problema no Periodo.
- **Funil_Jornada**: bloco secundário e opcional com origem da Jornada (QR x busca), abandono e deflexão por camada.
- **Indicadores_De_IA**: `ia_cache`, `ia_modelo`, acerto do cache, quantidade de respostas da IA, camada `ia` e custo de IA.
- **PII**: dados pessoais, incluindo telefone, CPF, e-mail e CEP.
- **Mascarar_Pii**: função `mascarar_pii` de `packages/dominio/src/dominio/pii.py`.
- **Modo_Local**: modo de execução do Servidor_Local com repositórios em memória, sem acesso à AWS.
- **Servidor_Local**: processo iniciado por `scripts/dev_local.py`.
- **Ponto_De_Entrada_CLI**: execução de `python scripts/dev_local.py` pela linha de comando (bloco `if __name__ == "__main__"`), único lugar que liga a Semente_Demo ao passar `com_semente=True` para `main()`.
- **Snapshot**: arquivo `.dados-demo/estado.json` com o estado persistido da demo.
- **Semente_Demo**: conjunto de Jornadas, Chamados e Avaliacoes fictícios criado pelo `scripts/dev_local.py` para a demonstração.
- **Chamados_De_Exemplo**: os 3 Chamados fictícios criados por `_chamados_de_exemplo` em `scripts/dev_local.py`.
- **Biblioteca_Graficos**: biblioteca de gráficos do front-end (por exemplo, Recharts), instalada com versão exata e compatível com React 19.
- **Alternativa_Textual**: tabela ou texto que traz os mesmos valores de um gráfico.
- **Guia_Demo**: documento `docs/DEMO.md`.
- **LayoutPainel**: componente `apps/web/src/cs/LayoutPainel.tsx`, que renderiza o cabeçalho e o Menu_Painel do Painel_CS.
- **Menu_Painel**: elemento `nav` com `aria-label="Painel"` do LayoutPainel.
- **Dashboard**: tela principal do Painel_CS, exibida em `/cs` (rota índice), composta pela Visao_Geral e pelo Seletor_De_Abas.
- **Visao_Geral**: faixa de cards no topo do Dashboard com os totais de Chamados e, apenas para o Gestor, os Cards_De_Satisfacao.
- **Cards_De_Satisfacao**: cards "Nota média" e "Tempo médio até assumir", calculados no Periodo `7d` a partir da API_Insights, exibidos apenas ao Gestor.
- **Chamado_Ativo**: Chamado cujo status é `aberto` ou `em_atendimento`.
- **Chamado_Sem_Responsavel**: Chamado_Ativo cujo `responsavel` é nulo.
- **Chamado_Parado**: Chamado com status `em_atendimento` cujo `responsavel.inicio` ocorreu há pelo menos 60 minutos (Limite_Parado).
- **Limite_Parado**: 60 minutos.
- **Idade_Em_Minutos**: número inteiro de minutos completos entre `Chamado.criado_em` e o instante da requisição, nunca menor que 0.
- **Motivo_De_Foco**: um dos quatro valores `p1_ou_risco`, `resposta_nao_lida`, `sem_responsavel` e `parado`, nessa ordem de urgência (do mais urgente ao menos urgente). `p1_ou_risco` vale para Chamado_Ativo de prioridade P1 ou cuja Jornada tem `risco` marcado; `resposta_nao_lida` vale para Chamado_Ativo com `resposta_nao_lida` verdadeiro; `sem_responsavel` vale para Chamado_Sem_Responsavel; `parado` vale para Chamado_Parado.
- **Chamado_Em_Foco**: Chamado_Ativo que possui ao menos um Motivo_De_Foco.
- **Limite_Em_Foco**: 10 itens, quantidade máxima de Chamados_Em_Foco devolvidos pela API_Dashboard.
- **API_Dashboard**: rota `GET /api/cs/dashboard` da API, aberta aos perfis `gestor` e `atendente`.
- **Servico_Dashboard**: função pura em `services/api/servicos/` que monta a resposta da API_Dashboard a partir de registros já lidos e do instante atual recebido como parâmetro.
- **Seletor_De_Abas**: conjunto `tablist` do Dashboard com as abas Aba_Insights e Aba_Chamados_Em_Foco.
- **Aba_Insights**: aba "Insights" do Dashboard, visível apenas ao Gestor, cujo painel exibe o Conteudo_Insights.
- **Aba_Chamados_Em_Foco**: aba "Chamados em foco" do Dashboard, cujo painel exibe a Lista_Em_Foco.
- **Parametro_Aba**: parâmetro de query string `aba` da URL do Dashboard, com os valores `insights` e `chamados`.
- **Conteudo_Insights**: conteúdo da Tela_Insights (seletor de Periodo, cards, gráficos, Ranking_Problemas, Comentarios e Funil_Jornada), exibido tanto em `/cs/insights` quanto no painel da Aba_Insights.
- **Lista_Em_Foco**: lista ordenada dos Chamados_Em_Foco exibida no painel da Aba_Chamados_Em_Foco.
- **Tela_Dashboard**: componente do front-end exibido em `/cs`.

## Requirements

### Requirement 1

**User Story:** Como Gestor, quero uma rota de Insights restrita ao meu perfil, para consultar os indicadores de atendimento e satisfação com segurança.

#### Acceptance Criteria

1. WHEN o Gestor autenticado envia `GET /api/cs/insights`, THE API_Insights SHALL responder 200 com os indicadores do Periodo solicitado.
2. IF uma requisição sem sessão válida envia `GET /api/cs/insights`, THEN THE API_Insights SHALL responder 401 sem nenhum indicador.
3. IF um Atendente autenticado envia `GET /api/cs/insights`, THEN THE API_Insights SHALL responder 403 sem nenhum indicador.
4. THE API_Insights SHALL ser restrita ao perfil `gestor` pela declaração de perfis da própria rota (`Rota.perfis` igual a `{"gestor"}` combinado com `exigir_perfil("gestor")`), sem acrescentar entrada nem alterar a `MATRIZ` de autorização existente, de modo que Gestor seja permitido, Atendente receba 403 e a falta de sessão receba 401.
5. THE API_Insights SHALL responder 401 e 403 com o mesmo formato de corpo que a rota `GET /api/cs/metricas` usa para esses códigos.
6. THE API_Insights SHALL devolver um objeto JSON com conjunto fechado de chaves de primeiro nível: `periodo`, `modo_local`, `satisfacao`, `comentarios`, `atendimento`, `desfecho`, `p1_risco`, `ranking_problemas` e `funil`.
7. WHEN a API_Insights é executada no Modo_Local, THE API_Insights SHALL devolver `modo_local` igual a `true`.
8. IF a leitura de qualquer repositório necessário falha, THEN THE API_Insights SHALL responder com resposta 5xx com envelope de erro e sem nenhuma chave de indicador, sem incluir indicadores parciais (hoje, 502 `dependencia_indisponivel` para `ErroRepositorio` e 500 `erro_interno` para exceção inesperada).
9. WHEN o Gestor autenticado envia `GET /api/cs/insights`, THE API_Insights SHALL responder em até 3 segundos com a Semente_Demo carregada.

### Requirement 2

**User Story:** Como Gestor, quero escolher o período de análise, para comparar a satisfação e o atendimento em janelas diferentes.

#### Acceptance Criteria

1. WHERE o parâmetro `periodo` não é informado, THE API_Insights SHALL usar o Periodo `7d`.
2. WHEN `periodo` é `hoje`, THE API_Insights SHALL calcular os indicadores do dia corrente no Fuso_Referencia.
3. WHEN `periodo` é `7d` ou `30d`, THE API_Insights SHALL calcular os indicadores dos 7 ou dos 30 dias terminados no momento da requisição, respectivamente.
4. WHEN `periodo` é `personalizado` e os parâmetros `inicio` e `fim` são datas no formato AAAA-MM-DD, THE API_Insights SHALL calcular os indicadores do intervalo que vai do início do dia `inicio` ao fim do dia `fim`, ambos no Fuso_Referencia.
5. IF o valor de `periodo` não é `hoje`, `7d`, `30d` nem `personalizado`, THEN THE API_Insights SHALL responder 400 sem nenhum indicador.
6. IF `periodo` é `personalizado` e `inicio` ou `fim` está ausente, não é uma data válida, ou `fim` é anterior a `inicio`, THEN THE API_Insights SHALL responder 400 sem nenhum indicador.
7. IF `periodo` é `personalizado` e o intervalo excede 90 dias, THEN THE API_Insights SHALL responder 400 sem nenhum indicador.
8. THE API_Insights SHALL incluir no campo `periodo` da resposta o identificador escolhido e os instantes de início e fim efetivamente usados.
9. WHEN o denominador de um indicador é zero no Periodo, THE API_Insights SHALL devolver o valor Sem_Dados nesse indicador, e não 0.
10. THE API_Insights SHALL atribuir cada Avaliacao ao Periodo pela data da Avaliacao e cada Chamado_Encerrado pela data de `encerramento.em`.

### Requirement 3

**User Story:** Como Gestor, quero ver a nota média e a distribuição das avaliações, para entender o quanto os Consumidores estão satisfeitos.

#### Acceptance Criteria

1. THE API_Insights SHALL devolver em `satisfacao` a nota média geral das Avaliacoes do Periodo, com 1 casa decimal, arredondada para cima no meio.
2. THE API_Insights SHALL devolver em `satisfacao` a quantidade total de Avaliacoes do Periodo.
3. THE API_Insights SHALL devolver em `satisfacao` a distribuição das Avaliacoes com uma linha para cada nota de 1 a 5, cada linha com a quantidade e o percentual com 1 casa decimal, incluindo as notas com quantidade zero.
4. WHEN o Periodo não tem nenhuma Avaliacao, THE API_Insights SHALL devolver a nota média e os percentuais da distribuição como Sem_Dados e as quantidades como 0.
5. FOR ALL resposta da API_Insights, THE soma das quantidades da distribuição SHALL ser igual à quantidade total de Avaliacoes do Periodo.
6. THE Servico_Insights SHALL obter a nota média por camada, para uso como apoio, chamando a Agregar_Metricas, sem reimplementar a fórmula da média.

### Requirement 4

**User Story:** Como Gestor, quero ler uma amostra dos comentários dos Consumidores sem ver dados pessoais, para entender o motivo das notas.

#### Acceptance Criteria

1. THE API_Insights SHALL devolver em `comentarios` uma amostra de no máximo 10 Comentarios não vazios das Avaliacoes do Periodo, dos mais recentes para os mais antigos.
2. THE Servico_Insights SHALL aplicar a Mascarar_Pii a cada Comentario antes de incluí-lo na resposta.
3. IF a Mascarar_Pii falha para um Comentario, THEN THE Servico_Insights SHALL omitir esse Comentario da amostra.
4. THE API_Insights SHALL devolver para cada item da amostra apenas a nota, a data da Avaliacao e o texto mascarado do Comentario.
5. THE API_Insights SHALL omitir da amostra de comentários o `jornada_id`, o número do Chamado e qualquer outro identificador de Jornada ou de Chamado.
6. WHEN o Periodo não tem nenhum Comentario não vazio, THE API_Insights SHALL devolver a amostra como lista vazia.
7. THE Tela_Insights SHALL exibir o texto de cada Comentario como texto simples, escapado pelo React, sem usar `dangerouslySetInnerHTML` nem interpretar HTML ou Markdown.

### Requirement 5

**User Story:** Como Gestor, quero medir o tempo até assumir e até encerrar os Chamados, para avaliar a velocidade do atendimento.

#### Acceptance Criteria

1. THE API_Insights SHALL devolver em `atendimento` o Tempo_Ate_Assumir médio e mediano dos Chamados_Encerrados do Periodo que possuem `responsavel`.
2. THE API_Insights SHALL devolver em `atendimento` o Tempo_Ate_Encerrar médio e mediano dos Chamados_Encerrados do Periodo.
3. THE API_Insights SHALL formatar cada tempo como texto `min:seg` usando `formatar_min_seg` de `dominio.metricas`, e o campo `quantidade` de cada tempo SHALL informar quantos Chamados entraram no cálculo.
4. WHEN a quantidade de Chamados no cálculo da mediana é par, THE Servico_Insights SHALL calcular a mediana como a média dos dois valores centrais, arredondada ao segundo.
5. WHEN nenhum Chamado_Encerrado do Periodo entra no cálculo de um tempo, THE API_Insights SHALL devolver a média e a mediana desse tempo como Sem_Dados.
6. IF o Tempo_Ate_Assumir ou o Tempo_Ate_Encerrar de um Chamado seria negativo, THEN THE Servico_Insights SHALL tratá-lo como 0 segundo.

### Requirement 6

**User Story:** Como Gestor, quero ver os Chamados P1 de risco e a proporção de falso defeito, para priorizar segurança e entender a qualidade das escaladas.

#### Acceptance Criteria

1. THE API_Insights SHALL devolver em `p1_risco` a quantidade de Chamados_P1_De_Risco criados no Periodo e, entre eles, a quantidade ainda não encerrada.
2. THE API_Insights SHALL devolver em `desfecho` a quantidade e o percentual com 1 casa decimal de `falso_defeito` e de `defeito_real` entre os Chamados_Encerrados do Periodo.
3. IF um Chamado_Encerrado do Periodo não possui Desfecho reconhecido, THEN THE Servico_Insights SHALL contá-lo sob o rótulo `nao_informado` em `desfecho`.
4. WHEN o Periodo não tem nenhum Chamado_Encerrado, THE API_Insights SHALL devolver os percentuais de `desfecho` como Sem_Dados e as quantidades como 0.
5. FOR ALL resposta da API_Insights, THE soma das quantidades de `desfecho` SHALL ser igual ao total de Chamados_Encerrados do Periodo.
6. THE Servico_Insights SHALL obter a precisão da escalada (percentual de `defeito_real`) chamando a Agregar_Metricas, sem reimplementar a fórmula.

### Requirement 7

**User Story:** Como Gestor, quero um ranking dos problemas mais frequentes com o que virou Chamado e como foi resolvido, para identificar onde agir primeiro.

#### Acceptance Criteria

1. THE API_Insights SHALL devolver em `ranking_problemas` no máximo 10 itens, ordenados pela quantidade de seleções em ordem decrescente e, em caso de empate, pelo título em ordem alfabética sem distinção de acento e de caixa.
2. THE Servico_Insights SHALL obter a quantidade de seleções de cada problema dos contadores diários `problema_sel#<id>` do Periodo, chamando a Agregar_Metricas.
3. THE API_Insights SHALL devolver para cada item do ranking: `problema_id`, `titulo`, `selecoes`, `chamados`, `falso_defeito_pct`, `solucao_mais_registrada`.
4. THE Servico_Insights SHALL calcular `chamados` como a quantidade de Chamados criados no Periodo cuja Jornada tem o `problema_id` do item.
5. THE Servico_Insights SHALL calcular `falso_defeito_pct` como o percentual com 1 casa decimal de Chamados_Encerrados do Periodo com Desfecho `falso_defeito` entre os Chamados_Encerrados do Periodo do problema.
6. THE Servico_Insights SHALL calcular `solucao_mais_registrada` como a Solucao_Mais_Registrada do problema, com `solucao_tipo`, o texto de `solucao` mascarado pela Mascarar_Pii e limitado a 120 caracteres, e a quantidade de Chamados que a registraram, desempatando pelo texto em ordem alfabética.
7. WHEN o problema do item não tem Chamado_Encerrado no Periodo, THE API_Insights SHALL devolver `falso_defeito_pct` e `solucao_mais_registrada` como Sem_Dados.
8. THE API_Insights SHALL omitir do ranking os passos das instruções do manual.
9. WHEN o catálogo não traz o título de um problema, THE API_Insights SHALL usar o rótulo `Problema <id>` como título do item.
10. IF o catálogo está indisponível, THEN THE API_Insights SHALL manter o ranking com o rótulo `Problema <id>` e registrar um aviso no log, sem responder erro.
11. WHEN o Periodo não tem nenhuma seleção de problema, THE API_Insights SHALL devolver `ranking_problemas` como lista vazia.

### Requirement 8

**User Story:** Como Gestor, quero um contexto secundário sobre o funil da Jornada, para relacionar a satisfação com a origem e o abandono, sem que esse bloco seja essencial.

#### Acceptance Criteria

1. THE API_Insights SHALL devolver em `funil` a quantidade de Jornadas encerradas no Periodo por origem inicial (`qr` e `busca`), o percentual de abandono e a deflexão por camada `guia`, `humano` e `abandonada`.
2. THE Servico_Insights SHALL obter as Jornadas encerradas do Periodo pelo método `listar_encerradas` já existente em `JornadasRepo`, sem criar o método `listar_todas`.
3. THE Servico_Insights SHALL obter a deflexão por camada e o abandono chamando a Agregar_Metricas.
4. IF a leitura das Jornadas encerradas falha, THEN THE API_Insights SHALL devolver `funil` como `null`, registrar um aviso no log e manter os demais indicadores.
5. WHEN o Periodo não tem Jornada encerrada, THE API_Insights SHALL devolver os percentuais do `funil` como Sem_Dados.
6. THE Tela_Insights SHALL exibir o Funil_Jornada em seção secundária, depois dos blocos de satisfação, atendimento e ranking.
7. WHEN `funil` é `null`, THE Tela_Insights SHALL omitir a seção do Funil_Jornada, sem exibir erro.

### Requirement 9

**User Story:** Como Gestor, quero que a tela não mostre indicadores de IA, para que a demo sem IA não exiba números vazios ou enganosos.

#### Acceptance Criteria

1. THE API_Insights SHALL omitir da resposta os Indicadores_De_IA.
2. THE Tela_Insights SHALL omitir os Indicadores_De_IA.
3. THE Servico_Insights SHALL chamar a Agregar_Metricas com o parâmetro de custo por minuto igual a `0.00`, pois a API_Insights não devolve nenhum indicador de custo.
4. THE Servico_Insights SHALL ignorar a camada `ia` ao montar a deflexão do `funil`.

### Requirement 10

**User Story:** Como responsável pela privacidade, quero que a tela de Insights mostre apenas valores agregados, para que nenhum dado pessoal vaze para o Painel_CS.

#### Acceptance Criteria

1. THE API_Insights SHALL omitir da resposta telefone, CEP, e-mail, CPF, texto de mensagens do Chamado, resumo do Pacote, `jornada_id` e número do Chamado.
2. THE Servico_Insights SHALL receber apenas os campos dos Chamados, Jornadas e Avaliacoes necessários ao cálculo, sem acessar os repositórios de Dados Pessoais nem de mensagens.
3. THE Servico_Insights SHALL ser uma função pura, sem I/O e sem leitura do relógio, que recebe o Periodo e os registros já lidos.
4. THE Tela_Insights SHALL exibir somente os valores devolvidos pela API_Insights.

### Requirement 11

**User Story:** Como mantenedor do código, quero que as leituras de dados sigam o padrão do Modo_Local, para não ampliar o escopo para a AWS.

#### Acceptance Criteria

1. THE API_Insights SHALL obter os Chamados pelo método `listar_todos` de `ChamadosRepo`, já existente.
2. THE API_Insights SHALL obter as Avaliacoes pelo método `listar_periodo` de `AvaliacoesRepo` e os contadores diários pelo método `listar` de `AgregadosDiaRepo`, ambos já existentes.
3. IF `listar_todos` levanta `ErroIndisponivelForaDoModoLocal`, THEN THE API_Insights SHALL responder com resposta 5xx com envelope de erro e sem nenhuma chave de indicador (hoje, 502 `dependencia_indisponivel`), com o mesmo comportamento da rota `GET /api/cs/metricas`.
4. THE feature SHALL manter sem alteração a assinatura dos Protocols de `repositorios/interfaces.py`, o adaptador DynamoDB, os arquivos de `infra/`, os índices e as políticas de IAM.
5. THE feature SHALL manter a Agregar_Metricas e o contrato do pacote `dominio` sem mudança de comportamento, de modo que os testes existentes de `packages/dominio/tests/` continuem passando sem alteração.

### Requirement 12

**User Story:** Como Gestor, quero acessar a tela de Insights pelo menu do Painel_CS, para chegar aos indicadores sem digitar a URL.

#### Acceptance Criteria

1. WHILE o perfil da sessão é `gestor`, THE LayoutPainel SHALL exibir no menu um link "Insights" para `/cs/insights`.
2. WHILE o perfil da sessão é `atendente`, THE LayoutPainel SHALL omitir o link "Insights" do menu.
3. WHEN o Atendente abre `/cs/insights`, THE Painel_CS SHALL exibir a tela de acesso negado sem solicitar a API_Insights.
4. WHEN uma pessoa sem sessão abre `/cs/insights`, THE Painel_CS SHALL redirecionar para o login, como nas demais rotas do Painel_CS.
5. THE Painel_CS SHALL manter o link "Métricas" e a rota `/cs/metricas` com o comportamento atual.

### Requirement 13

**User Story:** Como Gestor, quero uma tela clara com cards e gráficos, para ler a satisfação e o atendimento de relance.

#### Acceptance Criteria

1. WHEN o Gestor abre `/cs/insights`, THE Tela_Insights SHALL solicitar `GET /api/cs/insights` com o Periodo `7d` selecionado.
2. WHEN o Gestor seleciona um Periodo, THE Tela_Insights SHALL solicitar a API_Insights com o Periodo escolhido e atualizar todos os indicadores com a nova resposta.
3. WHERE o Periodo `personalizado` é selecionado, THE Tela_Insights SHALL oferecer os campos de data inicial e final e impedir o envio de intervalo maior que 90 dias ou com data final anterior à inicial, exibindo uma mensagem que explica o motivo.
4. WHILE a Tela_Insights aguarda a resposta da API_Insights, THE Tela_Insights SHALL exibir um indicador de carregamento com `role="status"`.
5. IF a API_Insights responde com erro ou a requisição falha, THEN THE Tela_Insights SHALL exibir uma mensagem de erro e o botão "Tentar novamente", sem exibir valores parciais ou desatualizados como se fossem do Periodo selecionado.
6. WHEN o Gestor aciona "Tentar novamente", THE Tela_Insights SHALL repetir a solicitação com o Periodo selecionado.
7. THE Tela_Insights SHALL exibir em cards a nota média, a quantidade de Avaliacoes, o Tempo_Ate_Assumir médio e mediano, o Tempo_Ate_Encerrar médio e mediano, os Chamados_P1_De_Risco e o percentual de falso defeito.
8. THE Tela_Insights SHALL exibir em gráfico a distribuição das notas de 1 a 5 e a proporção de falso defeito x defeito real.
9. WHEN um valor da resposta é Sem_Dados, THE Tela_Insights SHALL exibir o texto "sem dados" no card ou na tabela correspondente.
10. THE Tela_Insights SHALL exibir o Ranking_Problemas em tabela com as colunas título, seleções, Chamados, percentual de falso defeito e Solucao_Mais_Registrada.
11. THE Tela_Insights SHALL exibir a amostra de Comentarios em lista, cada item com a nota e a data.
12. WHERE `modo_local` é `true`, THE Tela_Insights SHALL exibir o aviso visível "Dados de demonstração".
13. WHEN a resposta traz uma seção sem dados (distribuição zerada, ranking vazio ou amostra vazia), THE Tela_Insights SHALL exibir uma mensagem de que não há dados para essa seção no Periodo.

### Requirement 14

**User Story:** Como pessoa que usa leitor de tela ou não distingue cores, quero acessar os mesmos dados dos gráficos em texto, para não depender da cor nem da imagem.

#### Acceptance Criteria

1. THE Tela_Insights SHALL oferecer, para cada gráfico, a Alternativa_Textual com os mesmos rótulos e valores numéricos, visível ou acessível a leitores de tela.
2. THE Tela_Insights SHALL transmitir cada informação dos gráficos também por rótulo de texto ou valor numérico, nunca apenas por cor.
3. THE Tela_Insights SHALL fornecer a cada gráfico um nome acessível e uma descrição curta do que ele mostra.
4. THE Tela_Insights SHALL exibir cada título de seção como cabeçalho e cada tabela com legenda ou rótulo acessível, com células de cabeçalho com `scope`.
5. THE Tela_Insights SHALL permitir o uso do seletor de Periodo, dos campos de data e do botão "Tentar novamente" por teclado.
6. WHEN a Tela_Insights é renderizada nos estados carregando, erro e pronto, THE teste da Tela_Insights SHALL executar a verificação do `jest-axe` e não encontrar violações.

### Requirement 15

**User Story:** Como mantenedor do front-end, quero uma biblioteca de gráficos com versão fixa, para que o build seja reproduzível e compatível com o React do projeto.

#### Acceptance Criteria

1. THE Tela_Insights SHALL desenhar os gráficos com a Biblioteca_Graficos.
2. THE arquivo `apps/web/package.json` SHALL declarar a Biblioteca_Graficos com versão exata, sem prefixo `^` nem `~`, como as demais dependências do projeto.
3. THE Biblioteca_Graficos escolhida SHALL declarar compatibilidade com React 19 em suas dependências pares.
4. WHEN o comando `npm run build` do `apps/web` é executado, THE build SHALL concluir sem erro de tipos nem de empacotamento.
5. THE Tela_Insights SHALL carregar a Biblioteca_Graficos de forma tardia, junto com a rota `/cs/insights` e com o painel da Aba_Insights do Dashboard, sem incluí-la no pacote das rotas públicas do Consumidor, no pacote da rota índice `/cs` nem no pacote da Aba_Chamados_Em_Foco.

### Requirement 16

**User Story:** Como apresentador da demo, quero dados fictícios distribuídos no tempo, para que a tela de Insights abra com gráficos úteis já na primeira subida.

#### Acceptance Criteria

1. WHEN o Servidor_Local é iniciado pelo Ponto_De_Entrada_CLI sem Snapshot e sem a opção `--sem-demo`, THE Servidor_Local SHALL criar a Semente_Demo além dos Chamados_De_Exemplo e gravar o Snapshot inicial.
2. WHEN o Servidor_Local é iniciado pelo Ponto_De_Entrada_CLI com a opção `--resetar` e sem a opção `--sem-demo`, THE Servidor_Local SHALL criar a Semente_Demo.
3. WHEN o Servidor_Local inicia com Snapshot existente, THE Servidor_Local SHALL manter apenas os registros do Snapshot, sem criar nem recriar a Semente_Demo.
4. WHERE a opção `--sem-demo` está ativa, THE Servidor_Local SHALL iniciar sem a Semente_Demo e sem os Chamados_De_Exemplo.
5. THE Semente_Demo SHALL conter ao menos 30 Jornadas encerradas, 15 Chamados (abertos e encerrados) e 25 Avaliacoes, com datas distribuídas nos últimos 30 dias, incluindo ao menos 1 registro no dia corrente.
6. THE Semente_Demo SHALL conter Avaliacoes de cada nota de 1 a 5, ao menos 5 delas com Comentario fictício.
7. THE Semente_Demo SHALL conter Chamados com as prioridades P1, P2 e P3, ao menos 2 Chamados_P1_De_Risco, Chamados_Encerrados com os dois Desfechos, e Chamados abertos e em atendimento.
8. THE Semente_Demo SHALL conter Chamados_Encerrados com Tempo_Ate_Assumir e Tempo_Ate_Encerrar variados, entre 1 minuto e 48 horas.
9. THE Semente_Demo SHALL conter Jornadas de ao menos 3 problemas distintos do catálogo, com contadores diários `problema_sel#<id>` coerentes com as Jornadas, e Jornadas de origem `qr` e `busca` e da camada `abandonada`.
10. THE Semente_Demo SHALL gerar os mesmos registros relativos ao dia corrente a cada execução, usando valores aleatórios com semente fixa e instantes calculados a partir da data e hora da subida.
11. THE Semente_Demo SHALL usar somente texto fictício, sem telefone, CEP, e-mail ou CPF reais ou realistas.
12. THE Servidor_Local SHALL exibir no console, ao criar a Semente_Demo, uma mensagem que a identifica como dados de demonstração e informa as quantidades criadas.
13. THE Semente_Demo SHALL residir em `scripts/`, e nenhum arquivo de `services/`, `packages/`, `apps/` ou `infra/` SHALL conter código que crie dados de demonstração.
14. THE Servidor_Local SHALL ativar a Semente_Demo somente pelo Ponto_De_Entrada_CLI, por meio do parâmetro `com_semente` de `main()` e de `iniciar_estado()`, cujo padrão é `False`, de modo que chamadas existentes de `popular()`, `iniciar_estado()` e `main()` sem esse parâmetro mantenham os mesmos efeitos, incluindo exatamente 3 Chamados_De_Exemplo quando `com_demo` é verdadeiro.
15. THE Semente_Demo SHALL manter os Chamados_De_Exemplo funcionando na fila do Painel_CS, e os registros da semente SHALL usar identificadores distintos dos usados pelos Chamados_De_Exemplo.
16. WHEN a Semente_Demo cria registros, THE Servidor_Local SHALL criá-los pelos métodos dos repositórios em memória, de modo que os invariantes dos repositórios (uma avaliação por Jornada, um Chamado por Jornada e um encerramento por Chamado) continuem válidos.
17. WHEN o Servidor_Local grava o Snapshot depois da Semente_Demo, THE Serializador SHALL serializar os registros da semente sem alteração do formato do Snapshot.

### Requirement 17

**User Story:** Como Gestor, quero que a tela de Insights conviva com a de Métricas atual, para não perder o que já funciona.

#### Acceptance Criteria

1. THE feature SHALL manter sem alteração o contrato de resposta da rota `GET /api/cs/metricas` e o comportamento da MetricasCs.
2. THE feature SHALL manter passando, sem alteração, os testes existentes de `test_rotas_cs_metricas.py`, `test_metricas_chamados.py`, `test_autorizacao_cs.py`, `scripts/tests/test_dev_local.py`, `scripts/tests/test_persistencia_reinicio.py`, `PainelCs.test.tsx` e `rotas.test.tsx`, com a única exceção prevista nos Requisitos 17.3 e 26.11: `PainelCs.test.tsx` e `rotas.test.tsx` podem ganhar expectativas novas, sem que nenhuma expectativa existente seja removida ou enfraquecida.
3. IF um teste existente precisar de ajuste por causa dos novos links do menu ou da nova tela inicial, THEN THE ajuste SHALL limitar-se a acrescentar as expectativas dos links "Dashboard" e "Insights" para o Gestor, do link "Dashboard" e da ausência do link "Insights" para o Atendente, e da tela inicial `/cs` e do destino padrão do login, conforme o Requisito 26.

### Requirement 18

**User Story:** Como mantenedor, quero testes focados e documentação atualizada, para validar a feature sem rodar a suíte completa e para a demo ter roteiro.

#### Acceptance Criteria

1. THE suíte de testes SHALL incluir testes unitários do Servico_Insights para distribuição e nota média, amostra de comentários mascarada, tempo médio e mediana (quantidade par e ímpar), Chamados_P1_De_Risco, Desfecho, ranking com Solucao_Mais_Registrada e `falso_defeito_pct`, Sem_Dados e ausência de Indicadores_De_IA e de PII.
2. THE suíte de testes SHALL incluir testes de rota da API_Insights para Gestor (200), Atendente (403), ausência de sessão (401), `periodo` inválido (400), intervalo personalizado acima de 90 dias (400), repositório sem dados e falha de repositório (resposta 5xx com envelope de erro e sem nenhuma chave de indicador).
3. THE suíte de testes SHALL incluir teste da Semente_Demo em `scripts/tests/` que verifica as quantidades mínimas, a cobertura de notas, prioridades e Desfechos, o respeito ao Snapshot, o efeito de `--sem-demo` e a ausência de PII.
4. THE suíte de testes SHALL incluir testes da Tela_Insights para carregamento, sucesso, erro com "Tentar novamente", seções sem dados, troca de Periodo, escape de HTML em Comentario, aviso de demonstração e verificação do `jest-axe`.
5. THE suíte de testes SHALL incluir teste do menu do LayoutPainel para os links "Dashboard" e "Insights" do Gestor e a ausência do link "Insights" para o Atendente (ver também o Requisito 26).
6. WHEN a verificação é executada, THE equipe SHALL rodar somente os testes relacionados: os testes novos desta feature (inclusive os do Requisito 26), `test_rotas_cs_metricas`, `test_autorizacao_cs`, `packages/dominio/tests/test_metricas.py`, `scripts/tests/test_dev_local.py`, `scripts/tests/test_persistencia_reinicio.py`, `PainelCs.test.tsx` e `rotas.test.tsx`.
7. THE Guia_Demo SHALL descrever a tela `/cs/insights`, o que cada bloco mostra, a escolha de Periodo e o aviso de dados de demonstração.
8. THE Guia_Demo SHALL informar que a Semente_Demo é criada só na primeira subida (ou com `--resetar`), que `--sem-demo` a desliga e que os dados são fictícios.
9. THE Guia_Demo SHALL informar que os Indicadores_De_IA não aparecem na tela porque a demo roda sem IA.

### Requirement 19

**User Story:** Como usuário do Painel_CS, quero um menu com Dashboard, Fila de chamados e, se eu for Gestor, Métricas e Insights, para chegar a cada tela sem digitar a URL.

#### Acceptance Criteria

1. THE LayoutPainel SHALL exibir no Menu_Painel, para qualquer perfil, o link "Dashboard" para `/cs` e o link "Fila de chamados" para `/cs/fila`, nessa ordem.
2. WHILE o perfil da sessão é `gestor`, THE LayoutPainel SHALL exibir no Menu_Painel, depois dos links "Dashboard" e "Fila de chamados", o link "Métricas" para `/cs/metricas` e o link "Insights" para `/cs/insights`, nessa ordem.
3. WHILE o perfil da sessão é `atendente`, THE LayoutPainel SHALL omitir do Menu_Painel os links "Métricas" e "Insights".
4. WHILE a rota atual coincide com o destino de um link do Menu_Painel, THE LayoutPainel SHALL marcar esse link com `aria-current="page"`.
5. WHILE a rota atual é uma subrota de `/cs`, como `/cs/fila` ou `/cs/insights`, THE LayoutPainel SHALL manter o link "Dashboard" sem `aria-current`, de modo que somente a rota exata `/cs` marque o link "Dashboard".
6. THE LayoutPainel SHALL indicar o link da página atual também por estilo visual que não dependa apenas de cor (por exemplo, sublinhado ou peso da fonte).
7. WHEN o Gestor ativa o link "Insights", THE Painel_CS SHALL exibir a Tela_Insights em `/cs/insights` com o Periodo `7d` selecionado.
8. WHEN uma pessoa autenticada abre uma URL desconhecida sob `/cs`, como `/cs/inshigts`, THE Painel_CS SHALL exibir a página "Página não encontrada" dentro do LayoutPainel, mantendo o Menu_Painel disponível, sem redirecionar nem criar rota alternativa para o erro de digitação.
9. THE Painel_CS SHALL manter a rota `/cs/insights` como endereço único da Tela_Insights completa.

### Requirement 20

**User Story:** Como Gestor ou Atendente, quero abrir o Painel_CS e cair no Dashboard, para ver a situação geral dos Chamados antes de ir à fila.

#### Acceptance Criteria

1. WHEN uma pessoa com sessão válida abre `/cs`, THE Painel_CS SHALL exibir a Tela_Dashboard em `/cs`, sem redirecionar para `/cs/fila`.
2. WHEN uma pessoa sem sessão válida abre `/cs`, THE Painel_CS SHALL redirecionar para `/cs/login`, como nas demais rotas do Painel_CS, sem exibir nenhum dado do Dashboard.
3. WHEN o login é concluído sem destino anterior informado, THE Painel_CS SHALL levar a pessoa para `/cs`.
4. WHEN o login é concluído com destino anterior válido sob `/cs/`, THE Painel_CS SHALL levar a pessoa para esse destino, como hoje.
5. THE Painel_CS SHALL manter a Fila de chamados acessível em `/cs/fila`, sem alteração de comportamento.
6. THE Painel_CS SHALL manter o carregamento da Tela_Dashboard por importação dinâmica da rota, como as demais telas do Painel_CS.

### Requirement 21

**User Story:** Como mantenedor, quero uma rota própria de Dashboard aberta a Gestor e Atendente, para que o Atendente veja os Chamados em foco sem acessar a rota exclusiva do Gestor.

#### Acceptance Criteria

1. WHEN um Gestor ou um Atendente autenticado envia `GET /api/cs/dashboard`, THE API_Dashboard SHALL responder 200 com a visão geral dos Chamados e os Chamados_Em_Foco.
2. IF uma requisição sem sessão válida envia `GET /api/cs/dashboard`, THEN THE API_Dashboard SHALL responder 401 sem nenhum dado de Chamado, com o mesmo formato de corpo que a rota `GET /api/cs/fila` usa para esse código.
3. THE API_Dashboard SHALL declarar os perfis permitidos `gestor` e `atendente` na própria rota (`Rota.perfis` igual a `{"gestor", "atendente"}`), sem acrescentar entrada nem alterar a `MATRIZ` de autorização existente, pelo mesmo motivo registrado para a API_Insights (o teste `test_matriz_cobre_exatamente_as_rotas_do_design` não pode mudar).
4. THE API_Dashboard SHALL ser uma rota separada da API_Insights, e a API_Insights SHALL manter o conjunto fechado de chaves de primeiro nível do Requisito 1.6 e o perfil exclusivo `gestor`, de modo que o Atendente continue recebendo 403 em `GET /api/cs/insights`.
5. THE API_Dashboard SHALL devolver um objeto JSON com conjunto fechado de chaves de primeiro nível: `modo_local`, `gerado_em`, `visao_geral` e `em_foco`.
6. THE API_Dashboard SHALL devolver `gerado_em` como o instante da requisição em ISO 8601, lido uma única vez pela rota e entregue ao Servico_Dashboard.
7. WHEN a API_Dashboard é executada no Modo_Local, THE API_Dashboard SHALL devolver `modo_local` igual a `true`, pelo mesmo critério da API_Insights.
8. THE API_Dashboard SHALL obter os Chamados pelo método `listar_todos` de `ChamadosRepo` e a Jornada de cada Chamado pelo método `obter` de `JornadasRepo`, ambos já existentes, lendo cada Jornada uma única vez por requisição.
9. IF a leitura de qualquer repositório necessário falha, inclusive com `ErroIndisponivelForaDoModoLocal`, THEN THE API_Dashboard SHALL responder com resposta 5xx com envelope de erro e sem nenhuma chave de dado, sem incluir dados parciais, com o mesmo comportamento da rota `GET /api/cs/metricas`.
10. IF o catálogo está indisponível, THEN THE API_Dashboard SHALL usar o rótulo `Problema <id>` para os problemas e registrar um aviso no log, sem responder erro.
11. THE API_Dashboard SHALL manter sem alteração a assinatura dos Protocols de `repositorios/interfaces.py`, o adaptador DynamoDB, os arquivos de `infra/`, os índices e as políticas de IAM, sem criar método novo de listagem nos repositórios.
12. WHEN a API_Dashboard é executada com a Semente_Demo carregada, THE API_Dashboard SHALL responder em até 3 segundos.

### Requirement 22

**User Story:** Como Gestor ou Atendente, quero totais de Chamados e uma lista curta dos que pedem atenção agora, ordenada por urgência, para saber por onde começar.

#### Acceptance Criteria

1. THE API_Dashboard SHALL devolver em `visao_geral` as seis quantidades inteiras `abertos`, `em_atendimento`, `encerrados`, `p1_risco_abertos`, `sem_responsavel` e `respostas_nao_lidas`.
2. THE Servico_Dashboard SHALL calcular `abertos` como a quantidade de Chamados com status `aberto`, `em_atendimento` como a quantidade de Chamados com status `em_atendimento` e `encerrados` como a quantidade de Chamados com status `encerrado`, sem restrição de data.
3. THE Servico_Dashboard SHALL calcular `p1_risco_abertos` como a quantidade de Chamados_Ativos de prioridade P1 cuja Jornada tem `risco` marcado.
4. THE Servico_Dashboard SHALL calcular `sem_responsavel` como a quantidade de Chamados_Sem_Responsavel e `respostas_nao_lidas` como a quantidade de Chamados_Ativos com `resposta_nao_lida` verdadeiro.
5. FOR ALL resposta da API_Dashboard, THE soma de `abertos`, `em_atendimento` e `encerrados` SHALL ser igual à quantidade total de Chamados lidos.
6. THE API_Dashboard SHALL devolver em `em_foco` as chaves `total`, `limite` e `itens`, em que `total` é a quantidade de todos os Chamados_Em_Foco, `limite` é o Limite_Em_Foco e `itens` contém no máximo o Limite_Em_Foco itens.
7. THE API_Dashboard SHALL devolver cada item de `em_foco.itens` com o conjunto fechado de campos `numero`, `prioridade`, `status`, `modelo`, `problema`, `idade_min`, `risco`, `sem_responsavel`, `resposta_nao_lida`, `parado` e `motivos`.
8. THE Servico_Dashboard SHALL preencher `motivos` com os Motivos_De_Foco do Chamado na ordem de urgência definida no Glossário, e SHALL preencher `risco`, `sem_responsavel`, `resposta_nao_lida` e `parado` com valores booleanos conforme as definições do Glossário.
9. THE Servico_Dashboard SHALL preencher `idade_min` com a Idade_Em_Minutos do Chamado.
10. THE Servico_Dashboard SHALL preencher `modelo` com o identificador do modelo da Jornada e `problema` com o título do problema no catálogo, ou o rótulo `Problema <id>` quando o catálogo não traz o título.
11. IF a Jornada do Chamado não existe ou não informa o modelo ou o problema, THEN THE Servico_Dashboard SHALL usar o rótulo `nao_informado` no campo correspondente e `false` em `risco`.
12. THE Servico_Dashboard SHALL ordenar `em_foco.itens` pelo Motivo_De_Foco mais urgente do Chamado (ordem do Glossário), depois pela prioridade (P1, P2, P3), depois pela Idade_Em_Minutos em ordem decrescente e, em caso de empate, pelo número do Chamado em ordem crescente.
13. THE Servico_Dashboard SHALL produzir a mesma lista, na mesma ordem, para os mesmos registros e o mesmo instante, independentemente da ordem em que os Chamados foram lidos.
14. WHEN nenhum Chamado_Ativo possui Motivo_De_Foco, THE API_Dashboard SHALL devolver `em_foco.total` igual a 0 e `em_foco.itens` como lista vazia.
15. WHEN o repositório não tem nenhum Chamado, THE API_Dashboard SHALL devolver as seis quantidades de `visao_geral` iguais a 0 e `em_foco.itens` como lista vazia, e não o valor Sem_Dados.
16. THE Servico_Dashboard SHALL ser uma função pura, sem I/O e sem leitura do relógio, que recebe os Chamados, os dados mínimos das Jornadas, os títulos do catálogo e o instante atual.

### Requirement 23

**User Story:** Como responsável pela privacidade, quero que o Dashboard mostre apenas dados operacionais mínimos, para que nenhum dado pessoal vaze para a tela inicial do Painel_CS.

#### Acceptance Criteria

1. THE API_Dashboard SHALL omitir da resposta telefone, CEP, e-mail, CPF, texto de mensagens do Chamado, resumo do Pacote, `jornada_id`, nome e usuário do responsável, comentários de Avaliacoes e anexos.
2. THE API_Dashboard SHALL incluir o número do Chamado em cada item de `em_foco.itens`, por ser o identificador já exibido na Fila e necessário para o link do detalhe.
3. THE Servico_Dashboard SHALL receber das Jornadas apenas `risco`, `modelo_id` e `problema_id`, sem acessar os repositórios de Dados Pessoais, de mensagens nem de eventos.
4. THE Tela_Dashboard SHALL exibir somente os valores devolvidos pela API_Dashboard e pela API_Insights.
5. THE Tela_Dashboard SHALL exibir cada texto vindo da API como texto simples, escapado pelo React, sem usar `dangerouslySetInnerHTML`.

### Requirement 24

**User Story:** Como Gestor ou Atendente, quero um Dashboard com visão geral no topo e a lista de Chamados em foco, para decidir o próximo atendimento de relance.

#### Acceptance Criteria

1. THE Tela_Dashboard SHALL exibir o título "Dashboard" como cabeçalho de nível 1, seguido da Visao_Geral e do Seletor_De_Abas ou, para o Atendente, do painel de Chamados em foco.
2. THE Tela_Dashboard SHALL exibir na Visao_Geral, para qualquer perfil, os cards "Chamados abertos", "Em atendimento", "Encerrados", "P1 de risco abertos", "Sem responsável" e "Respostas não lidas", cada um com o valor numérico de `visao_geral`.
3. WHILE o perfil da sessão é `gestor`, THE Tela_Dashboard SHALL exibir também os Cards_De_Satisfacao "Nota média" e "Tempo médio até assumir", com os valores do Periodo `7d` e o texto "últimos 7 dias" em cada card.
4. WHILE o perfil da sessão é `atendente`, THE Tela_Dashboard SHALL omitir os Cards_De_Satisfacao e SHALL omitir qualquer solicitação à API_Insights.
5. WHEN um valor dos Cards_De_Satisfacao é Sem_Dados, THE Tela_Dashboard SHALL exibir o texto "sem dados" no card correspondente.
6. THE Lista_Em_Foco SHALL exibir cada Chamado_Em_Foco com: número do Chamado como link para `/cs/chamados/:numero` (com o número codificado na URL), prioridade com rótulo de texto (por exemplo, "P1 · Urgente"), status, modelo, problema, idade formatada (por exemplo, "5 min" ou "2 h 05 min") e um rótulo de texto para cada Motivo_De_Foco do item.
7. THE Lista_Em_Foco SHALL usar os rótulos "P1 ou risco", "Resposta não lida", "Sem responsável" e "Parado há mais de 60 min" para os Motivos_De_Foco `p1_ou_risco`, `resposta_nao_lida`, `sem_responsavel` e `parado`, respectivamente.
8. THE Lista_Em_Foco SHALL manter a ordem dos itens recebida da API_Dashboard.
9. THE Lista_Em_Foco SHALL exibir um link "Ver fila completa" para `/cs/fila`.
10. WHEN `em_foco.total` é maior que a quantidade de itens exibidos, THE Lista_Em_Foco SHALL exibir o texto "Mostrando N de M chamados em foco", com N igual à quantidade de itens exibidos e M igual a `em_foco.total`.
11. WHEN `em_foco.itens` é uma lista vazia, THE Lista_Em_Foco SHALL exibir a mensagem "Nenhum chamado pede atenção agora" e manter o link "Ver fila completa".
12. WHERE `modo_local` é `true` na resposta da API_Dashboard, THE Tela_Dashboard SHALL exibir o aviso visível "Dados de demonstração".
13. THE Tela_Dashboard SHALL transmitir a prioridade e cada Motivo_De_Foco também por texto, nunca apenas por cor.

### Requirement 25

**User Story:** Como Gestor, quero alternar entre as abas Insights e Chamados em foco com link direto, para compartilhar e voltar exatamente à visão que escolhi.

#### Acceptance Criteria

1. WHILE o perfil da sessão é `gestor`, THE Seletor_De_Abas SHALL exibir as abas "Insights" e "Chamados em foco", nessa ordem.
2. WHILE o perfil da sessão é `atendente`, THE Tela_Dashboard SHALL exibir somente o painel de Chamados em foco, com o cabeçalho "Chamados em foco" e sem `tablist`.
3. WHERE o Parametro_Aba não está na URL, THE Tela_Dashboard SHALL selecionar a Aba_Insights para o Gestor.
4. WHEN o Parametro_Aba é `insights` e o perfil é `gestor`, THE Tela_Dashboard SHALL selecionar a Aba_Insights.
5. WHEN o Parametro_Aba é `chamados`, THE Tela_Dashboard SHALL selecionar a Aba_Chamados_Em_Foco.
6. IF o Parametro_Aba tem um valor diferente de `insights` e `chamados`, THEN THE Tela_Dashboard SHALL selecionar a aba padrão do perfil, sem exibir erro.
7. WHEN o Parametro_Aba é `insights` e o perfil é `atendente`, THE Tela_Dashboard SHALL exibir a Aba_Chamados_Em_Foco, sem solicitar a API_Insights e sem exibir mensagem de erro nem de acesso negado.
8. WHEN o Gestor seleciona uma aba, THE Tela_Dashboard SHALL atualizar o Parametro_Aba na URL para `insights` ou `chamados`, sem recarregar a página, de modo que o link resultante abra o Dashboard na mesma aba.
9. THE Seletor_De_Abas SHALL usar `role="tablist"` com nome acessível, `role="tab"` em cada aba com `aria-selected` e `aria-controls`, e `role="tabpanel"` em cada painel com `aria-labelledby` apontando para a aba correspondente.
10. THE Seletor_De_Abas SHALL manter `tabindex="0"` apenas na aba selecionada e `tabindex="-1"` nas demais.
11. WHEN o foco está em uma aba e o Gestor pressiona a seta para a direita ou para a esquerda, THE Seletor_De_Abas SHALL mover o foco e a seleção para a aba seguinte ou anterior, voltando do último para o primeiro item e do primeiro para o último.
12. WHEN o foco está em uma aba e o Gestor pressiona Home ou End, THE Seletor_De_Abas SHALL mover o foco e a seleção para a primeira ou a última aba, respectivamente.
13. THE Seletor_De_Abas SHALL distinguir a aba selecionada por estilo visual que não dependa apenas de cor e por `aria-selected`.
14. WHILE a Aba_Insights está selecionada, THE Tela_Dashboard SHALL exibir no painel o Conteudo_Insights com o Periodo `7d` selecionado inicialmente, o seletor de Periodo e todos os estados do Requisito 13.
15. WHEN a Aba_Insights é selecionada com o Periodo `7d`, THE Tela_Dashboard SHALL reutilizar a resposta de 7 dias já obtida para os Cards_De_Satisfacao, sem enviar nova solicitação idêntica à API_Insights.
16. THE Tela_Dashboard SHALL exibir somente o painel da aba selecionada, de modo que exista no máximo um `tabpanel` visível por vez.
17. THE Tela_Dashboard SHALL carregar a Biblioteca_Graficos somente quando o painel da Aba_Insights é exibido pela primeira vez.

### Requirement 26

**User Story:** Como Gestor ou Atendente, quero estados claros de carregamento, erro e ausência de dados no Dashboard e testes que protejam o comportamento existente, para confiar na tela inicial e evoluí-la com segurança.

#### Acceptance Criteria

1. WHILE a Tela_Dashboard aguarda a resposta da API_Dashboard, THE Tela_Dashboard SHALL exibir um indicador de carregamento com `role="status"` no lugar da Visao_Geral e da Lista_Em_Foco.
2. IF a API_Dashboard responde com erro ou a requisição falha, THEN THE Tela_Dashboard SHALL exibir uma mensagem de erro com `role="alert"` e o botão "Tentar novamente" no lugar da Visao_Geral e da Lista_Em_Foco, sem exibir valores antigos como se fossem atuais.
3. WHEN a pessoa aciona "Tentar novamente" na Visao_Geral ou na Lista_Em_Foco, THE Tela_Dashboard SHALL repetir a solicitação à API_Dashboard.
4. IF a API_Insights responde com erro ou a requisição falha, THEN THE Tela_Dashboard SHALL exibir a mensagem de erro e o botão "Tentar novamente" apenas nos Cards_De_Satisfacao, mantendo a Visao_Geral e a Lista_Em_Foco exibidas.
5. WHILE a Tela_Dashboard está aberta e a página está visível, THE Tela_Dashboard SHALL atualizar a API_Dashboard automaticamente a cada 10 segundos (mesmo intervalo `INTERVALO_FILA_MS` da Fila) e interromper a atualização enquanto a página está oculta.
6. IF uma atualização automática da API_Dashboard falha depois de uma carga bem-sucedida, THEN THE Tela_Dashboard SHALL manter os últimos dados recebidos e exibir o aviso com `role="status"` de que não foi possível atualizar, com nova tentativa no próximo intervalo.
7. THE Tela_Dashboard SHALL permitir o uso das abas, dos links, do seletor de Periodo e dos botões "Tentar novamente" por teclado, com foco visível.
8. THE Tela_Dashboard SHALL exibir cada título de seção como cabeçalho e cada lista com nome acessível.
9. WHEN a Tela_Dashboard é renderizada nos estados carregando, erro, pronto com Chamados em foco e pronto sem Chamados em foco, para o Gestor (nas duas abas) e para o Atendente, THE teste da Tela_Dashboard SHALL executar a verificação do `jest-axe` e não encontrar violações.
10. THE feature SHALL manter sem alteração o contrato de `GET /api/cs/fila`, o contrato de `GET /api/cs/metricas`, a MATRIZ de autorização e os testes existentes de `test_rotas_cs_metricas.py`, `test_metricas_chamados.py`, `test_autorizacao_cs.py`, `FilaCs.test.tsx`, `MetricasCs.test.tsx`, `ChamadoCs.test.tsx`, `scripts/tests/test_dev_local.py` e `scripts/tests/test_persistencia_reinicio.py`.
11. THE feature SHALL limitar os ajustes em `PainelCs.test.tsx` e `rotas.test.tsx` a acrescentar expectativas, sem remover nem enfraquecer nenhuma existente: em `PainelCs.test.tsx`, a presença dos links "Dashboard", "Fila de chamados", "Métricas" e "Insights" para o Gestor e a ausência de "Métricas" e "Insights" para o Atendente; em `rotas.test.tsx`, a linha `["/cs", "Entrar no painel de atendimento"]` (sem sessão) da tabela de rotas.
12. THE suíte de testes SHALL incluir testes novos, em arquivo próprio, para: o Servico_Dashboard (contagens, soma dos status, Motivos_De_Foco, ordenação determinística, Limite_Em_Foco, `total`, Jornada ausente, repositório vazio e ausência de PII); a rota da API_Dashboard (Gestor 200, Atendente 200, sem sessão 401, falha de repositório com resposta 5xx com envelope de erro, e `decidir_acesso` com `Rota.perfis`); a API_Insights (Atendente continua recebendo 403); a Tela_Dashboard (carregamento, sucesso, erro com "Tentar novamente", lista vazia, abas por clique e por setas/Home/End, Parametro_Aba válido, inválido e `insights` para Atendente sem chamar a API_Insights, Cards_De_Satisfacao ocultos ao Atendente, escape de HTML e aviso de demonstração); e o LayoutPainel (links por perfil e `aria-current`).
13. THE suíte de testes SHALL incluir teste de que a navegação para `/cs` não redireciona para `/cs/fila`, de que o login sem destino anterior leva a `/cs` e de que `/cs/inshigts` exibe "Página não encontrada" dentro do LayoutPainel.
14. WHEN a verificação é executada, THE equipe SHALL rodar somente os testes relacionados: os testes novos do Dashboard, `test_rotas_cs_metricas`, `test_autorizacao_cs`, `PainelCs.test.tsx`, `rotas.test.tsx`, `FilaCs.test.tsx` e os testes da Tela_Insights.
15. THE Guia_Demo SHALL descrever o Dashboard em `/cs` (visão geral, aba "Insights", aba "Chamados em foco"), os links do menu e o endereço correto `/cs/insights`.
16. THE feature SHALL manter fora do escopo DynamoDB/AWS, `infra/`, IAM, agente de IA e deploy.
