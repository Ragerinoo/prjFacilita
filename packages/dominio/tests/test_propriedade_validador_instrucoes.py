"""Teste de propriedade do validador de instruções do seed.
Feature: tres-autoatendimento, Property 20: Validador de instruções do seed
**Validates: Requirements 3.1, 3.3, 3.4, 19.5**

Uma instrução é aceita sse tem 1 a 10 passos numerados a partir de 1, texto <= 140,
alt não vazio <= 125, texto_equivalente presente e (se informado) título <= 40.
Qualquer violação é reportada com o campo correspondente.
"""
from __future__ import annotations

import copy
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from dominio.guia import (
    MAX_ALT,
    MAX_PASSOS,
    MAX_TEXTO_PASSO,
    MAX_TITULO_PROBLEMA,
    instrucao_de_dict,
    validar_instrucao,
)

_ALFABETO = st.characters(blacklist_categories=("Cs", "Z", "C"))


def _texto(max_size: int) -> st.SearchStrategy[str]:
    """Texto não vazio, sem espaços em branco, com 1..max_size caracteres."""
    return st.text(_ALFABETO, min_size=1, max_size=max_size)


@st.composite
def _passos_validos(draw: st.DrawFn, quantidade: int) -> list[dict[str, Any]]:
    return [
        {
            "n": n,
            "texto": draw(_texto(MAX_TEXTO_PASSO)),
            "alt": draw(_texto(MAX_ALT)),
            "texto_equivalente": draw(_texto(300)),
            "midia_url": None,
            "midia_tipo": None,
        }
        for n in range(1, quantidade + 1)
    ]


@st.composite
def _instrucoes_validas(draw: st.DrawFn) -> dict[str, Any]:
    quantidade = draw(st.integers(min_value=1, max_value=MAX_PASSOS))
    return {
        "modelo_id": "tres-passione",
        "problema_id": draw(st.integers(min_value=1, max_value=99)),
        "variante": draw(st.sampled_from(["padrao", "externo"])),
        "passos": draw(_passos_validos(quantidade)),
    }


_titulos_validos = _texto(MAX_TITULO_PROBLEMA)


def _campos(erros: list[Any]) -> set[str]:
    return {e.campo for e in erros}


@given(_instrucoes_validas(), _titulos_validos)
def test_instrucao_dentro_dos_limites_e_aceita(instrucao: dict[str, Any], titulo: str) -> None:
    assert validar_instrucao(instrucao, titulo) == []
    # A forma tipada (Instrucao/Passo) também é aceita.
    assert validar_instrucao(instrucao_de_dict(instrucao), titulo) == []


# Cada violação: (função que corrompe a instrução, campo esperado no erro).
def _texto_longo(i: dict[str, Any], k: int) -> str:
    i["passos"][k]["texto"] = "a" * (MAX_TEXTO_PASSO + 1)
    return f"passos[{k}].texto"


def _alt_longo(i: dict[str, Any], k: int) -> str:
    i["passos"][k]["alt"] = "a" * (MAX_ALT + 1)
    return f"passos[{k}].alt"


def _alt_vazio(i: dict[str, Any], k: int) -> str:
    i["passos"][k]["alt"] = ""
    return f"passos[{k}].alt"


def _alt_ausente(i: dict[str, Any], k: int) -> str:
    del i["passos"][k]["alt"]
    return f"passos[{k}].alt"


def _equivalente_ausente(i: dict[str, Any], k: int) -> str:
    del i["passos"][k]["texto_equivalente"]
    return f"passos[{k}].texto_equivalente"


def _equivalente_vazio(i: dict[str, Any], k: int) -> str:
    i["passos"][k]["texto_equivalente"] = "   "
    return f"passos[{k}].texto_equivalente"


def _texto_vazio(i: dict[str, Any], k: int) -> str:
    i["passos"][k]["texto"] = ""
    return f"passos[{k}].texto"


_CORRUPCOES = [
    _texto_longo,
    _alt_longo,
    _alt_vazio,
    _alt_ausente,
    _equivalente_ausente,
    _equivalente_vazio,
    _texto_vazio,
]


@given(_instrucoes_validas(), _titulos_validos, st.sampled_from(_CORRUPCOES), st.data())
def test_violacao_de_passo_e_reportada_com_o_campo(
    instrucao: dict[str, Any], titulo: str, corrupcao: Any, data: st.DataObject
) -> None:
    k = data.draw(st.integers(min_value=0, max_value=len(instrucao["passos"]) - 1))
    corrompida = copy.deepcopy(instrucao)
    campo = corrupcao(corrompida, k)
    assert campo in _campos(validar_instrucao(corrompida, titulo))


@given(_instrucoes_validas(), _titulos_validos, st.integers(min_value=MAX_PASSOS + 1, max_value=25))
def test_mais_de_10_passos_e_reportado(
    instrucao: dict[str, Any], titulo: str, total: int
) -> None:
    instrucao = copy.deepcopy(instrucao)
    instrucao["passos"] = [
        {**instrucao["passos"][0], "n": n} for n in range(1, total + 1)
    ]
    assert "passos" in _campos(validar_instrucao(instrucao, titulo))


@given(_instrucoes_validas(), _titulos_validos)
def test_zero_passos_e_reportado(instrucao: dict[str, Any], titulo: str) -> None:
    instrucao = {**instrucao, "passos": []}
    assert "passos" in _campos(validar_instrucao(instrucao, titulo))


@given(_instrucoes_validas(), st.integers(min_value=MAX_TITULO_PROBLEMA + 1, max_value=200))
def test_titulo_com_mais_de_40_caracteres_e_reportado(
    instrucao: dict[str, Any], tamanho: int
) -> None:
    assert "titulo" in _campos(validar_instrucao(instrucao, "t" * tamanho))


@given(_instrucoes_validas(), st.sampled_from(["", "   ", "\n\t"]))
def test_titulo_vazio_e_reportado(instrucao: dict[str, Any], titulo: str) -> None:
    assert "titulo" in _campos(validar_instrucao(instrucao, titulo))


@given(_instrucoes_validas(), _titulos_validos, st.integers(min_value=1, max_value=MAX_PASSOS))
def test_fronteiras_exatas_sao_aceitas(
    instrucao: dict[str, Any], titulo: str, quantidade: int
) -> None:
    instrucao = copy.deepcopy(instrucao)
    instrucao["passos"] = [
        {
            "n": n,
            "texto": "a" * MAX_TEXTO_PASSO,
            "alt": "a" * MAX_ALT,
            "texto_equivalente": "x",
        }
        for n in range(1, quantidade + 1)
    ]
    assert validar_instrucao(instrucao, "t" * MAX_TITULO_PROBLEMA) == []
