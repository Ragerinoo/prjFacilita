"""Teste de propriedade das fórmulas dos indicadores (tarefa 6.5).

Feature: tres-autoatendimento, Property 13: Fórmulas dos indicadores

**Validates: Requirements 17.3, 17.4, 17.5, 17.6, 17.7, 17.8**

Compara `agregar_metricas` com um cálculo de referência independente, feito com
`fractions.Fraction` (aritmética exata) a partir das listas de entrada.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction

from hypothesis import given
from hypothesis import strategies as st

from dominio.metricas import (
    SEM_DADOS,
    AgregadoDia,
    Avaliacao,
    ChamadoEncerrado,
    ConfigMetricas,
    PeriodoMetricas,
    agregar_metricas,
)
from dominio.tipos import JornadaEncerrada

INI = datetime(2025, 1, 1, tzinfo=UTC)
FIM = datetime(2025, 1, 8, tzinfo=UTC)
PERIODO = PeriodoMetricas(INI, FIM)
PRIMEIRO_DIA = date(2025, 1, 1)
ULTIMO_DIA = date(2025, 1, 7)
CAMADAS = ("guia", "ia", "humano", "abandonada")

# ------------------------------------------------------------------ referência independente


def arredondar(valor: Fraction, casas: int) -> Decimal:
    """Meio para cima (valores não negativos) com `casas` casas decimais."""
    escala = 10**casas
    inteiro = (valor * escala + Fraction(1, 2)).__floor__()
    return Decimal(inteiro) / Decimal(escala)


def pct_ref(parte: int, total: int):
    if total == 0:
        return SEM_DADOS
    return arredondar(Fraction(100 * parte, total), 1)


def media_ref(valores: list[Fraction], casas: int):
    if not valores:
        return SEM_DADOS
    return arredondar(sum(valores, Fraction(0)) / len(valores), casas)


def min_seg_ref(segundos: int) -> str:
    return f"{segundos // 60}:{segundos % 60:02d}"


def chave_alfabetica(titulo: str) -> str:
    """Ordem alfabética do português: sem acento e sem diferença de caixa."""
    return titulo.translate(
        str.maketrans("ÁÀÂÃÉÊÍÓÔÕÚÇáàâãéêíóôõúç", "AAAAEEIOOOUCaaaaeeiooouc")
    ).casefold()


def mesma_casa(valor: Decimal, casas: int) -> bool:
    return valor.as_tuple().exponent == -casas


# ------------------------------------------------------------------ estratégias

instantes = st.integers(min_value=-2 * 86400, max_value=9 * 86400).map(
    lambda s: INI + timedelta(seconds=s)
)
camadas = st.sampled_from(CAMADAS)
custos_tokens = st.integers(min_value=0, max_value=500_000).map(lambda c: Decimal(c) / 10_000)
custos_minuto = st.integers(min_value=0, max_value=99_999).map(lambda c: Decimal(c) / 100)
TITULOS = ["Vazamento", "vazamento", "Água", "Barulho", "barulho", "Cheiro", "Zumbido", "Aviso"]


@st.composite
def cenarios(draw):
    n = draw(st.integers(min_value=0, max_value=25))
    jornadas = [
        JornadaEncerrada(
            f"J{i}",
            draw(camadas),
            draw(instantes),
            draw(st.integers(min_value=0, max_value=7200)),
            draw(custos_tokens),
            None,
            None,
        )
        for i in range(n)
    ]

    chamados = []
    for i, j in enumerate(jornadas):
        if draw(st.booleans()):
            encerrado = draw(instantes)
            atraso = draw(st.one_of(st.none(), st.integers(min_value=-60, max_value=7200)))
            chamados.append(
                ChamadoEncerrado(
                    f"T{i}",
                    j.jornada_id,
                    encerrado,
                    draw(st.sampled_from(["defeito_real", "falso_defeito"])),
                    None if atraso is None else encerrado - timedelta(seconds=atraso),
                )
            )
    # Chamados de Jornadas fora da lista (só contam para a precisão da escalada).
    for k in range(draw(st.integers(min_value=0, max_value=5))):
        chamados.append(
            ChamadoEncerrado(
                f"X{k}",
                f"outra{k}",
                draw(instantes),
                draw(st.sampled_from(["defeito_real", "falso_defeito"])),
            )
        )

    avaliacoes = [
        Avaliacao(f"A{k}", draw(st.integers(1, 5)), draw(camadas), draw(instantes))
        for k in range(draw(st.integers(min_value=0, max_value=30)))
    ]

    dias = st.integers(min_value=-2, max_value=9).map(lambda d: PRIMEIRO_DIA + timedelta(days=d))
    metricas = st.sampled_from(
        ["ia_cache", "ia_modelo", "outra", "problema_sel#1", "problema_sel#2", "problema_sel#3"]
        + [f"problema_sel#{p}" for p in range(4, 16)]
    )
    agregados = [
        AgregadoDia(draw(dias), draw(metricas), draw(st.integers(0, 50)))
        for _ in range(draw(st.integers(min_value=0, max_value=60)))
    ]

    titulos = {
        p: draw(st.sampled_from(TITULOS))
        for p in range(1, 16)
        if draw(st.integers(0, 4)) > 0  # alguns ficam sem título ("Problema <id>")
    }
    cfg = ConfigMetricas(draw(custos_minuto), titulos)
    return jornadas, chamados, avaliacoes, agregados, cfg


# ------------------------------------------------------------------ propriedade


@given(cenarios())
def test_formulas_dos_indicadores(cenario) -> None:
    # Feature: tres-autoatendimento, Property 13: Fórmulas dos indicadores
    jornadas, chamados, avaliacoes, agregados, cfg = cenario
    m = agregar_metricas(jornadas, chamados, avaliacoes, agregados, PERIODO, cfg)

    na_janela = [j for j in jornadas if PERIODO.contem(j.encerrada_em)]
    total = len(na_janela)
    chamados_ok = [c for c in chamados if PERIODO.contem(c.encerrado_em)]
    chamado_de = {c.jornada_id: c for c in chamados_ok}

    # 17.3 deflexão, 17.5 tempo, 17.6 custo, 17.8 nota média/quantidade — por camada
    for camada in CAMADAS:
        ind = m.camada(camada)
        js = [j for j in na_janela if j.camada == camada]
        assert ind.jornadas == len(js)
        assert ind.deflexao_pct == pct_ref(len(js), total)
        if ind.deflexao_pct != SEM_DADOS:
            assert 0 <= ind.deflexao_pct <= 100 and mesma_casa(ind.deflexao_pct, 1)

        notas = [a.nota for a in avaliacoes if a.camada == camada and PERIODO.contem(a.em)]
        assert ind.avaliacoes == len(notas)
        assert ind.nota_media == media_ref([Fraction(n) for n in notas], 1)
        if notas:
            assert 1 <= ind.nota_media <= 5 and mesma_casa(ind.nota_media, 1)

        if camada == "abandonada":
            assert ind.tempo_medio is None and ind.custo_medio_brl is None
            continue

        # tempo médio em min:seg (média arredondada ao segundo, sem abandonadas)
        if not js:
            assert ind.tempo_medio == SEM_DADOS and ind.custo_medio_brl == SEM_DADOS
            continue
        tempos = [j.tempo_s for j in js]
        medio = arredondar(Fraction(sum(tempos), len(tempos)), 0)
        assert ind.tempo_medio == min_seg_ref(int(medio))
        assert min(tempos) <= int(medio) <= max(tempos)

        if camada == "guia":
            esperado = Decimal("0.00")
        elif camada == "ia":
            esperado = media_ref([Fraction(j.custo_brl) for j in js], 2)
        else:
            custos = []
            for j in js:
                ch = chamado_de.get(j.jornada_id)
                segundos = 0
                if ch is not None and ch.inicio_atendimento is not None:
                    segundos = max(
                        0, int((ch.encerrado_em - ch.inicio_atendimento).total_seconds())
                    )
                custos.append(Fraction(segundos, 60) * Fraction(cfg.custo_minuto_brl))
            esperado = media_ref(custos, 2)
        assert ind.custo_medio_brl == esperado
        assert mesma_casa(ind.custo_medio_brl, 2)

    # 17.4 precisão da escalada
    reais = sum(1 for c in chamados_ok if c.desfecho == "defeito_real")
    assert m.chamados_encerrados == len(chamados_ok)
    assert m.precisao_escalada_pct == pct_ref(reais, len(chamados_ok))
    if m.precisao_escalada_pct != SEM_DADOS:
        assert 0 <= m.precisao_escalada_pct <= 100 and mesma_casa(m.precisao_escalada_pct, 1)

    # 17.7 acerto do cache
    def soma(nome: str) -> int:
        return sum(
            a.valor for a in agregados if a.metrica == nome and PRIMEIRO_DIA <= a.dia <= ULTIMO_DIA
        )

    cache, modelo = soma("ia_cache"), soma("ia_modelo")
    assert m.respostas_ia == cache + modelo
    assert m.acerto_cache_pct == pct_ref(cache, cache + modelo)
    if m.acerto_cache_pct != SEM_DADOS:
        assert 0 <= m.acerto_cache_pct <= 100 and mesma_casa(m.acerto_cache_pct, 1)

    # 17.8 ranking: top 10, ordem decrescente, desempate alfabético por título
    contagem: dict[int, int] = {}
    for a in agregados:
        if a.metrica.startswith("problema_sel#") and PRIMEIRO_DIA <= a.dia <= ULTIMO_DIA:
            pid = int(a.metrica.split("#")[1])
            contagem[pid] = contagem.get(pid, 0) + a.valor
    titulo_de = {p: cfg.titulos_problemas.get(p, f"Problema {p}") for p in contagem}
    ordem = sorted(
        (p for p, n in contagem.items() if n > 0),
        key=lambda p: (-contagem[p], chave_alfabetica(titulo_de[p]), titulo_de[p], p),
    )[:10]
    assert [(i.problema_id, i.titulo, i.jornadas) for i in m.ranking] == [
        (p, titulo_de[p], contagem[p]) for p in ordem
    ]
    assert len(m.ranking) <= 10
    pares = list(zip(m.ranking, m.ranking[1:], strict=False))
    assert all(a.jornadas >= b.jornadas for a, b in pares)
    assert all(
        chave_alfabetica(a.titulo) <= chave_alfabetica(b.titulo)
        for a, b in pares
        if a.jornadas == b.jornadas
    )
