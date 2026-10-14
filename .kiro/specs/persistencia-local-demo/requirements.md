# Requirements Document

## Introduction

Hoje o servidor local de demonstração (`scripts/dev_local.py`) mantém todos os dados em repositórios em memória: ao reiniciar, os Chamados, as Jornadas e as mensagens somem. Esta feature faz o estado da demo sobreviver a reinícios e entrega um painel mínimo de métricas para o Gestor.

A persistência é um snapshot JSON atômico em `.dados-demo/estado.json`, gravado pelo Handler do `dev_local.py` depois de cada requisição diferente de GET. Os repositórios em memória continuam sendo a fonte de verdade em tempo de execução e a interface `Repositorios` não muda, com uma única exceção aditiva: o método `listar_todos`, que lista todos os Chamados (inclusive os encerrados), necessário para as métricas. O método é adicionado ao Protocol `ChamadosRepo` e implementado apenas no repositório em memória. O adaptador DynamoDB existente declara `listar_todos` somente para satisfazer o Protocol e levanta um erro explícito de indisponibilidade fora do Modo_Local. Não há SQLite.

Ao subir, o Servidor_Local recarrega o snapshot. Os Chamados de exemplo só são criados na primeira subida, quando não existe estado gravado. A opção `--resetar` apaga o estado e recomeça do zero. Os usuários do Painel_CS (`atendente` e `gestor`) são recriados por `popular()` com a senha de demonstração, sem hashes ou sessões no snapshot.

A feature também adiciona `GET /api/cs/metricas` (somente Gestor) com contagens simples e a tela `MetricasCs`, e atualiza `docs/DEMO.md`.

Fora do escopo: agente de IA, DynamoDB/AWS e deploy. Isso significa nenhuma mudança em `infra/`, em `dados_stack`, em índices (incluindo `gsi_todos`) nem em IAM, e nenhuma consulta Query ou Scan nova. A implementação real de `listar_todos` na camada AWS fica como pendência para quando essa camada entrar em escopo. Também ficam de fora das métricas: filtro de período, deflexão, custo, nota, ranking e configuração.

## Glossary

- **Servidor_Local**: processo iniciado por `scripts/dev_local.py` que roda a API real com repositórios em memória, somente para demonstração e desenvolvimento.
- **Handler**: classe `BaseHTTPRequestHandler` construída por `construir_handler` em `scripts/dev_local.py`, que converte cada requisição HTTP em evento da API e devolve a resposta.
- **Repositorios**: conjunto de repositórios definido em `services/api/repositorios/interfaces.py`, implementado em memória por `services/api/repositorios/memoria.py`.
- **Estado_Persistido**: conjunto de registros dos Repositorios incluídos no snapshot: Jornadas, Eventos, Chamados, Mensagens de Chamado, Dados Pessoais, Acessos a Dados Pessoais, Ordens de Serviço, Cache de Respostas, Avaliações, Agregados do Dia e Config.
- **Snapshot**: arquivo JSON que contém o Estado_Persistido em `.dados-demo/estado.json`.
- **Diretorio_Dados_Demo**: diretório `.dados-demo/` na raiz do repositório, que contém o Snapshot e o arquivo temporário de gravação.
- **Arquivo_Temporario**: arquivo criado no Diretorio_Dados_Demo, no mesmo sistema de arquivos do Snapshot, onde o novo conteúdo é escrito antes de substituir o Snapshot por `os.replace`.
- **Serializador**: módulo que converte o Estado_Persistido em JSON e reconstrói o Estado_Persistido a partir de JSON.
- **Chamado**: registro de escalada para atendimento humano (`Chamado` em `repositorios/modelos.py`) com status `aberto`, `em_atendimento` ou `encerrado`.
- **Chamado_Aberto**: Chamado cujo status é `aberto` ou `em_atendimento`.
- **Chamado_Encerrado**: Chamado cujo status é `encerrado`.
- **Jornada**: sessão do Consumidor, de onde o Chamado herda o `modelo_id` e o `problema_id`.
- **Desfecho**: valor `falso_defeito` ou `defeito_real` gravado no encerramento do Chamado.
- **Chamados_De_Exemplo**: os 3 Chamados fictícios criados por `_chamados_de_exemplo` em `scripts/dev_local.py`.
- **Usuarios_Demo**: os usuários `atendente` e `gestor` do Painel_CS, criados por `popular()`.
- **Senha_Demo**: senha vinda de `CS_SENHA_INICIAL` ou, se vazia, `demo-tres-2025`.
- **Painel_CS**: front-end de atendimento acessado em `/cs`.
- **Gestor**: usuário do Painel_CS com perfil `gestor`.
- **Atendente**: usuário do Painel_CS com perfil `atendente`.
- **Consumidor**: pessoa que usa o site público (pesquisa, QR, guia e Chamado).
- **API_Metricas**: rota `GET /api/cs/metricas` da API.
- **Tela_Metricas**: componente `MetricasCs` do front-end, exibido em `/cs/metricas`.
- **Contagem_Por_Dimensao**: lista de pares (rótulo, quantidade) para uma dimensão das métricas.
- **Rotulo_Nao_Informado**: rótulo `nao_informado` usado quando o Chamado não tem valor para a dimensão (por exemplo, Jornada sem `problema_id`).
- **Guia_Demo**: documento `docs/DEMO.md`.
- **Modo_Local**: modo de execução do Servidor_Local com Repositorios em memória, sem acesso à AWS.
- **Adaptador_DynamoDB**: classe `ChamadosDynamoDB` em `services/api/repositorios/dynamodb/chamados.py`, que implementa o ChamadosRepo sobre DynamoDB.
- **Erro_Indisponivel_Fora_Do_Modo_Local**: erro explícito levantado pelo Adaptador_DynamoDB em `listar_todos`, cuja mensagem informa que a consulta está indisponível fora do Modo_Local.
- **Teste_De_Contrato_Memoria**: teste de contrato de `test_repositorios_contrato.py` executado somente contra a implementação em memória do ChamadosRepo.

