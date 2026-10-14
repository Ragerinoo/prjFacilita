"""Teste de propriedade do invariante de métricas por camada (Req 17.9, 17.11).

Feature: tres-autoatendimento, Property 12: A soma das camadas é igual ao total de Jornadas
encerradas no período

Para qualquer conjunto de Jornadas (encerradas e não encerradas) e qualquer período, a soma das
contagens por camada (guia, ia, humano, abandonada) é igual ao total de Jornadas encerradas no
período; Jornadas não encerradas ou encerradas fora do período nunca são contadas; e com
denominador zero as taxas são "sem dados".

**Validates: Requirements 17.9, 17.11**
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from dominio.encerramento import EstadoDaJornada
from dominio.metricas import (
    CAMADAS,
    SEM_DADOS,
    ConfigMetricas,
    PeriodoMetricas,
    agregar_metricas,
)
from dominio.tipos import JornadaEncerrada

_BASE = datetime(2025, 3, 1, 0, 0, 0, tzinfo=UTC)
_CFG = ConfigMetricas(custo_minuto_brl=Decimal("1.50"))
_CAMADAS_RESOLVIDAS = ("guia", "ia", "humano")

_DIA_S = 86_400
_MAX_PERIODO_S = 90 * _DIA_S


@st.composite
def _periodos(draw: st.DrawFn) -> PeriodoMetricas:
    inicio = _BASE + timedelta(seconds=draw(st.integers(0, 10 * _DIA_S)))
    duracao = draw(
        st.one_of(
            st.just(0),  # período vazio: nenhuma Jornada pode entrar
            st.integers(0, _MAX_PERIODO_S),
        )
    )
    return PeriodoMetricas(inicio=inicio, fim=inicio + timedelta(seconds=duracao))


def _instantes(periodo: PeriodoMetricas) -> st.SearchStrategy[datetime]:
    """Instantes dentro, fora e exatamente nas bordas ``[inicio, fim)`` do período."""
    bordas = st.sampled_from(
        [
            periodo.inicio - timedelta(microseconds=1),
            periodo.inicio,
            periodo.inicio + timedelta(microseconds=1),
            periodo.fim - timedelta(microseconds=1),
            periodo.fim,
            periodo.fim + timedelta(microseconds=1),
        ]
    )
    aleatorios = st.integers(-30 * _DIA_S, 120 * _DIA_S).map(
        lambda s: periodo.inicio + timedelta(seconds=s)
    )
    return st.one_of(bordas, aleatorios)


@st.composite
def _jornadas(
    draw: st.DrawFn, periodo: PeriodoMetricas
) -> list[EstadoDaJornada | JornadaEncerrada]:
    quantidade = draw(st.integers(0, 25))
    itens: list[EstadoDaJornada | JornadaEncerrada] = []
    for i in range(quantidade):
        jornada_id = f"j-{i}"
        tipo = draw(st.sampled_from(["aberta", "estado_encerrada", "registro_encerrado"]))
        if tipo == "aberta":
            # Jornada não encerrada (ativa ou escalada): nunca é contada.
            estado = draw(st.sampled_from(["ativa", "escalada"]))
            itens.append(
                EstadoDaJornada(
                    jornada_id=jornada_id,
                    criada_em=periodo.inicio,
                    ultima_interacao=periodo.inicio,
                    estado=estado,
                    chamado_numero="TRES-0001" if estado == "escalada" else None,
                )
            )
            continue
        registro = JornadaEncerrada(
            jornada_id=jornada_id,
            camada=draw(st.sampled_from(CAMADAS)),
            encerrada_em=draw(_instantes(periodo)),
            tempo_s=draw(st.integers(0, 7200)),
            custo_brl=draw(
                st.decimals(
                    min_value=0, max_value=50, places=4, allow_nan=False, allow_infinity=False
                )
            ),
            problema_id=None,
            desfecho=None,
        )
        if tipo == "registro_encerrado":
            itens.append(registro)
        else:
            itens.append(
                EstadoDaJornada(
                    jornada_id=jornada_id,
                    criada_em=periodo.inicio,
                    ultima_interacao=periodo.inicio,
                    estado="encerrada",
                    encerramento=registro,
                )
            )
    return itens


@st.composite
def _cenarios(draw: st.DrawFn) -> tuple[PeriodoMetricas, list[EstadoDaJornada | JornadaEncerrada]]:
    periodo = draw(_periodos())
    return periodo, draw(_jornadas(periodo))


def _registro(j: EstadoDaJornada | JornadaEncerrada) -> JornadaEncerrada | None:
    return j.encerramento if isinstance(j, EstadoDaJornada) else j


@given(cenario=_cenarios())
def test_soma_das_camadas_e_igual_ao_total_de_encerradas_no_periodo(
    cenario: tuple[PeriodoMetricas, list[EstadoDaJornada | JornadaEncerrada]],
) -> None:
    # Feature: tres-autoatendimento, Property 12: A soma das camadas é igual ao total de
    # Jornadas encerradas no período
    periodo, jornadas = cenario

    # Oráculo independente: só entram Jornadas com encerramento em [inicio, fim).
    contadas = [
        r
        for j in jornadas
        if (r := _registro(j)) is not None and periodo.inicio <= r.encerrada_em < periodo.fim
    ]
    esperado_por_camada = {c: sum(1 for r in contadas if r.camada == c) for c in CAMADAS}

    m = agregar_metricas(jornadas, [], [], [], periodo, _CFG)

    # Invariante central: soma das camadas == total == Jornadas encerradas no período.
    assert m.total_encerradas == len(contadas)
    assert sum(c.jornadas for c in m.camadas) == m.total_encerradas
    assert [c.camada for c in m.camadas] == list(CAMADAS)
    # Abertas e fora do período nunca são contadas, em nenhuma camada.
    for camada in CAMADAS:
        assert m.camada(camada).jornadas == esperado_por_camada[camada]

    if m.total_encerradas == 0:
        # Denominador zero: toda taxa/média é "sem dados", nunca 0 nem erro (Req 17.11).
        for c in m.camadas:
            assert c.jornadas == 0
            assert c.deflexao_pct == SEM_DADOS
            if c.camada in _CAMADAS_RESOLVIDAS:
                assert c.tempo_medio == SEM_DADOS
                assert c.custo_medio_brl == SEM_DADOS
            assert c.nota_media == SEM_DADOS
    else:
        # Com total > 0 a deflexão é numérica e fica entre 0 e 100.
        for c in m.camadas:
            assert c.deflexao_pct != SEM_DADOS
            assert Decimal(0) <= c.deflexao_pct <= Decimal(100)
            if c.camada in _CAMADAS_RESOLVIDAS and c.jornadas == 0:
                assert c.tempo_medio == SEM_DADOS
                assert c.custo_medio_brl == SEM_DADOS

    # Sem Chamados, avaliações nem contadores diários, os demais denominadores são zero.
    assert m.chamados_encerrados == 0
    assert m.precisao_escalada_pct == SEM_DADOS
    assert m.respostas_ia == 0
    assert m.acerto_cache_pct == SEM_DADOS
    assert m.ranking == ()
