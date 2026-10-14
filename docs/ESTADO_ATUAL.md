# Estado atual do projeto

Resumo curto do que o projeto é hoje. Onde este documento e o restante do README ou das specs divergirem, vale este (foi escrito lendo o código).

## 1. O que mudou: sem AWS e sem IA

- **Sem AWS.** O projeto roda inteiro na sua máquina com `scripts/dev_local.py`. A API é a mesma de `services/api`, mas os repositórios ficam **em memória** (`services/api/repositorios/memoria.py`). O estado é salvo num snapshot em `.dados-demo/estado.json` (fora do Git), que sobrevive a reinícios da API.
- **Legado, não apagado.** A pasta `infra/` (CDK em Python, stacks de dados, API, borda, armazenamento e conhecimento), o adaptador DynamoDB (`services/api/repositorios/dynamodb/`) e os scripts de deploy continuam no repositório só como referência. Nada disso é necessário para rodar a demo.
- **Sem IA.** O assistente deixou de ser ponto de entrada. No front, o painel provisório "Fale com o assistente" (que só mostrava "em breve") foi substituído pelo formulário. O código do agente (`services/agente/` e as peças da API) **não foi apagado**, mas nenhuma tela do portal o usa.
- **No lugar do assistente entra o formulário "Abrir chamado"** (`/abrir-chamado`), alcançado por dois caminhos:
  - "Meu problema não está na lista" (Não listados), na tela da máquina;
  - botão "Abrir chamado" na Jornada de qualquer um dos 13 fluxos do guia.

  Não há mais link para ele no início/rodapé do portal.

## 2. Como o chamado é aberto

Arquivos: `apps/web/src/paginas/AbrirChamado.tsx` e `apps/web/src/api/abrirChamado.ts`. Só usa rotas públicas que já existiam:

1. `POST /jornadas` cria a Jornada.
2. `POST /jornadas/{id}/escalar` com motivo `pedido_humano` cria o Chamado na fila do CS e devolve o protocolo (`TRES-...`).
3. `POST /chamados/{numero}/mensagens` envia as respostas do formulário (assunto, urgência, nome, descrição, quando começou, o que já tentou) e a linha **Origem**, com o contexto de onde o cliente veio (fluxo/modelo).
4. `POST /chamados/{numero}/contato` envia o telefone, com consentimento.

Se um passo falhar, "tentar novamente" retoma do passo que falhou, sem duplicar o chamado. Na confirmação, o cliente vê o protocolo e a mensagem de que a equipe retornará o contato em breve.

### Como rodar

```bash
# uma vez
python3 -m venv .venv-demo
.venv-demo/bin/pip install -e packages/dominio argon2-cffi jsonschema boto3
cd apps/web && npm install && cd ..

# terminal 1: API em http://127.0.0.1:8000
.venv-demo/bin/python scripts/dev_local.py

# terminal 2: front em http://localhost:5173
cd apps/web && npm run dev
```

Mais detalhes em [`DEMO.md`](DEMO.md).

## 3. Como o risco e a prioridade são validados

Tudo é **regra fixa em Python, sem IA**. A mesma entrada dá sempre a mesma saída. Há três peças:

| Peça | Arquivo | Papel |
|------|---------|-------|
| Detector de risco | `packages/dominio/src/dominio/risco.py` | Diz se um texto tem palavra de risco de segurança |
| Marcação de risco | `services/api/servicos/escalada.py` (`marcar_risco`, `escalar`) | Grava o risco na Jornada e abre a escalada P1 |
| Motor de escalada | `packages/dominio/src/dominio/escalada.py` (`decidir_escalada`) | Escolhe P1, P2 ou P3 |

### 3.1 Detector de risco (`detectar_risco`)

- Procura termos numa lista, de forma determinística.
- Antes de comparar, o texto e os termos são normalizados: minúsculas, sem acentos, pontuação vira espaço. Então "FUMAÇA!" e "fumaca" são iguais.
- O termo precisa aparecer como **palavra ou expressão inteira**. "choque" casa, "choquei" não.
- **Negação não desliga a detecção.** "não sai fumaça" também conta como risco, por segurança.
- Lista inicial (`TERMOS_RISCO_PADRAO`): `queimado`, `cheiro de queimado`, `fumaca`, `choque`, `faisca`, `vazamento interno`.
- A função aceita uma lista própria no lugar da padrão (a spec prevê guardá-la na tabela `config`). A lista final **ainda precisa ser validada pela 3corações**.
- `pede_atendimento_humano` faz o mesmo tipo de busca para pedidos como "atendente", "falar com uma pessoa" e "humano".

### 3.2 Marcação de risco (`marcar_risco`)

- A origem do risco é `lista` (termo detectado), `ia` ou `guia` (por exemplo, o cliente diz que o vazamento é interno).
- A marcação é **monotônica**: depois de marcada, o risco não é removido.
- Cada Jornada tem **uma única escalada P1**. Chamar de novo não cria outro Chamado.
- Se o repasse ao CS falhar, a marcação de risco continua valendo (segurança primeiro).

### 3.3 Motor de escalada (`decidir_escalada`)

Só dois fatos entram na decisão: `risco_seguranca` e `guia_respondeu_nao` (o cliente respondeu "Não" a uma instrução do guia). Horário, sentimento, ordem dos gatilhos e texto livre não mudam o resultado.

| Critério | Condição | Prioridade | Classificação | Canal |
|----------|----------|------------|---------------|-------|
| 1 | `risco_seguranca` | **P1** | provável defeito | ligação imediata |
| 2 | sem risco e `guia_respondeu_nao` | **P2** | provável defeito | chat ou ligação, à escolha do cliente |
| 3 | demais casos | **P3** | provável uso | chat assíncrono |

Precedência: P1 > P2 > P3. `reavaliar_prioridade` só **sobe** a prioridade, nunca reduz (um P3 vira P1 se o risco aparecer depois).

### Exemplo

O cliente diz "sai cheiro de queimado da máquina". Se o sistema marca o risco, a Jornada passa a ter `risco_seguranca = True`, o critério 1 vale e o Chamado nasce **P1** com ligação imediata, mesmo que o cliente também tenha respondido "Não" no guia. Se o cliente apenas respondeu "Não" ao guia e não há risco, o Chamado nasce **P2**. Sem nenhum dos dois, **P3**.

### 3.4 Limitação conhecida: o formulário "Abrir chamado" nasce como P3

Confirmado no código:

- `abrirChamado.ts` escala com `pedido_humano` e não chama `detectar_risco` nem `marcar_risco`.
- A rota `escalar_jornada` (`services/api/routes/resolucao.py`) só chama `marcar_risco` quando o motivo é `risco`.
- Fora do formulário, hoje o risco só é marcado pela resposta "interno" na pergunta de vazamento do guia. Nenhum código da API chama `detectar_risco` (só o pacote de domínio e os testes).
- A urgência escolhida no formulário ("Alta", por exemplo) vai **apenas como texto** na mensagem ao CS e não altera a prioridade.

Resultado: chamados abertos pelo formulário nascem **P3**, a menos que a Jornada já tivesse risco ou "Não" no guia antes. Quem atende lê a urgência e a descrição na mensagem.

**Próximo passo (não feito):** rodar `detectar_risco` sobre a descrição no envio do formulário e, se der verdadeiro, chamar `marcar_risco`. Opcionalmente, mapear a urgência "Alta" para uma revisão manual.
