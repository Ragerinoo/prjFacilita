"""Ciclo de vida compartilhado dos handlers: app e roteador criados uma vez por container."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.app import criar_app
from core.contexto import Aplicacao
from core.processamento import processar
from core.roteador import Destino, Roteador, criar_roteador

_cache: dict[str, tuple[Aplicacao, Roteador]] = {}


def obter(destino: Destino) -> tuple[Aplicacao, Roteador]:
    """Cria (na partida a frio) e reaproveita a aplicação e as rotas do `destino`."""
    if destino not in _cache:
        _cache[destino] = (criar_app(), criar_roteador().filtrar(destino))
    return _cache[destino]


def redefinir() -> None:
    """Só para testes: descarta o cache do container."""
    _cache.clear()


def tratar_http(destino: Destino, evento: Mapping[str, Any]) -> dict[str, Any]:
    app, roteador = obter(destino)
    return processar(app, roteador, evento)
