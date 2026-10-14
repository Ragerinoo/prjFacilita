# Plano de Implementação: Insights do Gestor

## Visão geral

Implementação incremental em Python (API, `scripts/`) e TypeScript/React (front). A ordem segue as camadas da feature:

1. Serviço puro `services/api/servicos/insights.py` (`resolver_periodo`, projeções e `montar_insights`) e seus testes.
2. Rota `services/api/routes/cs_insights.py` (autorização por `Rota.perfis` + `exigir_perfil`, sem alterar a `MATRIZ`) e seus testes.
3. `scripts/semente_demo.py` e integração no `scripts/dev_local.py` (`com_semente`, `--sem-demo`, `--resetar`, Snapshot) e seus testes.
4. Front: instalar `recharts` e `react-is` com versão exata, tela `InsightsCs.tsx`, rota `lazy`, link "Insights" no `LayoutPainel` só para o Gestor e seus testes (`jest-axe`).
5. `docs/DEMO.md`.
6. Dashboard e navegação (Requisitos 19 a 26, decisões D9 a D15): `servicos/dashboard.py` e `routes/cs_dashboard.py` (perfis `gestor` e `atendente` por `Rota.perfis`), extração de `ConteudoInsights` e do hook `useBuscaInsights`, `Dashboard.tsx` com `cs/dashboard/` (Visão geral, abas WAI-ARIA, Lista em foco e atualização de 10 s sem piscar), rota índice `/cs` = Dashboard (em vez de `Navigate`; `/cs/insights` mantida), destino padrão do login `/cs`, menu com Dashboard, Fila de chamados, Métricas e Insights, acréscimos nos testes existentes `PainelCs.test.tsx` e `rotas.test.tsx`, testes novos (`jest-axe`), `isolamentoGraficos.test.ts`, `scripts/verificar-chunks.mjs` e a seção do Dashboard no `docs/DEMO.md`.
7. Verificação final, rodando só os testes relacionados.

Alinhamentos já feitos no `requirements.md`, conforme as divergências documentadas no design:

- Req 1.8 e 11.3: "500" virou "resposta 5xx com envelope de erro e sem nenhuma chave de indicador" (hoje 502 para `ErroRepositorio` e 500 para exceção inesperada).
- Req 1.4: a rota é exclusiva do Gestor por `Rota.perfis` + `exigir_perfil("gestor")`, sem alterar a `MATRIZ`.
- Req 16.1 e 16.14: a semente só é ligada pelo Ponto_De_Entrada_CLI, via `com_semente` (padrão `False`) em `main()` e `iniciar_estado()`.

Alinhamento adicional do `requirements.md` (Dashboard): o texto do Req 17.2 passou a apontar para a exceção dos Req 17.3 e 26.11, de modo que `PainelCs.test.tsx` e `rotas.test.tsx` só ganham expectativas novas (tarefas 14.11 e 14.12), sem remover nem enfraquecer as existentes.

Restrições de escopo: nenhuma tarefa toca `infra/` nem a AWS. Não há método novo nos Protocols de `repositorios/interfaces.py`, nem mudança no adaptador DynamoDB, no pacote `dominio`, em `/api/cs/metricas` ou nos testes existentes.

## Tarefas

- [x] 1. Serviço puro `servicos/insights.py`
  - [x] 1.1 Criar o módulo com constantes, erro e `resolver_periodo`
    - Criar `services/api/servicos/insights.py` com `FUSO_REFERENCIA = UTC`, `PERIODOS`, `PERIODO_PADRAO`, `MAX_DIAS_PERSONALIZADO`, `MAX_COMENTARIOS`, `MAX_CARACTERES_SOLUCAO` e `CHAVES_PRIMEIRO_NIVEL`
    - Definir `ErroPeriodoInsights(campo, motivo)` e `PeriodoInsights(id, inicio, fim)` com intervalo semiaberto `[inicio, fim)`
    - Implementar `resolver_periodo(agora, periodo, inicio, fim)`: `7d` (padrão) e `30d` terminam no próximo segundo inteiro depois de `agora`; `hoje` vai de 00:00 UTC ao 00:00 UTC do dia seguinte; `personalizado` exige `AAAA-MM-DD` (regex antes de `date.fromisoformat`), `fim >= inicio` e no máximo 90 dias inclusivos; `inicio`/`fim` são ignorados fora do personalizado
    - Erros apontam o campo (`periodo`, `inicio` ou `fim`); a função não lê o relógio
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 10.3_

  - [x] 1.2 Implementar as projeções `ChamadoInsights` e `JornadaInsights`
    - `ChamadoInsights` (dataclass `frozen`, `slots`) com só `prioridade`, `status`, `criado_em`, `assumido_em`, `encerrado_em`, `desfecho`, `solucao_tipo`, `solucao`, `problema_id` e `jornada_risco`, e o construtor `de(chamado, jornada)`; ficam de fora pacote, número do Chamado e `jornada_id`
    - `JornadaInsights` com `origem_inicial` e o `JornadaEncerrada` do domínio; `de(jornada)` devolve `None` se a Jornada não está encerrada
    - Não ler `dados_pessoais`, `mensagens` nem `acessos_pii`
    - _Requirements: 10.1, 10.2, 10.3_

  - [x] 1.3 Implementar auxiliares numéricos, satisfação e comentários
    - Auxiliar local de arredondamento com `Decimal` e `ROUND_HALF_UP` (1 casa) para a nota média geral e para os percentuais, sem acrescentar função pública ao `dominio`
    - Montar `satisfacao`: `nota_media`, `total`, `distribuicao` (sempre 5 linhas, zeros incluídos), `por_camada` só com `guia` e `humano`; `"sem dados"` (`SEM_DADOS`) quando `total` é 0
    - Montar `comentarios`: avaliações do período com texto não vazio, mais recentes primeiro (desempate por `jornada_id` decrescente), `mascarar_pii` em cada texto, comentário que falha no mascaramento é omitido, no máximo 10, cada item com só `nota`, `em` e `texto`
    - Fazer o filtro `inicio <= x < fim` dentro do serviço, preparar a chamada única de `agregar_metricas` (`ConfigMetricas(Decimal("0.00"), titulos)`, Jornadas sem a camada `ia`) e usar dela a nota por camada
    - _Requirements: 2.9, 2.10, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 9.3_

  - [x] 1.4 Implementar atendimento, desfecho e Chamados P1 de risco
    - `atendimento.ate_assumir` (Chamados_Encerrados do período com `assumido_em`) e `ate_encerrar` (todos os Chamados_Encerrados do período): média `(2 * soma + n) // (2 * n)`, mediana (ímpar: valor central; par: `(a + b + 1) // 2`), duração negativa vira 0, texto por `formatar_min_seg`, `quantidade` e `"sem dados"` quando `n` é 0
    - `desfecho`: sempre as 3 linhas (`falso_defeito`, `defeito_real`, `nao_informado`), valor não reconhecido conta como `nao_informado`, soma igual a `total`, e `precisao_escalada_pct` vindo de `agregar_metricas`
    - `p1_risco`: `total` de Chamados P1 com `jornada_risco` criados no período e `nao_encerrados` (status diferente de `encerrado`)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [x] 1.5 Implementar ranking, funil e `montar_insights`
    - `ranking_problemas`: ordem, título e `selecoes` vindos de `agregar_metricas` (sem reordenar, no máximo 10, `Problema <id>` quando falta o título); por item, `chamados`, `falso_defeito_pct` e `solucao_mais_registrada` (mascarar cada texto, agrupar por `(solucao_tipo, texto)`, desempate pelo menor texto e depois pelo menor tipo, cortar em 120 caracteres só depois de mascarar, `"sem dados"` sem Chamado_Encerrado)
    - `funil`: `total_encerradas`, `por_origem` (`qr`, `busca`), `abandono_pct` e `deflexao` (`guia`, `humano`, `abandonada`, sem `ia`) a partir de `agregar_metricas`; `None` quando `jornadas_encerradas` é `None`
    - `montar_insights(periodo, *, modo_local, chamados, avaliacoes, agregados, titulos, jornadas_encerradas)` junta tudo no dicionário fechado de 9 chaves, sem `ia_cache`, `ia_modelo`, `ia` nem custo, sem I/O e sem relógio
    - _Requirements: 1.6, 1.7, 2.8, 2.10, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.11, 8.1, 8.3, 8.5, 9.1, 9.4, 10.1, 10.3_

  - [ ]* 1.6 Escrever testes unitários do serviço
    - Em `services/api/tests/test_servico_insights.py` (novo): distribuição e média de um caso fixo, mediana par e ímpar, comentário que falha no mascaramento (`monkeypatch`), custo `0.00` no `ConfigMetricas`, ausência de campos de PII nas projeções (`dataclasses.fields`), `modo_local` repassado, `"sem dados"` e ausência de Indicadores_De_IA
    - _Requirements: 3.1, 3.4, 4.3, 5.4, 9.1, 9.3, 10.1, 18.1_

  - [ ]* 1.7 Escrever teste de propriedade da forma fechada da resposta
    - Em `services/api/tests/test_propriedade_insights.py` (novo), com Hypothesis e comentário `# Feature: insights-gestor, Property 1`
    - **Property 1: Forma fechada da resposta e ausência de Indicadores_De_IA**
    - **Validates: Requirements 1.6, 4.4, 7.3, 7.8, 9.1**

  - [ ]* 1.8 Escrever teste de propriedade de vazamento de dados
    - **Property 2: A resposta não vaza dados pessoais nem identificadores**
    - **Validates: Requirements 4.2, 4.5, 7.6, 10.1**

  - [ ]* 1.9 Escrever teste de propriedade da resolução do período
    - **Property 3: Resolução do período**
    - **Validates: Requirements 2.1, 2.2, 2.3, 2.4, 2.8**

  - [ ]* 1.10 Escrever teste de propriedade dos períodos inválidos
    - **Property 4: Períodos inválidos são rejeitados e a fronteira de 90 dias é exata**
    - **Validates: Requirements 2.5, 2.6, 2.7**

  - [ ]* 1.11 Escrever teste de propriedade da invariância à janela
    - **Property 5: Invariância à janela**
    - **Validates: Requirements 2.10**

  - [ ]* 1.12 Escrever teste de propriedade da satisfação
    - Referência exata com `fractions.Fraction`
    - **Property 6: Satisfação**
    - **Validates: Requirements 2.9, 3.1, 3.2, 3.3, 3.4, 3.5**

  - [ ]* 1.13 Escrever teste de propriedade da nota por camada
    - **Property 7: Nota por camada coerente com o domínio**
    - **Validates: Requirements 3.6**

  - [ ]* 1.14 Escrever teste de propriedade da amostra de comentários
    - **Property 8: Amostra de comentários**
    - **Validates: Requirements 4.1, 4.2, 4.6**

  - [ ]* 1.15 Escrever teste de propriedade dos tempos de atendimento
    - **Property 9: Tempos de atendimento**
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 5.5, 5.6**

  - [ ]* 1.16 Escrever teste de propriedade do desfecho
    - **Property 10: Desfecho e precisão da escalada**
    - **Validates: Requirements 6.2, 6.3, 6.4, 6.5, 6.6**

  - [ ]* 1.17 Escrever teste de propriedade dos Chamados P1 de risco
    - **Property 11: Chamados P1 de risco**
    - **Validates: Requirements 6.1**

  - [ ]* 1.18 Escrever teste de propriedade do ranking
    - **Property 12: Ordem e seleções do ranking**
    - **Validates: Requirements 7.1, 7.2, 7.9, 7.11**

  - [ ]* 1.19 Escrever teste de propriedade por problema
    - **Property 13: Chamados, falso defeito e solução mais registrada por problema**
    - **Validates: Requirements 7.4, 7.5, 7.6, 7.7**

  - [ ]* 1.20 Escrever teste de propriedade do funil
    - **Property 14: Funil**
    - **Validates: Requirements 8.1, 8.3, 8.5, 9.4**

  - [ ]* 1.21 Escrever teste de propriedade de pureza e determinismo
    - **Property 15: Pureza, determinismo e independência da ordem**
    - **Validates: Requirements 10.3**

