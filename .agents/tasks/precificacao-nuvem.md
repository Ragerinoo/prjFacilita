# Precificação em nuvem do TRES Autoatendimento (AWS)

Data-base: 14/10/2026. Região de referência: **sa-east-1 (São Paulo)**, com comparativo em us-east-1. Câmbio: **US$ 1 = R$ 5,0441** (PTAX venda do Banco Central, 14/10/2026 13:05; compra 5,0435). Todos os valores em USD são preços de lista (on-demand), sem impostos, IOF ou descontos.

> Este relatório foi gerado em modo somente leitura. Nenhum arquivo do projeto foi alterado, nenhum `.env` foi lido (só o `.env.example`, que contém nomes de variáveis) e nenhum comando de deploy ou `cdk synth` foi executado.

---

## 1. Sumário executivo

**Resposta curta:** manter o projeto em nuvem custa **cerca de US$ 5 a 6 por mês na demo**, **US$ 6 a 6,5 no piloto** e **cerca de US$ 40 por mês (≈ R$ 200/mês, ≈ R$ 2,4 mil/ano) em produção inicial com 5.000 usuários ativos**. O custo ocioso, sem nenhum acesso, é de **≈ US$ 1,9/mês (≈ R$ 9,7)**.

| Cenário (sa-east-1) | Usuários ativos/mês | Jornadas/mês | Mensal USD (sem / com free tier) | Anual USD (sem / com) | Mensal BRL (sem / com) | Anual BRL (sem / com) |
|---|---:|---:|---:|---:|---:|---:|
| A. Demo/Hackathon | 40 | 300 | 5,25 / 4,91 | 62,96 / 58,89 | 26,46 / 24,75 | 317,55 / 297,04 |
| B. Piloto | 500 | 650 | 6,22 / 5,44 | 74,59 / 65,28 | 31,35 / 27,44 | 376,26 / 329,28 |
| C. Produção inicial | 5.000 | 6.500 | 39,71 / 33,43 | 476,54 / 401,17 | 200,31 / 168,63 | 2.403,69 / 2.023,54 |
| D. Sensibilidade 10x | 50.000 | 65.000 | 346,40 / 305,89 | 4.156,85 / 3.670,74 | 1.747,30 / 1.542,96 | 20.967,58 / 18.515,58 |

Pontos principais:

1. **A IA domina a conta.** Em produção inicial, Bedrock (LLM) + AgentCore Runtime somam ~71% do total (US$ 28,4 de US$ 39,7). O restante da arquitetura serverless (API Gateway, Lambda, DynamoDB, CloudFront, S3, KMS, Secrets, logs) custa só ~US$ 11,3/mês (≈ R$ 57).
2. **A arquitetura é de fato serverless e sem custo fixo relevante.** Não há VPC, NAT Gateway, EC2, RDS, OpenSearch nem Cognito no código. Os únicos custos fixos são 1 chave KMS (US$ 1) e 2 segredos (US$ 0,80).
3. **Custo por usuário ativo cai com a escala:** R$ 0,66 (demo, 40 pessoas) → R$ 0,063 (piloto) → **R$ 0,040 (produção inicial)** → R$ 0,035 (10x). Custo por jornada em produção inicial: **R$ 0,031**.
4. **Três achados que mudam o orçamento ou exigem decisão** (detalhes nas seções 5 e 8):
   - O **AgentCore Runtime V2** (que `services/agente/premissas.py` adota) **não está disponível em sa-east-1**. O anúncio da AWS lista só us-east-1, us-east-2, us-west-2, eu-west-1 e ap-northeast-1. Em São Paulo só o runtime original (V1) seria possível, e ele cobra memória pelo pico durante toda a sessão, inclusive nos 15 min ociosos configurados.
   - O **modelo padrão (Claude Haiku 4.5, US$ 1/US$ 5 por 1M tokens)** já tem sucessor na lista oficial de preços: **Claude Haiku 5.5 a US$ 0,10/US$ 0,50 por 1M tokens (perfil global)**, 90% mais barato. Trocar exige validar qualidade com o conjunto dourado (tarefa 17.6).
   - **Não há proteção financeira contra abuso**: sem WAF (Q12), sem limite por cliente, sem alarmes de custo, e a rota pública de IA aceita 20 req/s. O teto teórico de abuso é da ordem de US$ 300/hora (seção 5.3).
5. **Otimizações somadas** (ociosidade do runtime 900 s → 120 s, Haiku 5.5, cache 35% → 60%, polling do painel 10 s → 30 s) reduzem o cenário C de US$ 39,71 para **US$ 11,68/mês (−71%, ≈ R$ 59/mês)**. Sem trocar de modelo: US$ 24,38 (−39%).

---

## 2. Arquitetura e inventário de recursos

Fonte: leitura de `infra/app.py` e das cinco stacks CDK (Python, `aws-cdk-lib==2.273.0`). Estado do repositório: **sem commits no Git, sem `infra/cdk.out`, sem evidência de deploy**. Tudo abaixo é "definido no código", não "confirmado em conta AWS".

### 2.1 Implementado no CDK (definido em código)

