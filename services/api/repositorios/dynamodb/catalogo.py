"""Adaptador DynamoDB de `CatalogoRepo` (tabelas `modelos`, `problemas` e `instrucoes`).

Somente leitura: o papel da Lambda `api` não grava nestas tabelas (o seed as carrega por fora).
O papel também não tem `Scan`, então nenhuma listagem varre a tabela:

  * modelos: `Query` no índice esparso `gsi_catalogo` (PK constante `catalogo_pk`, SK
    `nome_normalizado`), que já devolve a ordem alfabética do Req 2.1. O seed grava o atributo
    `catalogo_pk` em cada modelo;
  * problemas: `BatchGetItem` das chaves 1 a 13 (a lista é fixa, Req 3.1);
  * instruções: `GetItem` por (`modelo_id`, `"<problema_id>#<variante>"`).
"""

from __future__ import annotations

from typing import Any, Final

from botocore.exceptions import BotoCoreError, ClientError

from repositorios.catalogo import (
    VARIANTE_PADRAO,
    InstrucaoCatalogo,
    ModeloCatalogo,
    ProblemaCatalogo,
)
from repositorios.dynamodb._base import Tabela, de_dynamo
from repositorios.erros import ErroRepositorio

GSI_CATALOGO: Final = "gsi_catalogo"
CATALOGO_PK_ATRIBUTO: Final = "catalogo_pk"
CATALOGO_PK_VALOR: Final = "CATALOGO"
IDS_PROBLEMAS: Final = tuple(range(1, 14))  # Req 3.1
_TENTATIVAS_NAO_PROCESSADAS: Final = 3


class CatalogoDynamoDB:
    def __init__(self, recurso: Any, prefixo: str = "tres") -> None:
        self._recurso = recurso
        self._modelos = Tabela(recurso, f"{prefixo}-modelos", "modelos", pk="modelo_id")
        self._problemas = Tabela(recurso, f"{prefixo}-problemas", "problemas", pk="problema_id")
        self._instrucoes = Tabela(
            recurso, f"{prefixo}-instrucoes", "instrucoes", pk="modelo_id", sk="problema_variante"
        )

    def listar_modelos(self) -> list[ModeloCatalogo]:
        itens = self._modelos.consultar(
            "#pk = :pk",
            {"#pk": CATALOGO_PK_ATRIBUTO},
            {":pk": CATALOGO_PK_VALOR},
            indice=GSI_CATALOGO,
        )
        return [ModeloCatalogo.de_item(de_dynamo(i)) for i in itens]

    def obter_modelo(self, modelo_id: str) -> ModeloCatalogo | None:
        item = self._modelos.obter(self._modelos.chave(modelo_id))
        return None if item is None else ModeloCatalogo.de_item(de_dynamo(item))

    def listar_problemas(self) -> list[ProblemaCatalogo]:
        nome = self._problemas.nome
        pendentes: list[dict[str, Any]] = [{"problema_id": n} for n in IDS_PROBLEMAS]
        itens: list[dict[str, Any]] = []
        for _ in range(_TENTATIVAS_NAO_PROCESSADAS):
            try:
                resposta = self._recurso.batch_get_item(
                    RequestItems={nome: {"Keys": pendentes, "ConsistentRead": True}}
                )
            except (ClientError, BotoCoreError) as exc:
                codigo = (
                    exc.response.get("Error", {}).get("Code", "desconhecido")
                    if isinstance(exc, ClientError)
                    else type(exc).__name__
                )
                raise ErroRepositorio(f"problemas: batch_get_item falhou ({codigo})") from exc
            itens.extend(resposta.get("Responses", {}).get(nome, []))
            pendentes = resposta.get("UnprocessedKeys", {}).get(nome, {}).get("Keys", [])
            if not pendentes:
                break
        else:
            raise ErroRepositorio("problemas: batch_get_item deixou chaves sem processar")
        problemas = [ProblemaCatalogo.de_item(de_dynamo(i)) for i in itens]
        return sorted(problemas, key=lambda p: (p.ordem, p.problema_id))

    def obter_instrucao(
        self, modelo_id: str, problema_id: int, variante: str = VARIANTE_PADRAO
    ) -> InstrucaoCatalogo | None:
        item = self._instrucoes.obter(
            self._instrucoes.chave(modelo_id, f"{problema_id}#{variante}")
        )
        return None if item is None else InstrucaoCatalogo.de_item(de_dynamo(item))


__all__ = [
    "CATALOGO_PK_ATRIBUTO",
    "CATALOGO_PK_VALOR",
    "GSI_CATALOGO",
    "CatalogoDynamoDB",
]
