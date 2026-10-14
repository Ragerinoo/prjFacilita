"""Teste de propriedade do custo da chamada ao modelo.

Feature: tres-autoatendimento, Property 17: Custo da chamada ao modelo

**Validates: Requirements 7.2, 7.3**
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, localcontext

from hypothesis import given
from hypothesis import strategies as st

from dominio.custo import Precos, custo_chamada_brl

_tokens = st.integers(min_value=0, max_value=10_000_000)
# Preços em USD/1M tokens e cotação com até 4 casas decimais.
_precos_usd = st.decimals(
    min_value=Decimal("0"), max_value=Decimal("1000"), places=4, allow_nan=False
)
_cotacoes = st.decimals(
    min_value=Decimal("0.0001"), max_value=Decimal("100"), places=4, allow_nan=False
)
_precos = st.builds(Precos, entrada_por_1m=_precos_usd, saida_por_1m=_precos_usd)

_QUATRO_CASAS = Decimal("0.0001")


def _referencia(t_ent: int, t_sai: int, precos: Precos, cotacao: Decimal) -> Decimal:
    """Fórmula do design calculada com precisão alta e arredondada só no final."""
    with localcontext() as ctx:
        ctx.prec = 100
        parcela_entrada = Decimal(t_ent) * precos.entrada_por_1m / Decimal(1_000_000)
        parcela_saida = Decimal(t_sai) * precos.saida_por_1m / Decimal(1_000_000)
        return ((parcela_entrada + parcela_saida) * cotacao).quantize(
            _QUATRO_CASAS, rounding=ROUND_HALF_UP
        )


@given(_tokens, _tokens, _precos, _cotacoes)
def test_custo_confere_com_a_formula_e_tem_quatro_casas(t_ent, t_sai, precos, cotacao):
    custo = custo_chamada_brl(t_ent, t_sai, precos, cotacao)

    assert custo == _referencia(t_ent, t_sai, precos, cotacao)
    assert custo >= 0
    assert custo.as_tuple().exponent == -4


@given(_precos, _cotacoes)
def test_zero_tokens_custa_zero(precos, cotacao):
    custo = custo_chamada_brl(0, 0, precos, cotacao)

    assert custo == Decimal("0.0000")
    assert str(custo) == "0.0000"


@given(_tokens, _tokens, _tokens, _tokens, _precos, _cotacoes)
def test_custo_nao_diminui_quando_tokens_aumentam(t_ent, t_sai, extra_ent, extra_sai, precos, cot):
    base = custo_chamada_brl(t_ent, t_sai, precos, cot)

    assert custo_chamada_brl(t_ent + extra_ent, t_sai, precos, cot) >= base
    assert custo_chamada_brl(t_ent, t_sai + extra_sai, precos, cot) >= base
    assert custo_chamada_brl(t_ent + extra_ent, t_sai + extra_sai, precos, cot) >= base
