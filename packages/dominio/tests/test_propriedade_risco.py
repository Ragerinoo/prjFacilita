"""Teste de propriedade do Detector_Risco (Req 8.1).

Feature: tres-autoatendimento, Property 3: Detector_Risco encontra qualquer termo de risco,
com qualquer caixa, acento ou negação

Para qualquer texto que contenha, como palavra ou expressão inteira, um termo da lista de risco
(com caixa e acentuação arbitrárias, cercado por qualquer outro texto e precedido ou não de
negação), `detectar_risco` devolve verdadeiro. Para qualquer texto sem termo da lista, devolve
falso.

**Validates: Requirements 8.1**
"""

from __future__ import annotations

import unicodedata

from hypothesis import given
from hypothesis import strategies as st

from dominio.risco import TERMOS_RISCO_PADRAO, detectar_risco

# Grafias possíveis de cada termo padrão (com e sem acento, como o cliente digitaria).
_GRAFIAS = {
    "queimado": ("queimado",),
    "cheiro de queimado": ("cheiro de queimado",),
    "fumaca": ("fumaca", "fumaça"),
    "choque": ("choque",),
    "faisca": ("faisca", "faísca"),
    "vazamento interno": ("vazamento interno",),
}

# Palavras neutras: nenhuma é termo de risco nem contém o termo como palavra inteira.
# Inclui quase-acertos ("queimadura", "choques", "fumacento") que não devem casar.
_PALAVRAS_NEUTRAS = (
    "minha", "cafeteira", "não", "liga", "a", "o", "de", "com", "quando", "eu", "tenho",
    "uma", "tres", "coração", "água", "vaza", "pela", "tampa", "barulho", "estranho",
    "queimadura", "choques", "fumacento", "faiscante", "vazamento", "interna", "cheiro",
    "bom", "café", "sai", "hoje", "ontem", "máquina", "12", "3corações", "ç", "ÃÕ",
)

_SEPARADORES = st.sampled_from(
    [" ", "  ", ", ", ". ", "! ", "? ", "; ", " - ", "\n", "\t", " (", ") "]
)


@st.composite
def _alterar_caixa(draw, texto: str) -> str:
    """Caixa arbitrária por caractere."""
    return "".join(
        c.upper() if draw(st.booleans()) else c.lower() for c in texto
    )


@st.composite
def _alterar_forma(draw, texto: str) -> str:
    """Forma Unicode arbitrária (composta/decomposta), preservando o texto visível."""
    forma = draw(st.sampled_from(["NFC", "NFD"]))
    return unicodedata.normalize(forma, texto)


_palavras_neutras = st.lists(st.sampled_from(_PALAVRAS_NEUTRAS), max_size=5)


@st.composite
def _contexto(draw) -> str:
    palavras = draw(_palavras_neutras)
    sep = draw(_SEPARADORES)
    return sep.join(palavras)


@st.composite
def _termo_variado(draw) -> str:
    base = draw(st.sampled_from(TERMOS_RISCO_PADRAO))
    grafia = draw(st.sampled_from(_GRAFIAS[base]))
    grafia = draw(_alterar_caixa(grafia))
    return draw(_alterar_forma(grafia))


@st.composite
def _texto_com_risco(draw) -> str:
    antes = draw(_contexto())
    termo = draw(_termo_variado())
    depois = draw(_contexto())
    negacao = draw(st.sampled_from(["", "não ", "NÃO ", "nao ", "nunca ", "sem ", "nem "]))
    s1 = draw(_SEPARADORES) if antes else ""
    s2 = draw(_SEPARADORES) if depois else ""
    return f"{antes}{s1}{negacao}{termo}{s2}{depois}"


@st.composite
def _texto_sem_risco(draw) -> str:
    palavras = draw(st.lists(st.sampled_from(_PALAVRAS_NEUTRAS), max_size=10))
    sep = draw(_SEPARADORES)
    texto = sep.join(palavras)
    return draw(_alterar_caixa(texto))


@given(texto=_texto_com_risco())
def test_detector_encontra_termo_com_qualquer_caixa_acento_ou_negacao(texto: str) -> None:
    assert detectar_risco(texto) is True


@given(texto=_texto_sem_risco())
def test_detector_nao_acusa_texto_sem_termo(texto: str) -> None:
    assert detectar_risco(texto) is False
