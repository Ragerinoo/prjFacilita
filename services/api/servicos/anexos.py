"""Porta de leitura de anexos (fotos) do Chamado para o Painel_CS (Req 14.x, 18.x).

`PortaAnexos.url_leitura(chave, mime, expira_s)` devolve uma URL pré-assinada de GET de vida
curta. Implementações:
  * `AnexosS3`: S3 real (`generate_presigned_url`), bucket em ``TRES_BUCKET_FOTOS``;
  * `AnexosLocal`: stub do modo local/testes (URL fictícia, sem rede).
`criar_porta_anexos(modo, ambiente)` escolhe; `definir_porta_anexos` permite injetar uma porta
(testes). A chave do objeto nunca vem do cliente: vem do Chamado.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any, Final, Protocol

from core.erros import ErroConfiguracao

EXPIRACAO_PADRAO_S: Final = 60


class PortaAnexos(Protocol):
    def url_leitura(self, chave: str, mime: str, expira_s: int = EXPIRACAO_PADRAO_S) -> str: ...


class AnexosLocal:
    """Stub local: URL fictícia que carrega a expiração; nunca acessa a rede."""

    def __init__(self, base: str = "https://anexos.local", relogio: Any = None) -> None:
        self._base = base.rstrip("/")
        self._relogio = relogio

    def url_leitura(self, chave: str, mime: str, expira_s: int = EXPIRACAO_PADRAO_S) -> str:
        url = f"{self._base}/{chave}?expira_s={expira_s}"
        if self._relogio is not None:
            limite: datetime = self._relogio() + timedelta(seconds=expira_s)
            url += f"&ate={limite.strftime('%Y%m%dT%H%M%SZ')}"
        return url


class AnexosS3:
    def __init__(self, bucket: str, cliente: Any | None = None) -> None:
        if not bucket:
            raise ErroConfiguracao("TRES_BUCKET_FOTOS ausente")
        self._bucket = bucket
        self._cliente = cliente

    def _s3(self) -> Any:
        if self._cliente is None:
            import boto3  # noqa: PLC0415 - sob demanda (cold start do modo local)

            self._cliente = boto3.client("s3")
        return self._cliente

    def url_leitura(self, chave: str, mime: str, expira_s: int = EXPIRACAO_PADRAO_S) -> str:
        return str(
            self._s3().generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": chave, "ResponseContentType": mime},
                ExpiresIn=expira_s,
            )
        )


_injetada: PortaAnexos | None = None
_cache_s3: dict[str, PortaAnexos] = {}


def definir_porta_anexos(porta: PortaAnexos | None) -> None:
    """Injeta (ou remove, com None) a porta usada pelas rotas. Para testes."""
    global _injetada  # noqa: PLW0603
    _injetada = porta


def criar_porta_anexos(modo: str, ambiente: Mapping[str, str] | None = None) -> PortaAnexos:
    if _injetada is not None:
        return _injetada
    env = os.environ if ambiente is None else ambiente
    if modo == "local":
        return AnexosLocal()
    bucket = env.get("TRES_BUCKET_FOTOS", "")
    if bucket not in _cache_s3:
        _cache_s3[bucket] = AnexosS3(bucket)
    return _cache_s3[bucket]
