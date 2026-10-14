# Plano de Implementação: Persistência Local da Demo

## Visão geral

Implementação incremental em Python (API, `scripts/`) e TypeScript/React (front). A ordem segue as camadas da feature:

1. `listar_todos` (Protocol, memória e adaptador DynamoDB com erro explícito).
2. `scripts/estado_demo.py` (Serializador, captura/aplicação do estado e Persistencia).
3. Integração no `scripts/dev_local.py` (Handler, `iniciar_estado`, `--resetar`, mensagens).
4. Métricas (`metricas_chamados` e rota `cs_metricas`).
5. Tela `MetricasCs.tsx` e ajuste do `PainelCs.test.tsx`.
6. `.gitignore` e `docs/DEMO.md`.
7. Verificação final, rodando só os testes relacionados.

Restrições de escopo: nenhuma tarefa toca `infra/` nem a AWS. Não há índice novo (`gsi_todos`), Query ou Scan novo, nem mudança em IAM. O adaptador DynamoDB apenas declara `listar_todos` e levanta `ErroIndisponivelForaDoModoLocal`.

## Tarefas

- [x] 1. `listar_todos` no ChamadosRepo
  - [x] 1.1 Criar o erro, declarar no Protocol e implementar em memória
    - Em `services/api/repositorios/erros.py`: adicionar `MENSAGEM_INDISPONIVEL_FORA_DO_MODO_LOCAL` e a classe `ErroIndisponivelForaDoModoLocal(ErroRepositorio)` com o atributo `operacao`
    - Em `services/api/repositorios/interfaces.py`: declarar `ChamadosRepo.listar_todos() -> list[Chamado]` com a docstring do design
    - Em `services/api/repositorios/memoria.py`: implementar `ChamadosMemoria.listar_todos`, sob `_trava`, ordenando por `(criado_em, numero)`
    - Manter inalterados os métodos existentes, incluindo `listar_fila`
    - _Requirements: 1.8, 8.1, 8.2, 8.3, 8.4_

  - [x] 1.2 Declarar `listar_todos` no adaptador DynamoDB com erro explícito
    - Em `services/api/repositorios/dynamodb/chamados.py`: método que levanta `ErroIndisponivelForaDoModoLocal("ChamadosDynamoDB.listar_todos")`, sem usar `self._t`, sem Query e sem Scan
    - Registrar a pendência da camada AWS na docstring do método e na docstring do módulo, junto da lista de garantias
    - Não alterar `infra/`, `dados_stack`, índices, `_tabelas_dynamodb.py` nem IAM
    - _Requirements: 8.5, 8.6, 8.7, 8.8_

  - [x]* 1.3 Escrever teste de propriedade para `listar_todos` em memória
    - Em `services/api/tests/test_repositorios_memoria.py`, com Hypothesis e tag `Feature: persistencia-local-demo, Property 10`
    - **Property 10: `listar_todos` devolve todos os Chamados**
    - **Validates: Requirements 8.1, 8.2, 8.4**

  - [x]* 1.4 Escrever o Teste_De_Contrato_Memoria de `listar_todos`
    - Em `services/api/tests/test_repositorios_contrato.py`, criar o repositório com `criar_repositorios_memoria()` direto, sem a fixture parametrizada `amb` (nenhum caso DynamoDB/moto para o método novo)
    - Cobrir: todos os status (inclusive encerrados), ordem por `criado_em` e `numero`, repositório vazio e `listar_fila` só com não encerrados
    - _Requirements: 8.1, 8.3, 8.4, 12.3_

  - [x]* 1.5 Escrever teste unitário do adaptador DynamoDB
    - Novo arquivo `services/api/tests/test_chamados_dynamodb_listar_todos.py`, sem moto, sem boto3 e sem rede
    - Usar `ChamadosDynamoDB.__new__(ChamadosDynamoDB)` (sem `_t`) e verificar que `listar_todos()` levanta `ErroIndisponivelForaDoModoLocal`
    - Verificar que o erro é `ErroRepositorio`, que a mensagem contém "indisponível fora do modo local" e o nome da operação, e que a docstring registra a pendência da camada AWS
    - _Requirements: 8.5, 8.6, 8.7, 12.4_

