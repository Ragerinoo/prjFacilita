"""Guia_Diagnostico puro (Req 3, 19.5).

Dados, não código: as instruções vêm do catálogo (seed) por
`(modelo_id, problema_id, variante)`. A mesma entrada gera sempre os mesmos
passos (Req 3.6): nada aqui usa relógio, aleatoriedade, I/O ou IA.

Formato aceito do catálogo (`seed/instrucoes/<modelo_id>.json`):
  * um mapeamento com a chave `"instrucoes"` (lista de instruções); ou
  * um mapeamento `(modelo_id, problema_id, variante) -> instrução`; ou
  * qualquer iterável de instruções (dicionários ou `Instrucao`).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from dominio.pacote import ErroCampo

VARIANTE_PADRAO = "padrao"
VARIANTE_EXTERNO = "externo"
VARIANTES = (VARIANTE_PADRAO, VARIANTE_EXTERNO)

MAX_PASSOS = 10  # Req 3.3
MAX_TEXTO_PASSO = 140  # Req 3.3
MAX_ALT = 125  # Req 3.4
MAX_TITULO_PROBLEMA = 40  # Req 3.1


@dataclass(frozen=True, slots=True)
class Passo:
    """Um passo da instrução: uma ação, com mídia e alternativas textuais."""

    n: int
    texto: str
    alt: str
    texto_equivalente: str
    midia_url: str | None = None
    midia_tipo: str | None = None


@dataclass(frozen=True, slots=True)
class Instrucao:
    """Instrução de um Problema_Catalogado para um modelo e uma variante."""

    modelo_id: str
    problema_id: int | str
    variante: str
    passos: tuple[Passo, ...]


# --------------------------------------------------------------------------- #
# Conversão
# --------------------------------------------------------------------------- #


def passo_de_dict(obj: Mapping[str, Any]) -> Passo:
    """Constrói um `Passo` a partir de um dicionário no formato do seed."""
    return Passo(
        n=obj["n"],
        texto=obj["texto"],
        alt=obj["alt"],
        texto_equivalente=obj["texto_equivalente"],
        midia_url=obj.get("midia_url"),
        midia_tipo=obj.get("midia_tipo"),
    )


def instrucao_de_dict(obj: Mapping[str, Any]) -> Instrucao:
    """Constrói uma `Instrucao` (passos ordenados por `n`) a partir do formato do seed."""
    passos = tuple(sorted((passo_de_dict(p) for p in obj["passos"]), key=lambda p: p.n))
    return Instrucao(
        modelo_id=obj["modelo_id"],
        problema_id=obj["problema_id"],
        variante=obj["variante"],
        passos=passos,
    )


def _iterar_instrucoes(catalogo: Any) -> Iterable[Any]:
    if isinstance(catalogo, Mapping):
        if "instrucoes" in catalogo:
            return catalogo["instrucoes"]
        return catalogo.values()
    return catalogo


def _campo(item: Any, nome: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(nome)
    return getattr(item, nome, None)


# --------------------------------------------------------------------------- #
# Resolução
# --------------------------------------------------------------------------- #


def resolver_instrucao(
    catalogo: Any,
    modelo_id: str,
    problema_id: int | str,
    variante: str,
) -> Instrucao | None:
    """Devolve a instrução de `(modelo_id, problema_id, variante)` ou `None` (Req 3.6, 3.10, 3.11).

    Determinística: depende só dos argumentos. Não há cair para outra variante:
    a variante `externo` só existe para Vazamento, e vazamento interno não tem
    passos (Req 3.8). Se houver entradas repetidas para a mesma chave, vale a
    primeira na ordem do catálogo. Os passos saem ordenados por `n`.
    """
    if variante not in VARIANTES:
        return None
    for item in _iterar_instrucoes(catalogo):
        if (
            _campo(item, "modelo_id") == modelo_id
            and str(_campo(item, "problema_id")) == str(problema_id)
            and _campo(item, "variante") == variante
        ):
            if isinstance(item, Instrucao):
                return Instrucao(
                    item.modelo_id,
                    item.problema_id,
                    item.variante,
                    tuple(sorted(item.passos, key=lambda p: p.n)),
                )
            try:
                return instrucao_de_dict(item)
            except (KeyError, TypeError):
                return None
    return None


# --------------------------------------------------------------------------- #
# Validação (Req 3.1, 3.3, 3.4, 19.5)
# --------------------------------------------------------------------------- #


def _texto_valido(valor: Any, maximo: int | None = None) -> str | None:
    """Devolve o motivo da invalidade de um texto obrigatório, ou `None` se válido."""
    if not isinstance(valor, str) or not valor.strip():
        return "obrigatório e não vazio"
    if maximo is not None and len(valor) > maximo:
        return f"no máximo {maximo} caracteres (tem {len(valor)})"
    return None


def validar_titulo_problema(titulo: Any) -> list[ErroCampo]:
    """Título de Problema_Catalogado: 1 a 40 caracteres (Req 3.1)."""
    motivo = _texto_valido(titulo, MAX_TITULO_PROBLEMA)
    return [ErroCampo("titulo", motivo)] if motivo else []


def validar_instrucao(instrucao: Any, titulo: str | None = None) -> list[ErroCampo]:
    """Valida uma instrução; lista vazia significa válida.

    Regras: 1 a 10 passos numerados a partir de 1 (sequência 1, 2, 3...), texto de
    cada passo com até 140 caracteres, `alt` com até 125, `texto_equivalente`
    presente e, se `titulo` for informado, título com até 40 caracteres.
    Aceita `Instrucao` ou dicionário no formato do seed; nunca lança exceção.
    """
    erros: list[ErroCampo] = []
    if titulo is not None:
        erros.extend(validar_titulo_problema(titulo))

    if _campo(instrucao, "variante") not in VARIANTES:
        erros.append(ErroCampo("variante", f"deve ser uma de {', '.join(VARIANTES)}"))
    passos = _campo(instrucao, "passos")
    if isinstance(passos, (str, bytes)) or not isinstance(passos, (list, tuple)):
        erros.append(ErroCampo("passos", "deve ser uma lista de passos"))
        return erros
    if not 1 <= len(passos) <= MAX_PASSOS:
        erros.append(
            ErroCampo("passos", f"deve ter de 1 a {MAX_PASSOS} passos (tem {len(passos)})")
        )

    for indice, passo in enumerate(passos, start=1):
        base = f"passos[{indice - 1}]"
        n = _campo(passo, "n")
        if isinstance(n, bool) or n != indice or not isinstance(n, int):
            erros.append(ErroCampo(f"{base}.n", f"deve ser {indice} (numeração a partir de 1)"))
        for nome, maximo in (
            ("texto", MAX_TEXTO_PASSO),
            ("alt", MAX_ALT),
            ("texto_equivalente", None),
        ):
            motivo = _texto_valido(_campo(passo, nome), maximo)
            if motivo:
                erros.append(ErroCampo(f"{base}.{nome}", motivo))
    return erros


def instrucao_valida(instrucao: Any, titulo: str | None = None) -> bool:
    """Atalho booleano de `validar_instrucao`."""
    return not validar_instrucao(instrucao, titulo)
