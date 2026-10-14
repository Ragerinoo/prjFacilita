"""Detector_Risco e detector de pedido de atendimento humano (Req 8.1, 9.3).

Funções puras, sem I/O. As listas abaixo são apenas os valores iniciais: o serviço
lê `config.termos_risco` e `config.expressoes_humano` e as passa por parâmetro,
sobrescrevendo estes padrões. A lista final depende de validação da 3corações (Q11).

Regras de casamento:
- texto e termos são normalizados (minúsculas, sem acentos, pontuação vira espaço);
- o termo casa como palavra inteira ou expressão inteira (limites de palavra),
  nunca como pedaço de outra palavra;
- negação não desativa a detecção: "não sai fumaça" também é risco (Req 8.1).
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence

# Valores iniciais (Req 8.1 / design 3.1). Sobrescritíveis pela tabela `config`.
TERMOS_RISCO_PADRAO: tuple[str, ...] = (
    "queimado",
    "cheiro de queimado",
    "fumaca",
    "choque",
    "faisca",
    "vazamento interno",
)

# Valores iniciais (Req 9.3). Sobrescritíveis pela tabela `config`.
EXPRESSOES_HUMANO_PADRAO: tuple[str, ...] = (
    "atendente",
    "falar com uma pessoa",
    "humano",
)


def _normalizar(texto: str) -> str:
    """Minúsculas, sem acentos, pontuação/símbolos viram espaço, espaços únicos."""
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acentos = "".join(c for c in decomposto if unicodedata.category(c) != "Mn")
    minusculas = sem_acentos.casefold()
    # Pontuação (P*) e símbolos (S*) viram espaço, para "fumaça,choque" separar as palavras.
    separado = "".join(
        " " if unicodedata.category(c)[0] in ("P", "S") else c for c in minusculas
    )
    return " ".join(separado.split())


def _contem_alguma(texto: str, termos: Sequence[str]) -> bool:
    alvo = f" {_normalizar(texto)} "
    for termo in termos:
        norm = _normalizar(termo)
        if norm and f" {norm} " in alvo:
            return True
    return False


def detectar_risco(texto: str, termos: Sequence[str] | None = None) -> bool:
    """Verdadeiro se `texto` contém algum termo de risco como palavra ou expressão inteira.

    `termos=None` usa `TERMOS_RISCO_PADRAO`; uma sequência explícita (inclusive vazia)
    a substitui. Ignora caixa e acentos; a negação não desativa a detecção (Req 8.1).
    """
    return _contem_alguma(texto, TERMOS_RISCO_PADRAO if termos is None else termos)


def pede_atendimento_humano(texto: str, expressoes: Sequence[str] | None = None) -> bool:
    """Verdadeiro se `texto` contém alguma expressão de pedido de atendimento humano.

    `expressoes=None` usa `EXPRESSOES_HUMANO_PADRAO`. Ignora caixa e acentos (Req 9.3).
    """
    return _contem_alguma(texto, EXPRESSOES_HUMANO_PADRAO if expressoes is None else expressoes)