## Requirements

### Requirement 1

**User Story:** Como apresentador da demo, quero que os dados sobrevivam a reinícios do servidor local, para que eu possa derrubar e subir a API sem perder os Chamados e as Jornadas.

#### Acceptance Criteria

1. WHEN o Handler conclui o processamento de uma requisição cujo método HTTP é diferente de GET e de HEAD, THE Servidor_Local SHALL gravar o Snapshot com o Estado_Persistido atual antes de enviar a resposta ao cliente.
2. WHEN o Handler conclui o processamento de uma requisição GET ou HEAD, THE Servidor_Local SHALL manter o Snapshot sem alteração.
3. WHEN o Servidor_Local grava o Snapshot, THE Servidor_Local SHALL escrever o conteúdo completo no Arquivo_Temporario e, em seguida, substituir o Snapshot por `os.replace`.
4. IF a gravação do Arquivo_Temporario falha, THEN THE Servidor_Local SHALL remover o Arquivo_Temporario, registrar o erro no log do console e manter o conteúdo anterior do Snapshot.
5. IF a gravação do Snapshot falha, THEN THE Servidor_Local SHALL continuar atendendo requisições e responder ao cliente com o resultado já calculado.
6. WHEN duas requisições não-GET concluem ao mesmo tempo, THE Servidor_Local SHALL serializar as gravações do Snapshot para que cada Snapshot gravado represente um estado consistente dos Repositorios.
7. WHEN o Servidor_Local cria o Diretorio_Dados_Demo, THE Servidor_Local SHALL criá-lo na raiz do repositório com todos os diretórios pais necessários.
8. THE Repositorios SHALL manter as interfaces e o comportamento dos repositórios em memória existentes, com a única adição do método `listar_todos` definido no Requirement 8.

### Requirement 2

**User Story:** Como apresentador da demo, quero que o servidor recarregue o estado gravado ao subir, para que a demo continue de onde parou.

#### Acceptance Criteria

