"""Testes unitários do Detector_Risco e do detector de pedido humano (Req 8.1, 9.3)."""

from __future__ import annotations

import pytest

from dominio.risco import (
    EXPRESSOES_HUMANO_PADRAO,
    TERMOS_RISCO_PADRAO,
    detectar_risco,
    pede_atendimento_humano,
)


@pytest.mark.parametrize(
    "texto",
    [
        "sai FUMAÇA da máquina",
        "Senti um CHOQUE",
        "tem cheiro de queimado",
        "a placa está queimada e o café QUEIMADO",
        "vi uma faísca!",
        "FAÍSCA",
        "há vazamento interno na máquina",
        "não sai fumaça",  # negação não desativa
        "nao tem choque",
        "fumaça,choque",  # pontuação separa palavras
    ],
)
def test_detecta_risco(texto: str) -> None:
    assert detectar_risco(texto, TERMOS_RISCO_PADRAO)


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "   ",
        "a máquina não liga",
        "vazamento externo na bandeja",
        "cheiro de café",
        "choques",  # pedaço/variação de palavra não casa
        "fumacento",
    ],
)
def test_nao_detecta_sem_termo_inteiro(texto: str) -> None:
    assert not detectar_risco(texto, TERMOS_RISCO_PADRAO)


def test_termos_configurados_substituem_padrao() -> None:
    assert detectar_risco("está pegando fogo", ["Pegando FOGO"])
    assert not detectar_risco("sai fumaça", ["pegando fogo"])
    assert not detectar_risco("sai fumaça", [])
    # Sem argumento, usa o padrão.
    assert detectar_risco("sai fumaça")


def test_termo_vazio_na_configuracao_nao_casa_tudo() -> None:
    assert not detectar_risco("tudo normal", ["", "   "])


@pytest.mark.parametrize(
    "texto",
    ["quero um ATENDENTE", "Falar com uma pessoa, por favor", "preciso de um humano", "Atendênte"],
)
def test_pede_humano(texto: str) -> None:
    assert pede_atendimento_humano(texto, EXPRESSOES_HUMANO_PADRAO)


@pytest.mark.parametrize("texto", ["", "a máquina não liga", "desumano", "atendentes"])
def test_nao_pede_humano(texto: str) -> None:
    assert not pede_atendimento_humano(texto, EXPRESSOES_HUMANO_PADRAO)


def test_expressoes_configuradas_substituem_padrao() -> None:
    assert pede_atendimento_humano("chama o gerente", ["gerente"])
    assert not pede_atendimento_humano("quero um atendente", ["gerente"])
