# Implementation Plan: TRES Autoatendimento

## Overview

Plano de implementação do MVP do TRES Autoatendimento (hackathon de 2 dias, projeto greenfield). A linguagem de implementação já está definida no design: **Python 3.12** no backend (`dominio`, API Lambda, agente Strands no AgentCore), **CDK em Python** na infraestrutura e **React + Vite + TypeScript** no front-end.

A ordem segue a prioridade de dia 1 / dia 2 do `design.md` e busca ter um fluxo demonstrável o mais cedo possível:

1. Repositório Git com varredura de segredos e estrutura de pastas (Tarefa 1).
2. Pacote `dominio` puro, com as propriedades de correção do núcleo (Tarefas 2 a 7).
3. Infraestrutura, persistência e carga idempotente (Tarefas 8 a 10).
4. API, escalada e Painel_CS no backend (Tarefas 11 a 13).
5. Portal_TRES e Painel_CS no front-end (Tarefas 14 e 15).
6. **Checkpoint de demo sem IA** (Tarefa 16): QR → guia dos 13 problemas → "Não" → Chamado → Painel_CS. Esse é o plano B da demo.
7. Assistente_IA no AgentCore com Knowledge Base e pipeline na API (Tarefas 17 a 19).
8. Métricas, Seletor_Visual reduzido e fechamento (Tarefas 20 a 23).

Todo o escopo marcado como **[Depois]** no design fica de fora (veja as Notas).

## Tasks

- [x] 1. Repositório Git, estrutura de pastas e varredura de segredos
  - [x] 1.1 Inicializar o repositório Git e a estrutura de pastas do design
    - Executar `git init` e criar `apps/web`, `services/api`, `services/agente`, `packages/dominio`, `infra`, `seed`, `scripts`, `docs` (com `.gitkeep` onde estiverem vazias)
    - Criar `.gitignore` (inclui `.env`, `.env.*`, `cdk.out`, `node_modules`, `.venv`, `__pycache__`, `.hypothesis`) e `.env.example` apenas com nomes de variáveis, sem valores
    - _Requirements: 20.5_
  - [x] 1.2 Configurar varredura de segredos e CI
    - Criar `.gitleaks.toml`, `.pre-commit-config.yaml` (gitleaks em pré-commit) e `.github/workflows/ci.yml` com os jobs: varredura de segredos, testes do `dominio` (pytest + Hypothesis com 200 exemplos), testes da API, lint e testes do front-end
    - Falha do job de segredos deve bloquear o merge
    - _Requirements: 20.5_
  - [x] 1.3 Configurar o ferramental Python dos pacotes
    - Criar `pyproject.toml` de `packages/dominio`, `services/api`, `services/agente` e `infra`, com dependências em versões fixas (pytest, hypothesis, jsonschema, boto3, moto, ruff, aws-cdk-lib, strands-agents)
    - Configurar pytest com `max_examples=100` por padrão e perfil `ci` com 200
    - Garantir que `dominio` não importe `boto3` nem use rede (regra de pureza verificada por teste de importação)
    - _Requirements: 20.5_
  - [x] 1.4 Criar o esqueleto do front-end
    - Criar projeto Vite + React + TypeScript em `apps/web`, com `react-router`, Vitest, Testing Library e `jest-axe`
    - Configurar divisão de código por rota e meta viewport mobile-first
    - _Requirements: 19.1, 19.2_

- [x] 2. Domínio: cache, mascaramento de PII e detecção de risco
  - [x] 2.1 Criar os tipos de domínio
    - Em `packages/dominio`, definir `Prioridade`, `Classificacao`, `Camada`, `Nivel`, `Gatilho`, `FatosJornada`, `DecisaoEscalada`, `JornadaEncerrada`, `EntradaCache`, `ResultadoInsercao` e as exceções (`ErroMascaramento`)
    - Todas as estruturas imutáveis, sem I/O e sem relógio global
    - _Requirements: 9.7, 10.1, 11.1, 11.2, 11.3_
  - [x] 2.2 Implementar o Cache_Respostas puro
    - Implementar `normalizar_pergunta` (minúsculas, sem acentos, sem pontuação, espaços únicos, sem espaços nas pontas), `chave_cache` (`modelo_id#sha256`) e `aceitar_insercao_cache` (exige aprovador, rejeita duplicata mantendo a entrada existente)
    - _Requirements: 7.1, 7.2, 7.6, 7.7, 16.3, 16.8_
  - [x] 2.3 Escrever o teste de propriedade da normalização do cache
    - **Property 14: Normalização da pergunta é idempotente e unifica variações**
    - **Validates: Requirements 7.1, 7.2**
  - [x] 2.4 Escrever o teste de propriedade do cache de respostas aprovadas
    - **Property 15: O cache só guarda respostas aprovadas e nunca altera entradas existentes**
    - **Validates: Requirements 7.6, 7.7, 16.3, 16.8**
  - [x] 2.5 Implementar o mascaramento de PII
    - Implementar `mascarar_pii` para telefone (com e sem +55, parênteses, hífen, espaços), CPF (com e sem pontos), e-mail e CEP, trocando por marcadores do tipo correspondente
    - Levantar `ErroMascaramento` em falha interna
    - _Requirements: 18.3, 18.8_
  - [x] 2.6 Escrever o teste de propriedade do mascaramento de PII
    - **Property 16: Mascaramento remove toda PII**
    - **Validates: Requirements 18.3**
  - [x] 2.7 Implementar o Detector_Risco e o detector de pedido humano
    - Implementar `detectar_risco` (termo inteiro ou expressão, sem diferenciar caixa e acento, a negação não desativa a detecção) e `pede_atendimento_humano`
    - Listas iniciais de termos em constantes sobrescritíveis pela tabela `config` (a lista final depende de validação da 3corações, Q11)
    - _Requirements: 8.1, 9.3_
  - [x] 2.8 Escrever o teste de propriedade do Detector_Risco
    - **Property 3: Detector_Risco encontra qualquer termo de risco, com qualquer caixa, acento ou negação**
    - **Validates: Requirements 8.1**

