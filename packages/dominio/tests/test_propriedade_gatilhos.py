"""Teste de propriedade dos gatilhos baseados em contagem.

Feature: tres-autoatendimento, Property 6: Gatilhos baseados em contagem disparam
exatamente no ponto correto

**Validates: Requirements 6.10, 9.2, 9.5**
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from dominio.escalada import (
    frustracao_dispara_escalada,
    negativas_ia_disparam_escalada,
    proximo_contador_negativas_ia,
    proximo_estado_frustracao,
)

# Respostas "Sim/Não" a soluções do assistente (camada "ia") intercaladas com
# respostas do guia (camada "guia"), em qualquer ordem.
_respostas = st.lists(
    st.tuples(st.sampled_from(["ia", "guia"]), st.sampled_from(["sim", "nao"])),
    max_size=30,
)
_niveis = st.lists(st.sampled_from(["baixa", "média", "alta"]), max_size=30)


@given(_respostas)
def test_negativas_ia_disparam_exatamente_na_segunda_nao_do_assistente(respostas):
    contagem = 0
    nao_ia_vistos = 0
    for camada, resposta in respostas:
        contagem = proximo_contador_negativas_ia(contagem, camada, resposta)
        if camada == "ia" and resposta == "nao":
            nao_ia_vistos += 1

        # Somente "Não" do assistente conta; "Sim" e respostas do guia são ignoradas.
        assert contagem == nao_ia_vistos
        # Dispara exatamente a partir da segunda "Não" do assistente, nunca antes.
        assert negativas_ia_disparam_escalada(contagem) == (nao_ia_vistos >= 2)
        # A segunda solução só é oferecida depois da primeira "Não" (e antes da escalada).
        segunda_solucao_oferecida = contagem == 1
        assert segunda_solucao_oferecida == (nao_ia_vistos == 1)


@given(_respostas)
def test_primeiro_disparo_ocorre_na_segunda_nao_do_assistente(respostas):
    contagem = 0
    indice_disparo = None
    for i, (camada, resposta) in enumerate(respostas):
        contagem = proximo_contador_negativas_ia(contagem, camada, resposta)
        if indice_disparo is None and negativas_ia_disparam_escalada(contagem):
            indice_disparo = i

    indices_nao_ia = [
        i for i, (camada, resposta) in enumerate(respostas) if camada == "ia" and resposta == "nao"
    ]
    esperado = indices_nao_ia[1] if len(indices_nao_ia) >= 2 else None
    assert indice_disparo == esperado


@given(_niveis)
def test_frustracao_dispara_na_primeira_ocasiao_de_duas_altas_consecutivas(niveis):
    seq = 0
    indice_disparo = None
    for i, nivel in enumerate(niveis):
        seq = proximo_estado_frustracao(seq, nivel)
        if indice_disparo is None and frustracao_dispara_escalada(seq):
            indice_disparo = i

    esperado = next(
        (i for i in range(1, len(niveis)) if niveis[i] == "alta" and niveis[i - 1] == "alta"),
        None,
    )
    assert indice_disparo == esperado


@given(_niveis)
def test_nivel_diferente_de_alta_reinicia_a_contagem(niveis):
    seq = 0
    corrida = 0  # tamanho da sequência atual de "alta" consecutivas
    for nivel in niveis:
        seq = proximo_estado_frustracao(seq, nivel)
        corrida = corrida + 1 if nivel == "alta" else 0
        assert seq == corrida
        if nivel != "alta":
            assert seq == 0
            assert not frustracao_dispara_escalada(seq)
