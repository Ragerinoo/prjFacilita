"""Fila do Painel_CS: chave de ordenação do índice `gsi_fila` e `ordenar_fila` (Req 14.1).

Uma única regra de ordem serve ao índice e ao ordenador:

    fila_sk = "{prioridade}#{criado_em UTC, segundos, sufixo Z}#{numero}"

Os adaptadores do DynamoDB (tarefa 9.2) gravam `fila_pk = FILA_PK` e `fila_sk =
montar_fila_sk(...)`; `ordenar_fila` usa a mesma função como chave de comparação.
A ordem lexicográfica da chave é: prioridade (P1, P2, P3), horário de criação
crescente e número do Chamado crescente.

O horário tem resolução de segundos, como no formato do design
(`P2#2025-01-01T12:05:11Z#TRES-7K3M9QX2PD`). Chamados criados no mesmo segundo
desempatam pelo número, tanto no índice quanto no ordenador.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from dominio.tipos import Prioridade

# Chave de partição constante do índice esparso `gsi_fila`.
FILA_PK = "ABERTO"

_SEPARADOR = "#"
_PRIORIDADES_VALIDAS = frozenset({"P1", "P2", "P3"})


@dataclass(frozen=True, slots=True)
class ChamadoFila:
    """Visão mínima de um Chamado aberto para ordenação da fila."""

    numero: str
    prioridade: Prioridade
    criado_em: datetime


def formatar_horario_fila(criado_em: datetime) -> str:
    """ISO 8601 em UTC, segundos, sufixo `Z` (largura fixa, ordena como texto)."""
    if criado_em.tzinfo is None or criado_em.utcoffset() is None:
        raise ValueError("criado_em deve ter fuso horário (datetime ciente de fuso)")
    return criado_em.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def montar_fila_sk(prioridade: Prioridade, criado_em: datetime, numero: str) -> str:
    """Monta a chave `fila_sk` de um Chamado aberto (Req 14.1)."""
    if prioridade not in _PRIORIDADES_VALIDAS:
        raise ValueError(f"prioridade inválida: {prioridade!r}")
    if not numero or _SEPARADOR in numero:
        raise ValueError(f"número de Chamado inválido: {numero!r}")
    return _SEPARADOR.join((prioridade, formatar_horario_fila(criado_em), numero))


def chave_fila(chamado: ChamadoFila) -> str:
    """`fila_sk` de um `ChamadoFila`."""
    return montar_fila_sk(chamado.prioridade, chamado.criado_em, chamado.numero)


def ordenar_fila(chamados: Iterable[ChamadoFila]) -> list[ChamadoFila]:
    """Ordena por prioridade, horário de criação e número, igual à ordem de `fila_sk`."""
    return sorted(chamados, key=chave_fila)