| Stack (arquivo) | Recursos | Configuração que afeta custo |
|---|---|---|
| `tres-dados` (`infra/stacks/dados_stack.py`) | 1 chave KMS gerenciada pelo cliente (`alias/tres-dados`); **16 tabelas DynamoDB** (modelos, problemas, instrucoes, jornadas, eventos, chamados, mensagens_chamado, dados_pessoais, acessos_pii, ordens_servico, cache_respostas, avaliacoes, agregados_dia, usuarios_cs, sessoes_cs, config); **4 GSIs** (`gsi_catalogo`, `gsi_ativas`, `gsi_encerradas`, `gsi_fila`, projeção `ALL`) | `BillingMode.PAY_PER_REQUEST` em todas (sem capacidade provisionada); SSE-KMS com a chave do cliente; rotação anual da chave; TTL só em `sessoes_cs`; **sem PITR/backup**; `RETAIN` por padrão |
| `tres-armazenamento` (`armazenamento_stack.py`) | 3 buckets S3 (site, fotos, manuais [versionado]); fila SQS `encerramentos` + DLQ; 1 segredo (`tres/segredo-app`); 2 parâmetros SSM | SSE-KMS com bucket key; **sem regra de expiração de objetos** (só aborta multipart em 7 dias); SQS com KMS, DLQ retém 14 dias |
| `tres-api` (`api_stack.py`) | **5 Lambdas Python 3.12 arm64**: `api` (1024 MB, 28 s), `dados_pessoais` (512 MB, 15 s), `enriquecimento` (512 MB, 15 s), `encerramento` (256 MB, 8 s, SQS batch 1, concorrência máx. 5), `varredura` (256 MB, 60 s); 1 Lambda autorizador (128 MB, 5 s, cache de resposta 5 min); **HTTP API com 37 rotas** e throttling por rota; 1 segredo (`tres/segredo-origem`); EventBridge Scheduler `rate(5 minutes)`; 6 log groups | Sem VPC; **logs com retenção de 1 mês**; sem provisioned concurrency, sem X-Ray, sem access log do API Gateway; throttling padrão 50 rps/100 de rajada, IA 20/40, login 5/10, sensíveis 10/20 |
| `tres-borda` (`borda_stack.py`) | 1 distribuição CloudFront (site + `/api/*` na mesma origem, HTTP/2+3, OAC para S3), 1 CloudFront Function (reescrita do SPA), políticas de cache e de cabeçalhos | **Price class padrão (todas as regiões)**; sem WAF, sem logs de acesso, sem domínio próprio/ACM/Route 53 (usa `*.cloudfront.net`) |
| `tres-conhecimento` (`conhecimento_stack.py`) | S3 Vectors (vector bucket + índice 1024 dim, float32, cosseno); Bedrock Knowledge Base (embeddings `cohere.embed-multilingual-v3`, chunking FIXED_SIZE 300 tokens/20%); data source S3 (prefixo `secoes/`); 3 parâmetros SSM | Vector store barato por desenho (S3 Vectors em vez de OpenSearch Serverless); `top_k = 5` por consulta |

Ausências verificadas por busca no código: nenhum VPC/NAT/EC2/Fargate/RDS/OpenSearch/Cognito/Step Functions/SNS/SES/WAF/alarme CloudWatch/Route 53 nas stacks. O login do Painel_CS é próprio (Argon2id + sessão em DynamoDB), por decisão D6 do design.

### 2.2 Planejado ou parcial (não está pronto no código)

| Item | Estado | Evidência |
|---|---|---|
| **AgentCore Runtime** (agente Strands) | **Não implantável hoje.** O CDK só recebe o ARN via contexto `agente_runtime_arn`; o deploy é por `agentcore configure/launch` (tarefa 17.4 aberta). `services/agente` tem config, contratos, modelo, recuperação e privacidade, mas o `prompts.py` citado em `modelo.py` não existe | `.kiro/specs/tres-autoatendimento/tasks.md` (17.3, 17.4, 17.5 abertas); `infra/app.py` |
| Pipeline do Assistente_IA na API (cache, limite de 10 chamadas, custo por chamada) | Planejado (tarefas 18.x abertas). O cálculo de custo existe em `packages/dominio/src/dominio/custo.py` | `tasks.md` |
| Métricas/insights/dashboard em DynamoDB | `ChamadosDynamoDB.listar_todos` levanta `ErroIndisponivelForaDoModoLocal`; essas telas hoje só funcionam no modo local | `services/api/repositorios/dynamodb/chamados.py` |
| WAF, limite por cliente | Fora do MVP (Q12) | `api_stack.py`, `borda_stack.py`, `design.md` |
| Domínio próprio, certificado, alarmes, backup/PITR, observabilidade do agente | Não existem | busca nas stacks |
| Preços e câmbio de IA | O código manda preencher `config.precos_modelo` e `config.cotacao_usd_brl` antes da demo; **nenhum preço está no repositório** | `premissas.py`, `design.md` |

Também existe um modo local sem AWS (`scripts/dev_local.py`, `docs/DEMO.md`), que não gera custo de nuvem.

### 2.3 Região

`services/agente/premissas.py` define `REGIAO_PADRAO = "sa-east-1"` e `REGIAO_ALTERNATIVA = "us-east-1"`. O CDK não fixa região: usa `CDK_DEFAULT_REGION` do ambiente (`infra/app.py`). Por isso o relatório usa sa-east-1 como base e us-east-1 como comparativo.

### 2.4 Fluxo de uso que gera custo (derivado das rotas e do front)

- Consumidor: página estática via CloudFront (bundle inicial ≈ 78 KB + 26 KB gzip, mais chunks de rota de 2 a 6 KB gzip) → ~16 chamadas de API no caminho do guia (criar Jornada, instrução, eventos de passo, resolução, avaliação).
- IA (só quando o guia não resolve): `POST /jornadas/{id}/mensagens`, limite de 10 chamadas ao modelo por Jornada, cache de respostas aprovadas antes de chamar o modelo.
- Escalada: cria Chamado, Lambda `enriquecimento` chama o agente (resumo), fotos até 5 MB por URL pré-assinada direto no S3, e o consumidor acompanha o chamado por polling.
- Atendente (Painel_CS): a fila é recarregada a cada **10 s** (`INTERVALO_FILA_MS`) e o dashboard também (`INTERVALO_DASHBOARD_MS`); cada chamada valida e renova a sessão no DynamoDB e consulta a partição inteira do `gsi_fila` com leitura consistente.
- Fundo: a varredura de abandono roda a cada 5 min (8.640 execuções/mês) mesmo sem usuários.

---

## 3. Premissas por cenário