1. WHEN o Servidor_Local inicia e o Snapshot existe, THE Servidor_Local SHALL carregar o Estado_Persistido do Snapshot nos Repositorios antes de aceitar a primeira requisição.
2. WHEN o Servidor_Local inicia e o Snapshot não existe, THE Servidor_Local SHALL iniciar com Repositorios vazios, executar `popular()` e criar os Chamados_De_Exemplo.
3. WHEN o Servidor_Local inicia pela primeira vez e conclui `popular()`, THE Servidor_Local SHALL gravar o Snapshot inicial antes de aceitar a primeira requisição.
4. WHEN o Servidor_Local inicia e o Snapshot existe, THE Servidor_Local SHALL omitir a criação dos Chamados_De_Exemplo e manter apenas os Chamados presentes no Snapshot.
5. WHERE a opção `--sem-demo` está ativa e o Snapshot não existe, THE Servidor_Local SHALL iniciar sem criar os Chamados_De_Exemplo.
6. IF o Snapshot existe e contém JSON inválido ou estrutura que o Serializador não reconhece, THEN THE Servidor_Local SHALL encerrar a inicialização com código de saída diferente de zero e exibir mensagem que identifica o arquivo e sugere a opção `--resetar`.
7. IF o Snapshot existe e contém JSON inválido ou estrutura que o Serializador não reconhece, THEN THE Servidor_Local SHALL manter o arquivo do Snapshot sem alteração.
8. WHEN o Servidor_Local inicia e carrega o Snapshot, THE Servidor_Local SHALL recarregar o catálogo a partir de `seed/`, sem gravar o catálogo no Snapshot.
9. WHEN o Servidor_Local gera o número de um novo Chamado depois de carregar o Snapshot, THE Servidor_Local SHALL gerar um número distinto de todos os números dos Chamados carregados.

### Requirement 3

**User Story:** Como apresentador da demo, quero uma opção para apagar o estado gravado, para que eu possa recomeçar a demo do zero.

#### Acceptance Criteria

1. WHEN o Servidor_Local inicia com a opção `--resetar`, THE Servidor_Local SHALL apagar o Snapshot e o Arquivo_Temporario existentes antes de popular os Repositorios.
2. WHEN o Servidor_Local inicia com a opção `--resetar`, THE Servidor_Local SHALL popular os Repositorios com o mesmo procedimento da primeira subida, incluindo os Chamados_De_Exemplo, e gravar o Snapshot inicial.
3. WHERE as opções `--resetar` e `--sem-demo` estão ativas, THE Servidor_Local SHALL recomeçar sem criar os Chamados_De_Exemplo.
4. WHEN o Servidor_Local inicia com a opção `--resetar` e o Snapshot não existe, THE Servidor_Local SHALL concluir a inicialização sem erro.
5. WHEN o Servidor_Local inicia sem a opção `--resetar`, THE Servidor_Local SHALL manter o Snapshot existente sem apagar.

### Requirement 4

**User Story:** Como desenvolvedor, quero que o Snapshot represente fielmente todos os tipos do domínio, para que o estado recarregado seja idêntico ao estado gravado.

#### Acceptance Criteria

1. THE Serializador SHALL converter valores `datetime` com fuso em texto ISO 8601 que preserva o fuso e os microssegundos.
2. THE Serializador SHALL converter valores `Decimal` em texto que preserva todas as casas decimais, sem passar por ponto flutuante.
3. THE Serializador SHALL converter enums e valores `Literal` em seus valores primitivos.
4. THE Serializador SHALL converter dataclasses congeladas, incluindo dataclasses aninhadas, em objetos JSON e reconstruí-las com os mesmos tipos.
5. THE Serializador SHALL reconstruir campos declarados como `tuple` como `tuple`, e não como `list`.
6. FOR ALL Estado_Persistido válido, THE Serializador SHALL reconstruir, a partir do JSON gerado, um Estado_Persistido igual ao original (propriedade de ida e volta).
7. THE Serializador SHALL excluir do Snapshot os usuários do Painel_CS, os hashes de senha e as sessões.
8. THE Serializador SHALL excluir do Snapshot o catálogo de modelos, problemas e instruções.
9. IF o Serializador encontra um valor de tipo que não reconhece, THEN THE Serializador SHALL levantar um erro que identifica o campo e o tipo, e THE Servidor_Local SHALL manter o Snapshot anterior sem alteração.
10. THE Snapshot SHALL conter um campo de versão do formato.
11. IF o campo de versão do Snapshot difere da versão que o Serializador suporta, THEN THE Servidor_Local SHALL tratar o Snapshot como estrutura não reconhecida, conforme o Requirement 2.

### Requirement 5

