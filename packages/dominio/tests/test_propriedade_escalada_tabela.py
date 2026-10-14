"""Teste de propriedade da tabela de decisão do Motor_Escalada.

Feature: tres-autoatendimento, Property 2: Tabela de decisão e precedência P1 > P2 > P3

**Validates: Requirements 11.1, 11.2, 11.3, 11.6, 5.3**
"""

from __future__ import annotations

from typing import get_args

from hypothesis import given
from hypothesis import strategies as st

from dominio.escalada import CANAL_P1, CANAL_P2, CANAL_P3, decidir_escalada
from dominio.tipos import FatosJornada, Gatilho, Nivel

_ORDEM = {"P1": 1, "P2": 2, "P3": 3}

# Fatos arbitrários: os dois booleanos relevantes mais campos irrelevantes à decisão.
fatos_strategy = st.builds(
    FatosJornada,
    risco_seguranca=st.booleans(),
    guia_respondeu_nao=st.booleans(),
    gatilhos=st.frozensets(st.sampled_from(get_args(Gatilho))),
    sentimento=st.one_of(st.none(), st.sampled_from(get_args(Nivel))),
    problema_id=st.one_of(st.none(), st.text(max_size=20)),
)


@given(fatos=fatos_strategy)
def test_tabela_de_decisao_e_precedencia(fatos: FatosJornada) -> None:
    decisao = decidir_escalada(fatos)

    # Critérios atendidos (1: risco, 2: sem risco e guia "não", 3: demais casos).
    atendidos = {
        "P1": fatos.risco_seguranca,
        "P2": fatos.guia_respondeu_nao,
        "P3": True,
    }
    # Precedência: a prioridade resultante é a mais alta entre os critérios atendidos.
    mais_alta = min((p for p, ok in atendidos.items() if ok), key=_ORDEM.__getitem__)
    assert decisao.prioridade == mais_alta

    if fatos.risco_seguranca:  # Req 11.1 (vale mesmo com guia_respondeu_nao verdadeiro)
        assert decisao.prioridade == "P1"
        assert decisao.classificacao == "provável defeito"
        assert decisao.canal == CANAL_P1 == "ligação imediata"
        assert decisao.criterio == 1
    elif fatos.guia_respondeu_nao:  # Req 11.2
        assert decisao.prioridade == "P2"
        assert decisao.classificacao == "provável defeito"
        assert decisao.canal == CANAL_P2 == "chat ou ligação, à escolha do Consumidor"
        assert decisao.criterio == 2
    else:  # Req 11.3
        assert decisao.prioridade == "P3"
        assert decisao.classificacao == "provável uso"
        assert decisao.canal == CANAL_P3 == "chat assíncrono"
        assert decisao.criterio == 3