- [x] 2. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. `scripts/estado_demo.py`: Serializador, captura/aplicação e Persistencia
  - [x] 3.1 Implementar erros, `EstadoPersistido`, codec e texto do snapshot
    - Criar `scripts/estado_demo.py` com o bootstrap de `sys.path` (`services/api` e `packages/dominio/src`)
    - Definir `VERSAO_FORMATO`, `NOME_SNAPSHOT`, `NOME_TEMPORARIO`, `ErroSerializacao(campo, tipo)` e `ErroSnapshot(caminho, motivo)`
    - Definir `EstadoPersistido`, `PERSISTIDOS` e `EXCLUIDOS`
    - Implementar `codificar` (Enum, `datetime` com fuso, `Decimal` como texto, `tuple`/`list`, `dict`, dataclasses) e `decodificar` dirigido por `get_type_hints` (com cache por classe), com as regras de leitura do design (`bool` estrito, `Literal`, `X | None`, `tuple[X, ...]`, `dict[str, V]`, `Any` só JSON-nativo, chave desconhecida é erro)
    - Implementar `serializar_estado` (`ensure_ascii=False`, `allow_nan=False`, campo `versao`) e `ler_estado` (JSON inválido, versão diferente ou ausente e estrutura desconhecida viram `ErroSnapshot`)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11_

  - [x] 3.2 Implementar `capturar_estado` e `aplicar_estado`
    - `capturar_estado`: cópia rasa sob a `RLock` compartilhada (`repos.jornadas._trava`), achatando mensagens e acessos PII, convertendo agregados em `AgregadoDia` e fazendo `deepcopy` de `config`
    - `aplicar_estado`: montar todos os dicionários novos antes de entrar na trava (chaves `numero`, `jornada_id`, `(jornada_id, ts_ulid)`, `os_id_de(numero)`, `chave`, `(dia, metrica)`), depois `clear()` + `update()` em cada `_itens`
    - Restaurar direto nos repositórios existentes, sem trocar a instância de `Repositorios` e sem chamar `criar`, `assumir` nem `encerrar`
    - _Requirements: 4.7, 4.8, 7.5, 7.6, 7.7_

  - [x] 3.3 Implementar a classe `Persistencia`
    - `gravar(repos) -> bool`: sob `threading.Lock`, capturar, serializar **antes** de abrir arquivo, escrever `estado.json.tmp` com `flush` + `fsync` e `os.replace`; em falha remover o `.tmp`, registrar caminho e erro (sem conteúdo do estado) e devolver `False`; nunca levantar
    - `_gravar_texto`: `mkdir(parents=True, exist_ok=True)`
    - `carregar()`: converter `OSError`, `UnicodeDecodeError` e JSON inválido em `ErroSnapshot`
    - `apagar()`: remover `estado.json` e `estado.json.tmp`, ausentes não são erro
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 3.1, 3.4, 4.9, 5.3_

  - [x]* 3.4 Escrever teste de propriedade da ida e volta
    - Em `scripts/tests/test_estado_demo.py` (novo), com geradores de `datetime` com fusos e microssegundos, `Decimal` finitos, `Literal`, `tuple`, dataclasses aninhadas e `dados` JSON-nativos
    - **Property 1: Ida e volta do Estado_Persistido**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6**

  - [x]* 3.5 Escrever teste de propriedade da exclusão de segredos e catálogo
    - **Property 2: Usuários, hashes, sessões e catálogo ficam fora do snapshot**
    - **Validates: Requirements 4.7, 4.8, 5.4**

  - [x]* 3.6 Escrever teste de propriedade para tipos desconhecidos
    - **Property 3: Valor de tipo desconhecido não corrompe o snapshot**
    - **Validates: Requirements 4.9**

  - [x]* 3.7 Escrever teste de propriedade para snapshot inválido (`ler_estado`)
    - Corromper um snapshot válido (truncar, JSON malformado, versão diferente ou ausente, campo removido, campo desconhecido, tipo trocado, `Literal` fora do domínio, `datetime` sem fuso)
    - **Property 4: Snapshot inválido é rejeitado sem alteração** (parte do Serializador)
    - **Validates: Requirements 2.6, 4.11**

  - [x]* 3.8 Escrever teste de propriedade da gravação atômica
    - Injetar falhas na escrita do temporário e no `os.replace`
    - **Property 5: Gravação atômica**
    - **Validates: Requirements 1.3, 1.4, 5.3**

  - [x]* 3.9 Escrever testes unitários do módulo
    - `{f.name for f in fields(Repositorios)} == PERSISTIDOS | EXCLUIDOS`
    - Diretório criado com os pais, `ensure_ascii=False` preservando acentos, `apagar()` sem arquivos
    - Gravação concorrente (várias threads) produz JSON válido e igual ao estado final
    - _Requirements: 1.6, 1.7, 4.7, 4.8, 12.2_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Integração no `scripts/dev_local.py`
  - [x] 5.1 Gravar o snapshot no Handler
    - Adicionar `DIR_DADOS_DEMO`, `METODOS_LEITURA` e `_RAIZ / "scripts"` ao `sys.path`; importar `estado_demo`
    - `construir_handler(..., persistencia: Persistencia | None = None)` com default `None` (a fixture atual de `test_dev_local.py` continua válida)
    - `_api()` passa a devolver `(status, cabecalhos, corpo)`; `_tratar` chama `persistencia.gravar(app.repos)` para métodos fora de GET/HEAD **antes** de `_responder`
    - _Requirements: 1.1, 1.2, 1.5, 1.6_

  - [x] 5.2 Implementar `iniciar_estado`, `--resetar` e as mensagens de `main`
    - `iniciar_estado(app, senha, persistencia, *, resetar, com_demo) -> str`: apagar se `resetar`; com snapshot, `carregar()` antes de `popular(com_demo=False)` e `aplicar_estado`; sem snapshot, `popular(com_demo)` e gravar o snapshot inicial; devolver `carregado`, `novo` ou `resetado`
    - `main(argv=None, *, dir_dados=DIR_DADOS_DEMO)`: opção `--resetar`; `ErroSnapshot` vira mensagem em `stderr` com caminho do arquivo e sugestão `--resetar`, retorno `2`, arquivo intacto
    - Mostrar o caminho do Snapshot no `help` e na mensagem de início; trocar a docstring do módulo e o banner que dizem que os dados somem ao reiniciar
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1, 3.2, 3.3, 3.4, 3.5, 5.1, 5.2, 5.5, 5.6, 6.2, 6.3_

  - [x]* 5.3 Escrever testes por exemplo de `scripts/tests/test_dev_local.py`
    - Usar diretório temporário (`tmp_path`/`dir_dados`), sem tocar o `.dados-demo/` do repositório
    - Cobrir: POST grava o snapshot antes da resposta; GET e HEAD não alteram bytes nem `mtime`; primeira subida cria os 3 Chamados de exemplo e o snapshot inicial; `--sem-demo`; segunda subida não recria exemplos; `--resetar` (com e sem `--sem-demo`, sem snapshot); snapshot inválido devolve 2 e não altera o arquivo; falha de gravação injetada ainda responde com o status calculado; login após reiniciar (cookie antigo dá 401, nova `CS_SENHA_INICIAL` entra, perfis preservados); estresse com 8 threads
    - _Requirements: 1.1, 1.2, 1.5, 1.6, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 3.1, 3.2, 3.3, 3.4, 3.5, 5.2, 5.5, 5.6, 12.1, 12.8_

  - [x]* 5.4 Escrever teste de propriedade de reinício
    - Hypothesis sobre `processar` com relógio injetado e persistência ligada; recriar a aplicação com `iniciar_estado` no mesmo diretório
    - **Property 6: Reiniciar preserva o estado**
    - **Validates: Requirements 2.1, 2.4, 7.5, 7.6, 7.7, 9.8**

  - [x]* 5.5 Escrever teste de propriedade de `--resetar`
    - **Property 7: `--resetar` descarta qualquer estado anterior**
    - **Validates: Requirements 3.1, 3.2, 3.4**

  - [x]* 5.6 Escrever teste de propriedade das operações condicionais após recarga
    - **Property 8: Operações condicionais continuam valendo depois de recarregar**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.4**

  - [x]* 5.7 Escrever teste de propriedade de colisão de números
    - Gerador de números que devolve primeiro um número já carregado
    - **Property 9: Número novo não colide com os carregados**
    - **Validates: Requirements 2.9**

  - [x]* 5.8 Escrever teste de propriedade para snapshot inválido em `main`
    - `main(..., dir_dados=tmp)` com arquivo corrompido devolve código diferente de zero, mensagem com o caminho e `--resetar`, arquivo byte a byte igual
    - **Property 4: Snapshot inválido é rejeitado sem alteração** (parte do `main`)
    - **Validates: Requirements 2.6, 2.7**

