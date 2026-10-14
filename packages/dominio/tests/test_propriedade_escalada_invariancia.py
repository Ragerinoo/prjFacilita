"""Teste de propriedade da invariância da decisão do Motor_Escalada (Req 11.5).

Feature: tres-autoatendimento, Property 1: Decisão do Motor_Escalada é determinística e
invariante a fatores irrelevantes

Para quaisquer dois `FatosJornada` com os mesmos valores de `risco_seguranca` e
`guia_respondeu_nao`, e qualquer variação de sentimento, problema, conjunto e ordem dos
gatilhos, `decidir_escalada` devolve a mesma prioridade, classificação, canal e critério.

**Validates: Requirements 11.5**
"""

from __future__ import annotations

from typing import get_args

from hypothesis import given
from hypothesis import strategies as st

from dominio.escalada import decidir_escalada
from dominio.tipos import FatosJornada, Gatilho, Nivel

_gatilhos = st.lists(st.sampled_from(get_args(Gatilho)), max_size=10)
_sentimentos = st.one_of(st.none(), st.sampled_from(get_args(Nivel)))
_problemas = st.one_of(st.none(), st.text(max_size=30))


@st.composite
def _fatos_com_mesmos_relevantes(draw):
    """Dois FatosJornada com risco/guia iguais e todo o resto variando livremente."""
    risco = draw(st.booleans())
    guia_nao = draw(st.booleans())

    def _fatos() -> FatosJornada:
        # Gatilhos montados a partir de listas em ordens arbitrárias (a ordem de inserção
        # é a única "ordem" possível num frozenset).
        return FatosJornada(
            risco_seguranca=risco,
            guia_respondeu_nao=guia_nao,
            gatilhos=frozenset(draw(_gatilhos)),
            sentimento=draw(_sentimentos),
            problema_id=draw(_problemas),
        )

    return _fatos(), _fatos()


@given(_fatos_com_mesmos_relevantes())
def test_decisao_invariante_a_fatores_irrelevantes(par):
    a, b = par
    assert decidir_escalada(a) == decidir_escalada(b)


@given(_fatos_com_mesmos_relevantes())
def test_decisao_e_deterministica(par):
    a, _ = par
    primeira = decidir_escalada(a)
    assert decidir_escalada(a) == primeira
    assert (primeira.prioridade, primeira.classificacao, primeira.canal, primeira.criterio) == (
        decidir_escalada(a).prioridade,
        decidir_escalada(a).classificacao,
        decidir_escalada(a).canal,
        decidir_escalada(a).criterio,
    )


@given(
    risco=st.booleans(),
    guia_nao=st.booleans(),
    gatilhos=_gatilhos,
    sentimento=_sentimentos,
    problema=_problemas,
)
def test_decisao_igual_a_dos_fatos_minimos(risco, guia_nao, gatilhos, sentimento, problema):
    """Fatos completos decidem como os fatos reduzidos aos dois campos relevantes."""
    completos = FatosJornada(
        risco_seguranca=risco,
        guia_respondeu_nao=guia_nao,
        gatilhos=frozenset(gatilhos),
        sentimento=sentimento,
        problema_id=problema,
    )
    minimos = FatosJornada(risco_seguranca=risco, guia_respondeu_nao=guia_nao)
    assert decidir_escalada(completos) == decidir_escalada(minimos)