- [x] 3. Domínio: Motor_Escalada
  - [x] 3.1 Implementar o Motor_Escalada
    - Implementar `decidir_escalada` (tabela de decisão P1/P2/P3 com critério 1/2/3), `reavaliar_prioridade` (nunca reduz), `pode_chamar_modelo` (limite de 10), `proximo_estado_frustracao` e a contagem de "Não" do assistente (a segunda dispara; "Não" do guia não conta)
    - Resultado depende só de `risco_seguranca` e `guia_respondeu_nao`
    - _Requirements: 6.10, 7.4, 7.5, 9.1, 9.2, 9.5, 9.7, 9.9, 11.1, 11.2, 11.3, 11.5, 11.6_
  - [x] 3.2 Escrever o teste de propriedade da invariância da decisão
    - **Property 1: Decisão do Motor_Escalada é determinística e invariante a fatores irrelevantes**
    - **Validates: Requirements 11.5**
  - [x] 3.3 Escrever o teste de propriedade da tabela de decisão
    - **Property 2: Tabela de decisão e precedência P1 > P2 > P3**
    - **Validates: Requirements 11.1, 11.2, 11.3, 11.6, 5.3**
  - [x] 3.4 Escrever o teste de propriedade dos gatilhos por contagem
    - **Property 6: Gatilhos baseados em contagem disparam exatamente no ponto correto**
    - **Validates: Requirements 6.10, 9.2, 9.5**

- [ ] 4. Domínio: Pacote_Repasse
  - [x] 4.1 Implementar o esquema e as funções do Pacote_Repasse
    - Criar o JSON Schema versão 1 do design em `packages/dominio/.../schemas/pacote_repasse_v1.json`
    - Implementar `validar_pacote` (usa `jsonschema`, devolve todos os `{campo, motivo}`), `pacote_para_json` (UTF-8, `ensure_ascii=False`), `pacote_de_json`, `pacote_fallback` e a montagem do Pacote a partir dos campos determinísticos mais a saída do assistente (fallback se erro, tempo esgotado, resumo vazio ou maior que 300)
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.9_
  - [x] 4.2 Escrever o teste de propriedade de ida e volta do Pacote
    - **Property 8: Ida e volta do Pacote_Repasse**
    - **Validates: Requirements 10.1, 10.5, 10.6, 10.9**
  - [x] 4.3 Escrever o teste de propriedade da rejeição fora do esquema
    - **Property 9: Pacote fora do esquema é rejeitado com a lista dos campos inválidos**
    - **Validates: Requirements 10.7**
  - [x] 4.4 Escrever o teste de propriedade do fallback do Pacote
    - **Property 10: Pacote com falha do assistente continua válido**
    - **Validates: Requirements 10.2, 10.4**

- [x] 5. Domínio: validadores, QR, guia, seletor e fila
  - [x] 5.1 Implementar os validadores de entrada
    - `validar_telefone`, `validar_cep`, `validar_foto` (JPEG/PNG, até 5 MB, máximo de 3), `validar_mensagem_consumidor` (1 a 1000, não só espaços), `dados_pessoais_solicitados` (P1: telefone; P2: telefone e CEP; P3: nenhum, menos o já informado), nota e comentário (1 a 5, até 500), mensagem do Atendente (1 a 2000), agendamento (futuro, até 30 dias, fuso de Brasília), encerramento (Desfecho e solução de 1 a 500) e limites de pergunta e resposta do cache (1 a 300 e 1 a 1000)
    - _Requirements: 5.2, 5.5, 6.11, 12.2, 12.3, 12.4, 12.6, 12.7, 12.10, 15.3, 15.6, 15.8, 15.9, 16.1, 16.2, 16.6_
  - [x] 5.2 Implementar `interpretar_qr`
    - Extrair o `modelo_id` somente se casar com o padrão e a série somente se tiver de 1 a 30 caracteres alfanuméricos; série inválida é descartada; URL ilegível devolve "não legível"; nunca lança exceção
    - _Requirements: 1.2, 1.4, 1.5, 1.6_
  - [x] 5.3 Implementar o Guia_Diagnostico e o Seletor_Visual puros
    - `resolver_instrucao` (determinístico, variantes `padrao` e `externo`), `validar_instrucao` (1 a 10 passos, 140 caracteres por passo, `alt` até 125, texto equivalente, título até 40), `resolver_seletor` (`unico`, `multiplos` até 5, `nenhum`) e validador do mapa (áreas sem sobreposição, 2 a 5 estados por área)
    - _Requirements: 3.1, 3.3, 3.4, 3.6, 3.7, 3.10, 3.11, 4.1, 4.3, 4.4, 4.6, 19.5_
  - [x] 5.4 Implementar `ordenar_fila`
    - Ordenar por prioridade, horário de criação e número do Chamado, com a mesma regra da chave `fila_sk` do índice
    - _Requirements: 14.1_
  - [x] 5.5 Escrever o teste de propriedade de telefone e CEP
    - **Property 21: Validação de telefone e CEP**
    - **Validates: Requirements 12.6**
  - [x] 5.6 Escrever o teste de propriedade dos dados pessoais solicitados
    - **Property 23: Dados pessoais solicitados dependem só da prioridade e do que falta**
    - **Validates: Requirements 12.2, 12.3, 12.4**
  - [x] 5.7 Escrever o teste de propriedade da mensagem do Consumidor
    - **Property 24: Validação da mensagem do Consumidor**
    - **Validates: Requirements 6.11**
  - [x] 5.8 Escrever o teste de propriedade da URL do QR
    - **Property 25: Interpretação da URL do QR**
    - **Validates: Requirements 1.2, 1.5, 1.6**
  - [x] 5.9 Escrever o teste de propriedade do determinismo do guia
    - **Property 19: O guia é determinístico**
    - **Validates: Requirements 3.6**
  - [x] 5.10 Escrever o teste de propriedade do validador de instruções
    - **Property 20: Validador de instruções do seed**
    - **Validates: Requirements 3.1, 3.3, 3.4, 19.5**
  - [x] 5.11 Escrever o teste de propriedade da ordenação da fila
    - **Property 26: Ordenação da fila**
    - **Validates: Requirements 14.1**