- [x] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. API de métricas
  - [x] 7.1 Implementar `services/api/servicos/metricas_chamados.py`
    - Função pura `calcular_metricas(chamados, obter_jornada, titulos_problemas)` com `ROTULO_NAO_INFORMADO`, `PRIORIDADES` e `DESFECHOS`
    - Regras: abertos vs encerrados; `por_problema` e `por_modelo` só com quantidade maior que zero, ordenados por quantidade decrescente e rótulo crescente; `por_prioridade` sempre P1/P2/P3; `por_desfecho` só encerrados, sempre `falso_defeito` e `defeito_real`, mais `nao_informado` apenas se maior que zero; rótulo `Problema {id}` quando o catálogo não conhece o id
    - Chaves de primeiro nível fechadas; nunca copiar telefone, CEP, mensagem nem resumo
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.9, 9.10, 9.13, 9.14_

  - [x] 7.2 Implementar a rota `services/api/routes/cs_metricas.py`
    - `@exigir_perfil("gestor")`, cache de Jornadas por requisição, títulos do catálogo com aviso no log se `ErroRepositorio`, e `ROTAS = [Rota("GET", "/metricas", metricas, escopo="cs", nome="cs_metricas")]`
    - Deixar `Rota.perfis = None` para a matriz existente decidir; não alterar a matriz nem `infra/`
    - _Requirements: 9.1, 9.8, 9.11, 9.12, 9.15_

  - [x]* 7.3 Escrever teste de propriedade dos invariantes das contagens
    - Em `services/api/tests/test_metricas_chamados.py` (novo)
    - **Property 11: Invariantes das contagens de métricas**
    - **Validates: Requirements 9.1, 9.2, 9.5, 9.6, 9.9, 9.10**

  - [x]* 7.4 Escrever teste de propriedade do agrupamento por Jornada
    - Incluir Jornadas sem `problema_id`, sem `modelo_id` e inexistentes
    - **Property 12: Agrupamento correto por Jornada**
    - **Validates: Requirements 9.3, 9.4, 9.7**

  - [x]* 7.5 Escrever teste de propriedade de vazamento de dados
    - Em `services/api/tests/test_rotas_cs_metricas.py` (novo)
    - **Property 13: A resposta de métricas não vaza dados**
    - **Validates: Requirements 9.13, 9.14**

  - [x]* 7.6 Escrever teste de propriedade da autorização
    - **Property 14: Autorização da rota de métricas**
    - **Validates: Requirements 9.11, 9.12, 9.15**

  - [x]* 7.7 Escrever testes por exemplo da rota de métricas
    - Gestor 200, Atendente 403, sem sessão 401, sem Chamados com totais zero e soma consistente
    - _Requirements: 9.1, 9.9, 9.10, 9.11, 9.12, 12.5_