### 3.1 Parâmetros de cada cenário (explícitos e numéricos)

| Parâmetro | A. Demo | B. Piloto | C. Produção inicial | D. 10x (sensibilidade) |
|---|---:|---:|---:|---:|
| Usuários ativos/mês (consumidores únicos) | 40 | 500 | 5.000 | 50.000 |
| Jornadas/mês | 300 | 650 | 6.500 | 65.000 |
| % de Jornadas que usam o Assistente IA | 40% | 20% | 20% | 20% |
| % de Jornadas que viram Chamado | 40% | 25% | 25% | 25% |
| Mensagens enviadas à IA por Jornada com IA | 3 | 3 | 3 | 3 |
| Acerto do Cache_Respostas (mensagens sem custo de LLM) | 0% | 15% | 35% | 50% |
| Horas de Painel_CS abertas no mês | 12 | 80 | 750 | 7.500 |
| Foto por chamado | 50% dos chamados com 2 fotos de 1,5 MB | idem | idem | idem |
| Chamadas de API por mês (consumidor + painel) | 15.720 | 56.868 | 543.675 | 5.436.750 |
| Chamados/mês | 120 | 162 | 1.625 | 16.250 |

Notas: o cenário A é uma "demo pesada" (ensaios com IA e escalada acima do normal). O cenário D não é um dos três pedidos; serve só para demonstrar linearidade. A proporção 25% de Jornadas escaladas é uma hipótese: o requisito diz que mais de 70% dos chamados atuais são falsos defeitos, e o produto busca resolver a maior parte no guia.

### 3.2 Premissas por unidade de uso (INFERIDAS do código; precisam de medição)

| Item | Valor adotado | Base |
|---|---|---|
| Chamadas de API por Jornada (guia) | 16; +6 se usar IA; +8 se virar Chamado; +24 de polling do consumidor por Chamado (5 s × 2 min) | rotas em `api_stack.py`, `routes/guia.py` |
| Painel_CS | 500 req/h por atendente (fila 360/h + dashboard e ações) | `FilaCs.tsx`, `useDashboard.ts` |
| DynamoDB por Jornada | ~60 WRU + ~25 RRU (guia); +20 WRU/+8 RRU (IA); +30 WRU/+60 RRU (Chamado). Painel: 1 WRU + 17 RRU por poll | cada evento grava `eventos` e atualiza `jornadas` (com `gsi_ativas`); leituras consistentes (`ConsistentRead=True` em `_base.py`) |
| Lambda | `api` 150 ms médios a 1024 MB, mais 4 s de espera do agente por chamada `responder` e 3 s por `sugestão`; `enriquecimento` 4 s a 512 MB; logs de 1,2 KB por invocação | timeouts em `api_stack.py` |
| Autorizador | até 37 rotas × 8.640 janelas de 5 min (teto conservador) | cache de 5 min em `_criar_api_http` |
| Tokens por chamada ao LLM | `responder`: 2.500 entrada / 350 saída (top_k 5 × até 300 tokens + sistema + histórico); `resumo_repasse`: 1.500 / 200; `sugestão_atendente`: 2.000 / 300 | `RETRIEVE_TOP_K=5`, `CHUNKING_MAX_TOKENS=300`, `LLM_MAX_TOKENS_SAIDA=700` em `premissas.py`. **Os prompts ainda não existem**, então é estimativa |
| Chamadas ao LLM | `responder` = mensagens × (1 − cache); `resumo` = 1 por Chamado; `sugestão` = 0,6 por Chamado | `design.md` (D4, 3.5) |
| AgentCore Runtime | 1 vCPU e 1 GB por sessão; sessão com IA vive 3 min + 900 s ociosos; sessão de chamada única vive 10 s + 900 s; CPU ativa 2 s (`responder`) ou 1,5 s | `RUNTIME_OCIOSO_S = 900` em `premissas.py`; modelo de cobrança V1 (pico de memória durante a sessão) |
| CloudFront | 20 requisições estáticas e ~0,3 MB por Jornada; resposta de API 2 KB; resposta do painel 8 KB | `apps/web/dist` |
| KMS | 16 tabelas × janelas de 5 min com chave de dados em cache, mais segredos, SQS e S3 (estimativa, teto de 400 mil req/mês) | comportamento de cache de chave de dados do DynamoDB |
| Armazenamento | DynamoDB ~10 KB por Jornada (×3 por GSIs e overhead); fotos acumulam por 12 meses (média de 6,5 meses no ano 1); ninguém apaga objetos | sem lifecycle de expiração |

### 3.3 Como ler "com free tier" e "sem free tier"

- **Sem free tier:** tudo a preço de lista.
- **Com free tier:** desconta as franquias permanentes (Lambda 1 M req e 400 mil GB-s; DynamoDB 25 GB; CloudFront 1 TB e 10 M req; CloudWatch Logs 5 GB; SQS 1 M req; EventBridge Scheduler 14 M; KMS 20 mil req; S3 transferência de saída 100 GB) mais 1 M de chamadas do HTTP API (franquia de 12 meses de contas antigas). Bedrock e AgentCore não têm franquia.
- Contas criadas desde 15/07/2025 recebem créditos de até US$ 200 e um plano gratuito de 6 meses (página de preços do API Gateway). Os créditos **não** foram modelados e podem zerar a conta da demo.

---

## 4. Tabelas de custo (sa-east-1, USD por mês)

Os totais anuais são 12 × o mês típico. Conversão para BRL a R$ 5,0441 por US$.

### Cenário A. Demo/Hackathon

