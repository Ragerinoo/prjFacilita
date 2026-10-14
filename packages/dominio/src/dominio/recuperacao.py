"""Avaliação da recuperação na Base_Conhecimento (Req 6.2, 6.3, 6.4).

Função pura: o Limiar_Relevancia é aplicado em código, antes de qualquer chamada ao modelo.

Regras:
  - Só contam trechos do modelo da Jornada (metadado `modelo_id` igual ao `modelo_id` pedido);
    trechos de outros modelos, ou sem `modelo_id`, são descartados (Req 6.2).
  - Pontuação ausente (None), não numérica ou NaN vale 0.0, abaixo de qualquer limiar > 0.
  - As fontes (manual, seção) vêm dos metadados `manual` e `secao` dos trechos, nunca do texto
    do modelo (Req 6.3). Trecho sem `manual` ou `secao` não pode ser citado e, por isso, não é
    considerado.
  - `sem_embasamento` é verdadeiro se não há trecho elegível ou se a maior pontuação entre os
    elegíveis é menor que o limiar (Req 6.4).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Final

LIMIAR_RELEVANCIA_PADRAO: Final = 0.5

CHAVE_MODELO: Final = "modelo_id"
CHAVE_MANUAL: Final = "manual"
CHAVE_SECAO: Final = "secao"


@dataclass(frozen=True)
class TrechoRecuperado:
    """Trecho devolvido pela Base_Conhecimento."""

    texto: str
    score: float | None = None
    metadados: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Fonte:
    """Origem citável de uma instrução (Req 6.3)."""

    manual: str
    secao: str


@dataclass(frozen=True)
class ResultadoRecuperacao:
    """Resultado de `avaliar_recuperacao`.

    `trechos` são os elegíveis com pontuação >= limiar (ordem de entrada preservada) e
    `fontes` as fontes distintas desses trechos. Ambos ficam vazios se `sem_embasamento`.
    `maior_pontuacao` é a maior pontuação entre os elegíveis (0.0 se não há nenhum).
    """

    sem_embasamento: bool
    trechos: tuple[TrechoRecuperado, ...] = ()
    fontes: tuple[Fonte, ...] = ()
    maior_pontuacao: float = 0.0


def _pontuacao(trecho: TrechoRecuperado) -> float:
    valor = trecho.score
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return 0.0
    valor = float(valor)
    return 0.0 if math.isnan(valor) else valor


def _texto_metadado(trecho: TrechoRecuperado, chave: str) -> str | None:
    valor = trecho.metadados.get(chave) if trecho.metadados else None
    if isinstance(valor, str) and valor.strip():
        return valor
    return None


def avaliar_recuperacao(
    trechos: Iterable[TrechoRecuperado],
    modelo_id: str,
    limiar: float = LIMIAR_RELEVANCIA_PADRAO,
) -> ResultadoRecuperacao:
    """Decide se há embasamento nos trechos recuperados para o modelo da Jornada.

    Levanta `ValueError` se `limiar` não for um número finito entre 0 e 1.
    """
    if (
        isinstance(limiar, bool)
        or not isinstance(limiar, (int, float))
        or not math.isfinite(limiar)
        or not 0.0 <= limiar <= 1.0
    ):
        raise ValueError("limiar deve ser um número entre 0 e 1")

    elegiveis = [
        t
        for t in trechos
        if _texto_metadado(t, CHAVE_MODELO) == modelo_id
        and _texto_metadado(t, CHAVE_MANUAL) is not None
        and _texto_metadado(t, CHAVE_SECAO) is not None
    ]
    if not elegiveis:
        return ResultadoRecuperacao(sem_embasamento=True)

    maior = max(_pontuacao(t) for t in elegiveis)
    if maior < limiar:
        return ResultadoRecuperacao(sem_embasamento=True, maior_pontuacao=maior)

    relevantes = tuple(t for t in elegiveis if _pontuacao(t) >= limiar)
    fontes: list[Fonte] = []
    for t in relevantes:
        fonte = Fonte(
            manual=_texto_metadado(t, CHAVE_MANUAL) or "",
            secao=_texto_metadado(t, CHAVE_SECAO) or "",
        )
        if fonte not in fontes:
            fontes.append(fonte)
    return ResultadoRecuperacao(
        sem_embasamento=False,
        trechos=relevantes,
        fontes=tuple(fontes),
        maior_pontuacao=maior,
    )
