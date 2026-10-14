"""Envelope `jornada` das respostas públicas (contrato do alerta de risco, Req 8.3 a 8.6).

Formato (ver o cabeçalho de `apps/web/src/risco/armazemRisco.ts`):

    {"jornada_id": "...", "estado": "ativa|escalada|encerrada_guia|encerrada_ia|
                                      encerrada_humano|abandonada",
     "risco": {"marcado": true, "origem": "lista|ia|guia", "em": "<ISO 8601>"},
     "contato_cs": "confirmado|pendente|nao_registrado"}

`risco.marcado` espelha `Jornada.risco` (monotônico no banco). `contato_cs` é `confirmado`
quando a Jornada já tem Chamado (o repasse ao CS foi gravado, Req 9.9) e `pendente` enquanto
não tem. O valor `nao_registrado` só pode ser dito por quem tentou o repasse e falhou: a
rota que escala passa `contato_cs="nao_registrado"` explicitamente.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from repositorios.modelos import Jornada

ContatoCS = Literal["confirmado", "pendente", "nao_registrado"]

_ESTADO_POR_CAMADA = {
    "guia": "encerrada_guia",
    "ia": "encerrada_ia",
    "humano": "encerrada_humano",
    "abandonada": "abandonada",
}


def _iso(valor: datetime) -> str:
    return valor.astimezone(UTC).isoformat().replace("+00:00", "Z")


def estado_publico(jornada: Jornada) -> str:
    if jornada.estado != "encerrada":
        return jornada.estado
    if jornada.encerramento is not None:
        return _ESTADO_POR_CAMADA[jornada.encerramento.camada]
    return "encerrada_humano" if jornada.escalada is not None else "encerrada_guia"


def envelope_jornada(jornada: Jornada, contato_cs: ContatoCS | None = None) -> dict[str, Any]:
    """O objeto `jornada` do envelope. Sem dados pessoais nem número de série."""
    if jornada.risco is None:
        risco: dict[str, Any] = {"marcado": False}
    else:
        risco = {"marcado": True, "origem": jornada.risco.origem, "em": _iso(jornada.risco.em)}
    if contato_cs is None:
        contato_cs = "confirmado" if jornada.escalada is not None else "pendente"
    return {
        "jornada_id": jornada.jornada_id,
        "estado": estado_publico(jornada),
        "risco": risco,
        "contato_cs": contato_cs,
    }


__all__ = ["ContatoCS", "envelope_jornada", "estado_publico"]