| Serviço | Sem free tier | Com free tier |
|---|---:|---:|
| API Gateway HTTP API | 0,02 | 0,00 |
| AWS Lambda (6 funções, arm64) | 0,08 | 0,00 |
| DynamoDB (on-demand, 16 tabelas) | 0,08 | 0,06 |
| CloudFront (site + /api) | 0,06 | 0,00 |
| S3 (site, fotos, manuais) | 0,08 | 0,05 |
| S3 Vectors + embeddings (KB) | 0,02 | 0,02 |
| Bedrock LLM (Claude Haiku 4.5) | 2,08 | 2,08 |
| AgentCore Runtime | 0,82 | 0,82 |
| KMS (1 chave + requisições) | 1,11 | 1,05 |
| Secrets Manager (2 segredos) | 0,83 | 0,83 |
| CloudWatch Logs (retenção 1 mês) | 0,04 | 0,00 |
| SQS + EventBridge Scheduler | 0,02 | 0,00 |
| **Total mensal (USD)** | **5,25** | **4,91** |
| **Total anual (USD)** | **62,96** | **58,89** |
| **Total mensal (BRL)** | **26,46** | **24,75** |
| **Total anual (BRL)** | **317,55** | **297,04** |

Volumes: 15.720 req de API; 120 chamados; 360 `responder` + 120 `resumo` + 72 `sugestão`; 1,22 M tokens de entrada e 0,17 M de saída; 5.624 GB-s de Lambda. Comparativo us-east-1: US$ 5,15 (sem) e US$ 4,86 (com free tier).

### Cenário B. Piloto

| Serviço | Sem free tier | Com free tier |
|---|---:|---:|
| API Gateway HTTP API | 0,09 | 0,00 |
| AWS Lambda (6 funções, arm64) | 0,18 | 0,00 |
| DynamoDB (on-demand, 16 tabelas) | 0,27 | 0,22 |
| CloudFront (site + /api) | 0,21 | 0,00 |
| S3 (site, fotos, manuais) | 0,10 | 0,07 |
| S3 Vectors + embeddings (KB) | 0,02 | 0,02 |
| Bedrock LLM (Claude Haiku 4.5) | 2,16 | 2,16 |
| AgentCore Runtime | 1,02 | 1,02 |
| KMS (1 chave + requisições) | 1,19 | 1,13 |
| Secrets Manager (2 segredos) | 0,83 | 0,83 |
| CloudWatch Logs (retenção 1 mês) | 0,13 | 0,00 |
| SQS + EventBridge Scheduler | 0,02 | 0,00 |
| **Total mensal (USD)** | **6,22** | **5,44** |
| **Total anual (USD)** | **74,59** | **65,28** |
| **Total mensal (BRL)** | **31,35** | **27,44** |
| **Total anual (BRL)** | **376,26** | **329,28** |

Volumes: 56.868 req de API (70% vêm do polling do painel); 162 chamados; 332 `responder` + 162 `resumo` + 98 `sugestão`; 1,27 M tokens de entrada e 0,18 M de saída. Comparativo us-east-1: US$ 5,98 (sem) e US$ 5,33 (com).

### Cenário C. Produção inicial

| Serviço | Sem free tier | Com free tier |
|---|---:|---:|
| API Gateway HTTP API | 0,86 | 0,00 |
| AWS Lambda (6 funções, arm64) | 1,52 | 0,00 |
| DynamoDB (on-demand, 16 tabelas) | 2,50 | 2,05 |
| CloudFront (site + /api) | 2,04 | 0,00 |
| S3 (site, fotos, manuais) | 1,02 | 0,66 |
| S3 Vectors + embeddings (KB) | 0,05 | 0,05 |
| Bedrock LLM (Claude Haiku 4.5) | 18,25 | 18,25 |
| AgentCore Runtime | 10,12 | 10,12 |
| KMS (1 chave + requisições) | 1,48 | 1,42 |
| Secrets Manager (2 segredos) | 0,88 | 0,88 |
| CloudWatch Logs (retenção 1 mês) | 0,96 | 0,00 |
| SQS + EventBridge Scheduler | 0,02 | 0,00 |
| **Total mensal (USD)** | **39,71** | **33,43** |
| **Total anual (USD)** | **476,54** | **401,17** |
| **Total mensal (BRL)** | **200,31** | **168,63** |
| **Total anual (BRL)** | **2.403,69** | **2.023,54** |

Volumes: 543.675 req de API; 1.625 chamados; 2.535 `responder` + 1.625 `resumo` + 975 `sugestão`; 10,72 M tokens de entrada e 1,50 M de saída; 0,85 M WRU e 6,69 M RRU; 0,89 M invocações Lambda e 100.633 GB-s; 1,0 GB de logs. Comparativo us-east-1: US$ 37,69 (sem) e US$ 32,45 (com).

### Cenário D (sensibilidade, 10x)

| Serviço | Sem free tier | Com free tier |
|---|---:|---:|
| API Gateway HTTP API | 8,64 | 7,05 |
| AWS Lambda | 14,03 | 8,50 |
| DynamoDB | 24,94 | 20,40 |
| CloudFront | 20,41 | 0,00 |
| S3 | 10,19 | 6,62 |
| S3 Vectors + embeddings | 0,32 | 0,32 |
| Bedrock LLM | 157,62 | 157,62 |
| AgentCore Runtime | 100,90 | 100,90 |
| KMS + Secrets | 2,90 | 2,84 |
| CloudWatch Logs | 6,34 | 1,63 |
| SQS + Scheduler | 0,11 | 0,00 |
| **Total mensal (USD)** | **346,40** | **305,89** |

Isto é R$ 1.747/mês (R$ 20.968/ano) sem free tier. Dez vezes o uso custa ~8,7 vezes o cenário C: o custo cresce de forma quase linear, sem degraus de infraestrutura.

### Custo ocioso (zero acessos)

US$ 1,93/mês (US$ 1,85 com free tier), ou R$ 9,7. É KMS (US$ 1,04) + Secrets Manager (US$ 0,83) + varredura a cada 5 min (Lambda, DynamoDB, Scheduler, ~US$ 0,05).

### Comparativo de região (cenário C, sem free tier)

