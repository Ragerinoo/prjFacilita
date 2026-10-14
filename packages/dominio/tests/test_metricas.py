"""Testes unitários de `agregar_metricas` (Req 17.3 a 17.11, 18.4)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from dominio.encerramento import EstadoDaJornada
from dominio.metricas import (
    SEM_DADOS,
    AgregadoDia,
    Avaliacao,
    ChamadoEncerrado,
    ConfigMetricas,
    ErroMetricas,
    PeriodoMetricas,
    agregar_metricas,
    formatar_min_seg,
)
from dominio.tipos import JornadaEncerrada

INI = datetime(2025, 1, 1, tzinfo=UTC)
FIM = datetime(2025, 1, 8, tzinfo=UTC)
PERIODO = PeriodoMetricas(INI, FIM)
CFG = ConfigMetricas(Decimal("2.00"), {1: "Vazamento", 2: "Água", 3: "Barulho"})
DENTRO = INI + timedelta(days=1)


def enc(jid, camada, tempo_s=60, custo="0", em=DENTRO) -> JornadaEncerrada:
    return JornadaEncerrada(jid, camada, em, tempo_s, Decimal(custo), None, None)


def agregar(jornadas=(), chamados=(), avaliacoes=(), agregados=(), periodo=PERIODO, cfg=CFG):
    return agregar_metricas(jornadas, chamados, avaliacoes, agregados, periodo, cfg)


def test_sem_dados_quando_denominadores_zero() -> None:
    m = agregar()
    assert m.total_encerradas == 0
    assert m.precisao_escalada_pct == SEM_DADOS
    assert m.acerto_cache_pct == SEM_DADOS
    assert m.ranking == ()
    for c in m.camadas:
        assert c.deflexao_pct == SEM_DADOS and c.nota_media == SEM_DADOS and c.avaliacoes == 0
    assert m.camada("guia").tempo_medio == SEM_DADOS
    assert m.camada("ia").custo_medio_brl == SEM_DADOS
    assert m.camada("abandonada").tempo_medio is None


def test_deflexao_soma_e_ignora_nao_encerradas_e_fora_do_periodo() -> None:
    aberta = EstadoDaJornada("A", INI, INI)
    fora = enc("F", "guia", em=FIM)  # fim é exclusivo
    js = [enc("1", "guia"), enc("2", "guia"), enc("3", "ia"), enc("4", "abandonada"), aberta, fora]
    m = agregar(js)
    assert m.total_encerradas == 4
    assert [c.jornadas for c in m.camadas] == [2, 1, 0, 1]
    assert sum(c.jornadas for c in m.camadas) == m.total_encerradas
    assert m.camada("guia").deflexao_pct == Decimal("50.0")
    assert m.camada("ia").deflexao_pct == Decimal("25.0")
    assert m.camada("humano").deflexao_pct == Decimal("0.0")


def test_aceita_jornada_estado_encerrada() -> None:
    j = EstadoDaJornada("E", INI, INI, estado="encerrada", encerramento=enc("E", "ia"))
    assert agregar([j]).camada("ia").jornadas == 1


def test_percentual_arredonda_para_1_casa() -> None:
    js = [enc("1", "guia"), enc("2", "ia"), enc("3", "ia")]
    assert agregar(js).camada("guia").deflexao_pct == Decimal("33.3")
    assert agregar(js).camada("ia").deflexao_pct == Decimal("66.7")


def test_precisao_da_escalada() -> None:
    cs = [
        ChamadoEncerrado("T1", "J1", DENTRO, "defeito_real"),
        ChamadoEncerrado("T2", "J2", DENTRO, "falso_defeito"),
        ChamadoEncerrado("T3", "J3", DENTRO, "defeito_real"),
        ChamadoEncerrado("T4", "J4", FIM, "defeito_real"),  # fora do período
    ]
    m = agregar(chamados=cs)
    assert m.chamados_encerrados == 3
    assert m.precisao_escalada_pct == Decimal("66.7")


def test_tempo_medio_min_seg_sem_abandonadas() -> None:
    js = [
        enc("1", "guia", 100),
        enc("2", "guia", 201),  # média 150,5 -> 151 s
        enc("3", "ia", 4503),  # 75:03
        enc("4", "abandonada", 99999),
    ]
    m = agregar(js)
    assert m.camada("guia").tempo_medio == "2:31"
    assert m.camada("ia").tempo_medio == "75:03"
    assert m.camada("humano").tempo_medio == SEM_DADOS
    assert m.camada("abandonada").tempo_medio is None


def test_formatar_min_seg() -> None:
    assert [formatar_min_seg(s) for s in (0, 59, 60, 312)] == ["0:00", "0:59", "1:00", "5:12"]


def test_custo_medio_por_camada() -> None:
    inicio = DENTRO
    js = [
        enc("G", "guia", custo="5"),  # guia sempre 0
        enc("I1", "ia", custo="0.10"),
        enc("I2", "ia", custo="0.25"),
        enc("H1", "humano"),
        enc("H2", "humano"),
    ]
    cs = [
        ChamadoEncerrado("T1", "H1", inicio + timedelta(minutes=10), "defeito_real", inicio),
        # 90 s = 1,5 min
        ChamadoEncerrado("T2", "H2", inicio + timedelta(seconds=90), "falso_defeito", inicio),
    ]
    m = agregar(js, cs)
    assert m.camada("guia").custo_medio_brl == Decimal("0.00")
    assert m.camada("ia").custo_medio_brl == Decimal("0.18")  # 0,175 meio para cima
    # (10 × 2,00 + 1,5 × 2,00) / 2 = 11,50
    assert m.camada("humano").custo_medio_brl == Decimal("11.50")
    assert m.camada("abandonada").custo_medio_brl is None


def test_custo_humano_sem_chamado_ou_inicio_conta_zero_minutos() -> None:
    js = [enc("H1", "humano"), enc("H2", "humano")]
    cs = [ChamadoEncerrado("T2", "H2", DENTRO, "falso_defeito", None)]
    assert agregar(js, cs).camada("humano").custo_medio_brl == Decimal("0.00")


def test_taxa_de_acerto_do_cache_respeita_dias_do_periodo() -> None:
    ag = [
        AgregadoDia(date(2025, 1, 1), "ia_cache", 3),
        AgregadoDia(date(2025, 1, 7), "ia_modelo", 9),  # último dia do período
        AgregadoDia(date(2025, 1, 8), "ia_cache", 100),  # fora
        AgregadoDia(date(2024, 12, 31), "ia_modelo", 100),  # fora
    ]
    m = agregar(agregados=ag)
    assert m.respostas_ia == 12
    assert m.acerto_cache_pct == Decimal("25.0")


def test_ranking_top_10_com_desempate_alfabetico() -> None:
    titulos = {i: f"P{i:02d}" for i in range(1, 14)}
    titulos.update({2: "Água", 3: "Barulho", 1: "Zumbido"})
    cfg = ConfigMetricas(Decimal("0"), titulos)
    ag = [AgregadoDia(date(2025, 1, 2), f"problema_sel#{i}", 5) for i in range(1, 14)]
    ag += [AgregadoDia(date(2025, 1, 3), "problema_sel#13", 1)]
    ag += [AgregadoDia(date(2025, 1, 3), "problema_sel#x", 50)]  # ignorado
    r = agregar(agregados=ag, cfg=cfg).ranking
    assert len(r) == 10
    assert r[0].problema_id == 13 and r[0].jornadas == 6
    assert [i.titulo for i in r[1:4]] == ["Água", "Barulho", "P04"]
    assert all(r[k].jornadas >= r[k + 1].jornadas for k in range(9))


def test_ranking_soma_dias_e_usa_titulo_padrao() -> None:
    ag = [
        AgregadoDia(date(2025, 1, 2), "problema_sel#9", 2),
        AgregadoDia(date(2025, 1, 4), "problema_sel#9", 3),
    ]
    (item,) = agregar(agregados=ag).ranking
    assert (item.problema_id, item.titulo, item.jornadas) == (9, "Problema 9", 5)


def test_nota_media_e_quantidade_por_camada() -> None:
    av = [
        Avaliacao("1", 5, "guia", DENTRO),
        Avaliacao("2", 4, "guia", DENTRO),
        Avaliacao("3", 4, "guia", DENTRO),
        Avaliacao("4", 1, "ia", DENTRO),
        Avaliacao("5", 5, "ia", FIM),  # fora do período
    ]
    m = agregar(avaliacoes=av)
    assert (m.camada("guia").nota_media, m.camada("guia").avaliacoes) == (Decimal("4.3"), 3)
    assert (m.camada("ia").nota_media, m.camada("ia").avaliacoes) == (Decimal("1.0"), 1)
    assert m.camada("humano").nota_media == SEM_DADOS


def test_nota_invalida_e_erro() -> None:
    with pytest.raises(ErroMetricas):
        agregar(avaliacoes=[Avaliacao("1", 6, "guia", DENTRO)])


def test_periodo_maximo_90_dias() -> None:
    PeriodoMetricas(INI, INI + timedelta(days=90))
    with pytest.raises(ErroMetricas):
        PeriodoMetricas(INI, INI + timedelta(days=90, seconds=1))
    with pytest.raises(ErroMetricas):
        PeriodoMetricas(FIM, INI)
    with pytest.raises(ErroMetricas):
        PeriodoMetricas(datetime(2025, 1, 1), FIM)


@pytest.mark.parametrize("valor", ["-0.01", "1000.00"])
def test_custo_por_minuto_fora_da_faixa(valor) -> None:
    with pytest.raises(ErroMetricas):
        ConfigMetricas(Decimal(valor))


def test_custo_por_minuto_nos_limites() -> None:
    ConfigMetricas(Decimal("0.00"))
    ConfigMetricas(Decimal("999.99"))


def test_resultado_so_tem_agregados() -> None:
    m = agregar([enc("1", "guia")])
    campos = {f for c in m.camadas for f in c.__slots__}
    assert "jornada_id" not in campos