- [ ] 6. Domínio: custo, recuperação, encerramento e métricas
  - [x] 6.1 Implementar o custo da chamada e a avaliação da recuperação
    - `custo_chamada_brl` (Decimal, 4 casas, tokens zero = 0,0000) e `avaliar_recuperacao` (`sem_embasamento` se a lista é vazia ou a maior pontuação é menor que o limiar; só trechos do modelo da Jornada; fontes vindas dos metadados dos trechos)
    - _Requirements: 6.2, 6.3, 6.4, 7.2, 7.3_
  - [x] 6.2 Implementar as regras de encerramento e abandono da Jornada
    - `aplicar_encerramento` (no máximo uma camada, permanente) e `marcar_abandono` (30 minutos sem interação e sem Chamado; abandono é terminal)
    - _Requirements: 17.1, 17.2_
  - [x] 6.3 Implementar `agregar_metricas`
    - Deflexão por camada, precisão da escalada, tempo médio (formato min:seg, sem abandonadas), custo médio por camada (guia 0, ia = soma de tokens, humano = minutos × custo por minuto), taxa de acerto do cache, ranking dos 10 mais acessados com desempate alfabético, nota média e quantidade por camada
    - Denominador zero devolve "sem dados"; período máximo de 90 dias; só agregados
    - _Requirements: 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.9, 17.10, 17.11, 18.4_
  - [x] 6.4 Escrever o teste de propriedade do invariante de métricas
    - **Property 12: A soma das camadas é igual ao total de Jornadas encerradas no período**
    - **Validates: Requirements 17.9, 17.11**
  - [x] 6.5 Escrever o teste de propriedade das fórmulas dos indicadores
    - **Property 13: Fórmulas dos indicadores**
    - **Validates: Requirements 17.3, 17.4, 17.5, 17.6, 17.7, 17.8**
  - [x] 6.6 Escrever o teste de propriedade do custo da chamada
    - **Property 17: Custo da chamada ao modelo**
    - **Validates: Requirements 7.2, 7.3**
  - [x] 6.7 Escrever o teste de propriedade do limiar de relevância
    - **Property 18: Limiar de relevância e fontes da resposta**
    - **Validates: Requirements 6.2, 6.3, 6.4**
  - [x] 6.8 Escrever o teste de propriedade da camada única de resolução
    - **Property 11: Cada Jornada tem no máximo uma camada de resolução, e ela é permanente**
    - **Validates: Requirements 17.1, 17.2**

- [ ] 7. Checkpoint - Domínio completo
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Infraestrutura (CDK em Python)
  - [x] 8.1 Criar o app CDK, a chave KMS e as tabelas DynamoDB
    - Em `infra`, criar o app CDK e a stack de dados com chave KMS do cliente e todas as tabelas do design em modo sob demanda: `modelos`, `problemas`, `instrucoes`, `jornadas` (com `gsi_ativas` e `gsi_encerradas` esparsos), `eventos`, `chamados` (com `gsi_fila` esparso), `mensagens_chamado`, `dados_pessoais`, `acessos_pii`, `ordens_servico`, `cache_respostas`, `avaliacoes`, `agregados_dia`, `usuarios_cs`, `sessoes_cs` (com TTL) e `config`
    - _Requirements: 18.2, 20.1, 14.1, 17.1_
  - [x] 8.2 Criar buckets, fila e parâmetros
    - Buckets S3 com SSE-KMS para o site estático, fotos e manuais; SQS de encerramentos com DLQ (3 tentativas, visibilidade de cerca de 10 s); parâmetros no SSM/Secrets Manager para segredos e configuração; nada de segredo no código
    - _Requirements: 18.2, 12.7, 17.12, 20.1, 20.5_
  - [x] 8.3 Criar as Lambdas, a API HTTP e a distribuição CloudFront
    - Definir as Lambdas `api`, `enriquecimento`, `encerramento` e `varredura de abandono` (EventBridge Scheduler a cada 5 min), o API Gateway HTTP API com throttling por rota, e o CloudFront com origem do site e `/api/*` na mesma origem, redirecionamento HTTP→HTTPS, HSTS e política de cabeçalhos de segurança (CSP, `X-Content-Type-Options`, `Referrer-Policy`)
    - Papéis IAM com privilégio mínimo; acesso à tabela `dados_pessoais` restrito ao papel do endpoint de dados pessoais; API Gateway acessível só pelo CloudFront
    - _Requirements: 18.2, 18.6, 18.7, 17.12, 20.1, 20.5_
  - [x] 8.4 Escrever os testes de asserção do CDK
    - Verificar KMS em tabelas e buckets, redirecionamento HTTPS, existência da DLQ e papéis IAM mínimos
    - _Requirements: 18.2, 18.7, 20.1, 20.5_

