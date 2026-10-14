"""Tipos de domínio imutáveis do TRES Autoatendimento.

Sem I/O, sem relógio global e sem aleatoriedade implícita: horários e dados entram
sempre por parâmetro. Todas as estruturas são `frozen` (design, "Estruturas de domínio").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

Prioridade = Literal["P1", "P2", "P3"]
Classificacao = Literal["provável defeito", "provável uso"]
Camada = Literal["guia", "ia", "humano", "abandonada"]
Nivel = Literal["baixa", "média", "alta"]
# Gatilhos reconhecidos de escalada (Req 9.7).
Gatilho = Literal[
    "risco_seguranca",
    "duas_negativas_ia",
    "pedido_humano",
    "sem_embasamento",
    "frustracao_alta",
    "limite_mensagens",
    "instrucao_sem_solucao",
]


@dataclass(frozen=True, slots=True)
class FatosJornada:
    """Fatos consolidados de uma Jornada, entrada do Motor_Escalada.

    Somente `risco_seguranca` e `guia_respondeu_nao` influenciam prioridade,
    classificação e canal. Os demais campos não alteram a decisão (Req 11.5).
    """

    risco_seguranca: bool  # Detector_Risco, em qualquer origem
    guia_respondeu_nao: bool  # "Não" após concluir a instrução de ao menos 1 problema
    gatilhos: frozenset[Gatilho] = field(default_factory=frozenset)
    sentimento: Nivel | None = None
    problema_id: str | None = None


@dataclass(frozen=True, slots=True)
class DecisaoEscalada:
    """Resultado da tabela de decisão do Motor_Escalada (Req 11.1, 11.2, 11.3)."""

    prioridade: Prioridade
    classificacao: Classificacao
    canal: str
    criterio: Literal[1, 2, 3]


@dataclass(frozen=True, slots=True)
class JornadaEncerrada:
    """Registro de encerramento de uma Jornada, com exatamente uma camada (Req 17.1)."""

    jornada_id: str
    camada: Camada
    encerrada_em: datetime
    tempo_s: int
    custo_brl: Decimal
    problema_id: int | None
    desfecho: str | None


@dataclass(frozen=True, slots=True)
class EntradaCache:
    """Entrada do Cache_Respostas. Só é aceita com `aprovador_id` (Req 7.6)."""

    modelo_id: str
    pergunta: str
    resposta: str
    aprovador_id: str | None
    aprovado_em: datetime | None


class StatusInsercao(StrEnum):
    """Desfecho de uma tentativa de inserção no Cache_Respostas."""

    ACEITA = "aceita"
    REJEITADA_SEM_APROVADOR = "rejeitada_sem_aprovador"  # Req 7.7
    DUPLICADA = "duplicada"  # Req 16.8: mantém a entrada existente


@dataclass(frozen=True, slots=True)
class ResultadoInsercao:
    """Resultado de `aceitar_insercao_cache`.

    `entrada` é a que deve permanecer no cache após a tentativa: a nova quando
    aceita, a existente quando duplicada, `None` quando rejeitada sem aprovador
    e sem entrada prévia.
    """

    status: StatusInsercao
    entrada: EntradaCache | None = None

    @property
    def aceita(self) -> bool:
        return self.status is StatusInsercao.ACEITA