**User Story:** Como apresentador da demo, quero entrar no Painel_CS com a senha de demonstração depois de reiniciar, sem guardar segredos no repositório.

#### Acceptance Criteria

1. WHEN o Servidor_Local inicia, THE Servidor_Local SHALL criar os Usuarios_Demo por `popular()` com hash gerado a partir da Senha_Demo vigente.
2. WHEN o Servidor_Local reinicia, THE Servidor_Local SHALL exigir novo login de todos os usuários do Painel_CS, pois as sessões não são persistidas.
3. THE Diretorio_Dados_Demo SHALL conter apenas o Snapshot e o Arquivo_Temporario.
4. THE Servidor_Local SHALL manter a Senha_Demo fora do Snapshot e fora de qualquer arquivo versionado novo desta feature.
5. WHEN o Servidor_Local reinicia com uma `CS_SENHA_INICIAL` diferente da anterior, THE Servidor_Local SHALL aceitar a nova senha para os Usuarios_Demo.
6. WHEN o Servidor_Local inicia com o Snapshot existente, THE Servidor_Local SHALL manter os Usuarios_Demo `atendente` e `gestor` com seus respectivos perfis.

### Requirement 6

**User Story:** Como mantenedor, quero que o `.dados-demo/` fique fora do controle de versão, para que dados de demonstração não vão para o repositório.

#### Acceptance Criteria

1. THE arquivo `.gitignore` SHALL conter uma entrada que ignora o diretório `.dados-demo/`.
2. THE Servidor_Local SHALL registrar em seu texto de ajuda e na mensagem de inicialização o caminho do Snapshot.
3. THE Servidor_Local SHALL substituir, na documentação do arquivo `scripts/dev_local.py` e na mensagem de inicialização, a afirmação de que os dados somem ao reiniciar.

### Requirement 7

**User Story:** Como mantenedor, quero que as garantias de atomicidade e idempotência continuem valendo depois de recarregar o estado, para que a demo não crie Chamados duplicados nem responsáveis conflitantes.

#### Acceptance Criteria

1. WHEN a escalada é solicitada para uma Jornada que já possui Chamado no Estado_Persistido recarregado, THE serviço de escalada SHALL devolver o Chamado existente sem criar um segundo Chamado para a Jornada.
2. WHEN `assumir` é solicitado para um Chamado que já possui responsável no Estado_Persistido recarregado, THE ChamadosRepo SHALL devolver `aplicado=False` com o responsável original.
3. WHEN `assumir` é solicitado para um Chamado sem responsável e não encerrado, THE ChamadosRepo SHALL gravar o responsável e o status `em_atendimento`.
4. WHEN `encerrar` é solicitado para um Chamado_Encerrado no Estado_Persistido recarregado, THE ChamadosRepo SHALL devolver `aplicado=False` e manter o encerramento original.
5. WHEN o Servidor_Local recarrega o Snapshot, THE Servidor_Local SHALL restaurar os registros diretamente nos Repositorios, sem repetir operações condicionais que alterariam horários, números ou responsáveis.
6. WHEN o Servidor_Local recarrega o Snapshot, THE ChamadosRepo SHALL listar a fila na mesma ordem de prioridade, horário de criação e número que tinha antes do reinício.
7. WHEN o Servidor_Local recarrega o Snapshot, THE MensagensChamadoRepo SHALL listar as mensagens de cada Chamado na mesma ordem cronológica que tinham antes do reinício.

### Requirement 8

**User Story:** Como Gestor, quero uma consulta de todos os Chamados no modo local, para que as métricas incluam os encerrados.

#### Acceptance Criteria