- [x] 9. Camada de persistência e encerramento de Jornada
  - [x] 9.1 Definir as interfaces de repositório e os fakes em memória
    - Em `services/api`, criar as interfaces (Jornadas, Eventos, Chamados, Mensagens, DadosPessoais, AcessosPII, OrdensServico, Cache, Avaliações, Agregados, UsuáriosCS, Sessões, Config) e implementações em memória com as mesmas garantias condicionais
    - _Requirements: 9.9, 14.6, 5.5, 17.1, 16.8, 11.8, 7.4_
  - [x] 9.2 Implementar os adaptadores DynamoDB
    - `TransactWriteItems` do Chamado com a atualização condicional da Jornada, assumir Chamado condicional, avaliação única, encerramento condicional (`estado <> encerrada`), Put condicional do cache, Ordem_Servico com chave `OS#<numero>`, contador do limite de mensagens com condição, idempotência por `evento_id`, e timeouts curtos de cliente para respeitar o limite de 10 s de gravação
    - _Requirements: 9.9, 14.6, 5.5, 17.1, 16.8, 11.8, 7.4, 3.12, 20.1, 20.6_
  - [x] 9.3 Escrever os testes de contrato dos repositórios
    - Mesmos testes contra o fake em memória e contra `moto`/DynamoDB Local, cobrindo as condições de escrita
    - _Requirements: 9.9, 14.6, 5.5, 17.1, 16.8, 20.1_
  - [x] 9.4 Implementar o serviço de encerramento de Jornada
    - Porta `encerrar_jornada` que enfileira o evento no SQS (sem bloquear o fluxo do Consumidor) e Lambda consumidora que grava `encerramento` na Jornada com `aplicar_encerramento`, até 3 tentativas e depois DLQ, com sinalização de falha para o Painel_Metricas
    - _Requirements: 5.2, 6.7, 16.4, 17.1, 17.12_

- [x] 10. Seed e carga idempotente
  - [x] 10.1 Criar os dados de seed
    - Em `seed/`: catálogo com 2 a 3 modelos, os 13 Problemas_Catalogados na ordem do Req 3.1, instruções com passos para o modelo da demo (textos de exemplo editáveis) e mapa do Seletor_Visual do modelo da demo
    - Dependência externa: instruções reais e manuais oficiais de ao menos 1 modelo devem ser fornecidos pela 3corações (Q20); o seed usa conteúdo de exemplo até lá
    - _Requirements: 3.1, 3.3, 3.4, 4.1, 20.3_
  - [x] 10.2 Implementar o script de carga
    - Em `scripts/`, validar tudo em memória primeiro (limites de texto, 13 problemas, mapa sem sobreposição, manuais presentes), depois gravar cada grupo em `TransactWriteItems`, enviar manuais ao S3 e remover os enviados naquela execução se falhar
    - Chaves determinísticas para que duas execuções deem o mesmo conjunto; em falha, indicar item e motivo e não deixar registros parciais
    - _Requirements: 20.3, 20.7, 3.3, 3.4_
  - [x] 10.3 Escrever os testes da carga
    - Idempotência (duas execuções, mesmo conjunto), falha injetada por grupo sem registros parciais e mensagem de erro com item e motivo
    - _Requirements: 20.3, 20.7_
  - [x] 10.4 Criar o gerador de QR codes da demo
    - Script em `scripts/` que gera QR codes com a URL `/m/{modelo_id}?s={serie}` para os modelos do seed
    - _Requirements: 1.1, 1.2_

- [ ] 11. API: núcleo e rotas públicas do guia
  - [x] 11.1 Criar o esqueleto da Lambda `api`
    - Roteador que descobre módulos em `routes/` (cada módulo expõe sua lista de rotas), envelope de erro padronizado, validação, idempotência por `Idempotency-Key`/`evento_id`, logs estruturados sem PII, carregamento de config e segredos (SSM/Secrets Manager e tabela `config`) e raiz de composição com os repositórios
    - _Requirements: 20.5, 20.6, 18.7_
  - [x] 11.2 Implementar as rotas de catálogo e Jornada
    - `GET /modelos`, `GET /modelos/{modelo_id}` (modelo, 13 problemas, mapa do seletor, timeout de 5 s), `POST /jornadas` (origem qr/busca, série inválida descartada, modelo inexistente cria Jornada sem modelo) e `PUT /jornadas/{id}/modelo` (origem vira busca)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.4_
  - [x] 11.3 Implementar as rotas de instrução e eventos do guia
    - `GET /jornadas/{id}/instrucao` (determinístico, 404 funcional sem instrução) e `POST /jornadas/{id}/eventos` (idempotente; registra problema, passo, tipo e horário; incrementa `problema_sel#id` no agregado diário só na primeira seleção da Jornada)
    - _Requirements: 3.3, 3.5, 3.6, 3.9, 3.10, 3.11, 3.12, 17.8_
  - [ ] 11.4 Escrever os testes das rotas do guia
    - Cobrir QR válido, modelo inexistente, série inválida, instrução inexistente e evento repetido
    - _Requirements: 1.2, 1.4, 1.5, 3.10, 3.12_

- [ ] 12. API: escalada, Chamado e repasse
  - [x] 12.1 Implementar o serviço de escalada e marcação de risco
    - `marcar_risco` (origens lista/ia/guia, monotônico, uma escalada P1 por Jornada) e `escalar(jornada_id, gatilho)`: consolidar fatos, registrar o gatilho (se falhar, escalar mesmo assim e marcar "não registrado"), decidir, `TransactWrite` do Chamado e da Jornada, número não sequencial `TRES-` + 10 caracteres, Pacote determinístico com valores provisórios de IA, Ordem_Servico rascunho em P2 e reavaliação sem criar novo Chamado
    - _Requirements: 8.1, 8.2, 8.4, 8.5, 8.7, 9.1, 9.7, 9.8, 9.9, 9.10, 10.2, 11.1, 11.2, 11.3, 11.4, 11.6, 11.7, 11.8_
  - [ ] 12.2 Implementar o enriquecimento do Pacote e a porta do agente
    - Definir a porta `AgenteClient` (modos `responder`, `resumo_repasse`, `sugestao_atendente`) com um fake, e a Lambda assíncrona que pede resumo, sentimento e próxima ação em até 10 s, aplicando o fallback do Req 10.4 em erro, tempo esgotado ou resumo inválido; Pacote disponível ao Painel em até 15 s
    - _Requirements: 10.3, 10.4, 10.8, 20.4_
  - [x] 12.3 Implementar as rotas de resolução, vazamento e escalada
    - `POST /jornadas/{id}/resolucao` ("Sim" marca resolvida na camada guia e encerra; "Não" escala como P2 sem passar pelo assistente), `POST /jornadas/{id}/vazamento` (externo devolve variante; interno marca risco `guia` e escala), `POST /jornadas/{id}/escalar` e `POST /jornadas/{id}/avaliacao` (1 por Jornada, até 500 caracteres)
    - _Requirements: 3.7, 3.8, 5.1, 5.2, 5.3, 5.5, 5.6, 5.7, 8.7, 9.3, 9.8_
  - [x] 12.4 Implementar as rotas do Chamado para o Consumidor
    - `POST /chamados/{numero}/contato` (telefone/CEP conforme prioridade, consentimento obrigatório, finalidade, dados já informados não pedidos de novo), anexos por URL pré-assinada (JPEG/PNG, 5 MB, até 3, rejeita só a foto inválida), `GET /chamados/{numero}` (status, mensagens, agendamento, sem Dados_Pessoais, 404 sem dados) e `POST /chamados/{numero}/mensagens` (1 a 2000, sinaliza resposta não lida)
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10, 12.11, 15.4, 15.5, 18.1_
  - [ ] 12.5 Escrever o teste de propriedade da escalada idempotente
    - **Property 5: Escalada é idempotente, o risco é permanente e a prioridade nunca diminui**
    - **Validates: Requirements 8.4, 8.5, 9.9**
  - [ ] 12.6 Escrever os testes de unidade da escalada e do Chamado
    - Falha injetada no registro do gatilho, na Ordem_Servico e no enriquecimento; rótulos de prioridade em linguagem simples e prazos (P1, P2, P3) sem siglas
    - _Requirements: 9.10, 11.8, 12.1, 10.4_

