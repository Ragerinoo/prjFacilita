"""Motor_Escalada: decisão determinística de prioridade, classificação e canal.

Funções puras (sem I/O, relógio ou aleatoriedade). Fonte de verdade: tabela de decisão do
design (seção 3.2) e Req 6.10, 7.4, 7.5, 9.1, 9.2, 9.5, 9.7, 9.9, 11.1 a 11.6.

Tabela de decisão, avaliada uma única vez sobre os fatos consolidados (Req 11.6):

    critério 1: risco_seguranca                    -> P1, provável defeito, ligação imediata
    critério 2: sem risco e guia_respondeu_nao     -> P2, provável defeito, chat ou ligação
    critério 3: demais casos                       -> P3, provável uso, chat assíncrono

Somente `risco_seguranca` e `guia_respondeu_nao` entram na decisão. Gatilhos, sentimento,
horário, ordem dos gatilhos e saída do modelo nunca a alteram (Req 11.5).
"""

from __future__ import annotations

from typing import Final, Literal

from dominio.tipos import (
    Camada,
    DecisaoEscalada,
    FatosJornada,
    Nivel,
    Prioridade,
)

# --- Constantes de negócio -------------------------------------------------------------

CANAL_P1: Final = "ligação imediata"
CANAL_P2: Final = "chat ou ligação, à escolha do Consumidor"
CANAL_P3: Final = "chat assíncrono"

LIMITE_MENSAGENS_MODELO: Final = 10  # Req 7.4
LIMITE_NEGATIVAS_IA: Final = 2  # Req 9.2, 6.10
LIMITE_FRUSTRACAO_ALTA: Final = 2  # Req 9.5

# P1 > P2 > P3: quanto menor o número, maior a prioridade.
_RANKING: Final[dict[Prioridade, int]] = {"P1": 0, "P2": 1, "P3": 2}

RespostaConsumidor = Literal["sim", "nao"]


# --- Tabela de decisão -----------------------------------------------------------------


def decidir_escalada(fatos: FatosJornada) -> DecisaoEscalada:
    """Aplica a tabela de decisão P1/P2/P3 (Req 11.1, 11.2, 11.3, 11.5, 11.6).

    Depende exclusivamente de `risco_seguranca` e `guia_respondeu_nao`. O risco tem
    precedência sobre qualquer outro fato (P1 > P2 > P3).
    """
    if fatos.risco_seguranca:
        return DecisaoEscalada(
            prioridade="P1",
            classificacao="provável defeito",
            canal=CANAL_P1,
            criterio=1,
        )
    if fatos.guia_respondeu_nao:
        return DecisaoEscalada(
            prioridade="P2",
            classificacao="provável defeito",
            canal=CANAL_P2,
            criterio=2,
        )
    return DecisaoEscalada(
        prioridade="P3",
        classificacao="provável uso",
        canal=CANAL_P3,
        criterio=3,
    )


def reavaliar_prioridade(atual: DecisaoEscalada, fatos: FatosJornada) -> DecisaoEscalada:
    """Reavalia uma Jornada já escalada com fatos novos; a prioridade nunca diminui.

    Devolve a decisão recalculada somente se ela eleva a prioridade (por exemplo, risco
    detectado depois de um P3). Caso contrário mantém `atual` sem alteração
    (Req 8.5, 9.9, 11.6; design 3.2, passo 5).
    """
    nova = decidir_escalada(fatos)
    if _RANKING[nova.prioridade] < _RANKING[atual.prioridade]:
        return nova
    return atual


# --- Limite de chamadas ao modelo ------------------------------------------------------


def pode_chamar_modelo(msgs_modelo: int, limite: int = LIMITE_MENSAGENS_MODELO) -> bool:
    """Indica se ainda é permitido acionar o modelo de linguagem na Jornada (Req 7.4, 7.5).

    `msgs_modelo` é a quantidade de mensagens já processadas pelo modelo (respostas do
    cache não contam). Com limite 10, a 10ª chamada é permitida (contagem 9); com a
    contagem em 10 o modelo fica bloqueado e a Jornada deve escalar por `limite_mensagens`.
    """
    _exigir_nao_negativo(msgs_modelo, "msgs_modelo")
    return msgs_modelo < limite


def atingiu_limite_mensagens(msgs_modelo: int, limite: int = LIMITE_MENSAGENS_MODELO) -> bool:
    """Verdadeiro quando a Jornada atingiu o limite e deve escalar (Req 7.5)."""
    return not pode_chamar_modelo(msgs_modelo, limite)


# --- Frustração alta (Req 9.5) ---------------------------------------------------------


def proximo_estado_frustracao(seq_alta: int, nivel: Nivel) -> int:
    """Próximo valor de `frustracao_alta_seq`: "alta" soma 1; outro nível zera (Req 9.5)."""
    _exigir_nao_negativo(seq_alta, "seq_alta")
    return seq_alta + 1 if nivel == "alta" else 0


def frustracao_dispara_escalada(seq_alta: int) -> bool:
    """Duas mensagens consecutivas "alta" disparam a escalada (Req 9.5)."""
    return seq_alta >= LIMITE_FRUSTRACAO_ALTA


# --- Negativas ao Assistente_IA (Req 6.10, 9.2) ----------------------------------------


def proximo_contador_negativas_ia(
    contagem: int, camada: Camada, resposta: RespostaConsumidor
) -> int:
    """Próximo valor de `ia_nao_count`.

    Só um "Não" ao "Isso resolveu?" do assistente (camada "ia") incrementa. "Sim" não
    zera (conta consecutivas ou não) e qualquer resposta do guia é ignorada (Req 9.2).
    """
    _exigir_nao_negativo(contagem, "contagem")
    if camada == "ia" and resposta == "nao":
        return contagem + 1
    return contagem


def negativas_ia_disparam_escalada(contagem: int) -> bool:
    """O segundo "Não" ao assistente dispara a escalada (Req 6.10, 9.2)."""
    return contagem >= LIMITE_NEGATIVAS_IA


# --- Auxiliares ------------------------------------------------------------------------


def _exigir_nao_negativo(valor: int, nome: str) -> None:
    if valor < 0:
        raise ValueError(f"{nome} não pode ser negativo: {valor}")
