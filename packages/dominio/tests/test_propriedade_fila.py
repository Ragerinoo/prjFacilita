"""Teste de propriedade da ordenação da fila do Painel_CS (Req 14.1).

Feature: tres-autoatendimento, Property 26: Ordenação da fila

Para qualquer conjunto de Chamados abertos, `ordenar_fila` devolve os Chamados por prioridade
(P1, P2, P3), depois por horário de criação crescente e depois por número crescente; o
resultado não depende da ordem de entrada e coincide com a ordem lexicográfica da chave
`fila_sk` do índice `gsi_fila`.

**Validates: Requirements 14.1**
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from hypothesis import given
from hypothesis import strategies as st

from dominio.fila import ChamadoFila, chave_fila, montar_fila_sk, ordenar_fila

_ORDEM_PRIORIDADE = {"P1": 0, "P2": 1, "P3": 2}

_prioridades = st.sampled_from(["P1", "P2", "P3"])

# Janela curta para provocar empates de horário (mesmo segundo, microssegundos diferentes) e
# fusos variados que representam o mesmo instante.
_fusos = st.integers(min_value=-12, max_value=14).map(lambda h: timezone(timedelta(hours=h)))
_instantes = st.datetimes(
    min_value=datetime(2025, 1, 1, 0, 0, 0),
    max_value=datetime(2025, 1, 1, 0, 0, 20),
).map(lambda d: d.replace(tzinfo=UTC))
_horarios = st.builds(lambda d, f: d.astimezone(f), _instantes, _fusos)

# Números sem o separador "#", com tamanhos variados (um é prefixo de outro).
_numeros = st.text(alphabet="ABC0123", min_size=1, max_size=4).map(lambda s: f"TRES-{s}")

_chamados = st.builds(ChamadoFila, numero=_numeros, prioridade=_prioridades, criado_em=_horarios)

# Conjuntos com números únicos (um Chamado por número) e listas com repetição de chaves.
_chamados_unicos = st.lists(_chamados, max_size=30, unique_by=lambda c: c.numero)
_chamados_qualquer = st.lists(_chamados, max_size=30)


def _chave_referencia(c: ChamadoFila) -> tuple[int, datetime, str]:
    """Ordem esperada, escrita de forma independente da implementação (resolução de segundos)."""
    instante = c.criado_em.astimezone(UTC).replace(microsecond=0)
    return (_ORDEM_PRIORIDADE[c.prioridade], instante, c.numero)


@given(_chamados_qualquer)
def test_ordenar_fila_segue_prioridade_horario_numero(chamados: list[ChamadoFila]) -> None:
    resultado = ordenar_fila(chamados)

    assert len(resultado) == len(chamados)
    assert sorted(resultado, key=chave_fila) == resultado
    assert [_chave_referencia(c) for c in resultado] == sorted(
        _chave_referencia(c) for c in chamados
    )
    # Mesmo multiconjunto de Chamados: nada se perde nem se duplica.
    assert sorted(resultado, key=lambda c: (c.numero, c.prioridade, c.criado_em)) == sorted(
        chamados, key=lambda c: (c.numero, c.prioridade, c.criado_em)
    )


@given(_chamados_unicos, st.randoms(use_true_random=False))
def test_ordenar_fila_nao_depende_da_ordem_de_entrada(
    chamados: list[ChamadoFila], rnd
) -> None:
    embaralhado = list(chamados)
    rnd.shuffle(embaralhado)

    assert ordenar_fila(embaralhado) == ordenar_fila(chamados)
    # Idempotente.
    assert ordenar_fila(ordenar_fila(chamados)) == ordenar_fila(chamados)


@given(_chamados_unicos)
def test_ordenar_fila_coincide_com_a_ordem_da_chave_fila_sk(
    chamados: list[ChamadoFila],
) -> None:
    resultado = ordenar_fila(chamados)
    chaves = [montar_fila_sk(c.prioridade, c.criado_em, c.numero) for c in resultado]

    assert chaves == [chave_fila(c) for c in resultado]
    assert chaves == sorted(chaves)
    # A ordem do índice (ordenar as chaves como texto) recompõe a mesma fila.
    por_chave = {montar_fila_sk(c.prioridade, c.criado_em, c.numero): c for c in chamados}
    assert [por_chave[k] for k in sorted(por_chave)] == resultado