- [ ] 13. API: autenticação e rotas do Painel_CS
  - [x] 13.1 Implementar a autenticação do Painel_CS
    - Hash Argon2id ou scrypt (confirmar disponibilidade no runtime, Q14), login com mensagem única de erro e tempo equalizado, bloqueio por 5 falhas em 15 min (15 min), sessão opaca com hash SHA-256 e expiração deslizante de 30 min, cookie `HttpOnly; Secure; SameSite=Strict`, cabeçalho `X-Requested-With` nas mutações, middleware 401/403 e script para criar usuários iniciais lendo a senha de variável de ambiente
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 20.5_
  - [x] 13.2 Implementar fila, card, assumir, dados pessoais e anexos
    - `GET /fila` (índice esparso, alerta P1 até alguém abrir), `GET /chamados/{n}` (resumo no topo, histórico cronológico), `POST .../assumir` (condicional, 409 com nome do responsável), `GET .../dados-pessoais` (grava o acesso **antes** de responder; falha do log devolve 403 sem dados) e URL pré-assinada curta para anexos
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 18.6, 18.9_
  - [x] 13.3 Implementar sugestão, mensagens, Ordem_Servico e agendamento
    - `GET .../sugestao` (timeout de 10 s, falha devolve campo vazio), `POST .../mensagens` (só com confirmação explícita, 1 a 2000), `POST .../ordem-servico` (idempotente), `POST .../agendamento` (futuro, até 30 dias, fuso de Brasília) e ação "Enviar instrução do manual"
    - _Requirements: 11.4, 11.8, 15.1, 15.2, 15.3, 15.4, 15.6, 15.7, 15.8, 15.9_
  - [x] 13.4 Implementar encerramento e Cache_Respostas pelo CS
    - `POST .../encerrar` (exige Desfecho e solução; marca camada humano via serviço de encerramento) e `POST /cache` (pergunta e resposta sem Dados_Pessoais, aprovador e data, aviso se já existir, falha não reabre o Chamado)
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6, 16.7, 16.8_
  - [ ] 13.5 Escrever o teste de propriedade da matriz de autorização
    - **Property 27: Matriz de autorização perfil × rota**
    - **Validates: Requirements 13.2, 13.3, 13.4**
  - [ ] 13.6 Escrever os testes de unidade do Painel_CS
    - Mensagem de login igual para usuário inexistente e senha errada, bloqueio por tentativas, ordem do log de acesso antes da resposta, assumir Chamado já assumido
    - _Requirements: 13.7, 13.8, 14.6, 18.6, 18.9_

- [ ] 14. Portal_TRES (front-end do Consumidor)
  - [x] 14.1 Criar a base do Portal
    - Cliente da API com timeout, fila local de eventos com `evento_id` e reenvio (3 tentativas a cada 5 s, sem interromper o fluxo), `jornada_id` em `sessionStorage`, estilos de acessibilidade (fonte mínima de 16 px, contraste, foco visível, alvos de 44×44 px, `prefers-reduced-motion`), tela de erro "tentar novamente" em 10 s sem perder dados, e roteador com todas as rotas (`/`, `/m/:modeloId`, `/m/:modeloId/p/:problemaId`, `/chamado/:numero`, `/privacidade`, `/cs/*`) apontando para páginas provisórias
    - _Requirements: 3.12, 5.7, 19.1, 19.3, 19.4, 19.6, 19.7, 19.8, 19.9_
  - [x] 14.2 Implementar a página inicial e a busca
    - Campo de busca (50 caracteres), filtro local a partir de 2 caracteres sem acento e caixa, grade em ordem alfabética com foto, imagem substituta, mensagem de "não encontramos" mantendo o texto, e catálogo indisponível com campo desabilitado e nova tentativa
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_
  - [x] 14.3 Implementar a Pagina_Maquina
    - Abertura direta por QR sem tela intermediária, mensagens para modelo não reconhecido e código ilegível (levando à busca), indisponibilidade com nova tentativa, os 13 problemas na ordem com ícone e texto alternativo, e a opção "Meu problema não está na lista / Não sei qual é"
    - _Requirements: 1.1, 1.4, 1.6, 1.7, 3.1, 3.2, 19.2_
  - [x] 14.4 Implementar a tela de instrução
    - Passos numerados com mídia, texto alternativo e texto equivalente, mídia que não carrega em 5 s cai para o texto sem bloquear o avanço, imagem estática com movimento reduzido, pergunta externo/interno do vazamento, mensagem de instrução inexistente com opções, e "O problema foi solucionado?" com Sim/Não, avaliação de 1 a 5 e "Prefiro descrever ao assistente" após o repasse
    - _Requirements: 3.3, 3.4, 3.5, 3.7, 3.8, 3.10, 3.11, 5.1, 5.2, 5.3, 5.4, 5.6, 19.5, 19.7_
  - [x] 14.5 Implementar o alerta de risco
    - Bloco `role="alert"` no topo, visível em todas as telas até o fim da Jornada, com "Desligue a máquina da tomada e não a utilize", estado vindo do servidor e não removível pelo cliente, aviso de contato não registrado e "Tentar novamente"
    - _Requirements: 8.3, 8.6_
  - [x] 14.6 Implementar confirmação do Chamado, contato, fotos e privacidade
    - Número do Chamado, prioridade em linguagem simples (sem P1/P2/P3) e prazo; formulário só com o dado que falta, finalidade, consentimento desmarcado, link do aviso de privacidade visível, validação de telefone e CEP, anexos de até 3 fotos, e aviso de que o prazo não é garantido sem o dado; página `/privacidade`
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.9, 12.10, 18.1, 18.5_
  - [x] 14.7 Implementar o acompanhamento do Chamado
    - Consulta por número (erro sem dados se inexistente), polling a cada 5 s com a página visível, mensagens com data e hora, resposta do Consumidor, agendamento de ligação e avaliação de 1 a 5 ao encerrar
    - _Requirements: 12.8, 12.11, 15.4, 15.5, 15.6, 16.5_
  - [ ] 14.8 Escrever os testes de componente e acessibilidade
    - Vitest, Testing Library e `jest-axe` nas telas das tarefas 14.2 a 14.7, incluindo filtro da busca, fila de reenvio e foco por teclado
    - _Requirements: 2.2, 2.3, 3.12, 19.3, 19.4_

