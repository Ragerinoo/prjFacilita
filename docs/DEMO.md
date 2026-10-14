# Demo local (sem AWS)

Roda a API real (`services/api`) com repositórios em memória e o front-end Vite na sua máquina.
Sem IA: é o plano B da demo (pesquisa de modelo → guia → Chamado → Painel_CS).
O estado da demo fica salvo em `.dados-demo/estado.json` e sobrevive a reinícios da API.

> Somente para demo. A senha é conhecida e o cookie de sessão perde o atributo `Secure`
> para funcionar em `http://localhost`. Não exponha esta porta na rede.

## 1. Preparar (uma vez)

Na raiz do repositório:

```bash
python3 -m venv .venv-demo
.venv-demo/bin/pip install -e packages/dominio argon2-cffi jsonschema boto3
cd apps/web && npm install && cd ..
```

`.venv-demo` está no `.gitignore`. Se o `.venv-demo` já existe e funciona, pule este passo.

## 2. Subir (dois terminais)

Terminal 1, API local em `http://127.0.0.1:8000`:

```bash
.venv-demo/bin/python scripts/dev_local.py
```

Terminal 2, front-end em `http://localhost:5173` (o Vite repassa `/api` e `/midia` para a porta 8000):

```bash
cd apps/web && npm run dev
```

Opções do servidor:

- `--porta 8000`: porta da API.
- `--sem-demo`: não cria os 3 Chamados de exemplo nem a semente de dados da tela de Insights (na primeira subida
  ou junto com `--resetar`).
- `--resetar`: apaga o estado salvo (`.dados-demo/estado.json`) e recomeça do zero, recriando os 3 Chamados de
  exemplo e a semente de dados da tela de Insights. Com `--resetar --sem-demo`, recomeça sem os exemplos e sem a
  semente.

A senha vem de `CS_SENHA_INICIAL` ou, se vazia, de `demo-tres-2025`.

## 3. Persistência dos dados

- Chamados, Jornadas, mensagens e demais dados da demo são gravados em `.dados-demo/estado.json` depois de cada
  requisição que altera algo (POST, PUT, PATCH, DELETE) e recarregados quando a API sobe de novo.
  Reiniciar a API não perde o que já foi feito.
- Os 3 Chamados de exemplo só são criados na primeira subida (ou com `--resetar`). Nas subidas seguintes a API
  mantém apenas o que está no arquivo.
- A semente de dados da tela de Insights (Jornadas, Chamados e avaliações **fictícios**, para a tela
  `/cs/insights` não aparecer vazia) segue a mesma regra: só é criada na primeira subida ou com `--resetar`, e
  apenas quando o servidor sobe por `python scripts/dev_local.py`. Ela fica salva no `estado.json` junto com o resto.
- **Importante para quem já tem `.dados-demo/estado.json`:** a semente só aparece depois de subir com `--resetar`.
  Esse comando **APAGA o estado salvo** (Chamados, mensagens e o que mais tiver sido feito na demo) e recomeça do
  zero. Sem `--resetar`, a API carrega o arquivo como está e `/cs/insights` mostra apenas os dados que já existiam.
- As sessões do Painel_CS **não** persistem: depois de reiniciar a API é preciso fazer login de novo.
  Os usuários `atendente` e `gestor` são recriados a cada subida com a senha vigente.
- Para recomeçar do zero, suba com `--resetar`:

  ```bash
  .venv-demo/bin/python scripts/dev_local.py --resetar
  ```

- Se o arquivo de estado estiver corrompido, a API não sobe e mostra o caminho do arquivo (que fica intacto).
  Use `--resetar` para recomeçar.

> Atenção: o `estado.json` pode conter telefone e CEP digitados na demo. A pasta `.dados-demo/` está no
> `.gitignore` e fica fora do Git. Não copie nem compartilhe esse arquivo, e use apenas dados fictícios.

## 4. Roteiro da demo

1. Abra `http://localhost:5173/` (pesquisa de modelo): digite o nome da máquina (por exemplo, "Passione") ou escolha pela foto.
   - Entrada alternativa: o QR da máquina abre direto `http://localhost:5173/m/tres-passione?s=DEMO001`.
