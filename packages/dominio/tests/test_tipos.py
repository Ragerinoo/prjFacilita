"""Testes dos tipos de domínio: imutabilidade e valores esperados."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from typing import get_args

import pytest

from dominio import (
    Camada,
    DecisaoEscalada,
    EntradaCache,
    ErroDominio,
    ErroMascaramento,
    FatosJornada,
    Gatilho,
    JornadaEncerrada,
    Nivel,
    Prioridade,
    ResultadoInsercao,
    StatusInsercao,
)


def test_literais_do_design() -> None:
    assert get_args(Prioridade) == ("P1", "P2", "P3")
    assert get_args(Camada) == ("guia", "ia", "humano", "abandonada")
    assert get_args(Nivel) == ("baixa", "média", "alta")
    assert len(get_args(Gatilho)) == 7  # Req 9.7


def _instancias() -> list[object]:
    agora = datetime(2025, 1, 1, tzinfo=UTC)
    entrada = EntradaCache("m1", "p", "r", "a1", agora)
    return [
        FatosJornada(risco_seguranca=False, guia_respondeu_nao=True),
        DecisaoEscalada("P3", "provável uso", "chat assíncrono", 3),
        JornadaEncerrada("j1", "guia", agora, 10, Decimal("0.0000"), None, None),
        entrada,
        ResultadoInsercao(StatusInsercao.ACEITA, entrada),
    ]


@pytest.mark.parametrize("obj", _instancias(), ids=lambda o: type(o).__name__)
def test_estruturas_sao_imutaveis(obj: object) -> None:
    campo = next(iter(obj.__dataclass_fields__))  # type: ignore[attr-defined]
    with pytest.raises(FrozenInstanceError):
        setattr(obj, campo, "x")


def test_fatos_gatilhos_padrao_vazio_e_hashable() -> None:
    fatos = FatosJornada(risco_seguranca=True, guia_respondeu_nao=False)
    assert fatos.gatilhos == frozenset()
    assert hash(fatos) == hash(FatosJornada(True, False))


def test_resultado_insercao_aceita() -> None:
    assert ResultadoInsercao(StatusInsercao.ACEITA).aceita
    assert not ResultadoInsercao(StatusInsercao.DUPLICADA).aceita


def test_erro_mascaramento_e_erro_de_dominio() -> None:
    assert issubclass(ErroMascaramento, ErroDominio)
    with pytest.raises(ErroDominio):
        raise ErroMascaramento("falha")