- [ ] 15. Painel_CS (front-end do Atendente)
  - [x] 15.1 Implementar login, guarda de rotas e layout do Painel
    - Tela de login, redirecionamento por 401 e expiração de sessão sem exibir dados, mensagem de bloqueio temporário, e ocultar o acesso ao Painel_Metricas para o perfil Atendente
    - _Requirements: 13.1, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8_
  - [x] 15.2 Implementar a fila de Chamados
    - Polling a cada 5 s, ordem do servidor, alerta visual P1 persistente até alguém abrir, responsável exibido, mensagem de fila vazia, erro com "Tentar novamente" mantendo a última fila
    - _Requirements: 14.1, 14.2, 14.5, 14.7, 14.8_
  - [x] 15.3 Implementar o card do Chamado
    - Topo com resumo, "já tentado", classificação, prioridade e canal; histórico cronológico com mensagens da IA e do Consumidor; fotos; botão "Ver contato" que mostra Dados_Pessoais só após o log; botão assumir com mensagem de conflito; indicador de resposta não lida
    - _Requirements: 14.3, 14.4, 14.5, 14.6, 14.8, 15.5, 18.6, 18.9_
  - [x] 15.4 Implementar ações, comunicação e encerramento
    - Ações "Abrir Ordem_Servico", "Enviar instrução do manual" e "Agendar ligação" com um clique, campo editável com a sugestão da IA (vazio se indisponível), envio só com confirmação, erros que preservam o texto, encerramento com Desfecho e solução, e "Adicionar ao Cache_Respostas" com campos editáveis
    - _Requirements: 11.8, 15.1, 15.2, 15.3, 15.7, 15.8, 15.9, 16.1, 16.2, 16.6, 16.7, 16.8_
  - [ ] 15.5 Escrever os testes de componente do Painel_CS
    - Guarda de rotas, ordem da fila, alerta P1 e preservação do texto em erro de envio
    - _Requirements: 13.1, 14.1, 14.2, 15.8_

- [ ] 16. Checkpoint - Demo sem IA (QR → guia → Chamado → Painel_CS)
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 17. Assistente_IA no Amazon Bedrock AgentCore e Knowledge Base
  - [x] 17.1 Verificar as premissas com a power `aws-agentcore`
    - Ativar a power `aws-agentcore` e consultar sua documentação e ferramentas para confirmar: S3 Vectors vs OpenSearch Serverless (Q1), semântica do score e nome da seção nos metadados (Q2), modelos de linguagem e embeddings na região (Q3), invocação do runtime a partir da Lambda, autenticação, partida a frio e limites (Q13), Argon2id no runtime Lambda (Q14) e limite de tempo do API Gateway (Q18)
    - Registrar os resultados em `services/agente/premissas.py` (constantes e decisões) e ajustar timeouts e escolhas de infra conforme o resultado
    - _Requirements: 6.4, 6.8, 6.12, 20.2_
  - [x] 17.2 Criar a Knowledge Base e a sincronização dos manuais
    - Stack CDK da Knowledge Base com o vector store escolhido, bucket de manuais com um prefixo por modelo e metadados (`modelo_id`, `manual`), script de sincronização e ingestão chamado pelo script de carga, com pré-processamento de seções se o chunking padrão não preservar o nome da seção
    - _Requirements: 6.2, 6.3, 20.2, 20.3_
  - [ ] 17.3 Implementar o agente Strands
    - Em `services/agente`, implementar os modos `responder` (recuperar com filtro `modelo_id`, aplicar `avaliar_recuperacao` em código, **uma** chamada ao modelo com saída JSON e `max_tokens` limitado, validar índices dos trechos, fontes vindas dos metadados, classificar sentimento e risco, oferecer o Problema_Catalogado correspondente), `resumo_repasse` e `sugestao_atendente`
    - O agente não tem ferramentas com efeito colateral nem acesso de escrita ao banco; empacotar o `dominio` junto ao runtime
    - _Requirements: 6.2, 6.3, 6.4, 6.5, 6.6, 7.3, 8.2, 9.4, 9.5, 10.3, 15.2, 20.2_
  - [ ] 17.4 Implementar o adaptador de invocação e o deploy do agente
    - Cliente real de `AgenteClient` na API (invocação do runtime, timeout de 25 s para `responder`, 10 s para resumo e sugestão), registro na raiz de composição, e configuração de deploy com `agentcore configure` e `agentcore launch`
    - _Requirements: 6.8, 6.12, 7.9, 20.2, 20.4_
  - [ ] 17.5 Escrever os testes de fumaça do agente
    - 1 a 3 invocações por modo, verificando o isolamento por `modelo_id` com 2 modelos e a medição do tempo de partida a frio contra o p90 de 10 s
    - _Requirements: 6.2, 6.8_
  - [ ] 17.6 Criar o conjunto dourado de avaliação offline
    - Arquivo JSONL com cerca de 20 perguntas (dentro e fora do manual, os 13 problemas em texto livre, risco de segurança, PII e injeção de prompt) e um executor que reporta os resultados
    - _Requirements: 6.2, 6.4, 6.5, 8.2, 18.3_

