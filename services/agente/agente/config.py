"""Configuração do agente, lida do ambiente do runtime (nada de segredo no código)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

import premissas

KNOWLEDGE_BASE_ENV: Final = "TRES_KNOWLEDGE_BASE_ID"
LIMIAR_ENV: Final = "TRES_LIMIAR_RELEVANCIA"

# Margem entre o teto interno de cada modo e o timeout do cliente (API): rede e partida a frio.
MARGEM_CLIENTE_S: Final = 2.0
# Tetos internos por modo: o do cliente (premissas) menos a margem.
TIMEOUT_POR_MODO_S: Final[Mapping[str, float]] = {
    "responder": premissas.AGENTE_RESPONDER_TIMEOUT_S - MARGEM_CLIENTE_S,
    "resumo_repasse": premissas.ENRIQUECIMENTO_TIMEOUT_S - MARGEM_CLIENTE_S,
    "sugestao_atendente": premissas.SUGESTAO_ATENDENTE_TIMEOUT_S - MARGEM_CLIENTE_S,
}
# Timeouts de leitura dos clientes boto3 (somados ficam abaixo do teto do modo `responder`).
RETRIEVE_READ_TIMEOUT_S: Final = 5
MODELO_READ_TIMEOUT_S: Final = 12
CONNECT_TIMEOUT_S: Final = premissas.AGENTE_CONNECT_TIMEOUT_S


@dataclass(frozen=True)
class Config:
    knowledge_base_id: str
    modelo_llm_id: str
    regiao: str
    limiar_relevancia: float
    top_k: int = premissas.RETRIEVE_TOP_K
    max_tokens_saida: int = premissas.LLM_MAX_TOKENS_SAIDA
    temperatura: float = premissas.LLM_TEMPERATURA


def carregar_config(env: Mapping[str, str] | None = None) -> Config:
    """Monta a configuração a partir do ambiente. Falta de KB é erro de implantação."""
    env = os.environ if env is None else env
    kb = env.get(KNOWLEDGE_BASE_ENV, "").strip()
    if not kb:
        raise RuntimeError(f"variável de ambiente {KNOWLEDGE_BASE_ENV} ausente")
    return Config(
        knowledge_base_id=kb,
        modelo_llm_id=env.get(premissas.MODELO_LLM_ENV, "").strip()
        or premissas.MODELO_LLM_ID_PADRAO,
        regiao=env.get("AWS_REGION") or env.get("AWS_DEFAULT_REGION") or premissas.REGIAO_PADRAO,
        limiar_relevancia=float(env.get(LIMIAR_ENV) or premissas.LIMIAR_RELEVANCIA_PADRAO),
    )