- [x] 8. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Tela de métricas no front-end
  - [x] 9.1 Substituir o placeholder `apps/web/src/cs/MetricasCs.tsx`
    - Seguir o padrão de `FilaCs.tsx` (`apiCs.get`, estados `carregando | erro | pronto`, ref `montado`)
    - `h1` "Métricas" em todas as fases; `role="status"` ao carregar; `role="alert"` com botão "Tentar de novo" no erro; `<dl>` com abertos e encerrados; quatro `<section>` com `<h2>` e `<table aria-labelledby>` com `<th scope="col">`; barras com `aria-hidden` e o número sempre em texto; mensagem "Não há chamados para esta dimensão." quando não há linha com quantidade maior que zero
    - `formatarRotulo` para `nao_informado`, `falso_defeito` e `defeito_real`
    - Criar `metricas.css` reaproveitando `--espaco` e `--cor-borda`, sem depender só de cor
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.8_

  - [x] 9.2 Ajustar `apps/web/src/cs/PainelCs.test.tsx`
    - Adicionar o handler `"GET /api/cs/metricas"` no caso do Gestor (o helper `simular` falha com requisição inesperada)
    - Manter o caso do Atendente sem esse handler, provando que a API não é chamada
    - _Requirements: 10.1, 10.7, 12.7_

  - [x]* 9.3 Escrever `apps/web/src/cs/MetricasCs.test.tsx`
    - Vitest + Testing Library + jest-axe, sem nova dependência: carregamento, sucesso (totais e uma tabela por dimensão com rótulo e número em texto), erro com "Tentar de novo" levando a sucesso, dimensão vazia, `it.each` com payloads variados e axe sem violações
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.8, 12.6_

