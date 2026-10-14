"""Roteador: descobre módulos em ``routes/`` e despacha requisições.

Contrato de um módulo de rotas (``routes/<nome>.py``): expõe ``ROTAS``, uma lista de `Rota`
(ou uma função ``rotas()`` que devolve essa lista). Módulos cujo nome começa com ``_`` são
ignorados. Módulo sem ``ROTAS`` é erro de configuração (falha cedo, no cold start).

Caminhos são escritos sem o prefixo ``/api/<escopo>`` (ex.: ``/jornadas/{id}/modelo``); o
roteador casa ``/api/pub/jornadas/...`` e ``/api/cs/...`` conforme o ``escopo`` da rota.
Rotas literais têm precedência sobre rotas com parâmetros.

Segurança: rota autenticada (por padrão todas do escopo ``cs`` exceto as marcadas
``autenticada=False``, como o login) sem `autenticador` configurado responde 401. O sistema
nunca "abre" uma rota por falta de configuração.
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final, Literal

from core.erros import ErroApi, ErroConfiguracao, nao_autenticado, nao_encontrado
from core.http import Requisicao, Resposta

if TYPE_CHECKING:
    from core.contexto import Contexto

Escopo = Literal["pub", "cs"]
Destino = Literal["api", "dados_pessoais"]
Handler = Callable[["Contexto"], "Resposta | Mapping[str, Any] | list[Any] | None"]
Autenticador = Callable[["Contexto", "Rota"], Any]

PREFIXO_API: Final = "/api"
_PARAM: Final = re.compile(r"^\{([a-z_][a-z0-9_]*)\}$")


@dataclass(frozen=True)
class Rota:
    metodo: str
    caminho: str  # relativo ao escopo, ex.: "/jornadas/{id}/modelo"
    handler: Handler
    escopo: Escopo = "pub"
    # Qual Lambda atende (mesmo valor de `infra.stacks.api_stack.Rota.destino`).
    destino: Destino = "api"
    # None = padrão do escopo (cs exige autenticação, pub não).
    autenticada: bool | None = None
    # Perfis aceitos (ex.: {"gestor"}); None = qualquer usuário autenticado.
    perfis: frozenset[str] | None = None
    nome: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        if not self.caminho.startswith("/"):
            raise ErroConfiguracao(f"Caminho de rota deve começar com '/': {self.caminho!r}")
        object.__setattr__(self, "metodo", self.metodo.upper())

    @property
    def exige_autenticacao(self) -> bool:
        return self.escopo == "cs" if self.autenticada is None else self.autenticada

    @property
    def caminho_completo(self) -> str:
        return f"{PREFIXO_API}/{self.escopo}{self.caminho}"

    @property
    def chave(self) -> str:
        return f"{self.metodo} {self.caminho_completo}"


def _segmentos(caminho: str) -> list[str]:
    return [s for s in caminho.split("/") if s]


class Roteador:
    def __init__(self, rotas: Iterable[Rota] = (), autenticador: Autenticador | None = None):
        self.autenticador = autenticador
        self._rotas: list[Rota] = []
        for rota in rotas:
            self.adicionar(rota)

    @property
    def rotas(self) -> tuple[Rota, ...]:
        return tuple(self._rotas)

    def adicionar(self, rota: Rota) -> None:
        if any(self._equivalentes(rota, outra) for outra in self._rotas):
            raise ErroConfiguracao(f"Rota duplicada: {rota.chave}")
        self._rotas.append(rota)
        # Literais primeiro: menos parâmetros vence; empate mantém a ordem de cadastro.
        self._rotas.sort(
            key=lambda r: sum(_PARAM.match(s) is not None for s in _segmentos(r.caminho))
        )

    @staticmethod
    def _equivalentes(a: Rota, b: Rota) -> bool:
        if a.metodo != b.metodo or a.escopo != b.escopo:
            return False
        sa, sb = _segmentos(a.caminho), _segmentos(b.caminho)
        return len(sa) == len(sb) and all(
            x == y or (_PARAM.match(x) and _PARAM.match(y)) for x, y in zip(sa, sb, strict=True)
        )

    def filtrar(self, destino: Destino) -> Roteador:
        """Roteador só com as rotas atendidas por uma Lambda (mesmo autenticador)."""
        return Roteador((r for r in self._rotas if r.destino == destino), self.autenticador)

    # -- casamento --------------------------------------------------------------------------
    def resolver(self, metodo: str, caminho: str) -> tuple[Rota, dict[str, str]]:
        """Rota e parâmetros de caminho. 404 se nenhum caminho casa; 405 se só outro método."""
        segmentos = _segmentos(caminho)
        permitidos: set[str] = set()
        for rota in self._rotas:
            params = self._casar(rota, segmentos)
            if params is None:
                continue
            if rota.metodo == metodo.upper():
                return rota, params
            permitidos.add(rota.metodo)
        if permitidos:
            raise ErroApi(
                405,
                "metodo_nao_permitido",
                "Este método não é permitido para esta rota.",
                cabecalhos={"Allow": ", ".join(sorted(permitidos))},
            )
        raise nao_encontrado("Rota não encontrada.")

    @staticmethod
    def _casar(rota: Rota, segmentos: list[str]) -> dict[str, str] | None:
        modelo = [PREFIXO_API.strip("/"), rota.escopo, *_segmentos(rota.caminho)]
        if len(modelo) != len(segmentos):
            return None
        params: dict[str, str] = {}
        for esperado, real in zip(modelo, segmentos, strict=True):
            casou = _PARAM.match(esperado)
            if casou:
                params[casou.group(1)] = real
            elif esperado != real:
                return None
        return params

    # -- despacho ---------------------------------------------------------------------------
    def despachar(self, ctx_base: Contexto) -> Resposta:
        """Executa o handler da rota. Erros de negócio sobem como `ErroApi` para o chamador."""
        requisicao: Requisicao = ctx_base.req
        rota, params = self.resolver(requisicao.metodo, requisicao.caminho)
        ctx = ctx_base.para_rota(rota, requisicao.com_params(params))
        if rota.exige_autenticacao:
            autenticador = self.autenticador or ctx_base.app.autenticador
            if autenticador is None:
                raise nao_autenticado()
            ctx.usuario = autenticador(ctx, rota)
        resultado = rota.handler(ctx)
        if isinstance(resultado, Resposta):
            return resultado
        if resultado is None:
            return Resposta.sem_conteudo()
        return Resposta.ok(resultado)


def descobrir_rotas(pacote: str = "routes") -> list[Rota]:
    """Importa cada módulo do pacote e coleta ``ROTAS`` (ou ``rotas()``)."""
    try:
        raiz = importlib.import_module(pacote)
    except ImportError as exc:
        raise ErroConfiguracao(f"Pacote de rotas não encontrado: {pacote}") from exc
    caminhos = getattr(raiz, "__path__", None)
    if caminhos is None:
        raise ErroConfiguracao(f"{pacote} não é um pacote")
    rotas: list[Rota] = []
    for info in sorted(pkgutil.iter_modules(caminhos), key=lambda i: i.name):
        if info.name.startswith("_"):
            continue
        modulo = importlib.import_module(f"{pacote}.{info.name}")
        fonte = getattr(modulo, "ROTAS", None)
        if fonte is None and callable(getattr(modulo, "rotas", None)):
            fonte = modulo.rotas()
        if fonte is None:
            raise ErroConfiguracao(f"Módulo de rotas sem ROTAS: {pacote}.{info.name}")
        for rota in fonte:
            if not isinstance(rota, Rota):
                raise ErroConfiguracao(f"{pacote}.{info.name}: ROTAS deve conter objetos Rota")
            rotas.append(rota)
    return rotas


def criar_roteador(pacote: str = "routes", autenticador: Autenticador | None = None) -> Roteador:
    return Roteador(descobrir_rotas(pacote), autenticador)


__all__ = [
    "Autenticador",
    "Handler",
    "Roteador",
    "Rota",
    "criar_roteador",
    "descobrir_rotas",
]
