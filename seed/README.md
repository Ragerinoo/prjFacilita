# Seed de dados

Fonte da carga idempotente (Req 20.3). **Todo o conteúdo aqui é de exemplo** (marcado com `conteudo_exemplo: true` ou `_aviso`) até a 3corações fornecer instruções, mídia e manuais oficiais (Q20).

| Caminho | Conteúdo | Chave determinística |
|---------|----------|----------------------|
| `catalogo.json` | 3 modelos (`tres-passione` é o da demo) com `nome_normalizado`, `foto_url`, `voltagens`, `manuais` (caminhos relativos a `seed/`) | `modelo_id` |
| `problemas.json` | 13 Problemas_Catalogados na ordem do Req 3.1 | `problema_id` (1 a 13) |
| `instrucoes/<modelo_id>.json` | Passos por `(problema_id, variante)`; só o modelo da demo tem instruções | `modelo_id#problema_id#variante` |
| `seletor/<modelo_id>.json` | Mapa do Seletor_Visual (áreas em % da imagem, estados com rótulo, regras `(area, estado) -> problemas`) | `modelo_id` |
| `manuais/<modelo_id>/` | Manual (`.md`) e `<arquivo>.metadata.json` (formato de metadados do Bedrock Knowledge Base) | caminho do objeto |
| `midia/exemplo/` | Ilustrações SVG de espaço reservado (fotos, passos, seletor), servidas em `/midia/exemplo/...` | caminho |

## Convenções

- Variantes: `padrao` para todos os 13 problemas; `externo` só para o problema 10 (Vazamento, Req 3.11). Vazamento interno não tem passos (Req 3.8).
- Limites validados na carga: título <= 40, <= 10 passos, texto do passo <= 140, `alt` <= 125, `texto_equivalente` presente.
- Seletor: 2 a 5 estados por área, áreas sem sobreposição, tamanho mínimo 16% x 12% (garante 44x44 px CSS a partir de 320 px de largura), até 5 problemas por regra. Combinações sem regra resultam em "nenhum" (vai ao assistente). `alavanca + travada` devolve 2 problemas (exemplo de "múltiplos").
- O título do problema 4 está abreviado para "Teclas e sensor vermelho piscando" (33 caracteres): o texto do Req 3.1 ("Teclas das xícaras e sensor vermelho piscando") tem 45 e excede o limite de 40 do mesmo critério.
- Mídia dos passos aponta para uma ilustração única de espaço reservado. Trocar `midia_url` por mídia real por passo quando disponível.
- Nenhum segredo ou dado pessoal neste diretório.

## Manuais e Base_Conhecimento (tarefa 17.2)
- O manual inteiro e o sidecar ficam em `manuais/<modelo_id>/` no S3 (fonte da verdade). O sidecar só precisa de `modelo_id` e `manual`.
- Com `python scripts/carregar_seed.py ... --sincronizar-conhecimento --knowledge-base-id <id>` (ou `TRES_KNOWLEDGE_BASE_ID`), cada manual é dividido em **uma seção por arquivo** (`scripts/preprocessar_manuais.py`) e enviado a `secoes/<modelo_id>/<arquivo-do-manual>/<slug>.md` com `.metadata.json` (`modelo_id`, `manual`, `secao`). Só o prefixo `secoes/` é indexado pela Knowledge Base; depois a ingestão roda e o script espera terminar.
- Formato do manual: Markdown com títulos `##`/`###` numerados (`### 3.1 Luz vermelha fixa`). Cada título com texto vira uma seção, e o texto do título vira o metadado `secao` usado nas fontes citadas pelo Assistente_IA. O primeiro `#` é o título do documento. Avisos em citação (`>`) antes da primeira seção não são indexados.
- O ID da Knowledge Base vem da saída `KnowledgeBaseId` da stack `<prefixo>-conhecimento` (também em `/<prefixo>/config/knowledge-base-id` no SSM).
