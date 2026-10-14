"""Contexto entregue a cada handler de rota e a raiz de composição (`Aplicacao`)."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from core.config import CarregadorConfig
from core.http import Requisicao
from core.idempotencia import Idempotencia, chave_da_requisicao
from core.logs import Log
from repositorios.interfaces import Repositorios

if TYPE_CHECKING:
    from core.roteador import Rota
    from servicos.encerramento import EncerradorDeJornada
    from servicos.escalada import ServicoEscalada


def agora_utc() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Aplicacao:
    """Raiz de composição: tudo que os handlers usam, injetado (nada de globais nas rotas)."""

    repos: Repositorios
    config: CarregadorConfig
    idempotencia: Idempotencia
    log: Log
    relogio: Callable[[], datetime] = agora_utc
    modo: str = "aws"  # "aws" ou "local"
    # Autenticador das rotas do Painel_CS (`(ctx, rota) -> usuário`); o `Roteador` o usa quando
    # não recebeu um próprio. Sem nenhum dos dois, rota autenticada responde 401 (falha fechada).
    autenticador: Callable[[Contexto, Rota], Any] | None = None
    # Serviço de escalada e marcação de risco (tarefa 12.1) e porta de encerramento de Jornada
    # (tarefa 9.4), usados pelas rotas de resolução, vazamento e escalada (tarefa 12.3). Sem
    # eles, as rotas que dependem deles respondem 500 (erro de configuração), nunca em silêncio.
    escalada: ServicoEscalada | None = None
    encerrador: EncerradorDeJornada | None = None

    def agora(self) -> datetime:
        """Horário atual, com fuso UTC."""
        return self.relogio()


@dataclass
class Contexto:
    """O que um handler recebe: requisição, aplicação, log da requisição e usuário (painel)."""

    req: Requisicao
    app: Aplicacao
    log: Log
    rota: Rota | None = None
    usuario: Any = None

    @property
    def repos(self) -> Repositorios:
        return self.app.repos

    def para_rota(self, rota: Rota, req: Requisicao) -> Contexto:
        return dataclasses.replace(
            self, rota=rota, req=req, log=self.log.com(rota=f"{rota.metodo} {rota.caminho}")
        )

    def json(self, obrigatorio: bool = True) -> Any:
        return self.req.json(obrigatorio)

    def chave_idempotencia(self, corpo: Any = None) -> str | None:
        """`Idempotency-Key` ou `evento_id` do corpo, se vier."""
        return chave_da_requisicao(self.req, corpo if isinstance(corpo, dict) else None)

    def primeira_vez(self, escopo: str, corpo: Any = None) -> bool:
        """True se esta é a primeira vez que a chave de idempotência é vista neste escopo."""
        return self.app.idempotencia.primeira_vez(escopo, self.chave_idempotencia(corpo))