- [x] 2. Rota `GET /api/cs/insights`
  - [x] 2.1 Implementar `services/api/routes/cs_insights.py`
    - `@exigir_perfil("gestor")` e `ROTAS = [Rota("GET", "/insights", insights, escopo="cs", nome="cs_insights", perfis=frozenset({"gestor"}))]`; não editar a `MATRIZ` de `servicos/autenticacao.py` (`Rota.perfis` tem precedência na decisão de acesso)
    - Resolver o período com `ctx.app.agora()`; `ErroPeriodoInsights` vira `ErroApi(400, VALIDACAO, "Período inválido.", [ErroCampo(campo, motivo)])`
    - Leituras obrigatórias sem captura de erro (`chamados.listar_todos()`, `jornadas.obter` só dos Chamados que interessam, `avaliacoes.listar_periodo`, `agregados.listar`), de modo que `ErroRepositorio` vire 5xx sem indicadores parciais
    - Leituras opcionais: `catalogo.listar_problemas()` (falha: títulos vazios e aviso `catalogo_indisponivel_insights`) e `jornadas.listar_encerradas` (falha: `funil=None` e aviso `funil_indisponivel_insights`)
    - `modo_local = (ctx.app.modo == MODO_LOCAL)`; docstring do módulo descreve o contrato, como `cs_metricas.py`; sem método novo nos Protocols
    - Rodar `test_autorizacao_cs.py` e `test_rotas_cs_metricas.py` para confirmar que continuam verdes sem alteração
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.7, 1.8, 2.5, 2.6, 2.7, 7.10, 8.2, 8.4, 11.1, 11.2, 11.3, 11.4, 17.1, 17.2_

  - [ ]* 2.2 Escrever testes de rota: autorização, período e resposta vazia
    - Em `services/api/tests/test_rotas_cs_insights.py` (novo), reusando `Cliente`/`montar_cliente` dos testes de `cs_metricas`/`cs_chamados`
    - Gestor 200 com as 9 chaves; Atendente 403 e sem sessão 401 com corpos iguais aos da `/metricas`; `decidir_acesso(True, "atendente", "GET", "/insights", ROTA.perfis)` dá `SEM_PERMISSAO` e o Gestor é permitido; `periodo` inválido 400; personalizado com 91 dias 400; personalizado válido 200; repositório vazio 200 com "sem dados"
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.5, 2.6, 2.7, 18.2_

  - [ ]* 2.3 Escrever testes de rota: falhas, degradação e modo local
    - No mesmo arquivo: `ErroRepositorio` em `listar_todos`, `listar_periodo` e `listar` (resposta 5xx com envelope de erro e sem nenhuma chave de indicador; fixar o par atual `ErroRepositorio` 502 e exceção genérica 500); `ErroIndisponivelForaDoModoLocal`; catálogo indisponível (200 e aviso); `listar_encerradas` falhando (200 e `funil: null`); `modo_local` `true` no app local e `false` com `modo="aws"` e repositórios em memória injetados; espiões confirmando o uso de `listar_todos`, `listar_periodo`, `listar` e `listar_encerradas` e de nenhum método novo; resposta em menos de 3 s
    - _Requirements: 1.7, 1.8, 1.9, 7.10, 8.2, 8.4, 11.1, 11.2, 11.3, 18.2_

