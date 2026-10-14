"""Testes unitários do Motor_Escalada (task 3.1)."""

from __future__ import annotations

import pytest

from dominio.escalada import (
    CANAL_P1,
    CANAL_P2,
    CANAL_P3,
    atingiu_limite_mensagens,
    decidir_escalada,
    frustracao_dispara_escalada,
    negativas_ia_disparam_escalada,
    pode_chamar_modelo,
    proximo_contador_negativas_ia,
    proximo_estado_frustracao,
    reavaliar_prioridade,
)
from dominio.tipos import FatosJornada


def _fatos(risco: bool, nao: bool, **kw) -> FatosJornada:
    return FatosJornada(risco_seguranca=risco, guia_respondeu_nao=nao, **kw)


@pytest.mark.parametrize(
    ("risco", "nao", "prio", "classe", "canal", "criterio"),
    [
        (True, True, "P1", "provável defeito", CANAL_P1, 1),
        (True, False, "P1", "provável defeito", CANAL_P1, 1),
        (False, True, "P2", "provável defeito", CANAL_P2, 2),
        (False, False, "P3", "provável uso", CANAL_P3, 3),
    ],
)
def test_tabela_de_decisao(risco, nao, prio, classe, canal, criterio):
    d = decidir_escalada(_fatos(risco, nao))
    assert (d.prioridade, d.classificacao, d.canal, d.criterio) == (prio, classe, canal, criterio)


def test_decisao_ignora_gatilhos_sentimento_e_problema():
    base = decidir_escalada(_fatos(False, True))
    outro = decidir_escalada(
        _fatos(
            False,
            True,
            gatilhos=frozenset({"frustracao_alta", "pedido_humano"}),
            sentimento="alta",
            problema_id="7",
        )
    )
    assert base == outro


def test_reavaliar_eleva_p3_para_p1_com_risco_tardio():
    atual = decidir_escalada(_fatos(False, False))
    nova = reavaliar_prioridade(atual, _fatos(True, False))
    assert nova.prioridade == "P1" and nova.criterio == 1


def test_reavaliar_eleva_p3_para_p2():
    atual = decidir_escalada(_fatos(False, False))
    assert reavaliar_prioridade(atual, _fatos(False, True)).prioridade == "P2"


def test_reavaliar_nunca_reduz():
    p1 = decidir_escalada(_fatos(True, False))
    assert reavaliar_prioridade(p1, _fatos(False, False)) == p1
    p2 = decidir_escalada(_fatos(False, True))
    assert reavaliar_prioridade(p2, _fatos(False, False)) == p2


def test_reavaliar_mesma_prioridade_mantem_atual():
    p2 = decidir_escalada(_fatos(False, True))
    assert reavaliar_prioridade(p2, _fatos(False, True)) is p2


@pytest.mark.parametrize(
    ("msgs", "esperado"), [(0, True), (9, True), (10, False), (11, False)]
)
def test_pode_chamar_modelo_limite_10(msgs, esperado):
    assert pode_chamar_modelo(msgs, 10) is esperado
    assert pode_chamar_modelo(msgs) is esperado
    assert atingiu_limite_mensagens(msgs) is (not esperado)


def test_pode_chamar_modelo_rejeita_contagem_negativa():
    with pytest.raises(ValueError):
        pode_chamar_modelo(-1, 10)


def test_frustracao_alta_soma_e_zera():
    assert proximo_estado_frustracao(0, "alta") == 1
    assert proximo_estado_frustracao(1, "alta") == 2
    assert proximo_estado_frustracao(1, "média") == 0
    assert proximo_estado_frustracao(1, "baixa") == 0
    assert not frustracao_dispara_escalada(1)
    assert frustracao_dispara_escalada(2)


def test_segunda_negativa_do_assistente_dispara():
    c = proximo_contador_negativas_ia(0, "ia", "nao")
    assert c == 1 and not negativas_ia_disparam_escalada(c)
    c = proximo_contador_negativas_ia(c, "ia", "sim")  # "Sim" não zera
    assert c == 1
    c = proximo_contador_negativas_ia(c, "ia", "nao")
    assert c == 2 and negativas_ia_disparam_escalada(c)


def test_nao_do_guia_nao_conta():
    assert proximo_contador_negativas_ia(0, "guia", "nao") == 0
    assert proximo_contador_negativas_ia(1, "guia", "nao") == 1
