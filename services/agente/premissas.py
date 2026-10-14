"""Premissas verificadas (Tarefa 17.1) para o Assistente_IA no AgentCore.

Este módulo é a única fonte das constantes e decisões derivadas da verificação das
questões em aberto Q1, Q2, Q3, Q13, Q14 e Q18 do design. Não faz I/O e só usa a biblioteca
padrão, então a API (Lambda), o agente, a infra (CDK) e os scripts podem importá-lo.

COMO A VERIFICAÇÃO FOI FEITA
    O servidor MCP da power `aws-agentcore` (busca/leitura de documentação, runtime, memória e
    gateway) estava "not connected" nesta sessão, então só o guia de uso da power foi lido
    (fluxo `agentcore create/dev/configure/launch/invoke`, `BedrockAgentCoreApp`,
    `@app.entrypoint`, `bedrock-agentcore` no requirements, `platformVersion`).
    Os demais fatos vieram da documentação oficial da AWS (links em cada seção), consultada
    em 2026. Cada decisão é marcada:

    VERIFICADO  - confirmado em documentação oficial ou por teste local.
    INFERIDO    - conclusão razoável, mas não afirmada pela documentação.
    PENDENTE    - só é possível confirmar na conta/região do hackathon (console ou deploy).
                  Há sempre um passo concreto em `PENDENCIAS_DE_CONTA`.

IMPACTO EM OUTRAS TAREFAS (resumo; detalhes em `AJUSTES_DE_INFRA` e `AJUSTES_DE_CODIGO`)
    - Timeout do agente cai de 25 s para 20 s (orçamento de 30 s do API Gateway, Q18).
    - Lambda `api` com timeout de 28 s e memória >= 1024 MB (hash de senha, Q14).
    - Vector store: S3 Vectors, sem busca híbrida; manuais pré-processados em um arquivo por
      seção com metadados `modelo_id`, `manual`, `secao` (Q1/Q2).
    - Runtime do agente com `platformVersion` V2 (partida a frio, Q13).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# ---------------------------------------------------------------------------------------------
# Região (afeta Q1, Q3, Q13)
# ---------------------------------------------------------------------------------------------
# VERIFICADO: sa-east-1 tem S3 Vectors
#   https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-regions-quotas.html
# VERIFICADO: AgentCore disponível em São Paulo (anúncio "AgentCore is now available in the
#   South America (São Paulo) Region", 2026-05) e página de regiões do AgentCore
#   https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html
# VERIFICADO: Cohere Embed Multilingual v3 aparece como suportado em Knowledge Bases em
#   sa-east-1 (e us-east-1, us-west-2)
#   https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-supported.html
# PENDENTE: acesso ao modelo de linguagem escolhido na conta e na região (ver Q3 abaixo).
REGIAO_PADRAO: Final = "sa-east-1"
# Plano B se o modelo de linguagem não estiver liberado em sa-east-1 (nem via perfil de
# inferência): todos os serviços do design têm presença documentada em us-east-1.
REGIAO_ALTERNATIVA: Final = "us-east-1"


# ---------------------------------------------------------------------------------------------
# Q1 - S3 Vectors vs OpenSearch Serverless
# ---------------------------------------------------------------------------------------------
# DECISÃO: S3 Vectors (mantém a preferência D10). OpenSearch Serverless só se uma pendência
# abaixo reprovar o S3 Vectors.
# VERIFICADO:
#   - Integra com Bedrock Knowledge Bases (Retrieve, RetrieveAndGenerate, sincronização).
#   - Custo ocioso baixo (armazenamento em S3); latência de consulta sub-segundo a frio e
#     ~100 ms a quente.
#   - Filtro de metadados é avaliado antes da busca vetorial (pré-filtragem), logo o filtro
#     `modelo_id` do Req 6.2 não derruba o recall.
#   - Só busca semântica: SEM busca híbrida. Só vetores de ponto flutuante.
#   - Limites com Knowledge Bases: até 1 KB de metadados customizados e 35 chaves por vetor.
#   - Chunking hierárquico pode estourar o limite de metadados (guarda contexto pai/filho
#     como metadado não filtrável).
#   https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-bedrock-kb.html
#   https://docs.aws.amazon.com/AmazonS3/latest/userguide/s3-vectors-metadata-filtering.html
# Consequências para a tarefa 17.2:
#   - Usar chunking FIXED_SIZE (ou NONE com um arquivo por seção). Não usar hierárquico.
#   - Metadados por arquivo: `modelo_id`, `manual`, `secao` (bem abaixo de 1 KB).
#   - Não configurar busca híbrida nem reranking: não existem nesse vector store.
VECTOR_STORE_ESCOLHIDO: Final = "s3_vectors"
VECTOR_STORE_ALTERNATIVO: Final = "opensearch_serverless"
S3_VECTORS_BUSCA_HIBRIDA: Final = False
S3_VECTORS_METADADOS_CUSTOM_MAX_BYTES: Final = 1024
S3_VECTORS_METADADOS_CHAVES_MAX: Final = 35
CHUNKING_ESTRATEGIA: Final = "FIXED_SIZE"  # nunca HIERARCHICAL com S3 Vectors
CHUNKING_MAX_TOKENS: Final = 300
CHUNKING_SOBREPOSICAO_PERCENTUAL: Final = 20
# Número de trechos pedidos ao Retrieve (top-k pequeno, Req 7.3 e custo).
RETRIEVE_TOP_K: Final = 5


# ---------------------------------------------------------------------------------------------
# Q2 - Semântica do score e nome da seção nos metadados
# ---------------------------------------------------------------------------------------------
# VERIFICADO: `Retrieve` devolve `retrievalResults[]` com `content`, `location`, `metadata`,
#   `documentId` e `score` (Double, OPCIONAL). A documentação descreve o score apenas como
#   "o nível de relevância do resultado para a consulta": não define escala nem garante
#   comparabilidade entre configurações.
#   https://docs.aws.amazon.com/bedrock/latest/APIReference/API_agent-runtime_KnowledgeBaseRetrievalResult.html
# INFERIDO: com S3 Vectors (só semântico, sem reranking) o score deriva da similaridade
#   vetorial e fica numa escala de 0 a 1. Por isso o Limiar_Relevancia 0,5 é só um ponto de
#   partida (Req glossário), NÃO um valor validado.
# PENDENTE (calibragem, ver PENDENCIAS_DE_CONTA): medir `score` de perguntas dentro e fora do
#   escopo do manual da demo e ajustar `config.limiar_relevancia` sem tocar no código.
# Regras para o código (tarefas 6.1 e 17.3):
#   - `score` ausente (None) é tratado como 0.0, ou seja, abaixo de qualquer limiar > 0.
#   - A decisão `sem_embasamento` é sempre feita em código, nunca pelo modelo (Req 6.4).
LIMIAR_RELEVANCIA_PADRAO: Final = 0.5
LIMIAR_RELEVANCIA_CALIBRADO: Final = False  # vira True depois da calibragem no console
SCORE_AUSENTE_VALE: Final = 0.0

# Seção do manual: o `Retrieve` NÃO devolve o nome da seção por padrão. Os metadados
# devolvidos são os do arquivo de origem (sidecar `<arquivo>.metadata.json`) mais campos
# técnicos (URI de origem, id do chunk). Também não há como derivar a seção do chunking
# FIXED_SIZE.
#   https://docs.aws.amazon.com/bedrock/latest/userguide/kb-metadata.html
# DECISÃO (pré-processamento, confirma a ressalva do design em 3.5):
#   O script de sincronização (17.2) divide cada manual em UM ARQUIVO POR SEÇÃO:
#     manuais/<modelo_id>/<slug-da-secao>.md
#     manuais/<modelo_id>/<slug-da-secao>.md.metadata.json
#   com o sidecar abaixo. Todo chunk herda esses metadados, e o agente monta as fontes (Req
#   6.3) a partir deles, nunca do texto do modelo.
CHAVE_METADADO_MODELO: Final = "modelo_id"
CHAVE_METADADO_MANUAL: Final = "manual"
CHAVE_METADADO_SECAO: Final = "secao"
METADADOS_OBRIGATORIOS: Final = (
    CHAVE_METADADO_MODELO,
    CHAVE_METADADO_MANUAL,
    CHAVE_METADADO_SECAO,
)
PREFIXO_S3_MANUAIS: Final = "manuais/"  # + <modelo_id>/


def sidecar_metadados(modelo_id: str, manual: str, secao: str) -> dict[str, dict[str, str]]:
    """Conteúdo do `.metadata.json` de uma seção, no formato aceito pelas Knowledge Bases."""
    return {
        "metadataAttributes": {
            CHAVE_METADADO_MODELO: modelo_id,
            CHAVE_METADADO_MANUAL: manual,
            CHAVE_METADADO_SECAO: secao,
        }
    }


def filtro_retrieve_por_modelo(modelo_id: str) -> dict[str, dict[str, str]]:
    """`retrievalConfiguration.vectorSearchConfiguration.filter` do Req 6.2."""
    return {"equals": {"key": CHAVE_METADADO_MODELO, "value": modelo_id}}


# ---------------------------------------------------------------------------------------------
# Q3 - Modelos de linguagem e de embeddings
# ---------------------------------------------------------------------------------------------
# EMBEDDINGS
# VERIFICADO: Cohere Embed Multilingual v3 (`cohere.embed-multilingual-v3`, 1024 dimensões)
#   é suportado por Knowledge Bases em sa-east-1; Titan Text Embeddings V2 também consta na
#   lista de modelos suportados (256/512/1024 dimensões).
#   https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base-supported.html
# DECISÃO: Cohere Embed Multilingual v3 (multilíngue por definição, adequado a pt-BR).
#   Titan Text Embeddings V2 fica como alternativa.
# PENDENTE: confirmar na região que o índice do S3 Vectors usa dimensão 1024, tipo float32 e
#   métrica cosseno, e liberar o acesso ao modelo em "Model access".
MODELO_EMBEDDINGS_ID: Final = "cohere.embed-multilingual-v3"
MODELO_EMBEDDINGS_ALTERNATIVO_ID: Final = "amazon.titan-embed-text-v2:0"
EMBEDDINGS_DIMENSOES: Final = 1024
EMBEDDINGS_TIPO_VETOR: Final = "float32"
EMBEDDINGS_METRICA: Final = "cosine"

# MODELO DE LINGUAGEM
# INFERIDO: o modelo pequeno/rápido recomendado pelo design (D4/Req 6.8) é o Claude Haiku
#   4.5, invocado por perfil de inferência entre regiões. O perfil global atende regiões
#   sem capacidade local; sa-east-1 não foi confirmada para este modelo.
#   https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-haiku-4-5.html
#   https://docs.aws.amazon.com/bedrock/latest/userguide/cross-region-inference-support.html
# PENDENTE: confirmar o ID exato do perfil de inferência no console (Bedrock > Inference
#   profiles), liberar o acesso e fazer uma chamada de teste. O ID é lido da variável de
#   ambiente `TRES_MODELO_LLM_ID`, para trocar sem alterar código.
# PREÇOS: NÃO ficam aqui. Ficam na tabela `config` (`precos_modelo`, `cotacao_usd_brl`) e
#   devem ser preenchidos com a página de preços vigente do Bedrock antes da demo (design,
#   "Modelo de custo"). Nenhum preço foi inventado.
MODELO_LLM_ID_PADRAO: Final = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
MODELO_LLM_ENV: Final = "TRES_MODELO_LLM_ID"
LLM_MAX_TOKENS_SAIDA: Final = 700  # saída JSON curta; reduz custo e latência (Req 7.3)
LLM_TEMPERATURA: Final = 0.2


# ---------------------------------------------------------------------------------------------
# Q13 - Invocar o AgentCore Runtime a partir da Lambda
# ---------------------------------------------------------------------------------------------
# VERIFICADO (API de dados `bedrock-agentcore`):
#   - Operação: `InvokeAgentRuntime` (boto3: `boto3.client("bedrock-agentcore")
#     .invoke_agent_runtime(...)`). Parâmetros: `agentRuntimeArn` (ARN completo, ou ID do
#     agente + `accountId`), `payload` (bytes), `contentType`, `accept`, `qualifier`
#     (endpoint; opcional) e `runtimeSessionId` (33 a 256 caracteres).
#   - Autorização IAM: `bedrock-agentcore:InvokeAgentRuntime` no papel da Lambda. O padrão do
#     runtime é autenticação IAM (SigV4), que o SDK faz sozinho.
#   - Autenticação OAuth/JWT: o SDK da AWS não serve; exigiria HTTPS manual. NÃO adotar.
#   - Cada `runtimeSessionId` ganha uma microVM própria e isolada; chamadas seguintes com o
#     mesmo id reusam a microVM (partida a quente, abaixo de 100 ms). O tempo ocioso padrão é
#     900 s e o tempo de vida máximo padrão é 28800 s (configuráveis, 60 a 28800 s).
#   - Limites: tempo de requisição síncrona 15 min (fixo), payload 100 MB (fixo), sessões
#     até 8 h. Nenhum desses limites restringe o MVP; o limite que manda é o da API (Q18).
#   - A resposta chega em fluxo (`response["response"]` é um StreamingBody); o MVP lê tudo
#     com `.read()` e faz `json.loads`, pois não há streaming para o Consumidor.
#   https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntime.html
#   https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html
#   https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-lifecycle-settings.html
# VERIFICADO (partida a frio): o "novo AgentCore runtime" (`platformVersion = V2`) tem partida
#   a frio P75 de cerca de 2 s, independente do tamanho da imagem, medida pela AWS com um
#   agente vazio e já incluindo a viagem entre regiões. O runtime original varia de ~5,4 s a
#   quase 30 s conforme o tamanho da imagem. A AWS recomenda iniciar a sessão assim que o
#   usuário engaja (por exemplo, ao abrir o chat) para esconder a partida a frio.
#   https://aws.amazon.com/blogs/machine-learning/the-new-agentcore-runtime-elastic-optimized-and-consistently-fast-starts/
# DECISÕES:
#   - Criar o runtime com `platformVersion = V2` (AJUSTES_DE_INFRA).
#   - Autenticação IAM; permissão mínima restrita ao ARN do runtime.
#   - `runtimeSessionId = "tres-jornada-" + jornada_id` (13 + 26 = 39 caracteres, dentro de
#     33 a 256). A mesma sessão serve os modos `responder`, `resumo_repasse` e
#     `sugestao_atendente` da Jornada, reaproveitando a microVM quente.
#   - Ociosidade 900 s (cobre o intervalo típico de um chat) e vida máxima 3600 s.
#   - "Aquecer" a sessão ao abrir o Assistente_IA (Req 6.1): a API pode disparar uma
#     invocação leve assíncrona. Isso exigiria um modo `aquecer` no contrato da tarefa 17.3
#     (sem custo de modelo); é uma sugestão, não um requisito.
#   - Sem retentativas dentro do orçamento de tempo (`max_attempts = 1` no cliente boto3).
# PENDENTE: medir a partida a frio e o p90 reais com o agente da demo (Req 6.8). O número da
#   AWS é de um agente vazio, não inclui Retrieve nem chamada ao modelo.
SERVICO_BOTO3_RUNTIME: Final = "bedrock-agentcore"
OPERACAO_BOTO3_RUNTIME: Final = "invoke_agent_runtime"
ACAO_IAM_INVOCAR_RUNTIME: Final = "bedrock-agentcore:InvokeAgentRuntime"
RUNTIME_AUTENTICACAO: Final = "iam_sigv4"
RUNTIME_PLATFORM_VERSION: Final = "V2"
RUNTIME_SESSION_ID_MIN: Final = 33
RUNTIME_SESSION_ID_MAX: Final = 256
RUNTIME_SESSION_PREFIXO: Final = "tres-jornada-"
RUNTIME_OCIOSO_S: Final = 900
RUNTIME_VIDA_MAXIMA_S: Final = 3600
RUNTIME_PAYLOAD_MAX_BYTES: Final = 100 * 1024 * 1024
RUNTIME_TIMEOUT_SINCRONO_MAX_S: Final = 15 * 60

# Nome do contrato com o agente (design 3.5), compartilhado por API e agente.
MODOS_AGENTE: Final = ("responder", "resumo_repasse", "sugestao_atendente")


def runtime_session_id(jornada_id: str) -> str:
    """Id de sessão do runtime para uma Jornada (33 a 256 caracteres, exigência da API)."""
    if not jornada_id or not jornada_id.isalnum():
        raise ValueError("jornada_id deve ser alfanumérico e não vazio")
    sessao = f"{RUNTIME_SESSION_PREFIXO}{jornada_id}"
    if not RUNTIME_SESSION_ID_MIN <= len(sessao) <= RUNTIME_SESSION_ID_MAX:
        raise ValueError(
            f"runtimeSessionId com {len(sessao)} caracteres; exigido de "
            f"{RUNTIME_SESSION_ID_MIN} a {RUNTIME_SESSION_ID_MAX}"
        )
    return sessao


# ---------------------------------------------------------------------------------------------
# Q18 - Limite de tempo do API Gateway e orçamento de tempo
# ---------------------------------------------------------------------------------------------
# VERIFICADO: o tempo máximo de integração do HTTP API é 30 s e NÃO é ajustável (diferente do
#   REST API, que chega a 29 s por padrão e pode ser aumentado só em APIs regionais/privadas).
#   O payload máximo é 10 MB.
#   https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-quotas.html
# CONCLUSÃO: o limite assumido pelo design (cerca de 30 s) está correto, mas o timeout de 25 s
#   para o agente NÃO deixa folga: cache (até 2 s) + agente (25 s) já dá 27 s antes de gravar
#   evento/custo e responder. Para o aviso de falha do Req 6.12 (e 7.9) aparecer antes de
#   30 s com margem, o agente cai para 20 s.
# INFERIDO (não reverificado agora): a origem do CloudFront espera a resposta por 30 s por
#   padrão; com a Lambda em 28 s a resposta chega antes disso. Se o CDK alterar o tempo de
#   espera da origem, mantê-lo >= 30 s.
API_GATEWAY_HTTP_TIMEOUT_MAX_S: Final = 30
API_GATEWAY_HTTP_TIMEOUT_AJUSTAVEL: Final = False
API_GATEWAY_INTEGRACAO_TIMEOUT_MS: Final = 29_000  # configurar a integração abaixo do teto

LAMBDA_API_TIMEOUT_S: Final = 28
LAMBDA_API_MEMORIA_MB: Final = 1024  # hash de senha (Q14) e CPU proporcional à memória

CACHE_TIMEOUT_S: Final = 2  # Req 7.8
CATALOGO_TIMEOUT_S: Final = 5  # Req 1.7
GRAVACAO_TIMEOUT_TOTAL_S: Final = 10  # Req 20.6 (teto por operação de gravação)
AGENTE_RESPONDER_TIMEOUT_S: Final = 20  # era 25 no design; ver conclusão acima
AGENTE_CONNECT_TIMEOUT_S: Final = 3
AGENTE_MAX_TENTATIVAS: Final = 1
# Reserva para validação, mascaramento, risco e gravação do evento/custo ou da falha.
RESERVA_POS_AGENTE_S: Final = 4
MARGEM_DE_SEGURANCA_S: Final = 2

SUGESTAO_ATENDENTE_TIMEOUT_S: Final = 10  # Req 15.7
ENRIQUECIMENTO_TIMEOUT_S: Final = 10  # Req 10.4
LAMBDA_ENRIQUECIMENTO_TIMEOUT_S: Final = 15  # 10 s do agente + gravação do resultado

# Req 6.8: início da resposta em até 10 s no p90. Sem streaming no MVP, o "início" é a
# resposta completa; o orçamento acima (20 s) é o teto duro, o alvo de p90 é este:
ALVO_P90_RESPOSTA_S: Final = 10


@dataclass(frozen=True)
class OrcamentoRespostaIA:
    """Soma do pior caso da rota `POST /jornadas/{id}/mensagens` com falha do agente."""

    cache_s: int
    agente_s: int
    pos_agente_s: int
    margem_s: int

    @property
    def total_s(self) -> int:
        return self.cache_s + self.agente_s + self.pos_agente_s + self.margem_s


def orcamento_resposta_ia() -> OrcamentoRespostaIA:
    """Pior caso: cache lento (2 s), agente até o timeout, depois gravar a falha."""
    return OrcamentoRespostaIA(
        cache_s=CACHE_TIMEOUT_S,
        agente_s=AGENTE_RESPONDER_TIMEOUT_S,
        pos_agente_s=RESERVA_POS_AGENTE_S,
        margem_s=MARGEM_DE_SEGURANCA_S,
    )


# ---------------------------------------------------------------------------------------------
# Q14 - Hash de senha do Painel_CS no runtime Lambda (Python 3.12)
# ---------------------------------------------------------------------------------------------
# VERIFICADO: existem wheels binárias de `argon2-cffi` 25.1.0 (py3-none-any) e de
#   `argon2-cffi-bindings` 21.2.0 (cp36-abi3, manylinux2014) para x86_64 E aarch64, instaláveis
#   com `pip install --only-binary=:all: --platform manylinux2014_<arch> --python-version 3.12`
#   (testado por download em 2026). Logo o Argon2id empacota na Lambda sem compilar nada.
# VERIFICADO: a OWASP recomenda Argon2id com no mínimo 19 MiB, 2 iterações e paralelismo 1
#   (m=19456, t=2, p=1); se Argon2id não estiver disponível, scrypt com N=2^17, r=8, p=1
#   (cerca de 128 MiB). https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
# VERIFICADO (local): `hashlib.scrypt` existe no Python da biblioteca padrão com OpenSSL 3.
# PENDENTE: confirmar `hashlib.scrypt` no runtime gerenciado python3.12 da Lambda (o Python
#   da Lambda é compilado contra OpenSSL; não testado aqui). O teste de fumaça de 13.1 deve
#   rodar na Lambda real.
# DECISÃO: Argon2id (argon2-cffi, versão fixa) como algoritmo principal. Fallback scrypt
#   (biblioteca padrão) só para hashes já gravados ou se a dependência faltar. O hash guarda o
#   algoritmo e os parâmetros no próprio texto ($argon2id$... / scrypt$N$r$p$salt$hash), então
#   dá para migrar sem invalidar senhas.
HASH_SENHA_ALGORITMO: Final = "argon2id"
HASH_SENHA_ARGON2 = {"memory_cost_kib": 19456, "time_cost": 2, "parallelism": 1}
HASH_SENHA_FALLBACK_ALGORITMO: Final = "scrypt"
HASH_SENHA_SCRYPT = {"n": 2**17, "r": 8, "p": 1, "dklen": 32, "maxmem_bytes": 256 * 1024 * 1024}
ARGON2_CFFI_VERSAO: Final = "25.1.0"
ARGON2_CFFI_BINDINGS_VERSAO: Final = "21.2.0"
LAMBDA_ARQUITETURA_PADRAO: Final = "arm64"  # as duas arquiteturas têm wheel; ver AJUSTES
LAMBDA_PLATAFORMAS_PIP: Final = {
    "arm64": "manylinux2014_aarch64",
    "x86_64": "manylinux2014_x86_64",
}


# ---------------------------------------------------------------------------------------------
# Resumo por questão (consumido por docs/testes; texto curto, em pt-BR)
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Decisao:
    questao: str
    estado: str  # "verificado" | "parcial" | "pendente"
    decisao: str
    requisitos: tuple[str, ...]


DECISOES: Final = (
    Decisao(
        "Q1",
        "verificado",
        "S3 Vectors como vector store; sem busca híbrida; chunking FIXED_SIZE; "
        "metadados <= 1 KB e 35 chaves. OpenSearch Serverless fica de reserva.",
        ("6.2", "20.2"),
    ),
    Decisao(
        "Q2",
        "parcial",
        "Score é um Double opcional sem escala documentada: manter o limiar 0,5 como ponto de "
        "partida, tratar score ausente como 0 e calibrar na conta. Seção do manual não vem "
        "pronta: pré-processar em um arquivo por seção com metadados modelo_id/manual/secao.",
        ("6.3", "6.4"),
    ),
    Decisao(
        "Q3",
        "parcial",
        "Embeddings: Cohere Embed Multilingual v3 (1024 dim) em sa-east-1. LLM: Claude Haiku "
        "4.5 por perfil de inferência, ID por variável de ambiente; acesso e preços a "
        "confirmar na conta.",
        ("6.8", "7.3"),
    ),
    Decisao(
        "Q13",
        "parcial",
        "boto3 'bedrock-agentcore'.invoke_agent_runtime com IAM (SigV4), sessão por Jornada "
        "(tres-jornada-<id>), runtime platformVersion V2 (partida a frio P75 ~2 s para agente "
        "vazio). Payload 100 MB e 15 min não restringem. p90 real a medir.",
        ("6.8", "6.12", "20.2"),
    ),
    Decisao(
        "Q14",
        "parcial",
        "Argon2id com argon2-cffi 25.1.0 (wheels manylinux x86_64 e aarch64 confirmadas); "
        "fallback scrypt N=2^17. hashlib.scrypt na Lambda a confirmar no deploy.",
        ("13.1",),
    ),
    Decisao(
        "Q18",
        "verificado",
        "HTTP API: 30 s fixos, não ajustável. Timeout do agente 25 s -> 20 s; Lambda api em "
        "28 s; integração em 29 s.",
        ("6.12", "7.9"),
    ),
)


# ---------------------------------------------------------------------------------------------
# Ajustes que dependem de outras tarefas (para o orquestrador repassar)
# ---------------------------------------------------------------------------------------------
AJUSTES_DE_INFRA: Final = (
    "8.3: Lambda `api` com timeout de 28 s e memória de 1024 MB; integração do HTTP API com "
    "timeout de 29 000 ms (teto do serviço: 30 s, fixo).",
    "8.3: Lambda `enriquecimento` com timeout de 15 s (10 s do agente + gravação).",
    "8.3: papel da Lambda `api` e da `enriquecimento` com `bedrock-agentcore:InvokeAgentRuntime` "
    "restrito ao ARN do runtime; nada de `*`.",
    "8.3: se o CDK definir o tempo de espera da origem no CloudFront, mantê-lo >= 30 s.",
    "8.3/13.1: empacotar `argon2-cffi==25.1.0` e `argon2-cffi-bindings==21.2.0` com "
    "`pip install --only-binary=:all: --platform manylinux2014_<arch> --python-version 3.12` "
    "(arquitetura da Lambda igual à da wheel).",
    "17.2: Knowledge Base com S3 Vectors, índice float32/1024/cosine, embeddings "
    "`cohere.embed-multilingual-v3`, chunking FIXED_SIZE (300 tokens, 20% de sobreposição).",
    "17.2: bucket de manuais com um arquivo por seção + `.metadata.json` "
    "(`modelo_id`, `manual`, `secao`).",
    "17.3/17.4: runtime criado com `platformVersion = V2`, ociosidade 900 s, vida máxima "
    "3600 s, autenticação IAM.",
    "17.3/17.4: ID do modelo de linguagem vem de TRES_MODELO_LLM_ID "
    "(padrão em MODELO_LLM_ID_PADRAO).",
)

AJUSTES_DE_CODIGO: Final = (
    "12.2/18.x: cliente boto3 do runtime com connect_timeout=3, read_timeout=20, "
    "retries max_attempts=1 (AGENTE_RESPONDER_TIMEOUT_S).",
    "12.2: `sugestao_atendente` com read_timeout=10 e `resumo_repasse` com read_timeout=10.",
    "6.1/avaliar_recuperacao: score None vale 0.0; filtro por modelo_id vem do metadado "
    "`modelo_id`; fontes (manual, secao) vêm dos metadados do trecho.",
    "design.md (Error Handling e Q18): trocar 'timeout de 25 s' por 'timeout de 20 s' e marcar "
    "Q1, Q2, Q3, Q13, Q14 e Q18 como verificadas/parciais (ver DECISOES).",
)

PENDENCIAS_DE_CONTA: Final = (
    "Liberar em Bedrock > Model access: Cohere Embed Multilingual v3 e o modelo de linguagem; "
    "anotar o ID do perfil de inferência e exportar TRES_MODELO_LLM_ID.",
    "Se o modelo de linguagem não estiver disponível em sa-east-1, mudar para "
    f"{REGIAO_ALTERNATIVA} (REGIAO_ALTERNATIVA) ou usar o perfil global.",
    "Calibrar o limiar: rodar `Retrieve` com ~10 perguntas dentro e ~10 fora do manual da demo, "
    "anotar `score` e ajustar `config.limiar_relevancia`; depois marcar "
    "LIMIAR_RELEVANCIA_CALIBRADO = True.",
    "Medir a partida a frio e o p90 do `responder` com o agente real (alvo: ALVO_P90_RESPOSTA_S).",
    "Smoke test na Lambda real: `hashlib.scrypt` disponível e Argon2id importando.",
    "Preencher `config.precos_modelo` e `config.cotacao_usd_brl` com a página de preços do "
    "Bedrock (nenhum preço está definido no repositório).",
)