- [x] 10. Configuração e documentação
  - [x] 10.1 Atualizar o `.gitignore`
    - Adicionar a linha `.dados-demo/` ao lado de `.venv-demo/`
    - _Requirements: 6.1_

  - [x] 10.2 Reescrever os pontos de `docs/DEMO.md`
    - Fluxo do Consumidor começando em `http://localhost:5173/` (pesquisa de modelo) e QR `/m/tres-passione?s=DEMO001` como entrada alternativa
    - Dados persistem em `.dados-demo/estado.json`; documentar `--resetar` (apaga o estado e recria os 3 Chamados de exemplo) ao lado de `--porta` e `--sem-demo`
    - Sessões do Painel_CS não persistem (login após reiniciar); citar `/cs/metricas` do Gestor
    - Remover "os dados somem ao reiniciar" e "Reiniciou a API: ... abra o QR de novo"
    - Avisar que o snapshot pode conter telefone e CEP e que `.dados-demo/` fica fora do Git
    - Acrescentar os comandos de teste focado
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

- [ ] 11. Verificação final (somente testes relacionados)
  - [x] 11.1 Rodar os testes relacionados
    - Python: `scripts/tests/test_dev_local.py`, `scripts/tests/test_estado_demo.py`, `test_repositorios_memoria`, `test_repositorios_contrato`, `test_chamados_dynamodb_listar_todos`, `test_servico_escalada`, `test_rotas_cs_chamados`, `test_rotas_cs_metricas`, `test_metricas_chamados`, `test_autenticacao_cs`, `test_script_criar_usuarios_cs`
    - Front: `npx vitest --run src/cs/PainelCs.test.tsx src/cs/MetricasCs.test.tsx`
    - Não rodar a suíte completa; corrigir qualquer falha encontrada
    - _Requirements: 12.7_

  - [x] 11.2 Conferir o roteiro do `docs/DEMO.md` contra a implementação
    - Verificar com `grep` cada item do Requirement 11 e que as opções citadas (`--resetar`, `--porta`, `--sem-demo`), o caminho `.dados-demo/estado.json` e as rotas (`/`, `/m/tres-passione?s=DEMO001`, `/cs/metricas`) batem com `dev_local.py` e `rotas.tsx`
    - Verificar com `git check-ignore .dados-demo/estado.json` que o diretório está ignorado
    - _Requirements: 6.1, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8_

  - [x] 11.3 Conferir o escopo (sem `infra/` nem AWS)
    - `git diff --stat -- infra services/api/tests/_tabelas_dynamodb.py` vazio e `grep -rn gsi_todos infra services` sem resultados
    - _Requirements: 8.5, 8.8_

- [x] 12. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notas

- Tarefas marcadas com `*` são opcionais (testes) e podem ser puladas para um MVP mais rápido.
- Cada tarefa referencia os requisitos específicos para rastreabilidade.
- Os testes de propriedade (Hypothesis) validam as propriedades de correção do design; os testes por exemplo cobrem servidor, tela e erro explícito do adaptador.
- A tarefa 9.2 não é opcional: sem o handler de métricas, o teste existente do Gestor falha.
- Nenhuma tarefa altera `infra/` nem acessa a AWS.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "10.1"] },
    { "id": 1, "tasks": ["1.2", "1.3", "1.4", "3.1", "7.1", "9.1"] },
    { "id": 2, "tasks": ["1.5", "3.2", "3.4", "7.2", "7.3", "9.2", "9.3"] },
    { "id": 3, "tasks": ["3.3", "3.5", "7.4", "7.7"] },
    { "id": 4, "tasks": ["3.6", "5.1", "7.5"] },
    { "id": 5, "tasks": ["3.7", "5.2", "7.6", "10.2"] },
    { "id": 6, "tasks": ["3.8", "5.3"] },
    { "id": 7, "tasks": ["3.9", "5.4"] },
    { "id": 8, "tasks": ["5.5"] },
    { "id": 9, "tasks": ["5.6"] },
    { "id": 10, "tasks": ["5.7"] },
    { "id": 11, "tasks": ["5.8"] },
    { "id": 12, "tasks": ["11.1", "11.2", "11.3"] }
  ]
}
```
