"""Custo estimado de uma chamada ao modelo de linguagem (Req 7.2, 7.3).

Fórmula do design (modelo de custo):

    custo = (tokens_entrada * preco_entrada_por_1M + tokens_saida * preco_saida_por_1M)
            / 1.000.000 * cotacao_usd_brl

Preços e cotação entram por parâmetro (vêm da tabela `config`); nunca ficam no código.
O resultado é um `Decimal` em BRL com exatamente 4 casas decimais.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Final

_UM_MILHAO: Final = Decimal(1_000_000)
_QUATRO_CASAS: Final = Decimal("0.0001")


@dataclass(frozen=True)
class Precos:
    """Preços do modelo em USD por 1 milhão de tokens."""

    entrada_por_1m: Decimal
    saida_por_1m: Decimal


def _validar_tokens(nome: str, valor: int) -> None:
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 0:
        raise ValueError(f"{nome} deve ser um inteiro maior ou igual a zero")


def _validar_decimal_nao_negativo(nome: str, valor: Decimal) -> None:
    if not isinstance(valor, Decimal) or not valor.is_finite() or valor < 0:
        raise ValueError(f"{nome} deve ser um Decimal finito maior ou igual a zero")


def custo_chamada_brl(
    tokens_entrada: int,
    tokens_saida: int,
    precos: Precos,
    cotacao_usd_brl: Decimal,
) -> Decimal:
    """Custo estimado da chamada em BRL, com 4 casas decimais (arredondamento half-up).

    Com zero tokens de entrada e de saída o custo é `Decimal("0.0000")` (Req 7.2).
    Levanta `ValueError` para tokens negativos/não inteiros e preços ou cotação inválidos.
    """
    _validar_tokens("tokens_entrada", tokens_entrada)
    _validar_tokens("tokens_saida", tokens_saida)
    _validar_decimal_nao_negativo("precos.entrada_por_1m", precos.entrada_por_1m)
    _validar_decimal_nao_negativo("precos.saida_por_1m", precos.saida_por_1m)
    _validar_decimal_nao_negativo("cotacao_usd_brl", cotacao_usd_brl)

    # Contexto local com precisão alta: a única perda é o arredondamento final.
    with localcontext() as ctx:
        ctx.prec = 60
        usd = (
            tokens_entrada * precos.entrada_por_1m + tokens_saida * precos.saida_por_1m
        ) / _UM_MILHAO
        return (usd * cotacao_usd_brl).quantize(_QUATRO_CASAS, rounding=ROUND_HALF_UP)
