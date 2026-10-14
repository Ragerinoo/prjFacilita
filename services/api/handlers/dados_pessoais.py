"""Lambda `dados_pessoais`: mesmo código, papel IAM separado (Req 18.6).

Atende só as rotas com `destino="dados_pessoais"` (contato do Consumidor e consulta de
Dados_Pessoais pelo Atendente). As demais respondem 404 aqui.
"""

from __future__ import annotations

from typing import Any

from handlers._comum import tratar_http


def lambda_handler(evento: dict[str, Any], contexto: Any = None) -> dict[str, Any]:
    return tratar_http("dados_pessoais", evento)