- [x] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Semente de demonstração e integração no `dev_local.py`
  - [x] 4.1 Criar `scripts/semente_demo.py`
    - Bootstrap de `sys.path` como em `estado_demo.py`; constantes `SEMENTE_ALEATORIA = 20250607`, `PREFIXO_JORNADA = "01JSEMENTE"` e `PREFIXO_CHAMADO = "TRES-SEM"`; `ResumoSemente(jornadas, chamados, avaliacoes, contadores)`
    - `criar_semente(repos, *, agora, log)`: `agora` com fuso (`ValueError` se ingênuo), `random.Random(SEMENTE_ALEATORIA)`, instantes sempre `agora - deslocamento >= 0`, cadeias de tempo de trás para frente, registros "de hoje" limitados pelas horas desde 00:00 UTC, dia dos contadores por `FUSO_REFERENCIA`
    - Volumes do design: 57 Jornadas (26 `guia`, 8 `abandonada`, 16 `humano`, 4 abertas, 3 em atendimento), 23 Chamados, 27 avaliações, 4 Chamados P1 de risco, notas 1 a 5 e 8 ou mais comentários fixos em português sem dígitos nem e-mail, 6 problemas do catálogo com pesos 14, 10, 8, 6, 4 e 3, 7 `falso_defeito` e 9 `defeito_real`, textos de solução fixos sem dígitos
    - Criar registros só pelos métodos dos repositórios em memória (`jornadas.criar/encerrar/marcar_abandono`, `ServicoEscalada(...).escalar`, `chamados.assumir/encerrar`, `avaliacoes.registrar`, `agregados.incrementar`) para preservar os invariantes
    - Idempotência: se a primeira Jornada da semente já existe, devolver `ResumoSemente(0, 0, 0, 0)` sem criar nada; mensagem `[demo] Semente de dados FICTÍCIOS criada: ...` pelo `log`
    - Nenhum arquivo de `services/`, `packages/`, `apps/` ou `infra/` ganha código de semente
    - _Requirements: 16.5, 16.6, 16.7, 16.8, 16.9, 16.10, 16.11, 16.12, 16.13, 16.15, 16.16_

  - [x] 4.2 Integrar a semente no `scripts/dev_local.py`
    - `iniciar_estado(..., com_semente: bool = False, agora_semente: datetime | None = None, log=print)` e `main(argv=None, *, dir_dados=DIR_DADOS_DEMO, com_semente: bool = False)`; `popular()` não muda
    - Só no ramo sem Snapshot (`novo`/`resetado`), depois de `popular(...)` e antes de `persistencia.gravar(...)`: `if com_demo and com_semente: criar_semente(...)`; o ramo `carregado` nunca chama a semente
    - `main` passa `com_semente=com_semente and not args.sem_demo`; falha ao criar a semente registra `[demo] não foi possível criar a semente: <erro>` e segue
    - `if __name__ == "__main__": raise SystemExit(main(com_semente=True))`; ajustar o texto de ajuda de `--sem-demo` ("não cria Chamados de exemplo nem a semente de demonstração") e a linha da semente na saída de `main`
    - Rodar `scripts/tests/test_dev_local.py` e `scripts/tests/test_persistencia_reinicio.py` para confirmar que continuam verdes sem alteração (continuam com exatamente 3 Chamados e 3 Jornadas)
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.12, 16.14, 16.17, 17.2_

  - [ ]* 4.3 Escrever teste de propriedade dos mínimos e da variedade da semente
    - Em `scripts/tests/test_semente_demo.py` (novo), com `max_examples` menor (por exemplo 30), repositórios em memória e catálogo da demo
    - **Property 16: A semente cobre os mínimos e a variedade exigidos**
    - **Validates: Requirements 16.5, 16.6, 16.7, 16.8, 16.9**

  - [ ]* 4.4 Escrever teste de propriedade do determinismo da semente
    - **Property 17: A semente é determinística e relativa ao dia corrente**
    - **Validates: Requirements 16.10**

  - [ ]* 4.5 Escrever teste de propriedade da semente fictícia e dos invariantes
    - **Property 18: A semente é fictícia, distinta dos exemplos e respeita os invariantes dos repositórios**
    - **Validates: Requirements 16.11, 16.15, 16.16**

  - [ ]* 4.6 Escrever teste de propriedade da ida e volta do Snapshot com a semente
    - **Property 19: Ida e volta do Snapshot com a semente**
    - **Validates: Requirements 16.17**

  - [ ]* 4.7 Escrever testes por exemplo da integração da semente
    - Usar `tmp_path`/`dir_dados`, sem tocar o `.dados-demo/` do repositório
    - Primeira subida com semente e Snapshot inicial; `--resetar` recria a semente; segunda subida preserva os bytes do Snapshot; `com_semente=False` mantém exatamente 3 Chamados; `--sem-demo` sem semente e sem exemplos; mensagem do console por `log` injetado; varredura garantindo que nada em `services/`, `packages/`, `apps/` e `infra/` importa `semente_demo` nem contém `PREFIXO_JORNADA`
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.12, 16.13, 16.14, 18.3_

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Tela de Insights no front-end
  - [x] 6.1 Instalar a biblioteca de gráficos com versão exata
    - Em `apps/web`: `npm install --save-exact recharts@3.10.1 react-is@19.3.0`, atualizando `package.json` (sem `^` nem `~`) e `package-lock.json`
    - Confirmar que as suítes existentes continuam verdes (`npx vitest --run`), já que o `react-is` aninhado na 17 não pode quebrar o `@testing-library/dom`
    - _Requirements: 15.2, 15.3, 17.2_

  - [x] 6.2 Criar tipos e utilitários em `apps/web/src/cs/insights/`
    - `tipos.ts`: `RespostaInsights` e `SEM_DADOS = "sem dados"`
    - `formatar.ts`: `formatarDecimal("4.2") -> "4,2"`, `formatarPercentual`, `formatarData` (pt-BR, `timeZone: "UTC"`), `rotuloDesfecho` e `validarIntervalo` (data final não anterior à inicial, no máximo 90 dias inclusivos)
    - _Requirements: 13.3, 13.9, 13.11_

  - [x] 6.3 Criar os componentes sem gráfico
    - `SeletorPeriodo.tsx` (`<select>` com Hoje, 7 dias, 30 dias e Personalizado; campos `type="date"` e botão "Aplicar" no personalizado, com mensagem de erro ligada por `aria-describedby`), `Cartoes.tsx` (cards em `<dl>`), `Ranking.tsx`, `Comentarios.tsx` e `Funil.tsx`
    - Comentários como texto simples do React com `white-space: pre-wrap`, sem `dangerouslySetInnerHTML`; título de seção em `<h2>`; tabelas com `aria-labelledby` e `<th scope="col">`; "Não há dados para esta seção no período." nas seções vazias; "sem dados" nos valores `SEM_DADOS`; nenhum rótulo de IA
    - Usar classes com prefixo `insights-`, definidas em `insights.css` na tarefa 6.5
    - _Requirements: 4.7, 8.6, 8.7, 9.2, 13.3, 13.7, 13.9, 13.10, 13.11, 13.13, 14.4, 14.5_

  - [x] 6.4 Criar os gráficos com Recharts
    - `GraficoDistribuicao.tsx` e `GraficoDesfecho.tsx`: `<figure>` com `<figcaption>` e descrição curta por `aria-describedby`; SVG dentro de `<div aria-hidden="true">` com `accessibilityLayer={false}`; `isAnimationActive={false}`; valores também em `LabelList`; importações nomeadas
    - Tabela equivalente visível logo abaixo de cada gráfico, com os mesmos rótulos e números; a linha `nao_informado` fica oculta quando a quantidade é 0
    - Só estes componentes importam `recharts`
    - _Requirements: 13.8, 14.1, 14.2, 14.3, 15.1_

  - [x] 6.5 Criar `InsightsCs.tsx` e `insights.css`
    - `export function Component`; estado `carregando | erro | pronto`; `useEffect` com `AbortController` que volta a `carregando` a cada mudança de `consulta` ou `tentativa`, sem mostrar valores do período anterior; `apiCs.get("/insights?periodo=...")` iniciando em `7d`; o personalizado só altera `consulta` quando `validarIntervalo` passa
    - Ordem: aviso "Dados de demonstração" (se `modo_local`), seletor, cards, distribuição, falso defeito x defeito real, ranking (com nota sobre o ranking por dia de calendário e "datas em UTC"), comentários e funil (só se `funil !== null`)
    - `role="status"` ao carregar; erro com mensagem e botão "Tentar novamente"; `h1` em todas as fases
    - Esta tarefa entrega a tela completa; a tarefa 11.2 extrai depois o conteúdo para `ConteudoInsights` e deixa a `InsightsCs` como casca
    - Criar `apps/web/src/cs/insights.css` (grid dos cards, gráficos, tabelas, aviso), no padrão de `metricas.css`, sem depender só de cor
    - _Requirements: 8.6, 8.7, 9.2, 10.4, 13.1, 13.2, 13.4, 13.5, 13.6, 13.9, 13.12, 13.13, 14.4, 15.5_

  - [x] 6.6 Registrar a rota `lazy` e o link no menu
    - `apps/web/src/app/rotas.tsx`: uma linha nova dentro dos filhos de `GuardaGestor`: `{ path: "insights", lazy: () => import("../cs/InsightsCs") }`
    - `LayoutPainel.tsx`: `NavLink` "Insights" ao lado de "Métricas", só para o perfil `gestor`; `MetricasCs`, `GuardaGestor` e `clienteCs` não mudam
    - Rodar `PainelCs.test.tsx`, `MetricasCs.test.tsx` e `rotas.test.tsx` para confirmar que continuam verdes sem alteração
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 15.5, 17.1, 17.2, 17.3_

  - [ ]* 6.7 Escrever `apps/web/src/cs/insights/formatar.test.ts`
    - Exemplos de `validarIntervalo` nas fronteiras (90 e 91 dias, fim antes do início), `formatarDecimal`, `formatarPercentual` e `formatarData`
    - _Requirements: 13.3, 13.9_

  - [ ]* 6.8 Escrever `InsightsCs.test.tsx`: estados, cards, tabelas e axe
    - Em `apps/web/src/cs/InsightsCs.test.tsx` (novo), com `vi.stubGlobal` de um `ResizeObserver` vazio; verificar tabela e `figure`, nunca os `<rect>` do SVG
    - Carregando (`role="status"`), sucesso (cards, tabelas, `figure` com nome acessível), erro e "Tentar novamente" repetindo a chamada, seções sem dados, "sem dados" nos cards, ordem das seções, ausência de rótulos de IA e `jest-axe` nos estados carregando, erro e pronto
    - _Requirements: 13.1, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9, 13.10, 13.11, 13.13, 14.1, 14.3, 14.4, 14.6, 18.4_

  - [ ]* 6.9 Escrever `InsightsCs.test.tsx`: período, escape, aviso e teclado
    - No mesmo arquivo: troca de período (a URL traz `periodo=30d`), personalizado inválido (mensagem e nenhuma chamada), troca de período seguida de erro (valores antigos não aparecem), comentário com HTML escapado (nenhum `<img>` criado), aviso "Dados de demonstração" com `modo_local` verdadeiro e falso, `funil: null` omite a seção, Tab pelo seletor, datas e botão, e leitura do código-fonte confirmando a ausência de `dangerouslySetInnerHTML`
    - _Requirements: 4.7, 8.7, 9.2, 13.2, 13.3, 13.5, 13.12, 14.5, 18.4_

  - [ ]* 6.10 Escrever `apps/web/src/cs/InsightsRota.test.tsx`
    - Com as `rotas` reais e `fetch` simulado (mesmo `simular`/`renderizar` do `PainelCs.test.tsx`): o Gestor vê o link "Insights"; o Atendente não vê o link e, ao abrir `/cs/insights`, recebe "Acesso negado" sem nenhuma chamada a `/insights`; sem sessão vai ao login; o link "Métricas" continua
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 17.3, 18.5_