2. Escolha um dos 13 problemas (por exemplo, "Máquina não está ligando") e siga os passos do guia.
3. Em "O problema foi solucionado?", responda **Não**. Isso cria o Chamado (prioridade P2) e mostra o número `TRES-...`.
4. Informe telefone/CEP (opcional, com consentimento) e, se quiser, uma foto.
5. Para mostrar o risco: escolha o problema de vazamento e responda que é interno. O alerta fica fixo no topo e o Chamado sai como P1.
6. Painel_CS: `http://localhost:5173/cs/login`
   - usuário `atendente` (ou `gestor`, que também vê as métricas e os Insights)
   - senha `demo-tres-2025` (ou o valor de `CS_SENHA_INICIAL`)
   - Depois do login a tela inicial é o **Dashboard**, em `http://localhost:5173/cs` (não é mais a fila). Se você
     tentou abrir antes uma página interna do painel (por exemplo, um Chamado), o login volta para ela.
   - O menu tem **Dashboard**, **Fila de chamados** e, só para o `gestor`, **Métricas** e **Insights**.
   - O Dashboard mostra, de cima para baixo:
     - **Visão geral:** 6 cards com contagens de todos os Chamados (sem filtro de data): Chamados abertos, Em
       atendimento, Encerrados, P1 de risco abertos, Sem responsável e Respostas não lidas. "P1 de risco abertos"
       conta Chamados P1 **e** de risco; as três últimas contagens olham só Chamados ainda não encerrados.
     - **Satisfação (só Gestor):** dois cards a mais, "Nota média" e "Tempo médio até assumir", ambos dos últimos
       7 dias. Se não houver dados no período aparece "sem dados".
     - **Abas (só Gestor):** "Insights" (padrão) e "Chamados em foco". A aba escolhida vai para o endereço:
       `/cs?aba=insights` e `/cs?aba=chamados` abrem a aba direto. Sem `aba` ou com um valor inválido abre
       "Insights". As abas funcionam por teclado (setas, Home e End).
     - **Atendente:** não há abas nem cards de satisfação; a tela mostra só "Chamados em foco", e
       `?aba=insights` não muda isso. O Atendente nunca consulta a API de Insights.
   - **Aba "Insights":** o mesmo conteúdo de `/cs/insights` (veja o passo 10), inclusive o seletor de Período.
   - **Aba "Chamados em foco":** lista os Chamados ainda não encerrados que pedem atenção, cada um com prioridade,
     número (link para o Chamado), status, modelo, problema, idade e o(s) **motivo(s) em texto**:
     - "P1 ou risco": o Chamado é P1 **ou** teve risco marcado na Jornada;
     - "Resposta não lida": o Consumidor respondeu e o Painel ainda não leu;
     - "Sem responsável": ninguém assumiu o Chamado;
     - "Parado há mais de 60 min": está em atendimento e o responsável assumiu há 60 minutos ou mais.

     A ordem é fixa: motivo mais urgente (na sequência acima), depois prioridade (P1, P2, P3), depois o mais antigo
     primeiro e, por fim, o número. A lista mostra no máximo **10** itens; havendo mais, aparece "Mostrando N de M
     chamados em foco". O link **"Ver fila completa"** leva a `/cs/fila`. Sem Chamados em foco, a tela diz
     "Nenhum chamado pede atenção agora".
   - **Atualização automática:** os dados do Dashboard são recarregados a cada **10 s** (o mesmo intervalo da
     fila), sem piscar, e a atualização pausa enquanto a aba do navegador está oculta. Se uma atualização
     falhar, os últimos dados continuam na tela com um aviso e a API tenta de novo no próximo ciclo. O horário
     ("Atualizado às HH:MM:SS") mostra quando a API gerou os dados. O Dashboard roda no modo local, então
     aparece o aviso **"Dados de demonstração"**.
   - Com a semente (primeira subida ou `--resetar`, veja a seção 3), o Dashboard já abre com Chamados em foco: os
     4 Chamados abertos da semente não têm responsável, um deles é um P1 de risco criado hoje, outro tem resposta
     não lida e um Chamado em atendimento está parado há mais de 100 minutos. Esses motivos mudam conforme você
     usa a demo: assumir tira "Sem responsável", enviar mensagem tira "Resposta não lida" e encerrar tira o
     Chamado do foco. A semente não é refeita sozinha nas subidas seguintes.
7. Abra a **Fila de chamados** (menu ou "Ver fila completa" no Dashboard). O P1 aparece primeiro com alerta. Abra o Chamado (também dá para entrar pelo número na lista "Chamados em foco"), clique em "Assumir" e em "Ver contato" (grava o acesso antes de mostrar o dado). Envie uma mensagem, agende uma ligação e encerre com Desfecho e solução. Ao voltar ao Dashboard, as contagens refletem a mudança em até 10 s.
8. Volte à página `/chamado/<numero>` do Consumidor: a mensagem aparece em até 5 s.
9. Como `gestor`, abra `http://localhost:5173/cs/metricas` (link "Métricas" no menu): totais de Chamados abertos e
   encerrados, e contagens por problema, modelo, prioridade e desfecho. O Atendente não acessa essa tela.
