"""Consulta ao Catalogo_Maquinas com prazo de 5 s (Req 1.7).

Regras:
  * modelo inativo (`ativo=false`) conta como inexistente: não aparece na grade (Req 2.1), não
    abre Pagina_Maquina e não vira modelo de Jornada;
  * `modelo_id` fora do formato de slug nem chega ao banco (Req 1.6);
  * se o catálogo não responde em `PRAZO_CATALOGO_S`, levanta `ErroApi` 504 ``tempo_esgotado``
    com a mensagem de indisponibilidade temporária; quem chama NÃO deve criar a Jornada.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

from core.erros import tempo_esgotado
from core.prazo import com_prazo
from dominio.qr import PADRAO_MODELO_ID, TAMANHO_MAX_MODELO_ID
from repositorios.catalogo import (
    CatalogoRepo,
    InstrucaoCatalogo,
    ModeloCatalogo,
    ProblemaCatalogo,
)
from repositorios.interfaces import Repositorios

PRAZO_CATALOGO_S: Final = 5.0  # Req 1.7
MENSAGEM_INDISPONIVEL: Final = (
    "O catálogo de máquinas está indisponível por um instante. Tente de novo."
)


def modelo_id_legivel(valor: Any) -> bool:
    """Verdadeiro se `valor` tem o formato de `modelo_id` (slug, até 64 caracteres)."""
    return (
        isinstance(valor, str)
        and len(valor) <= TAMANHO_MAX_MODELO_ID
        and PADRAO_MODELO_ID.fullmatch(valor) is not None
    )


def _consultar[T](repos: Repositorios, consulta: Callable[[CatalogoRepo], T]) -> T:
    try:
        return com_prazo(lambda: consulta(repos.catalogo), PRAZO_CATALOGO_S)
    except TimeoutError:
        raise tempo_esgotado(MENSAGEM_INDISPONIVEL) from None


def listar_modelos_ativos(repos: Repositorios) -> list[ModeloCatalogo]:
    """Modelos ativos em ordem alfabética de nome (Req 2.1)."""
    modelos = _consultar(repos, lambda c: c.listar_modelos())
    return sorted((m for m in modelos if m.ativo), key=lambda m: (m.nome_normalizado, m.modelo_id))


def obter_modelo_ativo(repos: Repositorios, modelo_id: Any) -> ModeloCatalogo | None:
    """O modelo, ou `None` se o id é ilegível, não existe ou está inativo."""
    if not modelo_id_legivel(modelo_id):
        return None
    modelo = _consultar(repos, lambda c: c.obter_modelo(modelo_id))
    return modelo if modelo is not None and modelo.ativo else None


def obter_instrucao(
    repos: Repositorios, modelo_id: str, problema_id: int, variante: str
) -> InstrucaoCatalogo | None:
    """O item de instrução cadastrado para (modelo, problema, variante), com prazo de 5 s."""
    return _consultar(repos, lambda c: c.obter_instrucao(modelo_id, problema_id, variante))


def carregar_pagina_maquina(
    repos: Repositorios, modelo_id: Any
) -> tuple[ModeloCatalogo, list[ProblemaCatalogo]] | None:
    """Modelo e Problemas_Catalogados numa só consulta com prazo; `None` se não há modelo."""
    if not modelo_id_legivel(modelo_id):
        return None

    def consulta(
        catalogo: CatalogoRepo,
    ) -> tuple[ModeloCatalogo, list[ProblemaCatalogo]] | None:
        modelo = catalogo.obter_modelo(modelo_id)
        if modelo is None or not modelo.ativo:
            return None
        return modelo, catalogo.listar_problemas()

    return _consultar(repos, consulta)


__all__ = [
    "MENSAGEM_INDISPONIVEL",
    "PRAZO_CATALOGO_S",
    "carregar_pagina_maquina",
    "listar_modelos_ativos",
    "obter_instrucao",
    "obter_modelo_ativo",
]
