"""Requisição/resposta HTTP e conversão de/para o evento do API Gateway HTTP API (payload v2)."""

from __future__ import annotations

import base64
import binascii
import dataclasses
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from functools import cached_property
from typing import Any, Final

from core.erros import CORPO_MUITO_GRANDE, ErroApi, json_invalido

LIMITE_CORPO_BYTES: Final = 256 * 1024
CABECALHOS_PADRAO: Final[Mapping[str, str]] = {
    "Content-Type": "application/json; charset=utf-8",
    # Respostas da API têm dados da Jornada e do Chamado: nada de cache por padrão.
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}

_SEM_CORPO: Final = object()


@dataclass(frozen=True)
class Requisicao:
    """Requisição normalizada. `caminho` é o caminho bruto (ex.: `/api/pub/jornadas`)."""

    metodo: str
    caminho: str
    cabecalhos: Mapping[str, str] = field(default_factory=dict)  # nomes em minúsculas
    consulta: Mapping[str, str] = field(default_factory=dict)
    corpo_bruto: bytes = b""
    cookies: Mapping[str, str] = field(default_factory=dict)
    request_id: str = ""
    # Preenchido pelo roteador depois do casamento da rota:
    params: Mapping[str, str] = field(default_factory=dict)

    def cabecalho(self, nome: str) -> str | None:
        return self.cabecalhos.get(nome.lower())

    @cached_property
    def _json(self) -> Any:
        if not self.corpo_bruto.strip():
            return _SEM_CORPO
        try:
            return json.loads(self.corpo_bruto.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise json_invalido() from None

    def json(self, obrigatorio: bool = True) -> Any:
        """Corpo como JSON. Corpo vazio: 400 se `obrigatorio`, senão `{}`.

        O conteúdo do corpo nunca entra em mensagem de erro nem em log.
        """
        valor = self._json
        if valor is _SEM_CORPO:
            if obrigatorio:
                raise json_invalido("A requisição precisa de um corpo JSON.")
            return {}
        return valor

    def com_params(self, params: Mapping[str, str]) -> Requisicao:
        return dataclasses.replace(self, params=dict(params))


@dataclass(slots=True)
class Resposta:
    status: int = 200
    corpo: Any = None
    cabecalhos: dict[str, str] = field(default_factory=dict)
    cookies: list[str] = field(default_factory=list)

    @classmethod
    def ok(cls, corpo: Any = None, status: int = 200, **cabecalhos: str) -> Resposta:
        return cls(status=status, corpo=corpo, cabecalhos=dict(cabecalhos))

    @classmethod
    def criado(cls, corpo: Any = None) -> Resposta:
        return cls(status=201, corpo=corpo)

    @classmethod
    def sem_conteudo(cls) -> Resposta:
        return cls(status=204)

    @classmethod
    def de_erro(cls, erro: ErroApi) -> Resposta:
        return cls(erro.status, erro.para_envelope(), dict(erro.cabecalhos))


def serializar(valor: Any) -> Any:
    """`default` do json: datas ISO, Decimal como texto (sem perder casas), dataclasses."""
    if isinstance(valor, datetime | date):
        return valor.isoformat()
    if isinstance(valor, Decimal):
        return str(valor)
    if isinstance(valor, Enum):
        return valor.value
    if dataclasses.is_dataclass(valor) and not isinstance(valor, type):
        return dataclasses.asdict(valor)
    if isinstance(valor, set | frozenset):
        return sorted(valor)
    raise TypeError(f"Tipo não serializável: {type(valor).__name__}")


def para_evento_v2(resposta: Resposta) -> dict[str, Any]:
    """Resposta no formato esperado pelo API Gateway HTTP API (payload v2)."""
    cabecalhos = {**CABECALHOS_PADRAO, **resposta.cabecalhos}
    corpo = ""
    if resposta.status == 204 or resposta.corpo is None:
        cabecalhos.pop("Content-Type", None)
    else:
        corpo = json.dumps(resposta.corpo, ensure_ascii=False, default=serializar)
    evento: dict[str, Any] = {
        "statusCode": resposta.status,
        "headers": cabecalhos,
        "body": corpo,
        "isBase64Encoded": False,
    }
    if resposta.cookies:
        evento["cookies"] = list(resposta.cookies)
    return evento


def _ler_cookies(evento: Mapping[str, Any], cabecalhos: Mapping[str, str]) -> dict[str, str]:
    brutos = evento.get("cookies")
    if not brutos and cabecalhos.get("cookie"):
        brutos = [p.strip() for p in cabecalhos["cookie"].split(";")]
    cookies: dict[str, str] = {}
    for item in brutos or ():
        nome, separador, valor = str(item).partition("=")
        if separador and nome.strip():
            cookies[nome.strip()] = valor.strip()
    return cookies


def de_evento_v2(evento: Mapping[str, Any]) -> Requisicao:
    """Normaliza o evento do API Gateway HTTP API (payload 2.0)."""
    contexto = evento.get("requestContext") or {}
    http = contexto.get("http") or {}
    metodo = str(http.get("method") or evento.get("httpMethod") or "GET").upper()
    caminho = str(evento.get("rawPath") or http.get("path") or evento.get("path") or "/")
    cabecalhos = {str(k).lower(): str(v) for k, v in (evento.get("headers") or {}).items()}
    consulta = {str(k): str(v) for k, v in (evento.get("queryStringParameters") or {}).items()}

    corpo = evento.get("body") or ""
    if isinstance(corpo, str):
        if evento.get("isBase64Encoded"):
            try:
                bruto = base64.b64decode(corpo, validate=True)
            except (binascii.Error, ValueError):
                raise json_invalido() from None
        else:
            bruto = corpo.encode("utf-8")
    else:
        bruto = bytes(corpo)
    if len(bruto) > LIMITE_CORPO_BYTES:
        raise ErroApi(
            413,
            CORPO_MUITO_GRANDE,
            "O conteúdo enviado é grande demais.",
        )

    return Requisicao(
        metodo=metodo,
        caminho=caminho,
        cabecalhos=cabecalhos,
        consulta=consulta,
        corpo_bruto=bruto,
        cookies=_ler_cookies(evento, cabecalhos),
        request_id=str(contexto.get("requestId") or ""),
    )
