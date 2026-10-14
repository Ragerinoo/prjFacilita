"""Teste de propriedade do determinismo do Guia_Diagnostico (Req 3.6).

Feature: tres-autoatendimento, Property 19: O guia é determinístico

Para qualquer catálogo, modelo, Problema_Catalogado e variante, duas chamadas a
`resolver_instrucao` devolvem a mesma sequência de passos, e o resultado não depende de
horário, nem da ordem de chamadas anteriores, nem de nenhum componente de IA.

**Validates: Requirements 3.6**
"""

from __future__ import annotations

import copy
import time

from hypothesis import given
from hypothesis import strategies as st

from dominio.guia import VARIANTES, instrucao_de_dict, resolver_instrucao

_modelos = st.sampled_from(["tres-passione", "tres-modo", "tres-s23"])
_problemas = st.one_of(st.integers(min_value=1, max_value=6), st.sampled_from(["1", "2", "x"]))
_variantes = st.sampled_from([*VARIANTES, "invalida"])
_texto = st.text(min_size=1, max_size=40)


@st.composite
def _passos(draw):
    ordem = draw(st.permutations(range(1, draw(st.integers(1, 5)) + 1)))
    return [
        {
            "n": n,
            "texto": draw(_texto),
            "alt": draw(_texto),
            "texto_equivalente": draw(_texto),
            "midia_url": draw(st.one_of(st.none(), _texto)),
            "midia_tipo": draw(st.one_of(st.none(), st.just("imagem"))),
        }
        for n in ordem  # ordem embaralhada: a resolução deve ordenar por `n`
    ]


@st.composite
def _instrucoes(draw):
    return {
        "modelo_id": draw(_modelos),
        "problema_id": draw(_problemas),
        "variante": draw(st.sampled_from(VARIANTES)),
        "passos": draw(_passos()),
    }


_catalogos = st.lists(_instrucoes(), max_size=8).map(
    lambda itens: {"modelo_id": "tres-passione", "instrucoes": itens}
)
_consulta = st.tuples(_modelos, _problemas, _variantes)


@given(_catalogos, _consulta, st.lists(_consulta, max_size=10))
def test_guia_e_deterministico(catalogo, consulta, consultas_anteriores):
    original = copy.deepcopy(catalogo)

    primeira = resolver_instrucao(catalogo, *consulta)

    # Chamadas anteriores/intercaladas com outras chaves não influenciam o resultado.
    for outra in consultas_anteriores:
        resolver_instrucao(catalogo, *outra)
    segunda = resolver_instrucao(catalogo, *consulta)

    assert primeira == segunda
    # Catálogo não é alterado pela resolução.
    assert catalogo == original
    # Uma cópia independente do catálogo gera a mesma sequência de passos.
    assert resolver_instrucao(copy.deepcopy(catalogo), *consulta) == primeira

    if primeira is not None:
        numeros = [p.n for p in primeira.passos]
        assert numeros == sorted(numeros)


@given(_catalogos, _consulta)
def test_guia_nao_depende_do_horario(catalogo, consulta):
    """Variar o relógio entre as chamadas não muda o resultado."""
    primeira = resolver_instrucao(catalogo, *consulta)
    relogio = time.time
    try:
        time.time = lambda: 0.0  # type: ignore[assignment]
        em_zero = resolver_instrucao(catalogo, *consulta)
        time.time = lambda: 4_102_444_800.0  # type: ignore[assignment]
        no_futuro = resolver_instrucao(catalogo, *consulta)
    finally:
        time.time = relogio
    assert primeira == em_zero == no_futuro


@given(_catalogos, st.data())
def test_guia_resolve_mesma_instrucao_do_catalogo(catalogo, data):
    """Chave existente no catálogo sempre resolve, e para a primeira entrada correspondente."""
    itens = catalogo["instrucoes"]
    if not itens:
        return
    alvo = data.draw(st.sampled_from(itens))
    resultado = resolver_instrucao(
        catalogo, alvo["modelo_id"], alvo["problema_id"], alvo["variante"]
    )
    primeiro = next(
        i
        for i in itens
        if i["modelo_id"] == alvo["modelo_id"]
        and str(i["problema_id"]) == str(alvo["problema_id"])
        and i["variante"] == alvo["variante"]
    )
    assert resultado == instrucao_de_dict(primeiro)
