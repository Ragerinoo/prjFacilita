"""Testes unitários do custo da chamada e da avaliação da recuperação (Req 6.2-6.4, 7.2, 7.3)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from dominio.custo import Precos, custo_chamada_brl
from dominio.recuperacao import (
    Fonte,
    TrechoRecuperado,
    avaliar_recuperacao,
)

PRECOS = Precos(entrada_por_1m=Decimal("1"), saida_por_1m=Decimal("5"))
COTACAO = Decimal("5")


# --- custo_chamada_brl ---------------------------------------------------------------------


def test_tokens_zero_custam_zero_com_quatro_casas() -> None:
    custo = custo_chamada_brl(0, 0, PRECOS, COTACAO)
    assert custo == Decimal("0")
    assert str(custo) == "0.0000"


def test_formula_do_design() -> None:
    # (1000*1 + 500*5)/1e6 * 5 = 0.0175
    assert custo_chamada_brl(1000, 500, PRECOS, COTACAO) == Decimal("0.0175")


def test_arredonda_half_up_para_quatro_casas() -> None:
    precos = Precos(entrada_por_1m=Decimal("1"), saida_por_1m=Decimal("0"))
    # 1 token * 1 / 1e6 * 0.5 = 0.0000005 -> 0.0000 ; 100 tokens -> 0.00005 -> 0.0001
    assert custo_chamada_brl(1, 0, precos, Decimal("0.5")) == Decimal("0.0000")
    assert custo_chamada_brl(100, 0, precos, Decimal("0.5")) == Decimal("0.0001")


def test_resultado_tem_exatamente_quatro_casas() -> None:
    custo = custo_chamada_brl(123, 456, PRECOS, COTACAO)
    assert custo.as_tuple().exponent == -4


@pytest.mark.parametrize(
    ("tin", "tout"),
    [(-1, 0), (0, -1), (1.5, 0), (True, 0)],
)
def test_tokens_invalidos_levantam_erro(tin: object, tout: object) -> None:
    with pytest.raises(ValueError):
        custo_chamada_brl(tin, tout, PRECOS, COTACAO)  # type: ignore[arg-type]


def test_preco_ou_cotacao_invalidos_levantam_erro() -> None:
    with pytest.raises(ValueError):
        custo_chamada_brl(1, 1, Precos(Decimal("-1"), Decimal("1")), COTACAO)
    with pytest.raises(ValueError):
        custo_chamada_brl(1, 1, PRECOS, Decimal("NaN"))


# --- avaliar_recuperacao -------------------------------------------------------------------


def _trecho(
    score: float | None,
    modelo: str = "M1",
    manual: str | None = "Manual M1",
    secao: str | None = "Limpeza",
    texto: str = "texto",
) -> TrechoRecuperado:
    meta = {"modelo_id": modelo}
    if manual is not None:
        meta["manual"] = manual
    if secao is not None:
        meta["secao"] = secao
    return TrechoRecuperado(texto=texto, score=score, metadados=meta)


def test_lista_vazia_e_sem_embasamento() -> None:
    r = avaliar_recuperacao([], "M1")
    assert r.sem_embasamento is True
    assert r.trechos == () and r.fontes == ()


def test_maior_pontuacao_abaixo_do_limiar_e_sem_embasamento() -> None:
    r = avaliar_recuperacao([_trecho(0.2), _trecho(0.49)], "M1")
    assert r.sem_embasamento is True
    assert r.trechos == ()


def test_pontuacao_igual_ao_limiar_tem_embasamento() -> None:
    r = avaliar_recuperacao([_trecho(0.5)], "M1")
    assert r.sem_embasamento is False
    assert len(r.trechos) == 1


def test_score_ausente_vale_zero() -> None:
    assert avaliar_recuperacao([_trecho(None)], "M1").sem_embasamento is True
    r = avaliar_recuperacao([_trecho(None), _trecho(0.8)], "M1")
    assert r.sem_embasamento is False
    assert [t.score for t in r.trechos] == [0.8]


def test_limiar_configuravel() -> None:
    assert avaliar_recuperacao([_trecho(0.6)], "M1", limiar=0.7).sem_embasamento is True
    assert avaliar_recuperacao([_trecho(0.6)], "M1", limiar=0.6).sem_embasamento is False


def test_trechos_de_outros_modelos_sao_descartados() -> None:
    r = avaliar_recuperacao([_trecho(0.99, modelo="M2")], "M1")
    assert r.sem_embasamento is True
    r = avaliar_recuperacao([_trecho(0.99, modelo="M2"), _trecho(0.6, modelo="M1")], "M1")
    assert r.sem_embasamento is False
    assert all(t.metadados["modelo_id"] == "M1" for t in r.trechos)
    assert r.maior_pontuacao == 0.6


def test_trecho_sem_modelo_nos_metadados_e_descartado() -> None:
    sem_modelo = TrechoRecuperado("x", 0.9, {"manual": "m", "secao": "s"})
    assert avaliar_recuperacao([sem_modelo], "M1").sem_embasamento is True


def test_fontes_vem_dos_metadados_sem_duplicatas() -> None:
    r = avaliar_recuperacao(
        [
            _trecho(0.9, manual="Manual A", secao="Limpeza"),
            _trecho(0.8, manual="Manual A", secao="Limpeza"),
            _trecho(0.7, manual="Manual A", secao="Descalcificação"),
            _trecho(0.1, manual="Manual B", secao="Outra"),
        ],
        "M1",
    )
    assert r.fontes == (Fonte("Manual A", "Limpeza"), Fonte("Manual A", "Descalcificação"))


def test_trecho_sem_manual_ou_secao_nao_e_citavel_e_nao_conta() -> None:
    r = avaliar_recuperacao([_trecho(0.9, manual=None), _trecho(0.9, secao=" ")], "M1")
    assert r.sem_embasamento is True


@pytest.mark.parametrize("limiar", [-0.1, 1.1, float("nan"), float("inf")])
def test_limiar_invalido_levanta_erro(limiar: float) -> None:
    with pytest.raises(ValueError):
        avaliar_recuperacao([_trecho(0.9)], "M1", limiar=limiar)
