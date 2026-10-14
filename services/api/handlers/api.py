"""Lambda `api`: roteador único das rotas `/api/pub` e `/api/cs` (HTTP API, payload v2)."""

from __future__ import annotations

from typing import Any

from handlers._comum import tratar_http


def lambda_handler(evento: dict[str, Any], contexto: Any = None) -> dict[str, Any]:
    return tratar_http("api", evento)