| Região | Total/mês USD | Observação |
|---|---:|---|
| sa-east-1 | 39,71 | Latência menor para usuários brasileiros; dados no Brasil (relevante para LGPD) |
| us-east-1 | 37,69 | ~5% mais barato (API Gateway US$ 1,00 vs 1,59/M; DynamoDB US$ 0,625/0,125 vs 0,9375/0,1875 por milhão; CloudWatch US$ 0,50 vs 0,90/GB) |

O CloudFront é cobrado pela região do **visitante**, não da origem, então o consumidor brasileiro paga a tarifa da América do Sul nas duas opções. A diferença de ~5% não compensa a latência extra nem a saída de dados do Brasil. A única vantagem real de us-east-1 é o AgentCore Runtime V2 (seção 5.4).

### Tabela de preços unitários usados

| Recurso | sa-east-1 | us-east-1 | Fonte |
|---|---|---|---|
| Lambda arm64 | US$ 0,0000133334/GB-s; US$ 0,20/M req | igual | Lista de preços oficial (AWSLambda) |
| API Gateway HTTP API | US$ 1,59/M (até 300 M) | US$ 1,00/M | Lista oficial (AmazonApiGateway) |
| DynamoDB sob demanda | US$ 0,9375/M WRU; US$ 0,1875/M RRU; US$ 0,375/GB-mês (após 25 GB) | US$ 0,625; 0,125; 0,25 | Lista oficial (AmazonDynamoDB) |
| S3 Standard | US$ 0,0405/GB; PUT US$ 0,007/mil; GET US$ 0,0056/10 mil | US$ 0,023/GB | Lista oficial (AmazonS3) |
| S3 Vectors | US$ 0,11/GB-mês; consulta US$ 4,4/M; ingestão US$ 0,35/GB | US$ 0,06; 2,5/M; 0,20 | Lista oficial (AmazonS3) |
| Saída de dados do S3 para a internet | US$ 0,15/GB | US$ 0,09/GB | Lista oficial (AWSDataTransfer) |
| KMS | US$ 1/chave-mês; US$ 0,03/10 mil req | igual | Lista oficial (awskms) |
| Secrets Manager | US$ 0,40/segredo; US$ 0,05/10 mil chamadas | igual | Lista oficial (AWSSecretsManager) |
| CloudWatch Logs (ingestão padrão) | US$ 0,90/GB; US$ 0,0408/GB-mês | US$ 0,50; 0,03 | Lista oficial (AmazonCloudWatch) |
| SQS padrão | US$ 0,40/M | igual | Lista oficial (AWSQueueService) |
| EventBridge Scheduler | US$ 1,70/M (após 14 M grátis) | US$ 1,00/M | Lista oficial (AWSEvents) |
| Claude Haiku 4.5 (perfil global) | US$ 1,00 entrada / US$ 5,00 saída por 1M tokens | igual (regional: US$ 1,10 / 5,50) | Lista oficial (AmazonBedrockFoundationModels) |
| Claude Haiku 5.5 (perfil global) | US$ 0,10 / US$ 0,50 por 1M tokens | igual | idem |
| Cohere Embed Multilingual v3 | US$ 0,10 por 1M tokens | igual | idem |
| AgentCore Runtime V1 (consumo) | **não consta na lista de sa-east-1**; usei US$ 0,0895/vCPU-h e US$ 0,00945/GB-h de us-east-1 como proxy | US$ 0,0895 e US$ 0,00945 | Lista oficial (AmazonBedrockAgentCore) |
| AgentCore Runtime V2 (consumo) | não disponível na região | US$ 0,1276/vCPU-h e US$ 0,0169/GB-h | idem |
| CloudFront (visitante na América do Sul) | ≈ US$ 0,11/GB e ≈ US$ 0,022/10 mil req HTTPS (**fonte secundária**); franquia permanente de 1 TB e 10 M req | | ver seção 9 |
| AWS WAF | US$ 5/web ACL; US$ 1/regra; US$ 0,60/M req | igual | Lista oficial (awswaf) |

---

## 5. Direcionadores de custo, riscos e otimizações

### 5.1 Principais direcionadores (cenário C)

| # | Direcionador | US$/mês | % do total | Por quê |
|---|---|---:|---:|---|
| 1 | Tokens do LLM (Bedrock) | 18,25 | 46% | 10,7 M tokens de entrada, dominados pelos trechos recuperados (top_k 5 × 300 tokens) em cada `responder` e `sugestão` |
| 2 | AgentCore Runtime | 10,12 | 25% | 90% é **memória retida durante a ociosidade** (900 s por sessão), não processamento. A sessão é por Jornada |
| 3 | DynamoDB | 2,50 | 6% | Polling do painel (10 s) lê a fila inteira com leitura consistente; cada evento da Jornada atualiza o item com GSI |
| 4 | CloudFront | 2,04 | 5% | Só aparece sem free tier; vem do preço da América do Sul (fonte secundária) |
| 5 | Lambda + API Gateway | 2,38 | 6% | Polling do painel responde por 69% das requisições de API |

Juntos, 1 e 2 somam 71%. O que o "pitch serverless" afirma (sem servidores ociosos) é verdade, mas o produto custa por causa da IA, não da infraestrutura.

### 5.2 Otimizações concretas (cenário C, sa-east-1, sem free tier, base US$ 39,71)