1. THE Protocol ChamadosRepo SHALL declarar o método `listar_todos`, que devolve todos os Chamados nos status `aberto`, `em_atendimento` e `encerrado`.
2. THE repositório de Chamados em memória SHALL implementar `listar_todos`.
3. THE ChamadosRepo SHALL manter inalterados os métodos existentes, incluindo `listar_fila`, que continua devolvendo apenas Chamados não encerrados.
4. WHEN `listar_todos` é chamado em um repositório em memória sem Chamados, THE repositório de Chamados em memória SHALL devolver uma lista vazia.
5. WHEN `listar_todos` é chamado no Adaptador_DynamoDB, THE Adaptador_DynamoDB SHALL levantar o Erro_Indisponivel_Fora_Do_Modo_Local sem executar nenhuma operação Query ou Scan e sem acessar a AWS.
6. THE Adaptador_DynamoDB SHALL declarar `listar_todos` somente para satisfazer o Protocol ChamadosRepo.
7. THE documentação do Adaptador_DynamoDB SHALL registrar que a implementação real de `listar_todos` é uma pendência para quando a camada AWS entrar em escopo.
8. THE feature SHALL manter sem alteração os arquivos de `infra/`, incluindo `dados_stack`, os índices existentes e as políticas de IAM, sem criar o índice `gsi_todos`.

### Requirement 9

**User Story:** Como Gestor, quero ver contagens de Chamados, para que eu acompanhe o volume e o perfil dos atendimentos durante a demo.

#### Acceptance Criteria

1. WHEN o Gestor autenticado envia `GET /api/cs/metricas`, THE API_Metricas SHALL responder 200 com o total de Chamados_Abertos e o total de Chamados_Encerrados.
2. WHEN o Gestor autenticado envia `GET /api/cs/metricas`, THE API_Metricas SHALL incluir uma Contagem_Por_Dimensao para cada uma das dimensões: problema, modelo, prioridade e Desfecho.
3. THE API_Metricas SHALL contar na dimensão problema todos os Chamados, agrupados pelo `problema_id` da Jornada do Chamado, com o título do problema vindo do catálogo.
4. THE API_Metricas SHALL contar na dimensão modelo todos os Chamados, agrupados pelo `modelo_id` da Jornada do Chamado.
5. THE API_Metricas SHALL contar na dimensão prioridade todos os Chamados, agrupados em P1, P2 e P3, incluindo as prioridades com contagem zero.
6. THE API_Metricas SHALL contar na dimensão Desfecho somente os Chamados_Encerrados, agrupados em `falso_defeito` e `defeito_real`, incluindo os Desfechos com contagem zero.
7. IF a Jornada do Chamado não possui valor para uma dimensão, THEN THE API_Metricas SHALL contar o Chamado sob o Rotulo_Nao_Informado nessa dimensão.
8. THE API_Metricas SHALL calcular as contagens a partir dos Chamados e Jornadas presentes nos Repositorios, o que inclui os registros recarregados do Snapshot.
9. FOR ALL resposta da API_Metricas, THE soma de Chamados_Abertos e Chamados_Encerrados SHALL ser igual à soma das contagens de cada dimensão problema, modelo e prioridade.
10. WHEN o Gestor envia `GET /api/cs/metricas` sem nenhum Chamado nos Repositorios, THE API_Metricas SHALL responder 200 com totais iguais a zero.
11. IF um Atendente autenticado envia `GET /api/cs/metricas`, THEN THE API_Metricas SHALL responder 403 sem nenhuma contagem.
12. IF uma requisição sem sessão válida envia `GET /api/cs/metricas`, THEN THE API_Metricas SHALL responder 401 sem nenhuma contagem.
13. THE API_Metricas SHALL omitir da resposta telefone, CEP, texto de mensagens e resumo do Pacote.
14. THE API_Metricas SHALL omitir da resposta filtro de período, deflexão, custo, nota, ranking e configuração.
15. THE API_Metricas SHALL ser classificada na matriz de autorização do Painel_CS como rota exclusiva do perfil `gestor`.

### Requirement 10

**User Story:** Como Gestor, quero uma tela simples de métricas no Painel_CS, para que eu leia as contagens sem ferramentas externas.

#### Acceptance Criteria