10. Ainda como `gestor`, abra `http://localhost:5173/cs/insights` (link "Insights" no menu; a URL correta é
    `/cs/insights`). O mesmo conteúdo aparece na aba "Insights" do Dashboard (`/cs`). Com um erro de digitação
    na URL (por exemplo, `/cs/inshigts`) o painel mostra "Página não encontrada" dentro do próprio layout.
    O Atendente não vê o link e, se abrir a URL, recebe "Acesso negado". Para a demo não ficar
    vazia, suba a API com a semente (primeira subida ou `--resetar`, veja a seção 3).
    - No topo aparece o aviso **"Dados de demonstração"**: a API está no modo local e os números vêm de dados
      fictícios, não de atendimentos reais.
    - **Período:** o seletor oferece Hoje, 7 dias (padrão), 30 dias e Personalizado. No personalizado, informe
      data inicial e final e clique em "Aplicar"; a data final não pode ser anterior à inicial e o intervalo vai
      até 90 dias. As datas são em UTC. Trocar o período recarrega todos os blocos.
    - **Cards:** nota média e total de avaliações, tempo até assumir e até encerrar (média e mediana), Chamados P1
      de risco (com quantos ainda não foram encerrados) e percentual de falso defeito.
    - **Distribuição das notas:** gráfico de barras de 1 a 5 estrelas, com a tabela equivalente logo abaixo.
    - **Falso defeito x defeito real:** gráfico do desfecho dos Chamados encerrados, também com tabela.
    - **Problemas mais frequentes:** ranking dos problemas mais pesquisados, com número de Chamados, percentual de
      falso defeito e a solução mais registrada para cada um.
    - **Comentários recentes:** até 10 comentários das avaliações do período, com dados pessoais mascarados.
    - **Funil da jornada:** de onde vieram as Jornadas (QR ou busca) e quantas foram resolvidas no guia,
      escaladas para atendimento humano ou abandonadas. Some se a API não conseguir calcular o funil.
    - Blocos sem dados no período mostram "sem dados" ou "Não há dados para esta seção no período.".
    - Indicadores de IA (cache, modelo e custo) não aparecem: a demo roda sem IA.

## Problemas comuns

- Tela em branco ou erro de rede: confirme que o terminal 1 está de pé (`curl http://127.0.0.1:8000/api/pub/saude`).
- Login não mantém sessão: acesse por `http://localhost:5173`, não pelo IP da rede.
- Reiniciou a API e o Painel_CS pediu login: é esperado, as sessões não persistem. Entre de novo; os Chamados continuam lá.
- A API não sobe e cita `.dados-demo/estado.json`: o arquivo está ilegível. Suba com `--resetar` para recomeçar.

## Testes

Teste de fumaça do servidor local:

```bash
.venv-demo/bin/python -m pytest scripts/tests/test_dev_local.py -q
```

Testes focados da persistência e das métricas (somente os relacionados, sem a suíte completa):

```bash
.venv-demo/bin/python -m pytest \
  scripts/tests/test_dev_local.py scripts/tests/test_estado_demo.py \
  services/api/tests/test_repositorios_memoria.py services/api/tests/test_repositorios_contrato.py \
  services/api/tests/test_chamados_dynamodb_listar_todos.py services/api/tests/test_autenticacao_cs.py \
  services/api/tests/test_servico_escalada.py \
  services/api/tests/test_rotas_cs_chamados.py services/api/tests/test_rotas_cs_metricas.py \
  services/api/tests/test_metricas_chamados.py \
  services/api/tests/test_script_criar_usuarios_cs.py \
  scripts/tests/test_persistencia_reinicio.py packages/dominio/tests/test_metricas.py -q
```

Os testes novos das features de Insights e do Dashboard (serviços, rotas, semente e telas) entram nesta lista
conforme os arquivos forem criados. Conferido no disco: até agora não existe nenhum arquivo de teste específico
de Insights ou do Dashboard (nem `test_servico_dashboard.py`, `test_rotas_cs_dashboard.py`,
`test_semente_demo.py`, `Dashboard.test.tsx` ou `isolamentoGraficos.test.ts`). Os testes que cobrem o menu e a
rota `/cs` são os já existentes `PainelCs.test.tsx` e `rotas.test.tsx`, listados abaixo.

Front-end (a partir de `apps/web`):

```bash
cd apps/web && npx vitest --run src/cs/PainelCs.test.tsx src/cs/MetricasCs.test.tsx src/cs/FilaCs.test.tsx src/app/rotas.test.tsx
```

Depois de um build (`npm run build -- --manifest`), o script `scripts/verificar-chunks.mjs` confere que o Recharts
fica fora do pacote inicial e do chunk do Dashboard:

```bash
cd apps/web && node scripts/verificar-chunks.mjs
```

## Deploy na AWS (opcional)

Veja `scripts/deploy.sh` (CDK, build do site, S3, CloudFront e carga do seed). Segredos vêm do
ambiente da AWS; nada é lido do repositório.
