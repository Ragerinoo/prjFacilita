"""Disparo assíncrono da Lambda `enriquecimento` pela API (porta do `ServicoEscalada`).

A escalada cria o Chamado com o Pacote_Repasse provisório (Req 10.2) e pede, sem esperar, o
preenchimento de resumo, sentimento e próxima ação. Em produção isso é um
``lambda:InvokeFunction`` com ``InvocationType="Event"`` na função ``enriquecimento``
(``TRES_FUNCAO_ENRIQUECIMENTO``, definida pela stack da API, que já concede a permissão).

Evento enviado à função: ``{"numero": "TRES-XXXXXXXXXX"}`` (só o identificador opaco do Chamado;
nada de PII). Falhas sobem como exceção e o `ServicoEscalada` as registra e as ignora, porque
o Pacote provisório já é válido (Req 10.4, 10.8).

Sem a variável, a porta fica nula (modo local, testes): o Chamado nasce igual e o
enriquecimento simplesmente não roda.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

from servicos.escalada import DisparadorEnriquecimento, DisparadorEnriquecimentoNulo

VARIAVEL_FUNCAO: Final = "TRES_FUNCAO_ENRIQUECIMENTO"

# O disparo está no caminho da resposta ao Consumidor: uma tentativa, no máximo ~3 s.
LAMBDA_TIMEOUT_CONEXAO_S: Final = 1
LAMBDA_TIMEOUT_LEITURA_S: Final = 2
LAMBDA_TENTATIVAS: Final = 1


class DisparadorLambda:
    """Invoca a Lambda de enriquecimento de forma assíncrona (``InvocationType="Event"``)."""

    def __init__(self, cliente: Any, funcao: str) -> None:
        self._cliente = cliente
        self._funcao = funcao

    def disparar(self, numero: str) -> None:
        self._cliente.invoke(
            FunctionName=self._funcao,
            InvocationType="Event",
            Payload=json.dumps({"numero": numero}).encode("utf-8"),
        )


def criar_cliente_lambda() -> Any:
    """`boto3.client("lambda")` com timeouts curtos (o disparo está no caminho do Consumidor)."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "lambda",
        config=Config(
            connect_timeout=LAMBDA_TIMEOUT_CONEXAO_S,
            read_timeout=LAMBDA_TIMEOUT_LEITURA_S,
            retries={"total_max_attempts": LAMBDA_TENTATIVAS, "mode": "standard"},
        ),
    )


def criar_disparador(
    ambiente: Mapping[str, str], *, cliente: Any | None = None
) -> DisparadorEnriquecimento:
    """`DisparadorLambda` se ``TRES_FUNCAO_ENRIQUECIMENTO`` existe; senão, o disparador nulo."""
    funcao = ambiente.get(VARIAVEL_FUNCAO) or None
    if not funcao:
        return DisparadorEnriquecimentoNulo()
    return DisparadorLambda(cliente if cliente is not None else criar_cliente_lambda(), funcao)
