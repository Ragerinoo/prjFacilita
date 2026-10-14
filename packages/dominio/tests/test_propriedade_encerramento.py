"""Teste de propriedade da camada única de resolução da Jornada (Req 17.1, 17.2).

Feature: tres-autoatendimento, Property 11: Cada Jornada tem no máximo uma camada de
resolução, e ela é permanente

Para qualquer sequência de eventos de uma Jornada (resolução no guia, resolução na IA,
encerramento do Chamado, varredura de abandono, interações posteriores, escalada), existe no
máximo um registro de encerramento e, depois de definido, a camada e o horário de encerramento
nunca mudam. Uma Jornada abandonada permanece "abandonada" mesmo com interações posteriores.

**Validates: Requirements 17.1, 17.2**
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from dominio.encerramento import (
    EstadoDaJornada,
    aplicar_encerramento,
    marcar_abandono,
    registrar_interacao,
)

_INICIO = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

# Deslocamentos em segundos a partir do início; cobrem antes e depois do limite de 30 min e
# instantes fora de ordem (as operações não precisam ser monotônicas).
_instantes = st.integers(min_value=0, max_value=4 * 3600).map(
    lambda s: _INICIO + timedelta(seconds=s)
)
_custos = st.decimals(min_value=0, max_value=100, places=4, allow_nan=False, allow_infinity=False)

_op_encerrar = st.builds(
    lambda camada, em, custo: ("encerrar", camada, em, custo),
    st.sampled_from(["guia", "ia", "humano"]),
    _instantes,
    _custos,
)
_op_abandono = st.builds(lambda em, custo: ("abandono", em, custo), _instantes, _custos)
_op_interacao = st.builds(lambda em: ("interacao", em), _instantes)
_op_escalar = st.just(("escalar",))

_operacoes = st.lists(
    st.one_of(_op_encerrar, _op_abandono, _op_interacao, _op_escalar),
    min_size=1,
    max_size=15,
)


def _aplicar(j: EstadoDaJornada, op: tuple) -> EstadoDaJornada:
    match op[0]:
        case "encerrar":
            _, camada, em, custo = op
            return aplicar_encerramento(j, camada, em, Decimal(custo)).jornada
        case "abandono":
            _, em, custo = op
            return marcar_abandono(j, em, Decimal(custo)).jornada
        case "interacao":
            return registrar_interacao(j, op[1])
        case _:  # escalar: só uma Jornada aberta pode ser escalada
            if j.encerrada:
                return j
            return replace(j, estado="escalada", chamado_numero="TRES-0001")


@given(
    ultima_interacao_s=st.integers(min_value=0, max_value=3600),
    operacoes=_operacoes,
)
def test_jornada_tem_no_maximo_uma_camada_e_ela_e_permanente(
    ultima_interacao_s: int, operacoes: list[tuple]
) -> None:
    # Feature: tres-autoatendimento, Property 11: Cada Jornada tem no máximo uma camada de
    # resolução, e ela é permanente
    jornada = EstadoDaJornada(
        jornada_id="j-1",
        criada_em=_INICIO,
        ultima_interacao=_INICIO + timedelta(seconds=ultima_interacao_s),
    )
    definido = None  # registro de encerramento fixado na primeira vez que aparece

    for op in operacoes:
        antes = jornada
        jornada = _aplicar(jornada, op)

        if definido is None:
            if jornada.encerramento is not None:
                # Primeiro (e único) registro: exige estado encerrado e uma camada válida.
                assert jornada.encerrada
                assert jornada.encerramento.camada in {"guia", "ia", "humano", "abandonada"}
                definido = jornada.encerramento
            else:
                assert not jornada.encerrada
            continue

        # Depois de definido: camada, horário e todo o registro nunca mudam.
        assert antes.encerrada
        assert jornada.encerrada
        assert jornada.encerramento == definido
        assert jornada.encerramento.camada == definido.camada
        assert jornada.encerramento.encerrada_em == definido.encerrada_em
        assert jornada.encerrada_em == definido.encerrada_em
        # A Jornada inteira permanece igual: interações e novas tentativas não a alteram.
        if op[0] != "escalar":
            assert jornada == antes