- [x] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Documentação
  - [x] 8.1 Atualizar `docs/DEMO.md`
    - Passo do roteiro: o Gestor abre `/cs/insights`, o que cada bloco mostra, a escolha de período e o aviso "Dados de demonstração"
    - Opções do servidor: `--sem-demo` (sem exemplos e sem semente) e `--resetar` (recria os dois); a semente é fictícia e criada só na primeira subida ou com `--resetar`
    - Nota de que os indicadores de IA não aparecem porque a demo roda sem IA; incluir os arquivos novos na lista de testes focados
    - _Requirements: 18.7, 18.8, 18.9_

- [x] 9. Serviço puro `servicos/dashboard.py` e rota `GET /api/cs/dashboard`
  - [x] 9.1 Criar `services/api/servicos/dashboard.py`
    - Constantes `LIMITE_PARADO = timedelta(minutes=60)`, `LIMITE_EM_FOCO = 10`, `MOTIVOS = ("p1_ou_risco", "resposta_nao_lida", "sem_responsavel", "parado")` (ordem de urgência) e as tuplas `CHAVES_PRIMEIRO_NIVEL`, `CHAVES_VISAO_GERAL`, `CHAVES_EM_FOCO` e `CHAVES_ITEM` (11 chaves)
    - `ChamadoDashboard` (dataclass `frozen`, `slots`) com exatamente `numero`, `prioridade`, `status`, `criado_em`, `responsavel_desde`, `resposta_nao_lida`, `risco`, `modelo_id` e `problema_id`, e o construtor `de(chamado, jornada)`; ficam de fora `jornada_id`, `pacote`, nome e usuário do responsável, anexos, encerramento e canal; Jornada ausente vira `risco=False`, `modelo_id=None` e `problema_id=None`
    - Funções públicas `motivos_de(chamado, agora)` (vazia para Chamado encerrado; `parado` com `>=` 60 min e só em `em_atendimento` com responsável), `idade_em_minutos(chamado, agora)` (`max(0, int(segundos // 60))`) e `chave_de_ordem(chamado, agora)` = `(índice do motivo mais urgente, RANKING_PRIORIDADE[prioridade], -idade_min, numero)`
    - `montar_dashboard(agora, *, modo_local, chamados, titulos)`: `visao_geral` com as seis contagens (`p1_risco_abertos` é P1 **e** risco; o motivo `p1_ou_risco` é P1 **ou** risco; as três contagens de status somam o total lido), `em_foco` com `total`, `limite` e `itens = ordenada[:10]`, `gerado_em = agora.isoformat()`, `modelo`/`problema` com `nao_informado` e `Problema <id>`; sem I/O e sem relógio
    - Importar `ROTULO_NAO_INFORMADO` de `servicos/metricas_chamados.py` e `RANKING_PRIORIDADE` de `repositorios/modelos.py`; não importar `repositorios.interfaces`, `core`, `boto3` nem `datetime.now`/`time`
    - _Requirements: 21.5, 21.6, 21.7, 22.1, 22.2, 22.3, 22.4, 22.5, 22.6, 22.7, 22.8, 22.9, 22.10, 22.11, 22.12, 22.13, 22.14, 22.15, 22.16, 23.1, 23.2, 23.3_

  - [x] 9.2 Implementar `services/api/routes/cs_dashboard.py`
    - `@exigir_perfil("gestor", "atendente")` e `ROTAS = [Rota("GET", "/dashboard", dashboard, escopo="cs", nome="cs_dashboard", perfis=frozenset({"gestor", "atendente"}))]`; não editar a `MATRIZ` de `servicos/autenticacao.py` nem `_MATRIZ_BRUTA`
    - Ler o relógio uma só vez (`agora = ctx.app.agora()`), `chamados.listar_todos()` uma vez e `jornadas.obter` uma vez por `jornada_id` (dict de cache por requisição); `ErroRepositorio` (inclusive `ErroIndisponivelForaDoModoLocal`) sobe sem captura, para virar 5xx sem dados parciais
    - Catálogo: `catalogo.listar_problemas()`; em falha, títulos vazios e aviso `catalogo_indisponivel_dashboard`; `modo_local = (ctx.app.modo == MODO_LOCAL)`
    - Docstring do módulo com o contrato (como `cs_metricas.py`); não editar `cs_metricas.py`, `cs_chamados.py` nem os Protocols de `repositorios/interfaces.py`
    - Rodar `test_autorizacao_cs.py`, `test_core_roteador.py`, `test_rotas_cs_metricas.py` e `test_metricas_chamados.py` para confirmar que continuam verdes sem alteração
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 21.7, 21.8, 21.9, 21.10, 21.11, 23.1, 23.2, 23.3, 26.10_

  - [ ]* 9.3 Escrever testes unitários do serviço do Dashboard
    - Em `services/api/tests/test_servico_dashboard.py` (novo): fronteira do `parado` (59:59 não, 60:00 sim, `responsavel_desde` no futuro não), `em_atendimento` sem responsável (é `sem_responsavel`, não `parado`), 14 Chamados em foco (`total` 14 e 10 itens), ordem de um caso desenhado à mão (empate por idade e por número), Jornada ausente, lista vazia (seis zeros e `itens` vazia), `p1_risco_abertos` (E) diferente do motivo `p1_ou_risco` (OU), campos de `ChamadoDashboard` por `dataclasses.fields`, e verificação por `ast` de que o módulo não importa `repositorios.interfaces`, `core`, `boto3` nem `datetime.now`/`time`
    - _Requirements: 22.1, 22.5, 22.8, 22.11, 22.12, 22.14, 22.15, 22.16, 23.3, 26.12_

  - [ ]* 9.4 Escrever teste de propriedade da forma fechada do Dashboard
    - Em `services/api/tests/test_propriedade_dashboard.py` (novo), com Hypothesis, referência escrita no próprio teste e comentário `# Feature: insights-gestor, Property 20`
    - **Property 20: Forma fechada da resposta do Dashboard**
    - **Validates: Requirements 21.5, 21.6, 21.7, 22.1, 22.6, 22.7, 22.15**

  - [ ]* 9.5 Escrever teste de propriedade das contagens da visão geral
    - **Property 21: Contagens da visão geral**
    - **Validates: Requirements 22.1, 22.2, 22.3, 22.4, 22.5, 22.15**

  - [ ]* 9.6 Escrever teste de propriedade dos motivos de foco
    - **Property 22: Motivos de foco**
    - **Validates: Requirements 22.8, 22.14**

  - [ ]* 9.7 Escrever teste de propriedade dos campos derivados do item
    - **Property 23: Campos derivados do item**
    - **Validates: Requirements 22.9, 22.10, 22.11**

  - [ ]* 9.8 Escrever teste de propriedade da ordem e do limite de `em_foco`
    - **Property 24: Ordem e limite de `em_foco`**
    - **Validates: Requirements 22.6, 22.12**

  - [ ]* 9.9 Escrever teste de propriedade do determinismo
    - **Property 25: Determinismo e independência da ordem de leitura**
    - **Validates: Requirements 22.13, 22.16, 21.6**

  - [ ]* 9.10 Escrever teste de propriedade de privacidade
    - **Property 26: A resposta do Dashboard não vaza dados pessoais nem identificadores internos**
    - **Validates: Requirements 23.1, 23.2, 23.3**

  - [ ]* 9.11 Escrever testes de rota do Dashboard: autorização e contrato
    - Em `services/api/tests/test_rotas_cs_dashboard.py` (novo), reusando `montar_cliente`/`criar_chamado`
    - Gestor 200 e Atendente 200 (4 chaves de primeiro nível); sem sessão 401 com o corpo da `/fila`; `decidir_acesso(True, perfil, "GET", "/dashboard", ROTA.perfis)` permitido para os dois perfis, `("GET", "/dashboard") not in MATRIZ` e `perfis_permitidos("GET", "/dashboard") == frozenset()`; no mesmo cliente, Atendente 200 em `/dashboard` e 403 em `/insights` (a API_Insights continua exclusiva do Gestor); `modo_local` true com `modo="local"` e false com `modo="aws"` e repositórios injetados
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.7, 26.12_

  - [ ]* 9.12 Escrever testes de rota do Dashboard: falhas, leitura única e privacidade
    - No mesmo arquivo: `listar_todos` com `ErroRepositorio` e com `ErroIndisponivelForaDoModoLocal` (502), `jornadas.obter` com `ErroRepositorio` (502) e exceção genérica (500), todas sem `visao_geral` nem `em_foco` no corpo; catálogo indisponível (200, `Problema <id>` e aviso no log); relógio que avança 7 minutos a cada chamada provando a leitura única (`idade_min == (gerado_em - criado_em) // 60 s`); `listar_todos` chamado uma vez e `jornadas.obter` uma vez por `jornada_id`; resposta sem telefone, CEP e mensagens; resposta em menos de 3 s com a semente
    - _Requirements: 21.6, 21.8, 21.9, 21.10, 21.12, 23.1, 26.12_

