"""Testes de `servicos.metricas_chamados.calcular_metricas` (função pura, sem I/O).

Os helpers (`cenarios`, `calcular`, `soma`) são reutilizáveis pelos demais testes de métricas.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from datetime import timedelta

from hypothesis import given
from hypothesis import strategies as st
from servicos.metricas_chamados import (
    DESFECHOS,
    PRIORIDADES,
    ROTULO_NAO_INFORMADO,
    calcular_metricas,
)

from repositorios.modelos import Chamado, EncerramentoChamado, Jornada
from tests.test_repositorios_memoria import T0, chamado, jornada, numero

CHAVES_PRIMEIRO_NIVEL = {"totais", "por_problema", "por_modelo", "por_prioridade", "por_desfecho"}
STATUS = ("aberto", "em_atendimento", "encerrado")


@dataclass(frozen=True)
class Cenario:
    """Chamados + Jornadas + catálogo gerados para um teste."""

    chamados: list[Chamado]
    jornadas: dict[str, Jornada]
    titulos: dict[int, str]

    def obter_jornada(self, jornada_id: str) -> Jornada | None:
        return self.jornadas.get(jornada_id)


def calcular(cenario: Cenario) -> dict:
    return calcular_metricas(cenario.chamados, cenario.obter_jornada, cenario.titulos)


def soma(linhas: list[dict]) -> int:
    return sum(linha["quantidade"] for linha in linhas)


@st.composite
def cenarios(draw, max_chamados: int = 15) -> Cenario:
    """Chamados em qualquer status/prioridade/desfecho; Jornadas parciais, ausentes ou sem dados."""
    indices = draw(st.lists(st.integers(0, 1023), unique=True, max_size=max_chamados))
    chamados: list[Chamado] = []
    jornadas: dict[str, Jornada] = {}
    for i in indices:
        jid = f"J{i}"
        status = draw(st.sampled_from(STATUS))
        prio = draw(st.sampled_from(PRIORIDADES))
        c = chamado(numero(i), jid, prio, T0 + timedelta(minutes=i))
        if status == "encerrado":
            # Sem registro de encerramento também vale (desfecho `nao_informado`).
            desfecho = draw(st.sampled_from((*DESFECHOS, None)))
            enc = (
                None
                if desfecho is None
                else EncerramentoChamado(desfecho, "outra", "ok", T0, "bruno")  # type: ignore[arg-type]
            )
            c = replace(c, status="encerrado", encerramento=enc)
        else:
            c = replace(c, status=status)  # type: ignore[arg-type]
        chamados.append(c)
        if draw(st.booleans()):  # Jornada inexistente quando falso
            jornadas[jid] = replace(
                jornada(jid),
                problema_id=draw(st.none() | st.integers(1, 5)),
                modelo_id=draw(st.none() | st.sampled_from(("m1", "m2", "m3"))),
            )
    titulos = draw(st.dictionaries(st.integers(1, 5), st.text(min_size=1, max_size=12), max_size=5))
    return Cenario(chamados, jornadas, titulos)


@given(cen=cenarios())
def test_propriedade_invariantes_das_contagens_de_metricas(cen: Cenario) -> None:
    """Feature: persistencia-local-demo, Property 11: Invariantes das contagens de métricas

    **Validates: Requirements 9.1, 9.2, 9.5, 9.6, 9.9, 9.10**
    """
    m = calcular(cen)
    total = len(cen.chamados)
    encerrados = sum(1 for c in cen.chamados if c.status == "encerrado")

    # Chaves de primeiro nível fechadas.
    assert set(m) == CHAVES_PRIMEIRO_NIVEL

    # abertos + encerrados == nº de Chamados (9.1, 9.2).
    assert m["totais"] == {"abertos": total - encerrados, "encerrados": encerrados}

    # Cada dimensão de status/problema/modelo/prioridade soma o total (9.9).
    assert soma(m["por_problema"]) == total
    assert soma(m["por_modelo"]) == total
    assert soma(m["por_prioridade"]) == total

    # por_prioridade: exatamente P1/P2/P3, inclusive com zero (9.5).
    assert [linha["chave"] for linha in m["por_prioridade"]] == list(PRIORIDADES)

    # por_desfecho: sempre falso_defeito/defeito_real; soma de todas as linhas == encerrados (9.6).
    chaves_desfecho = [linha["chave"] for linha in m["por_desfecho"]]
    assert chaves_desfecho[: len(DESFECHOS)] == list(DESFECHOS)
    assert set(chaves_desfecho) <= {*DESFECHOS, ROTULO_NAO_INFORMADO}
    assert soma(m["por_desfecho"]) == encerrados

    # Sem nenhum Chamado, tudo é zero (9.10).
    if total == 0:
        assert m["totais"] == {"abertos": 0, "encerrados": 0}
        assert m["por_problema"] == [] and m["por_modelo"] == []
        assert all(linha["quantidade"] == 0 for linha in m["por_prioridade"])
        assert all(linha["quantidade"] == 0 for linha in m["por_desfecho"])


def test_lista_vazia_devolve_totais_zero_e_linhas_fixas() -> None:
    m = calcular(Cenario([], {}, {}))
    assert m["totais"] == {"abertos": 0, "encerrados": 0}
    assert [(x["chave"], x["quantidade"]) for x in m["por_prioridade"]] == [
        ("P1", 0),
        ("P2", 0),
        ("P3", 0),
    ]
    assert [(x["chave"], x["quantidade"]) for x in m["por_desfecho"]] == [
        ("falso_defeito", 0),
        ("defeito_real", 0),
    ]


def _referencia(cen: Cenario) -> tuple[list[tuple[str, str, int]], list[tuple[str, str, int]]]:
    """Modelo de referência (Counter) de por_problema e por_modelo: (chave, rótulo, quantidade)."""
    por_problema: Counter[str] = Counter()
    por_modelo: Counter[str] = Counter()
    for c in cen.chamados:
        j = cen.jornadas.get(c.jornada_id)
        pid = j.problema_id if j is not None else None
        mid = j.modelo_id if j is not None else None
        por_problema["nao_informado" if pid is None else str(pid)] += 1
        por_modelo["nao_informado" if mid is None else mid] += 1

    def rotulo_problema(chave: str) -> str:
        if chave == "nao_informado":
            return chave
        return cen.titulos.get(int(chave)) or f"Problema {chave}"

    problemas = [(k, rotulo_problema(k), q) for k, q in por_problema.items() if q > 0]
    modelos = [(k, k, q) for k, q in por_modelo.items() if q > 0]
    ordem = lambda t: (-t[2], t[1])  # noqa: E731 - quantidade desc, rótulo asc
    return sorted(problemas, key=ordem), sorted(modelos, key=ordem)


@given(cen=cenarios())
def test_propriedade_agrupamento_correto_por_jornada(cen: Cenario) -> None:
    """Feature: persistencia-local-demo, Property 12: Agrupamento correto por Jornada

    **Validates: Requirements 9.3, 9.4, 9.7**
    """
    m = calcular(cen)
    esperado_problema, esperado_modelo = _referencia(cen)

    obtido_problema = [(x["chave"], x["rotulo"], x["quantidade"]) for x in m["por_problema"]]
    obtido_modelo = [(x["chave"], x["rotulo"], x["quantidade"]) for x in m["por_modelo"]]

    # Mesmas linhas, mesmos rótulos e mesma ordem do modelo de referência (9.3, 9.4, 9.7).
    assert obtido_problema == esperado_problema
    assert obtido_modelo == esperado_modelo

    # Só linhas com quantidade > 0, e a ordem é (quantidade desc, rótulo asc).
    for linhas in (m["por_problema"], m["por_modelo"]):
        assert all(x["quantidade"] > 0 for x in linhas)
        chaves_ordem = [(-x["quantidade"], x["rotulo"]) for x in linhas]
        assert chaves_ordem == sorted(chaves_ordem)


def test_agrupamento_sem_problema_sem_modelo_e_jornada_inexistente() -> None:
    jornadas = {
        "J1": replace(jornada("J1"), problema_id=2, modelo_id="m1"),
        "J2": replace(jornada("J2"), problema_id=None, modelo_id=None),
        # J3 inexistente; J4 com problema fora do catálogo
        "J4": replace(jornada("J4"), problema_id=9, modelo_id="m1"),
    }
    chamados = [
        chamado(numero(i), jid, "P1", T0 + timedelta(minutes=i))
        for i, jid in enumerate(("J1", "J2", "J3", "J4"), start=1)
    ]
    m = calcular(Cenario(chamados, jornadas, {2: "Não liga"}))
    assert [(x["chave"], x["rotulo"], x["quantidade"]) for x in m["por_problema"]] == [
        ("nao_informado", "nao_informado", 2),
        ("2", "Não liga", 1),
        ("9", "Problema 9", 1),
    ]
    assert [(x["chave"], x["quantidade"]) for x in m["por_modelo"]] == [
        ("m1", 2),
        ("nao_informado", 2),
    ]