| Otimização | O que mudar | Economia estimada | Observação |
|---|---|---:|---|
| Trocar para Claude Haiku 5.5 | `TRES_MODELO_LLM_ID` (parâmetro SSM `/tres/config/modelo-llm-id`) | **−US$ 16,42 (−41%)** | Preço da lista oficial: US$ 0,10/0,50 por 1M. Validar qualidade em pt-BR e o ID do perfil de inferência no console; Haiku 4.5 aparece como "legado" na documentação da Anthropic |
| Reduzir a ociosidade do runtime | `RUNTIME_OCIOSO_S` de 900 s para 120 s | **−US$ 7,99 (−20%)** | A próxima mensagem depois de 2 min cai em partida a frio. Combinar com aquecimento ao abrir o chat (já sugerido em `premissas.py`) |
| Subir o acerto do cache | Alimentar `cache_respostas` no encerramento (Req 16) até ~60% | −US$ 4,25 (−11%) | Cache de pergunta normalizada exata; depende de curadoria do atendente |
| Polling do painel de 10 s para 30 s | `INTERVALO_FILA_MS` e `INTERVALO_DASHBOARD_MS` | −US$ 3,09 (−8%) | Também reduz logs e leituras consistentes. Alternativa: leitura eventualmente consistente no `gsi_fila` (metade do RRU) |
| **Todas juntas** | | **−US$ 28,03 (−71%) → US$ 11,68 (R$ 58,9/mês)** | Sem trocar de modelo: US$ 24,38 (−39%) |
| Expirar fotos | Regra de lifecycle no bucket de fotos (hoje não há) | Evita crescimento linear a partir do 2º ano | Prazo depende da política de retenção, ainda em aberto no requisito |
| Orçamento e alarmes | AWS Budgets (2 orçamentos grátis) e alarme de custo de IA | Evita surpresa | Não existe hoje |

Não recomendado por custo: trocar a chave KMS do cliente por chave gerenciada (economia de ~US$ 1/mês), pois os requisitos 18.2 e 20.1 exigem a chave do cliente; mudar de região só pelo preço.

### 5.3 Riscos de custo surpresa

1. **Abuso da rota pública de IA (o maior risco).** `POST /api/pub/jornadas/{id}/mensagens` é pública, sem WAF nem limite por cliente (Q12), com throttling global de 20 req/s (rajada 40). O limite de 10 chamadas por Jornada não impede criar Jornadas novas (`POST /jornadas` aceita 50 rps). Teto teórico: 20 req/s × 3.600 s × ≈ US$ 0,0043 de tokens ≈ **US$ 300/hora (≈ R$ 1,5 mil/hora)**, sem contar o runtime. É um teto de papel (cotas do Bedrock e tempo de Lambda reduzem na prática), mas não há alarme que avise. Mitigações: AWS WAF com regra por taxa por IP (US$ 5 + US$ 1 por regra + US$ 0,60/M req; ≈ US$ 8,3/mês no cenário C), contador diário global de chamadas ao modelo na tabela `config`, limite mais baixo para essa rota e AWS Budgets com ação.
2. **Memória ociosa do AgentCore.** 90% do custo do runtime vem da ociosidade de 900 s. Escala linear com o número de Jornadas com IA.
3. **Fila do painel como partição única.** `listar_fila` consulta toda a partição `FILA_PK` do `gsi_fila` (projeção `ALL`, sem paginação, leitura consistente) a cada 10 s por atendente aberto. Assumi 17 RRU por poll (~25 chamados abertos). Com 200 chamados abertos seriam ~125 RRU por poll e o custo de leitura do cenário C subiria de ~US$ 1,2 para ~US$ 8,8. Um painel aberto 24 h por dia multiplica por 3 o consumo de um turno de 8 h.
4. **Logs.** Cada requisição gera ao menos uma linha de log por Lambda (≈ 1,2 KB), então o polling do painel domina o volume. A US$ 0,90/GB em São Paulo, cada 1 GB custa US$ 0,94 com a retenção de 1 mês. Se o `agentcore launch` habilitar observabilidade, soma-se ingestão de spans e logs do agente (não modelado, ordem de US$ 1 a 3 no cenário C).
5. **Crescimento sem expiração.** Fotos (S3), `eventos`, `mensagens_chamado` e `acessos_pii` nunca expiram. Em C são ~2,4 GB/mês de fotos (~29 GB ao fim de 12 meses, ≈ US$ 1,2/mês só de armazenamento no mês 12). Pequeno hoje, mas sem fim e sem política de retenção definida.
6. **KMS e rotação.** A lista de preços cobra por versão da chave; com rotação anual, a partir do 2º ano pode haver cobrança adicional por versão (confirmar). Requisições KMS ficam abaixo de US$ 1 até o cenário D.
7. **Créditos de conta nova e fim da franquia.** O custo "com free tier" some depois de 12 meses ou dos créditos; o cenário "sem free tier" é o orçamento realista.
8. **NAT Gateway, OpenSearch Serverless, RDS:** não existem hoje. Se a Q1 for revertida (S3 Vectors → OpenSearch Serverless), o custo ocioso passaria de ~US$ 2 para centenas de dólares por mês. O design D10 já registra esse risco; manter S3 Vectors.

### 5.4 Achado: AgentCore V2 não existe em sa-east-1

`premissas.py` decide `RUNTIME_PLATFORM_VERSION = "V2"` e `REGIAO_PADRAO = "sa-east-1"`, e cita a meta de partida a frio de ~2 s. O anúncio da AWS do novo Runtime lista as regiões us-east-1, us-east-2, us-west-2, eu-west-1 e ap-northeast-1. Em São Paulo, a opção documentada é o runtime original, com partida a frio de 5,4 a 30 s conforme o tamanho da imagem (segundo o mesmo anúncio), o que ameaça o alvo de p90 de 10 s do Req 6.8. Opções, com o efeito em custo:

