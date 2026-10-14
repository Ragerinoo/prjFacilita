"""Autorizador do API Gateway: só aceita requisições vindas do CloudFront (Req 18.7, 20.5).

O CloudFront acrescenta o cabeçalho ``x-origem-cloudfront`` com um valor guardado no Secrets
Manager (gerado no deploy). Este autorizador compara o cabeçalho recebido com o segredo e
devolve a resposta simples do HTTP API (``isAuthorized``). O valor nunca é registrado em log.

Variáveis de ambiente:
    TRES_SEGREDO_ORIGEM_ARN  ARN do segredo (JSON com o campo ``valor``).
"""

from __future__ import annotations

import hmac
import json
import os
import time

CABECALHO = "x-origem-cloudfront"
CAMPO_SEGREDO = "valor"
# O segredo muda raramente; evita uma chamada ao Secrets Manager a cada execução.
_TTL_CACHE_S = 300

_cache: dict[str, object] = {"valor": None, "expira": 0.0}


def _buscar_segredo() -> str:
    import boto3  # importação tardia: só quando o cache expira

    cliente = boto3.client("secretsmanager")
    resposta = cliente.get_secret_value(SecretId=os.environ["TRES_SEGREDO_ORIGEM_ARN"])
    return json.loads(resposta["SecretString"])[CAMPO_SEGREDO]


def _segredo_atual() -> str:
    agora = time.monotonic()
    if _cache["valor"] is None or agora >= float(_cache["expira"]):
        _cache["valor"] = _buscar_segredo()
        _cache["expira"] = agora + _TTL_CACHE_S
    return str(_cache["valor"])


def handler(event: dict, _context: object = None) -> dict:
    """Resposta simples do HTTP API: negado por padrão, inclusive em qualquer erro."""
    try:
        recebido = (event.get("headers") or {}).get(CABECALHO, "")
        esperado = _segredo_atual()
        autorizado = bool(recebido) and hmac.compare_digest(
            recebido.encode("utf-8"), esperado.encode("utf-8")
        )
    except Exception:  # noqa: BLE001 - falha fechada: qualquer erro nega o acesso
        autorizado = False
    return {"isAuthorized": autorizado}
