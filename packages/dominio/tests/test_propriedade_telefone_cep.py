"""Teste de propriedade da validação de telefone e CEP.
Feature: tres-autoatendimento, Property 21: Validação de telefone e CEP
**Validates: Requirements 12.6**
"""
from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

from dominio.validadores import validar_cep, validar_telefone

_PERMITIDOS = "0123456789 ()-"
_SO_PERMITIDOS = re.compile(r"[0-9 ()\-]*")

# Texto arbitrário (inclui dígitos unicode não-ASCII, letras, símbolos, quebras de linha).
_texto_livre = st.text(max_size=30)
# Texto só com o alfabeto permitido: 0 a 14 caracteres, cobrindo as bordas 7/8/9/10/11/12 dígitos.
_texto_permitido = st.text(alphabet=_PERMITIDOS, max_size=14)
# Texto permitido com um único caractere estranho injetado em posição arbitrária.
_texto_contaminado = st.builds(
    lambda base, ch, i: base[: i % (len(base) + 1)] + ch + base[i % (len(base) + 1) :],
    st.text(alphabet="0123456789", min_size=8, max_size=11),
    st.sampled_from(["a", ".", "+", "/", "\n", "\u0663", "\uff11", "x", "_"]),
    st.integers(min_value=0, max_value=20),
)
_entradas = st.one_of(_texto_livre, _texto_permitido, _texto_contaminado)


def _oraculo(s: str, aceitos: tuple[int, ...]) -> bool:
    """Especificação literal da propriedade, independente da implementação."""
    return _SO_PERMITIDOS.fullmatch(s) is not None and sum(c in "0123456789" for c in s) in aceitos


@given(_entradas)
def test_telefone_aceita_sse_formato_e_10_ou_11_digitos(s: str) -> None:
    assert validar_telefone(s) is _oraculo(s, (10, 11))


@given(_entradas)
def test_cep_aceita_sse_formato_e_8_digitos(s: str) -> None:
    assert validar_cep(s) is _oraculo(s, (8,))