- [x] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Hook de busca e extração do `ConteudoInsights`
  - [x] 11.1 Criar `insights/useInsights.ts` e acrescentar `montarConsulta` e os tipos de estado
    - Em `apps/web/src/cs/insights/formatar.ts`: `montarConsulta(selecao)` (`periodo=7d` ou `periodo=personalizado&inicio=...&fim=...`); em `tipos.ts`: `EstadoInsights` e `FonteInsights`
    - `useInsights.ts`: `CONSULTA_7D` e `useBuscaInsights(consulta, ativo = true)`, com `AbortController`, estado derivado da chave `consulta#tentativa` (resposta de outra consulta ou de antes de "Tentar novamente" nunca aparece) e `recarregar`; com `ativo` falso não envia nenhuma requisição
    - Só acrescentar exports; não alterar o que a tarefa 6.2 criou
    - _Requirements: 13.5, 13.6, 24.4, 25.15_

  - [x] 11.2 Extrair `ConteudoInsights` de `InsightsCs` (a `InsightsCs` vira casca)
    - Criar `apps/web/src/cs/insights/ConteudoInsights.tsx` (`export function ConteudoInsights({ fonte7d, semAvisoDemo })`) com o estado do Período, o seletor, os estados carregando/erro/pronto e todas as seções, usando `useBuscaInsights`; `usaFonteDoPai = fonte7d !== undefined && consulta === CONSULTA_7D`, com o hook próprio com `ativo` falso nesse caso; `semAvisoDemo` omite o aviso "Dados de demonstração"; é o único ponto de entrada do Recharts (via `GraficoDistribuicao` e `GraficoDesfecho`)
    - Reescrever `InsightsCs.tsx` como `export function Component` com `<h1>Insights</h1>` e `<ConteudoInsights />`, importando de forma estática; títulos de seção continuam `<h2>`; a rota `/cs/insights` e o comportamento da Tela_Insights não mudam
    - Rodar as suítes existentes `MetricasCs.test.tsx` e `PainelCs.test.tsx` (e `InsightsCs.test.tsx`, se já existir) para confirmar que continuam verdes
    - _Requirements: 8.6, 8.7, 9.2, 13.1, 13.2, 13.4, 13.5, 13.6, 13.12, 15.5, 19.7, 19.9, 25.14, 25.15_

  - [ ]* 11.3 Acrescentar exemplos de `montarConsulta` em `formatar.test.ts`
    - Em `apps/web/src/cs/insights/formatar.test.ts` (criado na 6.7): `periodo=7d`, `periodo=30d`, `periodo=hoje` e personalizado com `inicio` e `fim`
    - _Requirements: 13.2, 13.3_