- [ ] 18. API: pipeline do Assistente_IA
  - [ ] 18.1 Implementar o pipeline de mensagens
    - `POST /jornadas/{id}/mensagens`: validar, mascarar PII (falha nada envia), detectar risco (marca e escala P1 antes do modelo), pedido humano, limite de 10 chamadas, consulta ao cache com timeout de 2 s (falha = miss), invocação do agente, registro de origem, tokens e custo, eventos em ordem cronológica, sem embasamento escala, indisponibilidade preserva histórico, e agregados `ia_cache`/`ia_modelo`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.8, 6.9, 6.11, 6.12, 7.1, 7.2, 7.3, 7.4, 7.5, 7.8, 7.9, 8.1, 8.2, 8.4, 9.3, 9.4, 18.3, 18.8, 20.4_
  - [ ] 18.2 Implementar as respostas "Isso resolveu?"
    - `POST /jornadas/{id}/solucoes/{sid}/resposta`: "Sim" encerra na camada ia, primeiro "Não" pede segunda solução ao agente, segundo "Não" escala por `duas_negativas_ia`, frustração alta duas vezes seguidas escala, e mensagem de encaminhamento ao Consumidor
    - _Requirements: 6.6, 6.7, 6.10, 9.2, 9.5, 9.8_
  - [ ] 18.3 Escrever o teste de propriedade do pipeline com risco
    - **Property 4: Mensagem de risco resulta em um Chamado P1 sem chegar ao modelo**
    - **Validates: Requirements 8.1, 8.5, 9.1, 11.1**
  - [ ] 18.4 Escrever o teste de propriedade do limite de chamadas ao modelo
    - **Property 7: Limite de chamadas ao modelo por Jornada**
    - **Validates: Requirements 7.4, 7.5**
  - [ ] 18.5 Escrever os testes de unidade de cada ramo do pipeline
    - Mensagem inválida, falha de PII, risco, pedido humano, limite, cache hit e miss, sem embasamento, solução e erro do agente, usando agente e cache falsos
    - _Requirements: 6.11, 7.8, 7.9, 18.8_

- [ ] 19. Portal_TRES: assistente com IA
  - [ ] 19.1 Implementar o painel do Assistente_IA
    - Chat na mesma página em até 2 s, validação de mensagem com aviso e texto preservado, fontes (manual e seção), "Isso resolveu?" Sim/Não até a escolha, botão "Falar com uma pessoa" sempre visível sem rolagem (44×44 px), aviso de falha após 30 s com "Tentar novamente", e botão e guia funcionando com a IA fora do ar em até 2 s
    - _Requirements: 6.1, 6.3, 6.5, 6.6, 6.11, 6.12, 9.6, 9.8, 20.4_
  - [ ] 19.2 Integrar o assistente aos fluxos do Portal
    - Abrir pela opção "Meu problema não está na lista", pela instrução inexistente e pelo "Prefiro descrever ao assistente" mantendo o mesmo `jornada_id`; "Sim" mostra a avaliação; escalada leva à confirmação do Chamado sem pedir de novo modelo ou passos
    - _Requirements: 3.2, 3.10, 5.4, 5.6, 6.7, 9.8_

- [ ] 20. Métricas (Servico_Metricas e Painel_Metricas)
  - [x] 20.1 Implementar a varredura de abandono
    - Lambda agendada a cada 5 min que consulta `gsi_ativas` e marca como abandonada, de forma condicional e terminal, as Jornadas sem Chamado e sem interação há 30 minutos, usando o serviço de encerramento
    - _Requirements: 17.1, 17.2_
  - [ ] 20.2 Implementar a API de métricas e configuração
    - `GET /metricas?periodo=` (apenas Gestor; hoje, 7 dias padrão, 30 dias, personalizado até 90) usando `agregar_metricas` sobre `gsi_encerradas`, Chamados, avaliações e agregados, com "sem dados" e erro único sem valores parciais; `PUT /config` (custo por minuto de 0,00 a 999,99, limiar, termos, preços do modelo e cotação)
    - _Requirements: 13.3, 13.4, 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.10, 17.11, 17.12, 17.13, 18.4_
  - [ ] 20.3 Implementar a tela do Painel_Metricas
    - Seleção de período, deflexão por camada, precisão da escalada, tempo médio, custo médio, acerto do cache, ranking dos 10, nota média e quantidade por camada, "sem dados", aviso de falha de registro ao Gestor, erro com "Tentar novamente", apenas valores agregados
    - _Requirements: 17.3, 17.4, 17.5, 17.6, 17.7, 17.8, 17.10, 17.11, 17.12, 17.13, 18.4_
  - [ ] 20.4 Escrever os testes de integração das métricas
    - Fluxo de encerramento pela fila, varredura de abandono e consulta de métricas com repositórios em memória
    - _Requirements: 17.1, 17.2, 17.9, 17.12_

