"""Recuperação na Base_Conhecimento (Bedrock `agent-runtime`.`retrieve`), Req 6.2.

O cliente boto3 é injetado (testes usam um fake, sem rede). O filtro de metadados `modelo_id`
vai na própria consulta (pré-filtragem do S3 Vectors) e `avaliar_recuperacao` o reaplica em
código: trecho de outro modelo nunca chega ao prompt. Esta camada só traduz a resposta da
API; quem decide limiar, fontes e `sem_embasamento` é `dominio.recuperacao`.
"""

from __future__ import annotations

from typing import Any, Protocol

import premissas
from dominio.recuperacao import TrechoRecuperado

from . import erros
from .erros import ErroAgente


class ClienteRetrieve(Protocol):
    """Subconjunto do cliente boto3 `bedrock-agent-runtime` usado aqui."""

    def retrieve(self, **kwargs: Any) -> dict[str, Any]: ...


def montar_consulta(
    knowledge_base_id: str, modelo_id: str, consulta: str, top_k: int
) -> dict[str, Any]:
    """Parâmetros de `retrieve` com o filtro `modelo_id` (Req 6.2)."""
    return {
        "knowledgeBaseId": knowledge_base_id,
        "retrievalQuery": {"text": consulta},
        "retrievalConfiguration": {
            "vectorSearchConfiguration": {
                "numberOfResults": top_k,
                "filter": premissas.filtro_retrieve_por_modelo(modelo_id),
            }
        },
    }


def _trecho(item: Any) -> TrechoRecuperado | None:
    if not isinstance(item, dict):
        return None
    conteudo = item.get("content")
    texto = conteudo.get("text") if isinstance(conteudo, dict) else None
    if not isinstance(texto, str) or not texto.strip():
        return None
    score = item.get("score")  # opcional na API; ausente = None (vale 0.0 no domínio)
    metadados = item.get("metadata")
    # Só metadados textuais: `manual`, `secao` e `modelo_id` são strings (sidecar do 17.2).
    texto_meta = (
        {k: v for k, v in metadados.items() if isinstance(k, str) and isinstance(v, str)}
        if isinstance(metadados, dict)
        else {}
    )
    return TrechoRecuperado(
        texto=texto,
        score=score if isinstance(score, (int, float)) and not isinstance(score, bool) else None,
        metadados=texto_meta,
    )


class RecuperadorKB:
    """Recupera trechos da Knowledge Base filtrando por `modelo_id`."""

    def __init__(
        self,
        cliente: ClienteRetrieve,
        knowledge_base_id: str,
        top_k: int = premissas.RETRIEVE_TOP_K,
    ) -> None:
        self._cliente = cliente
        self._kb = knowledge_base_id
        self._top_k = top_k

    def recuperar(self, modelo_id: str, consulta: str) -> list[TrechoRecuperado]:
        try:
            resposta = self._cliente.retrieve(
                **montar_consulta(self._kb, modelo_id, consulta, self._top_k)
            )
        except Exception as exc:  # erro de rede, credencial, limite, timeout do cliente
            raise ErroAgente(
                erros.RECUPERACAO_INDISPONIVEL, "Base de conhecimento indisponível."
            ) from exc
        itens = resposta.get("retrievalResults") if isinstance(resposta, dict) else None
        if not isinstance(itens, list):
            return []
        return [t for t in (_trecho(i) for i in itens) if t is not None]
