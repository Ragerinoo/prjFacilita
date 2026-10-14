"""Testes unitários das regras de encerramento e abandono (Req 17.1, 17.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from dominio.encerramento import (
    ErroEncerramento,
    EstadoDaJornada,
    aplicar_encerramento,
    marcar_abandono,
    registrar_interacao,
)

T0 = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)


def jornada(**kw) -> EstadoDaJornada:
    base = {
        "jornada_id": "J1",
        "criada_em": T0,
        "ultima_interacao": T0 + timedelta(minutes=5),
    }
    return EstadoDaJornada(**{**base, **kw})


@pytest.mark.parametrize("camada", ["guia", "ia", "humano"])
def test_encerramento_registra_camada_tempo_e_custo(camada) -> None:
    em = T0 + timedelta(seconds=312)
    r = aplicar_encerramento(jornada(), camada, em, Decimal("0.125"), 7, "falso_defeito")
    assert r.aplicado
    assert r.jornada.estado == "encerrada"
    e = r.jornada.encerramento
    assert (e.camada, e.encerrada_em, e.tempo_s) == (camada, em, 312)
    assert e.custo_brl == Decimal("0.13")
    assert (e.problema_id, e.desfecho) == (7, "falso_defeito")
    assert r.jornada.encerrada_pk == "ENC" and r.jornada.ativa_pk is None
    assert r.jornada.encerrada_em == em


def test_segundo_encerramento_nao_altera_a_camada() -> None:
    primeiro = aplicar_encerramento(jornada(), "guia", T0 + timedelta(minutes=2)).jornada
    r = aplicar_encerramento(primeiro, "humano", T0 + timedelta(minutes=9))
    assert not r.aplicado
    assert r.jornada is primeiro
    assert r.jornada.encerramento.camada == "guia"


def test_abandonada_nao_aceita_encerramento_posterior() -> None:
    ab = marcar_abandono(jornada(), T0 + timedelta(minutes=40)).jornada
    r = aplicar_encerramento(ab, "ia", T0 + timedelta(minutes=50))
    assert not r.aplicado and r.jornada.encerramento.camada == "abandonada"


def test_camada_abandonada_so_via_marcar_abandono() -> None:
    with pytest.raises(ErroEncerramento):
        aplicar_encerramento(jornada(), "abandonada", T0)


def test_custo_negativo_e_rejeitado() -> None:
    with pytest.raises(ErroEncerramento):
        aplicar_encerramento(jornada(), "ia", T0, Decimal("-0.01"))


def test_abandono_exatamente_aos_30_minutos() -> None:
    j = jornada()
    antes = marcar_abandono(j, j.ultima_interacao + timedelta(minutes=30) - timedelta(seconds=1))
    assert not antes.aplicado and antes.jornada is j
    r = marcar_abandono(j, j.ultima_interacao + timedelta(minutes=30))
    assert r.aplicado
    e = r.jornada.encerramento
    assert e.camada == "abandonada"
    assert e.tempo_s == 300  # até a última interação, não até o abandono
    assert e.custo_brl == Decimal("0.00")
    assert r.jornada.encerrada_pk == "ENC"


def test_abandono_nao_se_aplica_com_chamado() -> None:
    for j in (jornada(chamado_numero="TRES-1"), jornada(estado="escalada")):
        r = marcar_abandono(j, T0 + timedelta(hours=5))
        assert not r.aplicado and r.jornada is j


def test_abandono_e_terminal_diante_de_interacoes_posteriores() -> None:
    ab = marcar_abandono(jornada(), T0 + timedelta(minutes=40)).jornada
    depois = registrar_interacao(ab, T0 + timedelta(minutes=60))
    assert depois is ab
    assert marcar_abandono(depois, T0 + timedelta(hours=3)).jornada is ab
    assert depois.encerramento.camada == "abandonada"


def test_indice_de_ativas_so_existe_ativa_e_sem_chamado() -> None:
    assert jornada().ativa_pk == "ATIVA"
    assert jornada(chamado_numero="TRES-1").ativa_pk is None
    assert jornada(estado="escalada").ativa_pk is None
    assert jornada().encerrada_pk is None


def test_interacao_em_jornada_aberta_avanca_mas_nao_retrocede() -> None:
    j = jornada()
    assert registrar_interacao(j, T0 + timedelta(minutes=9)).ultima_interacao == T0 + timedelta(
        minutes=9
    )
    assert registrar_interacao(j, T0) is j