- **Runtime V1 em sa-east-1** (modelado neste relatório): memória cobrada pelo pico durante a sessão. Preço de São Paulo não consta na lista oficial; usei o de us-east-1 como proxy.
- **Runtime V2 em us-east-1**, mantendo API e dados em sa-east-1: cobra pela memória realmente usada, a US$ 0,1276/vCPU-h e US$ 0,0169/GB-h. Em fontes secundárias, V2 só compensa se a memória média ficar abaixo de ~56% do pico, o que é típico de chat com longos períodos ociosos. Estimativa própria: reduz o AgentCore do cenário C de US$ 10,1 para algo na faixa de US$ 3 a 5 (supondo memória média de 15% a 25% do pico de 1 GB). Custo extra: ~100 a 150 ms de latência entre regiões e dados (já mascarados de PII) saindo do Brasil; avaliar com o jurídico/LGPD.
- Recomendação: decidir antes de implementar 17.4 e não prometer "p90 de 10 s" no pitch sem medir. Confirmar a tabela de regiões na documentação do AgentCore na data do deploy.

---

## 6. Custo por usuário ativo e sugestão de monetização

### 6.1 Custo unitário (sa-east-1, sem free tier)

| Cenário | Custo por usuário ativo/mês | Custo por Jornada | Custo por Chamado aberto |
|---|---:|---:|---:|
| A. Demo (40 usuários) | US$ 0,131 (R$ 0,66) | R$ 0,088 | R$ 0,22 |
| B. Piloto (500) | US$ 0,0124 (R$ 0,063) | R$ 0,048 | R$ 0,19 |
| C. Produção inicial (5.000) | **US$ 0,0079 (R$ 0,040)** | **R$ 0,031** | R$ 0,12 |
| D. 10x (50.000) | US$ 0,0069 (R$ 0,035) | R$ 0,027 | R$ 0,11 |

A queda de A para C vem da diluição do custo fixo de ~US$ 1,9. A partir do piloto, o custo marginal por Jornada fica entre R$ 0,03 e R$ 0,05 e é dominado por IA.

### 6.2 Sugestão de modelo (apenas sugestão para o pitch, não validada com o cliente)

Premissa: o cliente natural é a 3corações, e o valor do produto é evitar contato humano (mais de 70% dos chamados atuais são falsos defeitos, segundo o requisito).

- **Preço por Jornada resolvida sem humano:** R$ 0,30 a R$ 0,80. Com custo de infra de R$ 0,031 por Jornada em escala inicial, a margem bruta sobre infraestrutura fica entre ~90% e ~96%.
- **Ou mensalidade de plataforma por faixa:** por exemplo R$ 1.500/mês até 2 mil Jornadas (piloto), R$ 3.900/mês até 10 mil Jornadas, mais R$ 0,25 por Jornada excedente. Com 10 mil Jornadas o custo de infra é ≈ R$ 310/mês (extrapolação linear do cenário C), ou seja, ~92% de margem sobre infra.
- **Argumento de retorno (ilustrativo, valor a confirmar com a 3corações):** se um contato humano custa R$ 10 (hipótese), basta evitar ~320 contatos por mês para cobrir a infra do cenário C (R$ 200). No cenário C, bastaria que 10% das 4.875 Jornadas resolvidas sem Chamado tivessem evitado um contato para gerar R$ 4.875 de economia contra R$ 200 de infra.
- Estes números **não incluem** equipe, suporte, impostos, taxa de cartão ou o custo do atendimento humano. Margem sobre infra não é margem do negócio.

---

## 7. Resumo para o Pitch

1. Operar o TRES Autoatendimento na AWS custa **≈ R$ 26/mês na demo**, **≈ R$ 31/mês no piloto (500 usuários)** e **≈ R$ 200/mês (≈ R$ 2,4 mil/ano) com 5.000 usuários ativos**.
2. Isso dá **≈ R$ 0,04 por usuário ativo/mês** e **≈ R$ 0,03 por atendimento (Jornada)** em escala inicial.
3. Sem acesso nenhum, o custo é de **≈ R$ 10/mês**: arquitetura serverless (Lambda, DynamoDB sob demanda, S3, CloudFront), sem servidores, sem NAT, sem banco ligado.
4. Multiplicar o uso por 10 multiplica o custo por ~9, sem redesenho: **R$ 1,7 mil/mês para 50.000 usuários**.
5. Cerca de 70% da conta é IA; o guia determinístico e o cache existem para mantê-la baixa. Com otimizações já mapeadas, o cenário de 5.000 usuários cai para **≈ R$ 59/mês**.
6. Cada contato humano evitado paga centenas de Jornadas de infraestrutura.
7. Valores são **estimativas** com preços de lista de 14/10/2026 (região São Paulo) e uso hipotético; o assistente de IA ainda não está implantado.

---

## 8. Premissas e limitações

### 8.1 Verificado no código (leitura direta)

- Inventário de recursos, tamanhos de memória, timeouts, modo de cobrança do DynamoDB, retenção de logs, throttling por rota, rota e frequência da varredura, ausência de VPC/NAT/WAF/alarmes/PITR/lifecycle de fotos, modelo e região padrão (`premissas.py`), intervalos de polling do front, fila do painel consultando a partição inteira do GSI.
- Estado do projeto: 16 tabelas, 4 GSIs, 37 rotas (contagem por busca textual nos arquivos); tarefas 17.3, 17.4, 18.x e outras abertas em `tasks.md`.

### 8.2 Verificado em fonte externa (14/10/2026)

- Preços de Lambda, API Gateway, DynamoDB, S3, S3 Vectors, KMS, Secrets Manager, CloudWatch, SQS, EventBridge, WAF, transferência de dados, Bedrock (Haiku 4.5, Haiku 5.5, Cohere Embed) e AgentCore: lista de preços oficial da AWS (arquivos JSON públicos, publicada em 14/10/2026 16:50 UTC).
- Disponibilidade do AgentCore Runtime V2: anúncio oficial da AWS. Câmbio: PTAX do Banco Central.

### 8.3 Inferido (hipótese minha; precisa de medição)