1. WHEN o Gestor abre `/cs/metricas`, THE Tela_Metricas SHALL solicitar `GET /api/cs/metricas` e exibir o total de Chamados_Abertos e o total de Chamados_Encerrados.
2. WHEN a API_Metricas responde 200, THE Tela_Metricas SHALL exibir cada Contagem_Por_Dimensao de problema, modelo, prioridade e Desfecho como tabela ou como barras simples, com o rótulo e a quantidade de cada linha.
3. WHILE a Tela_Metricas aguarda a resposta da API_Metricas, THE Tela_Metricas SHALL exibir um indicador de carregamento.
4. IF a API_Metricas responde com erro ou a requisição falha, THEN THE Tela_Metricas SHALL exibir uma mensagem de erro e um botão para tentar novamente.
5. WHEN uma Contagem_Por_Dimensao não possui nenhuma linha com quantidade maior que zero, THE Tela_Metricas SHALL exibir uma mensagem de que não há Chamados para essa dimensão.
6. WHERE a Tela_Metricas usa barras, THE Tela_Metricas SHALL exibir também o valor numérico de cada barra em texto.
7. WHEN o Atendente abre `/cs/metricas`, THE Painel_CS SHALL exibir a tela de acesso negado sem solicitar a API_Metricas.
8. THE Tela_Metricas SHALL exibir cada título de seção e cada tabela com rótulos acessíveis a leitores de tela.

### Requirement 11

**User Story:** Como apresentador da demo, quero o roteiro atualizado, para que o fluxo e o comportamento dos dados batam com a versão atual do servidor.

#### Acceptance Criteria

1. THE Guia_Demo SHALL descrever o início do fluxo do Consumidor em `http://localhost:5173/` (pesquisa de modelo).
2. THE Guia_Demo SHALL descrever o QR (`/m/tres-passione?s=DEMO001`) como entrada alternativa ao fluxo.
3. THE Guia_Demo SHALL informar que os dados persistem entre reinícios em `.dados-demo/estado.json`.
4. THE Guia_Demo SHALL documentar a opção `--resetar` e informar que ela apaga o estado e recria os Chamados_De_Exemplo.
5. THE Guia_Demo SHALL informar que as sessões do Painel_CS não persistem e que o login é necessário após reiniciar.
6. THE Guia_Demo SHALL citar a tela de métricas do Gestor em `/cs/metricas`.
7. THE Guia_Demo SHALL remover as afirmações de que os dados somem ao reiniciar e de que o reinício exige abrir o QR de novo.
8. THE Guia_Demo SHALL informar que o Snapshot pode conter telefone e CEP informados na demo e que o `.dados-demo/` fica fora do Git.

### Requirement 12

**User Story:** Como mantenedor, quero testes automatizados focados nas partes alteradas, para que a feature tenha cobertura sem rodar a suíte completa.

#### Acceptance Criteria

1. THE suíte de testes SHALL incluir testes de `scripts/tests/test_dev_local.py` para gravação atômica, recarga, primeira subida com Chamados_De_Exemplo, `--resetar`, Snapshot inválido e Snapshot inalterado em requisição GET.
2. THE suíte de testes SHALL incluir testes do Serializador para `datetime`, `Decimal`, enums e dataclasses congeladas, com a propriedade de ida e volta do Requirement 4.
3. THE suíte de testes de contrato (`test_repositorios_contrato.py`) SHALL incluir o Teste_De_Contrato_Memoria para `listar_todos`, executado somente contra a implementação em memória do ChamadosRepo, sem teste de contrato DynamoDB ou moto para o novo método.
4. THE suíte de testes SHALL incluir um teste unitário novo do Adaptador_DynamoDB que verifica que `listar_todos` levanta o Erro_Indisponivel_Fora_Do_Modo_Local sem acessar a AWS.
5. THE suíte de testes (`test_rotas_cs_chamados.py` ou arquivo novo de rotas) SHALL cobrir a API_Metricas para os casos de Gestor, Atendente, ausência de sessão, ausência de Chamados e soma consistente.
6. THE suíte de testes SHALL incluir um teste novo da Tela_Metricas que cobre carregamento, sucesso, erro com nova tentativa e dimensão vazia.
7. WHEN a verificação é executada, THE equipe SHALL rodar somente os testes relacionados: `test_repositorios_memoria`, `test_repositorios_contrato`, `test_servico_escalada`, `test_rotas_cs_chamados`, `test_autenticacao_cs`, `test_script_criar_usuarios_cs`, `scripts/tests/test_dev_local.py`, `PainelCs.test.tsx`, o teste novo da Tela_Metricas e o teste novo do Adaptador_DynamoDB.
8. THE testes do Servidor_Local SHALL usar um diretório temporário para o Diretorio_Dados_Demo, mantendo o `.dados-demo/` do repositório sem alteração.
