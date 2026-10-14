"""Teste de propriedade da interpretação da URL do Codigo_QR (Req 1.2, 1.5, 1.6).

Feature: tres-autoatendimento, Property 25: Interpretação da URL do QR

Para qualquer URL no formato `/m/{modelo_id}?s={serie}` (com ou sem esquema e domínio), a
função devolve o `modelo_id` e a série quando esta tem de 1 a 30 caracteres alfanuméricos;
série ausente ou inválida é descartada sem invalidar o modelo. Para qualquer outra entrada
(texto arbitrário ou valor que não seja texto) a função nunca lança exceção e devolve
"não legível" ou um resultado legível com `modelo_id` válido.

**Validates: Requirements 1.2, 1.5, 1.6**
"""

from __future__ import annotations

import string
from urllib.parse import quote

from hypothesis import given
from hypothesis import strategies as st

from dominio.qr import (
    NAO_LEGIVEL,
    PADRAO_MODELO_ID,
    PADRAO_SERIE,
    TAMANHO_MAX_MODELO_ID,
    InterpretacaoQR,
    interpretar_qr,
)

_ALNUM = string.ascii_letters + string.digits
_SEGMENTO = string.ascii_lowercase + string.digits

_modelo_ids = st.lists(
    st.text(alphabet=_SEGMENTO, min_size=1, max_size=10), min_size=1, max_size=5
).map("-".join).filter(lambda m: len(m) <= TAMANHO_MAX_MODELO_ID)

_series_validas = st.text(alphabet=_ALNUM, min_size=1, max_size=30)

# Séries inválidas: vazias, longas demais ou com algum caractere fora de [A-Za-z0-9].
_series_invalidas = st.one_of(
    st.just(""),
    st.text(alphabet=_ALNUM, min_size=31, max_size=60),
    st.text(
        alphabet=st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=40
    ).filter(lambda s: PADRAO_SERIE.fullmatch(s) is None),
)

_prefixos = st.sampled_from(
    ["", "https://tres.example.com", "http://localhost:3000", "https://a.b.c.com.br"]
)


def _legivel_com_modelo_valido(r: InterpretacaoQR) -> bool:
    return (
        r.legivel
        and r.modelo_id is not None
        and len(r.modelo_id) <= TAMANHO_MAX_MODELO_ID
        and PADRAO_MODELO_ID.fullmatch(r.modelo_id) is not None
        and (r.numero_serie is None or PADRAO_SERIE.fullmatch(r.numero_serie) is not None)
    )


@given(modelo_id=_modelo_ids, serie=_series_validas, prefixo=_prefixos)
def test_url_valida_devolve_modelo_e_serie(modelo_id: str, serie: str, prefixo: str) -> None:
    r = interpretar_qr(f"{prefixo}/m/{modelo_id}?s={serie}")
    assert r == InterpretacaoQR(legivel=True, modelo_id=modelo_id, numero_serie=serie)


@given(modelo_id=_modelo_ids, prefixo=_prefixos, barra_final=st.booleans())
def test_url_sem_serie_devolve_modelo_sem_serie(
    modelo_id: str, prefixo: str, barra_final: bool
) -> None:
    r = interpretar_qr(f"{prefixo}/m/{modelo_id}{'/' if barra_final else ''}")
    assert r == InterpretacaoQR(legivel=True, modelo_id=modelo_id, numero_serie=None)


@given(modelo_id=_modelo_ids, serie=_series_invalidas, prefixo=_prefixos)
def test_serie_invalida_e_descartada_sem_invalidar_modelo(
    modelo_id: str, serie: str, prefixo: str
) -> None:
    r = interpretar_qr(f"{prefixo}/m/{modelo_id}?s={quote(serie, safe='')}")
    assert r == InterpretacaoQR(legivel=True, modelo_id=modelo_id, numero_serie=None)


@given(texto=st.text(max_size=200))
def test_texto_arbitrario_nunca_lanca_e_e_coerente(texto: str) -> None:
    r = interpretar_qr(texto)
    assert r == NAO_LEGIVEL or _legivel_com_modelo_valido(r)
    if not r.legivel:
        assert r.modelo_id is None and r.numero_serie is None


@given(
    valor=st.one_of(
        st.none(),
        st.integers(),
        st.floats(),
        st.booleans(),
        st.binary(max_size=50),
        st.lists(st.text(max_size=10), max_size=3),
        st.dictionaries(st.text(max_size=5), st.integers(), max_size=3),
    )
)
def test_entrada_que_nao_e_texto_e_nao_legivel(valor: object) -> None:
    assert interpretar_qr(valor) == NAO_LEGIVEL


@given(modelo_id=st.text(max_size=80), serie=st.text(max_size=40))
def test_urls_quase_validas_nunca_lancam_e_sao_coerentes(modelo_id: str, serie: str) -> None:
    r = interpretar_qr(f"/m/{modelo_id}?s={serie}")
    assert r == NAO_LEGIVEL or _legivel_com_modelo_valido(r)