- Todo o perfil de uso (jornadas, % IA, % Chamado, polling, chamadas por Jornada, WRU/RRU, duração de Lambda, tamanho de log).
- **Tokens por chamada**: os prompts ainda não existem. A conta de IA (71% do total) varia quase linearmente com isso: ±50% de tokens muda o cenário C em ≈ ±US$ 9.
- Memória e CPU do runtime do agente (1 vCPU, 1 GB) e duração das sessões.
- Requisições KMS e volume de logs.
- Que o Bedrock Knowledge Base não cobra por consulta além de vector store e embedding da consulta (a página oficial de preços do Bedrock não renderiza para leitura automática; confirmei só os SKUs de modelo e embedding).

### 8.4 Não foi possível verificar

- **Tarifas de CloudFront para a América do Sul:** a página oficial de preços não é legível por leitura automática. Usei US$ 0,11/GB e US$ 0,022 por 10 mil requisições HTTPS, de fontes secundárias (um artigo da AWS re:Post confirma "até US$ 0,12/GB" na região). Isso só pesa no cenário "sem free tier"; com a franquia permanente de 1 TB e 10 M req, o custo é zero até o cenário D.
- **Preço do AgentCore Runtime em sa-east-1:** não consta na lista oficial; proxy com us-east-1.
- Planos fixos do CloudFront (Free/Pro US$ 15/Business US$ 200/Premium US$ 1.000) existem, mas incluem WAF e Route 53 e não foram usados; "contas gratuitas não podem usar planos fixos" segundo a documentação.
- Se o `agentcore launch` habilita observabilidade por padrão; custo de domínio próprio (.com.br), certificado e Route 53 (fora do código); impostos e IOF sobre a fatura em reais; créditos AWS da conta do hackathon; Bedrock cotas/limites reais da conta; que a stack realmente implanta (nunca sintetizada nem implantada nesta análise).
- Preços de "regional inference" do Haiku 4.5 (US$ 1,10/5,50) só valem se o ID do perfil mudar de `global.` para o geográfico.

### 8.5 Escopo excluído

Equipe, suporte, suporte AWS (planos Business/Enterprise), CI/CD (GitHub Actions é gratuito para o volume do projeto), ambiente de desenvolvimento/teste separado, bootstrap do CDK (≈ centavos), domínio, impostos e a conta de atendimento humano. Um segundo ambiente (staging) dobraria o custo fixo de ~US$ 1,9.

---

## 9. Fontes (URLs)

Preços e dados da AWS (consultados em 14/10/2026; conteúdo parafraseado):

- Lista de preços oficial (índice, publicada 2026-10-14T16:50:30Z): https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/index.json
- Arquivos por serviço e região usados, no padrão `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<Oferta>/current/<região>/index.json`, com as ofertas: `AWSLambda`, `AmazonApiGateway`, `AmazonDynamoDB`, `AmazonS3`, `awskms`, `AWSSecretsManager`, `AmazonCloudWatch`, `AWSQueueService`, `AWSEvents`, `awswaf`, `AWSDataTransfer`, `AmazonBedrockFoundationModels`, `AmazonBedrockAgentCore` (regiões `sa-east-1` e `us-east-1`).
- Lambda: https://aws.amazon.com/lambda/pricing/
- API Gateway (inclui franquias e créditos de conta nova): https://aws.amazon.com/api-gateway/pricing/
- CloudFront: https://aws.amazon.com/cloudfront/pricing/
- CloudFront, planos fixos: https://docs.aws.amazon.com/PricingPlanManager/latest/UserGuide/plans.html
- CloudFront, franquia permanente de 1 TB e 10 M requisições: https://aws.amazon.com/developer/application-security-performance/articles/cost-optimization/
- Bedrock: https://aws.amazon.com/bedrock/pricing/
- AgentCore, preços: https://aws.amazon.com/bedrock/agentcore/pricing/
- AgentCore Runtime V2, disponibilidade e regiões (anúncio de setembro de 2026): https://aws.amazon.com/about-aws/whats-new/2026/09/new-agentcore-runtime-generally-available/
- AgentCore, regiões suportadas: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html
- Câmbio PTAX (Banco Central, API Olinda), cotação de 14/10/2026: https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoDolarPeriodo(dataInicial=@dataInicial,dataFinalCotacao=@dataFinalCotacao)?@dataInicial='10-07-2026'&@dataFinalCotacao='10-14-2026'&$format=json

Fontes secundárias (usadas só onde indicado):

- Tarifas do CloudFront para a América do Sul: https://blog.blazingcdn.com/en-us/understanding-cloudfront-request-and-data-transfer-costs e https://blog.blazingcdn.com/en-us/differences-between-cloudfront-origin-fetch-and-edge-fetch-costs; confirmação parcial em https://repost.aws/pt/articles/ARW8IO6PlQQsW9F33olXhG0w/understanding-cloudfront-flat-rate-pricing-plans-predictable-cdn-and-data-transfer-costs
- Cobrança do AgentCore Runtime V1 vs V2 (memória pelo pico vs uso real): https://www.logeshwaran.org/2026/09/what-is-bedrock-agentcore-plain-english.html
- Exemplo de conta do AgentCore por componente: https://builder.aws.com/content/3JpfQcT4rM40BW7AdJTPshIv5Ht/building-ai-agents-on-amazon-bedrock-agentcore-the-real-bill-component-by-component
- Haiku 4.5 como modelo legado: https://platform.claude.com/docs/en/models/haiku-4-5/overview

Arquivos do projeto citados: `infra/app.py`, `infra/stacks/{dados,armazenamento,api,borda,conhecimento}_stack.py`, `infra/lambdas/autorizador_origem/index.py`, `services/agente/premissas.py`, `services/agente/agente/{config,modelo,contratos}.py`, `services/api/repositorios/dynamodb/{chamados,_base}.py`, `packages/dominio/src/dominio/custo.py`, `apps/web/src/cs/{FilaCs.tsx,dashboard/useDashboard.ts}`, `scripts/deploy.sh`, `.kiro/specs/tres-autoatendimento/{requirements,design,tasks}.md`.

> Content was rephrased for compliance with licensing restrictions.