- [x] 12. Tela_Dashboard no front-end
  - [x] 12.1 Criar tipos e utilitários em `apps/web/src/cs/dashboard/`
    - `tipos.ts`: `RespostaDashboard`, `ItemEmFoco`, `MotivoDeFoco` e `lerRespostaDashboard(corpo)` (validação mínima; formato inesperado devolve `null`)
    - `formatar.ts`: `formatarIdade` (`menos de 1 min`, `5 min`, `2 h 05 min`), rótulos de prioridade (`P1 · Urgente`, `P2 · Alta`, `P3 · Normal`), status e motivo (`P1 ou risco`, `Resposta não lida`, `Sem responsável`, `Parado há mais de 60 min`; valor desconhecido aparece como veio; `nao_informado` vira "Não informado") e `abaEfetiva(parametro, perfil)` (gestor: `insights` por padrão e `chamados` quando pedido; atendente: sempre `chamados`)
    - Não importar nada de `cs/insights/` além de `tipos.ts`, `formatar.ts` e `useInsights.ts`
    - _Requirements: 24.6, 24.7, 24.13, 25.3, 25.4, 25.5, 25.6, 25.7_

  - [x] 12.2 Criar o hook `dashboard/useDashboard.ts`
    - `INTERVALO_DASHBOARD_MS = 10_000` e `useDashboard()` devolvendo `{ estado, tentarDeNovo }`; estados `carregando`, `erro` e `pronto` (`dados` e `falhaAtualizacao`)
    - A atualização automática nunca passa por `carregando`; um pedido em voo por vez (o tick espera, o "Tentar novamente" substitui); falha depois de sucesso mantém os dados e liga `falhaAtualizacao`; pausa com a página oculta e recarrega ao voltar; o cleanup faz `clearInterval`, remove o ouvinte e `abort()` do pedido em voo
    - Não importar a `FilaCs`; `FilaCs.tsx` fica intocada
    - _Requirements: 26.1, 26.2, 26.3, 26.5, 26.6_

  - [x] 12.3 Criar `dashboard/SeletorDeAbas.tsx`
    - Componente genérico em `Id extends string` com `tablist` de `aria-label="Seções do Dashboard"`, `<button role="tab">` com `id` (`useId`), `aria-selected`, `aria-controls` e `tabIndex` 0 só na selecionada; dois `role="tabpanel"` sempre presentes com `aria-labelledby`, só o painel selecionado recebe conteúdo e o outro fica `hidden` e vazio
    - Exportar `proximaAba(abas, atual, tecla)` (setas com volta circular, Home, End, `null` para as demais teclas); ativação automática: a seta move foco e seleção
    - Aba selecionada distinguida por `aria-selected` e por estilo que não é só cor (peso 700 e borda inferior)
    - _Requirements: 25.1, 25.9, 25.10, 25.11, 25.12, 25.13, 25.16, 26.7_

  - [x] 12.4 Criar `VisaoGeral.tsx` e `CartoesSatisfacao.tsx`
    - `VisaoGeral`: seis cards em `<dl>` ("Chamados abertos", "Em atendimento", "Encerrados", "P1 de risco abertos", "Sem responsável", "Respostas não lidas") com os valores de `visao_geral`; `role="status"` ao carregar e `role="alert"` com "Tentar novamente" no erro
    - `CartoesSatisfacao`: "Nota média" (`formatarDecimal`) e "Tempo médio até assumir" (`min:seg`), cada um com o texto "últimos 7 dias" e "sem dados" quando `SEM_DADOS`; lê a `FonteInsights` do pai; carregando com `role="status"` e erro da API_Insights com `role="alert"` e "Tentar novamente" só nessa faixa
    - Texto sempre como `{valor}` do React, sem `dangerouslySetInnerHTML`; classes `dashboard-*` definidas em `dashboard.css` na tarefa 12.6
    - _Requirements: 24.2, 24.3, 24.5, 23.4, 23.5, 26.1, 26.2, 26.3, 26.4, 26.8_

  - [x] 12.5 Criar `dashboard/ListaEmFoco.tsx`
    - `<section aria-labelledby>` com `<h2>Chamados em foco</h2>` e `<ul aria-labelledby>`; `<li key={numero}>` com prioridade em texto, número como link para `/cs/chamados/` + `encodeURIComponent(numero)`, status, modelo, problema, idade formatada e sublista `aria-label="Motivos do chamado <numero>"` com o texto de cada motivo
    - Manter a ordem recebida; "Mostrando N de M chamados em foco" quando `total > itens.length`; "Nenhum chamado pede atenção agora" quando vazia; link "Ver fila completa" para `/cs/fila` nos dois casos; carregando com `role="status"` e erro com `role="alert"` e "Tentar novamente"; a lista não é região `aria-live`
    - Prioridade e motivos sempre em texto, nunca só cor
    - _Requirements: 24.6, 24.7, 24.8, 24.9, 24.10, 24.11, 24.13, 23.4, 23.5, 26.1, 26.2, 26.3, 26.8_

  - [x] 12.6 Criar `Dashboard.tsx` e `dashboard.css`
    - `apps/web/src/cs/Dashboard.tsx`: `export function Component` (converte `useSessaoCs().perfil` em `gestor` ou, em qualquer outro caso, `atendente`) e `TelaDashboard({ perfil })`; `React.lazy(() => import("./insights/ConteudoInsights").then(...))` no escopo do módulo, dentro de `<Suspense fallback={<p role="status">…</p>}>`; nenhum outro import de `ConteudoInsights`, `Grafico*` ou `recharts` em `Dashboard.tsx` e em `cs/dashboard/`
    - Árvore: `<h1>Dashboard</h1>`, aviso "Dados de demonstração" (`modo_local`) e "Atualizado às HH:MM:SS" (`gerado_em`), aviso `role="status"` de falha de atualização, seção "Visão geral" (`VisaoGeral` e, só para o Gestor, `CartoesSatisfacao`), Gestor com `SeletorDeAbas` (Insights | Chamados em foco) e Atendente só com `ListaEmFoco`
    - `useDashboard()` e `useBuscaInsights(CONSULTA_7D, perfil === "gestor")`; o Atendente nunca solicita a API_Insights; `?aba=` por `useSearchParams` com `abaEfetiva`, e a seleção de aba usa `setSearchParams(..., { replace: true })`; `ConteudoInsights` recebe `fonte7d` e `semAvisoDemo`
    - Criar `apps/web/src/cs/dashboard.css` (grade dos cards, lista, abas, borda lateral por prioridade como reforço), no padrão de `fila.css`/`metricas.css`
    - _Requirements: 15.5, 20.6, 23.4, 23.5, 24.1, 24.2, 24.3, 24.4, 24.12, 25.2, 25.3, 25.4, 25.5, 25.6, 25.7, 25.8, 25.14, 25.15, 25.16, 25.17, 26.1, 26.2, 26.4, 26.5, 26.6, 26.7, 26.8_

- [x] 13. Navbar, rotas e destino do login
  - [x] 13.1 Atualizar `apps/web/src/app/rotas.tsx`
    - A rota índice de `/cs` passa a ser `{ index: true, lazy: () => import("../cs/Dashboard") }` em vez de `<Navigate to="/cs/fila" replace />`; remover `Navigate` do import (o `tsconfig` tem `noUnusedLocals`)
    - Manter `fila`, `chamados/:numero`, `metricas`, `insights` (dentro de `GuardaGestor`) e o `*` dentro do layout; não importar `Dashboard` nem `InsightsCs` de forma estática
    - Rodar `PainelCs.test.tsx`, `rotas.test.tsx`, `FilaCs.test.tsx` e `MetricasCs.test.tsx` para confirmar que continuam verdes sem alteração
    - _Requirements: 12.3, 12.4, 19.8, 19.9, 20.1, 20.2, 20.5, 20.6_

  - [x] 13.2 Atualizar o menu em `apps/web/src/cs/LayoutPainel.tsx`
    - `<NavLink to="/cs" end>Dashboard</NavLink>` e `<NavLink to="/cs/fila">Fila de chamados</NavLink>` para qualquer perfil; para o `gestor`, depois deles, "Métricas" e "Insights", nessa ordem; o Atendente não vê "Métricas" nem "Insights"
    - O `NavLink` já escreve `aria-current="page"` e o `painel.css` já distingue o link atual por peso e contorno; não mudar CSS
    - _Requirements: 12.1, 12.2, 12.5, 19.1, 19.2, 19.3, 19.4, 19.5, 19.6, 19.7_

  - [x] 13.3 Mudar o destino padrão do login em `apps/web/src/cs/LoginCs.tsx`
    - `DESTINO_PADRAO = "/cs"` e `destinoSeguro` aceitando `/cs`, `/cs/...` e `/cs?...`, recusando `/cs/login`, destinos externos (`//evil.com`, `https://x`) e prefixos como `/csx`
    - _Requirements: 20.3, 20.4_

