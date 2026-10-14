"""Teste de propriedade do limiar de relevância e das fontes da resposta (Req 6.2, 6.3, 6.4).

Feature: tres-autoatendimento, Property 18: Limiar de relevância e fontes da resposta

Para qualquer conjunto de trechos recuperados e qualquer limiar:
  - `sem_embasamento` é verdadeiro se e somente se não há trecho elegível (do modelo da Jornada,
    com `manual` e `secao` nos metadados) ou se a maior pontuação entre os elegíveis é menor
    que o limiar (Req 6.4);
  - só trechos do modelo da Jornada são considerados (Req 6.2);
  - as fontes vêm exclusivamente dos metadados dos trechos relevantes, nunca do texto (Req 6.3);
  - pontuação ausente (None) vale 0.

**Validates: Requirements 6.2, 6.3, 6.4**
"""

from __future__ import annotations

import string

from hypothesis import given
from hypothesis import strategies as st

from dominio.recuperacao import (
    Fonte,
    TrechoRecuperado,
    avaliar_recuperacao,
)

_MODELO = "modelo-alvo"
_OUTROS_MODELOS = ["outro-modelo", "modelo-x", "MODELO-ALVO", "modelo-alvo-2"]

_nomes = st.text(alphabet=string.ascii_letters + string.digits + " ._-", min_size=1, max_size=12)
_nomes = _nomes.filter(lambda s: s.strip() != "")

_scores = st.one_of(
    st.none(),
    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)

_limiares = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


@st.composite
def _trechos(draw) -> TrechoRecuperado:
    """Trecho com metadados completos, de um modelo qualquer (o alvo ou outro)."""
    modelo = draw(st.sampled_from([_MODELO, *_OUTROS_MODELOS]))
    metadados = {
        "modelo_id": modelo,
        "manual": draw(_nomes),
        "secao": draw(_nomes),
    }
    # Metadados incompletos: parte dos trechos perde manual/secao/modelo_id.
    for chave in draw(st.lists(st.sampled_from(sorted(metadados)), max_size=1, unique=True)):
        if draw(st.booleans()):
            del metadados[chave]
        else:
            metadados[chave] = ""
    texto = draw(st.text(max_size=40))
    return TrechoRecuperado(texto=texto, score=draw(_scores), metadados=metadados)


_listas = st.lists(_trechos(), max_size=12)


def _eh_elegivel(t: TrechoRecuperado) -> bool:
    m = t.metadados
    return (
        m.get("modelo_id") == _MODELO
        and bool(m.get("manual", "").strip())
        and bool(m.get("secao", "").strip())
    )


def _pontuacao(t: TrechoRecuperado) -> float:
    return 0.0 if t.score is None else t.score


@given(trechos=_listas, limiar=_limiares)
def test_sem_embasamento_se_e_somente_se_nenhum_elegivel_atinge_limiar(trechos, limiar):
    resultado = avaliar_recuperacao(trechos, _MODELO, limiar)

    elegiveis = [t for t in trechos if _eh_elegivel(t)]
    esperado = not elegiveis or max(_pontuacao(t) for t in elegiveis) < limiar

    assert resultado.sem_embasamento is esperado
    if resultado.sem_embasamento:
        assert resultado.trechos == ()
        assert resultado.fontes == ()


@given(trechos=_listas, limiar=_limiares)
def test_so_trechos_do_modelo_da_jornada_sao_considerados(trechos, limiar):
    resultado = avaliar_recuperacao(trechos, _MODELO, limiar)

    for t in resultado.trechos:
        assert t.metadados["modelo_id"] == _MODELO
        assert _pontuacao(t) >= limiar

    # Os trechos devolvidos são exatamente os elegíveis com pontuação >= limiar, em ordem.
    if not resultado.sem_embasamento:
        esperados = [t for t in trechos if _eh_elegivel(t) and _pontuacao(t) >= limiar]
        assert list(resultado.trechos) == esperados

    # Descartar os trechos de outros modelos não muda o resultado.
    so_do_modelo = [t for t in trechos if t.metadados.get("modelo_id") == _MODELO]
    assert avaliar_recuperacao(so_do_modelo, _MODELO, limiar) == resultado


@given(trechos=_listas, limiar=_limiares)
def test_fontes_vem_dos_metadados_dos_trechos_relevantes(trechos, limiar):
    resultado = avaliar_recuperacao(trechos, _MODELO, limiar)
    if resultado.sem_embasamento:
        return

    esperadas: list[Fonte] = []
    for t in trechos:
        if _eh_elegivel(t) and _pontuacao(t) >= limiar:
            fonte = Fonte(manual=t.metadados["manual"], secao=t.metadados["secao"])
            if fonte not in esperadas:
                esperadas.append(fonte)

    assert resultado.fontes
    assert list(resultado.fontes) == esperadas


@given(
    textos=st.lists(st.text(max_size=30), min_size=1, max_size=6),
    limiar=_limiares,
    manual=_nomes,
    secao=_nomes,
)
def test_fontes_nao_dependem_do_texto_dos_trechos(textos, limiar, manual, secao):
    """Trocar apenas o texto dos trechos não altera as fontes (Req 6.3)."""
    metadados = {"modelo_id": _MODELO, "manual": manual, "secao": secao}
    originais = [TrechoRecuperado(texto=x, score=1.0, metadados=metadados) for x in textos]
    alterados = [TrechoRecuperado(texto="Manual X, seção 9", score=1.0, metadados=metadados)] * len(
        textos
    )

    r1 = avaliar_recuperacao(originais, _MODELO, limiar)
    r2 = avaliar_recuperacao(alterados, _MODELO, limiar)

    assert r1.sem_embasamento is False
    assert r1.fontes == r2.fontes == (Fonte(manual=manual, secao=secao),)


@given(
    quantidade=st.integers(min_value=1, max_value=6),
    limiar=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)
def test_pontuacao_ausente_vale_zero(quantidade, limiar):
    metadados = {"modelo_id": _MODELO, "manual": "Manual", "secao": "1.1"}
    trechos = [TrechoRecuperado(texto="t", score=None, metadados=metadados)] * quantidade

    resultado = avaliar_recuperacao(trechos, _MODELO, limiar)

    # Equivale a pontuação 0.0: só atinge o limiar se ele for 0.
    com_zero = [TrechoRecuperado(texto="t", score=0.0, metadados=metadados)] * quantidade
    equivalente = avaliar_recuperacao(com_zero, _MODELO, limiar)
    assert resultado.sem_embasamento is equivalente.sem_embasamento is (limiar > 0.0)
    assert resultado.fontes == equivalente.fontes
    assert resultado.maior_pontuacao == equivalente.maior_pontuacao == 0.0
    assert len(resultado.trechos) == len(equivalente.trechos)
