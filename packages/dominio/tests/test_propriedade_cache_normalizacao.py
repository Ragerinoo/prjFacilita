# Feature: tres-autoatendimento, Property 14: Normalização da pergunta é idempotente
# e unifica variações
"""Teste de propriedade da normalização do Cache_Respostas.

**Validates: Requirements 7.1, 7.2**
"""

from __future__ import annotations

import string

from hypothesis import given
from hypothesis import strategies as st

from dominio.cache import chave_cache, normalizar_pergunta

# Letras (com e sem acento) e dígitos que formam as palavras da pergunta.
_ALFABETO_PALAVRA = (
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789áéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇ"
)
_PALAVRA = st.text(alphabet=_ALFABETO_PALAVRA, min_size=1, max_size=10)
_PALAVRAS = st.lists(_PALAVRA, min_size=0, max_size=8)

_ESPACOS = st.text(alphabet=" \t\n\r\u00a0", min_size=1, max_size=4)
_ESPACOS_OPCIONAIS = st.text(alphabet=" \t\n\r\u00a0", min_size=0, max_size=4)
_PONTUACAO = st.text(alphabet=string.punctuation + "¿¡«»", min_size=0, max_size=3)
_ACENTOS_COMBINANTES = st.text(
    alphabet="\u0300\u0301\u0302\u0303\u0308\u0327", min_size=0, max_size=2
)


@st.composite
def _variacao_da_palavra(draw: st.DrawFn, palavra: str) -> str:
    """Reescreve a palavra mudando só caixa, acentos combinantes e pontuação interna."""
    saida: list[str] = []
    for caractere in palavra:
        caixa = draw(st.sampled_from([str.lower, str.upper, str.swapcase, str]))
        saida.append(caixa(caractere))
        saida.append(draw(_ACENTOS_COMBINANTES))
        saida.append(draw(_PONTUACAO))
    return "".join(saida)


@st.composite
def _pergunta_e_variacao(draw: st.DrawFn) -> tuple[str, str]:
    """Gera uma pergunta e outra que difere só em caixa, acentos, pontuação e espaços."""
    palavras = draw(_PALAVRAS)
    original = " ".join(palavras)

    partes = [draw(_ESPACOS_OPCIONAIS), draw(_PONTUACAO)]
    for indice, palavra in enumerate(palavras):
        if indice > 0:
            partes.append(draw(_ESPACOS))  # separador entre palavras nunca é vazio
            partes.append(draw(_PONTUACAO))
            partes.append(draw(_ESPACOS_OPCIONAIS))
        partes.append(draw(_variacao_da_palavra(palavra)))
    partes.append(draw(_PONTUACAO))
    partes.append(draw(_ESPACOS_OPCIONAIS))
    return original, "".join(partes)


@given(st.text())
def test_normalizacao_e_idempotente(texto: str) -> None:
    uma_vez = normalizar_pergunta(texto)
    assert normalizar_pergunta(uma_vez) == uma_vez


@given(_pergunta_e_variacao())
def test_variacoes_unificam_pergunta_normalizada(par: tuple[str, str]) -> None:
    original, variacao = par
    assert normalizar_pergunta(variacao) == normalizar_pergunta(original)


@given(_pergunta_e_variacao(), st.text(alphabet=string.ascii_letters + string.digits, min_size=1))
def test_variacoes_unificam_chave_e_encontram_entrada_inserida(
    par: tuple[str, str], modelo_id: str
) -> None:
    original, variacao = par
    assert chave_cache(modelo_id, variacao) == chave_cache(modelo_id, original)

    # Entrada inserida com o texto original é encontrada pela consulta com a variação.
    cache = {chave_cache(modelo_id, original): "resposta aprovada"}
    assert cache.get(chave_cache(modelo_id, variacao)) == "resposta aprovada"