- [x] 14. Travas de empacotamento e testes do Dashboard
  - [x] 14.1 Criar `apps/web/scripts/verificar-chunks.mjs`
    - Script de verificação pós-build (não é teste do Vitest e não entra no bundle): lê `dist/.vite/manifest.json` e os arquivos de `dist/assets`, acha os chunks que contêm `recharts` (marca da biblioteca) e falha se algum deles está no fecho dos `imports` estáticos de `index.html` ou de `src/cs/Dashboard.tsx`; `vite.config.ts` e `package.json` não mudam
    - _Requirements: 15.5, 25.17_

  - [ ]* 14.2 Escrever `apps/web/src/cs/dashboard/formatar.test.ts`
    - `formatarIdade` (0, 1, 59, 60, 125 e 1440 minutos), `abaEfetiva` em tabela (os dois perfis; valores válidos, ausentes e inválidos), rótulos de prioridade, status e motivo, `lerRespostaDashboard` com formato inesperado
    - _Requirements: 24.6, 24.7, 25.3, 25.4, 25.5, 25.6, 25.7, 26.12_

  - [ ]* 14.3 Escrever `apps/web/src/cs/dashboard/SeletorDeAbas.test.tsx`
    - `proximaAba` em tabela (direita e esquerda com volta circular, Home, End, outras teclas dão `null`); atributos ARIA (`tablist` com nome, `aria-selected`, `aria-controls` apontando para um `tabpanel` existente, `aria-labelledby`, `tabindex` 0 e -1); um só `tabpanel` visível; teclado com `userEvent` (foco e seleção andam juntos)
    - _Requirements: 25.1, 25.9, 25.10, 25.11, 25.12, 25.13, 25.16, 26.7, 26.12_

  - [ ]* 14.4 Escrever `apps/web/src/cs/dashboard/useDashboard.test.tsx`
    - `renderHook` com temporizadores falsos: carga inicial; um pedido por intervalo e `INTERVALO_DASHBOARD_MS === INTERVALO_FILA_MS` (o teste pode importar a `FilaCs`); a atualização não passa por `carregando`; pedido lento não empilha outro; falha depois de sucesso mantém `dados` e liga `falhaAtualizacao`, e o sucesso seguinte a desliga; falha sem dados vira `erro`; "Tentar novamente" volta a `carregando`; página oculta pausa e ao voltar carrega e reinicia; ao desmontar o `signal` fica `aborted`; formato inesperado vira `erro`
    - _Requirements: 26.1, 26.2, 26.3, 26.5, 26.6, 26.12_

  - [ ]* 14.5 Escrever `apps/web/src/cs/Dashboard.test.tsx`: estados, cards e lista
    - `TelaDashboard({ perfil })` em `MemoryRouter`, `fetch` simulado por URL e `ConteudoInsights` substituído por stub leve (`vi.mock`)
    - Carregando (`role="status"`), sucesso (seis cards, lista na ordem recebida, link com número codificado, prioridade, motivos, idade e status em texto), "Mostrando N de M", lista vazia com "Nenhum chamado pede atenção agora" e "Ver fila completa", erro com "Tentar novamente", API_Insights falhando só nos cards, "sem dados", Atendente sem cards de satisfação, sem `tablist` e sem nenhum pedido a `/insights`
    - _Requirements: 23.4, 24.1, 24.2, 24.3, 24.4, 24.5, 24.6, 24.8, 24.9, 24.10, 24.11, 24.13, 25.2, 26.1, 26.2, 26.3, 26.4, 26.8, 26.12_

  - [ ]* 14.6 Escrever `apps/web/src/cs/Dashboard.test.tsx`: abas, escape, aviso e axe
    - No mesmo arquivo: `?aba=` ausente, `insights`, `chamados`, inválido (`Insights`, `x`, vazio) e `insights` para o Atendente; clique na aba atualiza `?aba=` com `replace` (o histórico não cresce); aviso "Dados de demonstração" com `modo_local` verdadeiro e falso; HTML em `problema` e `modelo` escapado (nenhum `<img>`); `jest-axe` em carregando, erro, pronto com itens e pronto vazio, para o Gestor nas duas abas e para o Atendente
    - _Requirements: 23.5, 24.12, 25.3, 25.4, 25.5, 25.6, 25.7, 25.8, 26.9, 26.12_

  - [ ]* 14.7 Escrever `apps/web/src/cs/DashboardInsights.test.tsx`
    - Integração com o `ConteudoInsights` real e `ResizeObserver` vazio (`vi.stubGlobal`): abrir o Dashboard como Gestor envia **uma** requisição `GET /api/cs/insights?periodo=7d` e a aba mostra a mesma resposta dos cards; ir para "Chamados em foco" e voltar não envia outra; 30 dias envia uma e voltar a 7 dias não envia nenhuma; "Tentar novamente" em 7 dias refaz uma só requisição e atualiza cards e aba juntos; com `?aba=chamados` o conteúdo de Insights não é renderizado; Atendente com `?aba=insights` nunca chama `/insights`; "Dados de demonstração" aparece uma só vez na tela
    - _Requirements: 24.4, 25.14, 25.15, 25.16, 25.17, 26.12_

  - [ ]* 14.8 Escrever `apps/web/src/cs/LayoutPainel.test.tsx`
    - Com as `rotas` reais e `fetch` simulado: links por perfil e a ordem Dashboard, Fila de chamados, Métricas, Insights; `aria-current="page"` no link certo em `/cs`, `/cs/fila`, `/cs/metricas` e `/cs/insights`; "Dashboard" sem `aria-current` em `/cs/fila` e `/cs/insights` e com `aria-current` em `/cs?aba=chamados`; nenhum link marcado em `/cs/chamados/X`
    - _Requirements: 12.1, 12.2, 18.5, 19.1, 19.2, 19.3, 19.4, 19.5, 26.12_

  - [ ]* 14.9 Escrever `apps/web/src/cs/DashboardRota.test.tsx`
    - Com sessão, `/cs` fica em `/cs` e mostra o `h1` "Dashboard" sem redirecionar para `/cs/fila`; sem sessão, `/cs` vai a `/cs/login` sem pedir `/dashboard`; login sem destino leva a `/cs`; login vindo de `/cs?aba=chamados` volta a `/cs?aba=chamados`; destinos recusados (`//evil.com`, `https://x`, `/cs/login`, `/csx`) caem em `/cs`; `/cs/inshigts` mostra "Página não encontrada" com o `nav` "Painel" à vista e sem mudar o caminho; Atendente em `/cs/insights` vê "Acesso negado" sem pedir `/insights`; `/cs/fila` segue funcionando
    - _Requirements: 12.3, 19.8, 19.9, 20.1, 20.2, 20.3, 20.4, 20.5, 26.13_

  - [ ]* 14.10 Escrever `apps/web/src/cs/isolamentoGraficos.test.ts`
    - Parte de `Dashboard.tsx`, segue só os imports estáticos relativos (`import ... from "./x"` e `export ... from "./x"`, resolvendo `.ts` e `.tsx`) e falha se algum arquivo alcançado tem `from "recharts"` ou importa `ConteudoInsights`/`Grafico*`; confere que `Dashboard.tsx` contém `import("./insights/ConteudoInsights")`, que `rotas.tsx` não importa `Dashboard` nem `InsightsCs` de forma estática e que nenhum arquivo de `Dashboard.tsx` e de `cs/dashboard/` contém `dangerouslySetInnerHTML`
    - _Requirements: 15.5, 20.6, 23.5, 25.17_

  - [ ]* 14.11 Acrescentar expectativas em `apps/web/src/cs/PainelCs.test.tsx`
    - Só acréscimos, sem remover nem enfraquecer nenhuma expectativa existente: no teste do Atendente que entra, `getByRole("link", { name: "Dashboard" })` presente e link "Insights" ausente; no teste do Atendente em `/cs/metricas`, link "Insights" ausente; no teste do Gestor, links "Dashboard", "Fila de chamados", "Métricas" e "Insights" presentes na ordem do menu (`within(nav).getAllByRole("link")`)
    - _Requirements: 17.3, 19.1, 19.2, 19.3, 26.11_

  - [ ]* 14.12 Acrescentar a linha de `/cs` em `apps/web/src/app/rotas.test.tsx`
    - Só acréscimo: `["/cs", "Entrar no painel de atendimento"]` (sem sessão, `/cs` leva ao login) ao lado de `["/cs/fila", ...]` na tabela `it.each`
    - _Requirements: 17.3, 20.2, 26.11_

- [x] 15. Documentação do Dashboard
  - [x] 15.1 Atualizar `docs/DEMO.md` com o Dashboard
    - O roteiro passa a abrir em `/cs` depois do login: Visão geral (seis contagens e, para o Gestor, nota média e tempo até assumir dos últimos 7 dias), aba "Insights" (o mesmo conteúdo de `/cs/insights`, com escolha de Período), aba "Chamados em foco" (motivo em texto e link "Ver fila completa"), aviso "Dados de demonstração" e atualização automática a cada 10 s
    - Links do menu (Dashboard, Fila de chamados, Métricas e Insights, os dois últimos só para o Gestor); o Atendente vê só "Chamados em foco"; `?aba=insights` e `?aba=chamados` abrem a aba direto; o endereço correto é `/cs/insights` (a URL com erro de digitação mostra "Página não encontrada" dentro do painel)
    - Com a semente, o Dashboard abre com Chamados em foco (os Chamados abertos da semente não têm responsável e há um P1 de risco criado hoje); os motivos "Resposta não lida" e "Parado" dependem de dados que a semente não garante; incluir os arquivos de teste novos na lista de testes focados
    - _Requirements: 26.15_