- [ ] 21. Seletor_Visual (versão reduzida para o modelo da demo)
  - [x] 21.1 Implementar a rota do Seletor_Visual
    - `POST /jornadas/{id}/seletor/resolver`: usa `resolver_seletor`, registra área e estado na Jornada, devolve `unico`, `multiplos` (até 5) ou `nenhum` (encaminha ao assistente com área e estado preservados)
    - _Requirements: 4.2, 4.3, 4.4, 4.6_
  - [ ] 21.2 Implementar o componente do Seletor_Visual
    - Áreas como botões de 44×44 px com rótulo acessível e acionamento por teclado, destaque da área tocada, pergunta de estado em até 1 s, voltar sem registrar, e mensagem de indisponibilidade com acesso ao assistente se o modelo não tem mapa ou a imagem não carrega em 5 s
    - _Requirements: 4.1, 4.2, 4.5, 4.7, 4.8_

- [ ] 22. Deploy e verificação de ponta a ponta
  - [x] 22.1 Criar os scripts de deploy
    - Script em `scripts/` que roda `cdk deploy`, gera o build do front-end, sincroniza o site com o S3, invalida o CloudFront e executa a carga; segredos lidos do ambiente da AWS, nunca do repositório
    - _Requirements: 18.7, 20.1, 20.3, 20.5_
  - [ ] 22.2 Escrever o teste de integração do fluxo da demo no backend
    - Com fakes: QR → problema → "Não" → Chamado P2 → assumir → encerrar → métricas, e o ramo de risco P1
    - _Requirements: 1.1, 5.3, 8.5, 11.2, 14.5, 16.4, 17.3_
  - [ ] 22.3 Escrever o teste automatizado do caminho da demo no navegador
    - Playwright: QR → problema → "Não" → Chamado → Painel_CS (fila, assumir, responder, encerrar) → Painel_Metricas, em viewports de 360 a 1280 px
    - _Requirements: 19.1, 19.2, 14.2, 17.10_

- [ ] 23. Checkpoint final - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tarefas marcadas com `*` são opcionais e podem ser puladas para um MVP mais rápido.
- Os testes de propriedade do núcleo (Properties 1, 2, 3, 8, 12, 14 e 16) **não** são opcionais: cobrem Motor_Escalada, round-trip do Pacote_Repasse, invariante das métricas, normalização do cache, mascaramento de PII e detecção de risco.
- Cada propriedade fica em um arquivo próprio (`tests/test_prop_<n>_*.py`) e leva o comentário `# Feature: tres-autoatendimento, Property N: <título>`.
- Ficam **fora** deste plano, por estarem marcadas como [Depois] no design: Property 22 (fotos), 28 (sessão e bloqueio de login), 29 (Seletor_Visual), 30 (filtro da busca), 31 (carga) e 32 e 33 (validadores do Atendente e da avaliação). As funcionalidades correspondentes **são** implementadas nas tarefas 5.1, 8, 10, 13, 14 e 15, apenas sem esses testes de propriedade.
- Também ficam fora: WhatsApp, telefonia integrada, integração com sistemas legados, cache semântico, identificação por foto com IA, vídeo, notificações ativas, login do Consumidor, SSO/MFA, AgentCore Memory e Gateway, streaming, WAF, e auditoria WCAG formal (que exige testes manuais com tecnologias assistivas).
- A tarefa 21 (Seletor_Visual) é [MVP-simplificado] e cobre só o modelo da demo. Pode ser cortada sem afetar o restante.
- A tarefa 17.1 precisa da power `aws-agentcore` ativa. Se as ferramentas MCP da power não estiverem disponíveis, registre cada questão (Q1, Q2, Q3, Q13, Q14, Q18) como não verificada em `premissas.py` e use os valores conservadores do design.
- Dependência externa (Q20): as instruções reais dos 13 problemas, a mídia e os manuais oficiais de ao menos 1 modelo precisam ser fornecidos pela 3corações. O seed usa conteúdo de exemplo até lá.
- Preços do modelo e cotação ficam na tabela `config` e precisam ser preenchidos antes da demo; não estão no código.
- Plano B da demo: a Tarefa 16 entrega o fluxo completo sem IA. Se a camada de IA falhar, o guia, o botão "Falar com uma pessoa", a escalada e o Painel_CS continuam funcionando.
- Cada tarefa referencia requisitos específicos para rastreabilidade. Checkpoints garantem validação incremental.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4"] },
    { "id": 2, "tasks": ["2.1", "8.1", "10.1", "14.1", "17.1"] },
    { "id": 3, "tasks": ["2.2", "2.5", "2.7", "3.1", "4.1", "5.1", "5.2", "5.3", "5.4", "6.1", "6.2", "8.2"] },
    { "id": 4, "tasks": ["2.3", "2.4", "2.6", "2.8", "3.2", "3.3", "3.4", "4.2", "4.3", "4.4", "5.5", "5.6", "5.7", "5.8", "5.9", "5.10", "5.11", "6.3", "6.6", "6.7", "6.8", "8.3", "9.1", "10.2", "10.4", "14.2", "14.3"] },
    { "id": 5, "tasks": ["6.4", "6.5", "8.4", "9.2", "9.4", "10.3", "11.1", "14.4", "14.5"] },
    { "id": 6, "tasks": ["9.3", "11.2", "11.3", "12.1", "13.1", "14.6", "14.7", "17.2", "20.1"] },
    { "id": 7, "tasks": ["11.4", "12.2", "12.3", "12.4", "13.2", "13.4", "14.8", "15.1", "17.3", "20.2", "21.1"] },
    { "id": 8, "tasks": ["12.5", "12.6", "13.3", "15.2", "15.3", "17.4", "17.6", "20.3", "20.4"] },
    { "id": 9, "tasks": ["13.5", "13.6", "15.4", "17.5", "18.1"] },
    { "id": 10, "tasks": ["15.5", "18.2", "18.3", "18.4", "19.1"] },
    { "id": 11, "tasks": ["18.5", "19.2"] },
    { "id": 12, "tasks": ["21.2", "22.1", "22.2"] },
    { "id": 13, "tasks": ["22.3"] }
  ]
}
```
