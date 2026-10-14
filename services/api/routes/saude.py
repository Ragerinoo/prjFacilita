"""Rota de saúde: exercita roteador, envelope e relógio sem tocar em dados."""

from __future__ import annotations

from core.contexto import Contexto
from core.roteador import Rota


def saude(ctx: Contexto) -> dict[str, str]:
    return {"status": "ok", "modo": ctx.app.modo, "em": ctx.app.agora().isoformat()}


ROTAS = [Rota("GET", "/saude", saude, escopo="pub", nome="saude")]
