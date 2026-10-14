"""Testes unitários da fila do Painel_CS (Req 14.1)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from dominio.fila import (
    FILA_PK,
    ChamadoFila,
    chave_fila,
    montar_fila_sk,
    ordenar_fila,
)

T0 = datetime(2025, 1, 1, 12, 5, 11, tzinfo=UTC)


def test_formato_da_chave_segue_o_design() -> None:
    assert FILA_PK == "ABERTO"
    assert montar_fila_sk("P2", T0, "TRES-7K3M9QX2PD") == "P2#2025-01-01T12:05:11Z#TRES-7K3M9QX2PD"


def test_horario_com_outro_fuso_e_convertido_para_utc() -> None:
    brasilia = timezone(timedelta(hours=-3))
    local = datetime(2025, 1, 1, 9, 5, 11, tzinfo=brasilia)
    assert montar_fila_sk("P1", local, "A") == montar_fila_sk("P1", T0, "A")


def test_ordem_prioridade_depois_horario_depois_numero() -> None:
    c = [
        ChamadoFila("TRES-B", "P3", T0),
        ChamadoFila("TRES-B", "P1", T0 + timedelta(hours=1)),
        ChamadoFila("TRES-A", "P2", T0),
        ChamadoFila("TRES-C", "P1", T0),
        ChamadoFila("TRES-A", "P1", T0),
    ]
    assert [(x.prioridade, x.numero) for x in ordenar_fila(c)] == [
        ("P1", "TRES-A"),
        ("P1", "TRES-C"),
        ("P1", "TRES-B"),
        ("P2", "TRES-A"),
        ("P3", "TRES-B"),
    ]


def test_ordem_do_ordenador_e_a_ordem_da_chave() -> None:
    c = [
        ChamadoFila("TRES-9", "P2", T0 + timedelta(days=400)),
        ChamadoFila("TRES-1", "P3", T0 - timedelta(days=3)),
        ChamadoFila("TRES-5", "P1", T0),
        ChamadoFila("TRES-2", "P2", T0),
    ]
    chaves = [chave_fila(x) for x in ordenar_fila(c)]
    assert chaves == sorted(chaves)


def test_fila_vazia() -> None:
    assert ordenar_fila([]) == []


def test_horario_sem_fuso_e_rejeitado() -> None:
    with pytest.raises(ValueError):
        montar_fila_sk("P1", datetime(2025, 1, 1, 12, 0), "A")


@pytest.mark.parametrize(("prio", "numero"), [("P4", "A"), ("P1", ""), ("P1", "A#B")])
def test_entradas_invalidas_sao_rejeitadas(prio: str, numero: str) -> None:
    with pytest.raises(ValueError):
        montar_fila_sk(prio, T0, numero)  # type: ignore[arg-type]
