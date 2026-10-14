"""Porta de armazenamento das fotos do Chamado (Req 12.7, 12.10).

A rota gera um POST pré-assinado do S3 (o navegador envia direto ao bucket) e, na confirmação,
confere o objeto. A porta é injetável:

  * `ArmazenamentoS3`: produção (`TRES_BUCKET_FOTOS`); a política do POST fixa o `Content-Type`,
    `content-length-range` de 1 byte a 5 MB e validade curta.
  * `ArmazenamentoLocal`: STUB para o modo local/demo, sem S3. O "destino" de envio é uma rota
    da própria API (`.../anexos/{anexo_id}/arquivo`, que aceita e descarta o arquivo) e a
    confirmação confia no tipo e no tamanho declarados no pedido. Use `confiar_declarado=False`
    e `simular_envio` para testar o caminho estrito.

`definir_armazenamento` substitui a porta (testes, composição); sem ela, `obter_armazenamento`
escolhe pelo modo da aplicação.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from dominio.validadores import FOTO_MAX_BYTES

VALIDADE_UPLOAD_S = 300


@dataclass(frozen=True, slots=True)
class DestinoUpload:
    url: str
    campos: dict[str, str]


@dataclass(frozen=True, slots=True)
class ObjetoFoto:
    bytes: int
    mime: str


class ArmazenamentoFotos(Protocol):
    def destino_upload(self, chave: str, mime: str, bytes_: int) -> DestinoUpload: ...

    def inspecionar(self, chave: str) -> ObjetoFoto | None: ...

    def descartar(self, chave: str) -> None: ...


class ArmazenamentoS3:
    """POST pré-assinado do S3 (`generate_presigned_post`)."""

    def __init__(self, bucket: str, cliente: Any | None = None) -> None:
        self._bucket = bucket
        self._cliente = cliente

    @property
    def cliente(self) -> Any:
        if self._cliente is None:
            import boto3

            self._cliente = boto3.client("s3")
        return self._cliente

    def destino_upload(self, chave: str, mime: str, bytes_: int) -> DestinoUpload:
        post = self.cliente.generate_presigned_post(
            Bucket=self._bucket,
            Key=chave,
            Fields={"Content-Type": mime},
            Conditions=[{"Content-Type": mime}, ["content-length-range", 1, FOTO_MAX_BYTES]],
            ExpiresIn=VALIDADE_UPLOAD_S,
        )
        return DestinoUpload(post["url"], dict(post["fields"]))

    def inspecionar(self, chave: str) -> ObjetoFoto | None:
        try:
            cabeca = self.cliente.head_object(Bucket=self._bucket, Key=chave)
        except Exception as exc:  # noqa: BLE001 - objeto ausente (404) ou sem acesso
            codigo = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            if codigo in ("404", "NoSuchKey", "NotFound"):
                return None
            raise
        return ObjetoFoto(int(cabeca["ContentLength"]), str(cabeca.get("ContentType", "")))

    def descartar(self, chave: str) -> None:
        try:
            self.cliente.delete_object(Bucket=self._bucket, Key=chave)
        except Exception:  # noqa: BLE001, S110 - descarte é melhor esforço
            pass


@dataclass
class ArmazenamentoLocal:
    """Stub em memória para o modo local (ver o docstring do módulo)."""

    confiar_declarado: bool = True
    prefixo_url: str = "/api/pub/chamados"
    _declarados: dict[str, ObjetoFoto] = field(default_factory=dict)
    _enviados: dict[str, ObjetoFoto] = field(default_factory=dict)
    descartados: list[str] = field(default_factory=list)

    def destino_upload(self, chave: str, mime: str, bytes_: int) -> DestinoUpload:
        # chave = chamados/<numero>/<anexo_id>
        _, numero, anexo_id = chave.split("/")
        self._declarados[chave] = ObjetoFoto(bytes_, mime)
        return DestinoUpload(
            f"{self.prefixo_url}/{numero}/anexos/{anexo_id}/arquivo",
            {"key": chave, "Content-Type": mime},
        )

    def simular_envio(self, chave: str, bytes_: int, mime: str) -> None:
        self._enviados[chave] = ObjetoFoto(bytes_, mime)

    def inspecionar(self, chave: str) -> ObjetoFoto | None:
        if chave in self._enviados:
            return self._enviados[chave]
        return self._declarados.get(chave) if self.confiar_declarado else None

    def descartar(self, chave: str) -> None:
        self.descartados.append(chave)
        self._declarados.pop(chave, None)
        self._enviados.pop(chave, None)


_substituto: ArmazenamentoFotos | None = None
_local = ArmazenamentoLocal()
_s3: ArmazenamentoS3 | None = None


def definir_armazenamento(armazenamento: ArmazenamentoFotos | None) -> None:
    """Injeta a porta (None volta ao padrão por modo)."""
    global _substituto
    _substituto = armazenamento


def obter_armazenamento(modo: str) -> ArmazenamentoFotos:
    global _s3
    if _substituto is not None:
        return _substituto
    if modo == "local":
        return _local
    if _s3 is None:
        bucket = os.environ.get("TRES_BUCKET_FOTOS", "")
        if not bucket:
            from core.erros import ErroConfiguracao

            raise ErroConfiguracao("TRES_BUCKET_FOTOS não definido")
        _s3 = ArmazenamentoS3(bucket)
    return _s3
