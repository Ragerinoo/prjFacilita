"""Matriz de autorização perfil × rota do Painel_CS (Req 13.2, 13.3, 13.4; design, rotas do CS).

Parte pura (sem I/O, sem relógio): `perfis_permitidos` e `decidir_acesso`. É o que o teste de
propriedade 27 exercita. O restante (cookie, sessão, cabeçalho anti-CSRF) fica em
`servicos/autenticacao.py`, que alimenta `decidir_acesso` com o estado da credencial.

Regras:
  * credencial inválida (ausente, malformada, expirada ou de sessão encerrada) -> 401;
  * perfil `atendente` em rota de métricas ou de configuração -> 403 (sem dados);
  * perfil `gestor` acessa tudo; `atendente` acessa o resto do Painel;
  * rota autenticada que NÃO consta da matriz nem declara `Rota.perfis` -> 403 para todos
    (falha fechada: uma rota nova precisa ser classificada de propósito).
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable, Mapping
from enum import Enum
from typing import Any, Final, TypeVar

from core.erros import ErroApi, nao_autenticado, sem_permissao

ATENDENTE: Final = "atendente"
GESTOR: Final = "gestor"
PERFIS: Final[frozenset[str]] = frozenset({ATENDENTE, GESTOR})
TODOS_OS_PERFIS: Final[frozenset[str]] = PERFIS
SOMENTE_GESTOR: Final[frozenset[str]] = frozenset({GESTOR})

METODOS_MUTACAO: Final[frozenset[str]] = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CABECALHO_CSRF: Final = "X-Requested-With"

_PARAMETRO: Final = re.compile(r"\{[^/{}]*\}")

# (método, caminho relativo a /api/cs com parâmetros como "{}") -> perfis aceitos.
# Fonte: tabela "Rotas do CS" do design. Login e logout não entram: não exigem credencial.
_MATRIZ_BRUTA: Final[Mapping[tuple[str, str], frozenset[str]]] = {
    ("GET", "/sessao"): TODOS_OS_PERFIS,
    ("GET", "/fila"): TODOS_OS_PERFIS,
    ("GET", "/chamados/{numero}"): TODOS_OS_PERFIS,
    ("POST", "/chamados/{numero}/assumir"): TODOS_OS_PERFIS,
    ("GET", "/chamados/{numero}/dados-pessoais"): TODOS_OS_PERFIS,
    ("GET", "/chamados/{numero}/anexos/{indice}"): TODOS_OS_PERFIS,
    ("GET", "/chamados/{numero}/sugestao"): TODOS_OS_PERFIS,
    ("POST", "/chamados/{numero}/mensagens"): TODOS_OS_PERFIS,
    ("POST", "/chamados/{numero}/ordem-servico"): TODOS_OS_PERFIS,
    ("POST", "/chamados/{numero}/agendamento"): TODOS_OS_PERFIS,
    ("POST", "/chamados/{numero}/encerrar"): TODOS_OS_PERFIS,
    ("POST", "/cache"): TODOS_OS_PERFIS,
    ("GET", "/metricas"): SOMENTE_GESTOR,
    ("PUT", "/config"): SOMENTE_GESTOR,
}


def normalizar_caminho(caminho: str) -> str:
    """Caminho de rota sem o nome dos parâmetros (``{numero}`` e ``{n}`` viram ``{}``)."""
    return _PARAMETRO.sub("{}", caminho.rstrip("/") or "/")


MATRIZ: Final[Mapping[tuple[str, str], frozenset[str]]] = {
    (metodo, normalizar_caminho(caminho)): perfis
    for (metodo, caminho), perfis in _MATRIZ_BRUTA.items()
}


class Acesso(Enum):
    PERMITIDO = 200
    NAO_AUTENTICADO = 401
    SEM_PERMISSAO = 403


def perfis_permitidos(metodo: str, caminho: str) -> frozenset[str]:
    """Perfis que podem chamar a rota autenticada; vazio se ela não consta da matriz."""
    return MATRIZ.get((metodo.upper(), normalizar_caminho(caminho)), frozenset())


def decidir_acesso(
    credencial_valida: bool,
    perfil: str | None,
    metodo: str,
    caminho: str,
    perfis_da_rota: frozenset[str] | None = None,
) -> Acesso:
    """Decisão pura de acesso a uma rota autenticada do Painel_CS.

    `perfis_da_rota` (de `Rota.perfis`) tem precedência sobre a matriz.
    """
    if not credencial_valida or perfil is None:
        return Acesso.NAO_AUTENTICADO
    permitidos = (
        perfis_da_rota if perfis_da_rota is not None else perfis_permitidos(metodo, caminho)
    )
    if perfil in permitidos and perfil in PERFIS:
        return Acesso.PERMITIDO
    return Acesso.SEM_PERMISSAO


def exigir_acesso(acesso: Acesso) -> None:
    """Converte a decisão em `ErroApi` (401/403 sem corpo com dados)."""
    if acesso is Acesso.NAO_AUTENTICADO:
        raise nao_autenticado()
    if acesso is Acesso.SEM_PERMISSAO:
        raise sem_permissao()


# --------------------------------------------------------------------------- anti-CSRF


def exige_cabecalho_csrf(metodo: str) -> bool:
    return metodo.upper() in METODOS_MUTACAO


def exigir_cabecalho_csrf(metodo: str, valor: str | None) -> None:
    """Mutação sem `X-Requested-With` é recusada (defesa em profundidade; design, Req 13)."""
    if exige_cabecalho_csrf(metodo) and not (valor and valor.strip()):
        raise ErroApi(
            403,
            "cabecalho_obrigatorio",
            "Requisição recusada: faltou o cabeçalho de segurança.",
        )


# --------------------------------------------------------------------------- decorator

F = TypeVar("F", bound=Callable[..., Any])


def exigir_perfil(*perfis: str) -> Callable[[F], F]:
    """Decorator de handler (``def handler(ctx)``): defesa em profundidade além da matriz.

    ``@exigir_perfil("gestor")`` responde 401 se `ctx.usuario` não existe e 403 se o perfil não
    está na lista, antes de executar o handler.
    """
    if not perfis or not set(perfis) <= PERFIS:
        raise ValueError(f"Perfis inválidos: {perfis!r}")
    aceitos = frozenset(perfis)

    def decorador(handler: F) -> F:
        @functools.wraps(handler)
        def embrulhado(ctx: Any, *args: Any, **kwargs: Any) -> Any:
            usuario = getattr(ctx, "usuario", None)
            perfil = getattr(usuario, "perfil", None)
            exigir_acesso(
                decidir_acesso(usuario is not None, perfil, "GET", "/", perfis_da_rota=aceitos)
            )
            return handler(ctx, *args, **kwargs)

        return embrulhado  # type: ignore[return-value]

    return decorador
