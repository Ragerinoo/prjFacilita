"""Teste de propriedade dos dados pessoais solicitados (Req 12.2, 12.3, 12.4).

Feature: tres-autoatendimento, Property 23: Dados pessoais solicitados dependem só da
prioridade e do que falta

Para qualquer prioridade e qualquer subconjunto de dados já informados, o conjunto solicitado é
o exigido pela prioridade (P1: telefone; P2: telefone e CEP; P3: nenhum) menos o que já foi
informado, sem nunca pedir de novo um dado já informado.

**Validates: Requirements 12.2, 12.3, 12.4**
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from dominio.validadores import CEP, TELEFONE, dados_pessoais_solicitados

_EXIGIDOS = {
    "P1": frozenset({TELEFONE}),
    "P2": frozenset({TELEFONE, CEP}),
    "P3": frozenset(),
}

_prioridades = st.sampled_from(["P1", "P2", "P3"])
_informados = st.frozensets(st.sampled_from([TELEFONE, CEP]))


@given(prioridade=_prioridades, ja_informados=_informados)
def test_solicitado_e_exigido_menos_informado(prioridade, ja_informados):
    solicitado = dados_pessoais_solicitados(prioridade, ja_informados)

    # Conjunto solicitado = exigido pela prioridade menos o já informado (Req 12.2, 12.3, 12.4).
    assert set(solicitado) == _EXIGIDOS[prioridade] - ja_informados
    # Nunca pede de novo um dado já informado, nem repete um dado (Req 12.4).
    assert not set(solicitado) & ja_informados
    assert len(solicitado) == len(set(solicitado))


@given(prioridade=_prioridades, ja_informados=_informados, extras=st.permutations([TELEFONE, CEP]))
def test_resultado_independe_do_tipo_e_da_ordem_dos_informados(prioridade, ja_informados, extras):
    # Só importa quais dados faltam: lista, tupla ou conjunto, em qualquer ordem.
    ordenados = [d for d in extras if d in ja_informados]
    esperado = dados_pessoais_solicitados(prioridade, ja_informados)
    assert dados_pessoais_solicitados(prioridade, ordenados) == esperado
    assert dados_pessoais_solicitados(prioridade, tuple(ordenados)) == esperado


@given(prioridade=_prioridades)
def test_sem_dados_informados_pede_tudo_que_a_prioridade_exige(prioridade):
    assert set(dados_pessoais_solicitados(prioridade)) == _EXIGIDOS[prioridade]
    assert set(dados_pessoais_solicitados(prioridade, ())) == _EXIGIDOS[prioridade]