- [x] 16. Verificação final (somente testes relacionados)
  - [x] 16.1 Conferir lint, build e carga tardia do Recharts
    - Em `apps/web`: `npm run lint`, `npm run build -- --manifest` e `node scripts/verificar-chunks.mjs` sem erro
    - Conferir que nenhum arquivo referenciado por `dist/index.html` contém `recharts`, que o chunk do `Dashboard` (rota índice `/cs`, com a aba "Chamados em foco") não importa a biblioteca de forma estática e que o código do gráfico está só no chunk de `ConteudoInsights` (rota `/cs/insights` e aba "Insights")
    - _Requirements: 15.4, 15.5, 25.17_

  - [x] 16.2 Conferir o escopo (sem `infra/` nem AWS)
    - `git diff --stat -- infra packages services/api/repositorios services/api/routes/cs_metricas.py services/api/routes/cs_chamados.py services/api/servicos/autenticacao.py` vazio e `git diff -- services/api/tests/test_autorizacao_cs.py` vazio (quando o repositório tiver histórico; sem histórico, conferir por `grep` que os arquivos citados não ganharam referências a `insights`, `dashboard` nem `semente`)
    - `PainelCs.test.tsx` e `rotas.test.tsx` só ganharam linhas (nenhuma linha removida no `git diff`); `FilaCs.test.tsx`, `MetricasCs.test.tsx` e `ChamadoCs.test.tsx` sem alteração
    - Nada em `services/`, `packages/`, `apps/` e `infra/` importa `semente_demo`; nenhum Protocol novo em `repositorios/interfaces.py`; `MATRIZ` sem entrada para `/insights` nem `/dashboard`
    - _Requirements: 11.4, 11.5, 16.13, 17.1, 17.2, 21.3, 21.11, 26.10, 26.16_

  - [x] 16.3 Conferir o roteiro do `docs/DEMO.md` contra a implementação
    - Com `grep`, verificar que as opções citadas (`--resetar`, `--sem-demo`, `--porta`), as rotas `/cs` e `/cs/insights`, os parâmetros `?aba=insights` e `?aba=chamados`, os nomes das abas, os links do menu e o aviso "Dados de demonstração" batem com `dev_local.py`, `rotas.tsx`, `LayoutPainel.tsx`, `Dashboard.tsx` e `ConteudoInsights.tsx`
    - _Requirements: 18.7, 18.8, 18.9, 26.15_

  - [ ]* 16.4 Rodar os testes relacionados
    - `services/api`: `pytest tests/test_propriedade_insights.py tests/test_servico_insights.py tests/test_rotas_cs_insights.py tests/test_propriedade_dashboard.py tests/test_servico_dashboard.py tests/test_rotas_cs_dashboard.py tests/test_rotas_cs_metricas.py tests/test_metricas_chamados.py tests/test_autorizacao_cs.py`
    - `packages/dominio`: `pytest tests/test_metricas.py`
    - `scripts`: `pytest tests/test_semente_demo.py tests/test_dev_local.py tests/test_persistencia_reinicio.py`
    - `apps/web`: `npx vitest --run src/cs/Dashboard.test.tsx src/cs/DashboardInsights.test.tsx src/cs/DashboardRota.test.tsx src/cs/LayoutPainel.test.tsx src/cs/isolamentoGraficos.test.ts src/cs/dashboard src/cs/InsightsCs.test.tsx src/cs/InsightsRota.test.tsx src/cs/insights src/cs/PainelCs.test.tsx src/cs/FilaCs.test.tsx src/cs/MetricasCs.test.tsx src/app/rotas.test.tsx`
    - Não rodar a suíte completa; corrigir qualquer falha encontrada
    - _Requirements: 17.2, 18.6, 26.14_

- [x] 17. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notas

- Tarefas marcadas com `*` são opcionais (testes) e podem ser puladas para um MVP mais rápido. Só sub-tarefas de teste são opcionais; a trava `verificar-chunks.mjs` (14.1) e as conferências 16.1 a 16.3 são obrigatórias porque dependem dela.
- Cada tarefa referencia os requisitos específicos para rastreabilidade.
- Os testes de propriedade (Hypothesis) validam as propriedades de correção do design (1 a 15 do Insights e 20 a 26 do Dashboard); os testes por exemplo cobrem rota, semente, telas e menu. O front não usa biblioteca de PBT.
- Atualização Dashboard (Requisitos 19 a 26, decisões D9 a D15): as tarefas 1 a 8 continuam como estavam. As tarefas 9 a 15 são novas. A antiga "9. Verificação final" virou **16** (9.1 a 9.4 viraram 16.1 a 16.4) e o antigo "10. Final checkpoint" virou **17**; as únicas referências a esses números estavam nestas Notas e no grafo, já atualizadas.
- A tarefa 6.5 cria a `InsightsCs` completa e a 11.2 a divide em `ConteudoInsights` + casca; a 6.6 e as tarefas 13.1 e 13.2 editam `rotas.tsx` e `LayoutPainel.tsx` em ondas diferentes.
- Ordem das ondas: as tarefas de front que entregam navbar, Dashboard e Insights vêm primeiro (ondas 0 a 5: 6.x, 11.x, 12.x e 13.x, junto com a rota do Dashboard 9.1 e 9.2 e a cadeia do serviço de Insights 1.x e 2.1). A semente (4.1 e 4.2) e a documentação (8.1 e 15.1) vêm depois, e a verificação final obrigatória (16.1 a 16.3) fecha as obrigatórias na onda 8.
- Grafo de ondas: todas as tarefas obrigatórias estão nas ondas 0 a 8, e todas as opcionais (testes e a execução dos testes relacionados, 16.4) estão nas ondas 9 em diante. Assim nenhuma tarefa obrigatória depende de uma opcional de onda anterior, e pular os testes não trava o agendador.
- Tarefas que escrevem no mesmo arquivo ficam em ondas diferentes (por exemplo, 1.1 a 1.5 em `insights.py`, 1.7 a 1.21 em `test_propriedade_insights.py`, 9.4 a 9.10 em `test_propriedade_dashboard.py`, 4.3 a 4.7 em `test_semente_demo.py`, 14.5 e 14.6 em `Dashboard.test.tsx`, 6.6, 13.1 em `rotas.tsx`, 6.6 e 13.2 em `LayoutPainel.tsx`, 8.1 e 15.1 em `DEMO.md`).
- As tarefas obrigatórias 1.1 a 1.5, 2.1, 4.2, 6.6, 9.2, 11.2 e 13.1 já rodam as suítes existentes afetadas, para confirmar que seguem verdes sem alteração. Os únicos testes existentes que ganham expectativas são `PainelCs.test.tsx` (14.11) e `rotas.test.tsx` (14.12), só com acréscimos (Req 17.3 e 26.11).
- Nenhuma tarefa altera `infra/` nem acessa a AWS; a rota `GET /api/cs/dashboard`, como a `/insights`, só existe no Modo_Local.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "6.1", "6.2", "9.1", "12.1", "12.3", "13.3"] },
    { "id": 1, "tasks": ["1.2", "6.3", "6.4", "9.2", "11.1", "12.2"] },
    { "id": 2, "tasks": ["1.3", "6.5", "12.4", "12.5"] },
    { "id": 3, "tasks": ["1.4", "6.6", "11.2"] },
    { "id": 4, "tasks": ["1.5", "8.1", "12.6", "13.2", "14.1"] },
    { "id": 5, "tasks": ["2.1", "13.1"] },
    { "id": 6, "tasks": ["4.1", "15.1"] },
    { "id": 7, "tasks": ["4.2"] },
    { "id": 8, "tasks": ["16.1", "16.2", "16.3"] },
    { "id": 9, "tasks": ["1.6", "1.7", "2.2", "4.3", "6.7", "6.8", "6.10", "9.3", "9.4", "9.11", "14.2", "14.3", "14.4", "14.5", "14.7", "14.8", "14.9", "14.10", "14.11", "14.12"] },
    { "id": 10, "tasks": ["1.8", "2.3", "4.4", "6.9", "9.5", "9.12", "11.3", "14.6"] },
    { "id": 11, "tasks": ["1.9", "4.5", "9.6"] },
    { "id": 12, "tasks": ["1.10", "4.6", "9.7"] },
    { "id": 13, "tasks": ["1.11", "4.7", "9.8"] },
    { "id": 14, "tasks": ["1.12", "9.9"] },
    { "id": 15, "tasks": ["1.13", "9.10"] },
    { "id": 16, "tasks": ["1.14"] },
    { "id": 17, "tasks": ["1.15"] },
    { "id": 18, "tasks": ["1.16"] },
    { "id": 19, "tasks": ["1.17"] },
    { "id": 20, "tasks": ["1.18"] },
    { "id": 21, "tasks": ["1.19"] },
    { "id": 22, "tasks": ["1.20"] },
    { "id": 23, "tasks": ["1.21"] },
    { "id": 24, "tasks": ["16.4"] }
  ]
}
```
