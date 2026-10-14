"""Idempotência de mutações por `Idempotency-Key` ou `evento_id` (design, contrato HTTP).

Repetir a mesma requisição não pode duplicar efeitos. O guarda usa a garantia que o
`EventosRepo` já dá (Put condicional por `evento_id`, Req 3.12), sem tabela nova:

  * a chave do cliente (cabeçalho `Idempotency-Key` ou campo `evento_id` do corpo) vira um
    `evento_id` determinístico (ULID válido derivado do SHA-256 da chave);
  * o registro mora numa partição própria (`idem#<escopo>`), então não polui a linha do tempo
    da Jornada que `EventosRepo.listar(jornada_id)` devolve.

`primeira_vez` devolve True só na primeira chamada para (escopo, chave). Sem chave, não há
como deduplicar: devolve True (a rota decide se exige a chave). O conteúdo da requisição não
é gravado, só o tipo e o horário, então nada de PII.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Final

from core.erros import validacao
from core.http import Requisicao
from dominio import ErroCampo
from repositorios.interfaces import EventosRepo
from repositorios.modelos import Evento

CABECALHO: Final = "idempotency-key"
TIPO_EVENTO: Final = "idempotencia"
PREFIXO_PARTICAO: Final = "idem#"
TAMANHO_MAXIMO_CHAVE: Final = 128

_ALFABETO: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def ulid_da_chave(chave: str) -> str:
    """ULID válido e determinístico para `chave` (128 bits do SHA-256, 26 símbolos Crockford)."""
    numero = int.from_bytes(hashlib.sha256(chave.encode("utf-8")).digest()[:16], "big")
    simbolos = []
    for _ in range(26):
        simbolos.append(_ALFABETO[numero & 0x1F])
        numero >>= 5
    return "".join(reversed(simbolos))  # 128 bits => primeiro símbolo em 0..3 (padrão ULID)


def chave_da_requisicao(
    requisicao: Requisicao, corpo: Mapping[str, Any] | None = None
) -> str | None:
    """`Idempotency-Key` (cabeçalho) ou `evento_id` (corpo); `None` se nenhum foi enviado.

    Chave presente mas inválida (vazia, texto demais, tipo errado) vira 422.
    """
    bruta: Any = requisicao.cabecalho(CABECALHO)
    campo = "Idempotency-Key"
    if bruta is None and corpo is not None:
        bruta = corpo.get("evento_id")
        campo = "evento_id"
    if bruta is None:
        return None
    if not isinstance(bruta, str) or not bruta.strip() or len(bruta) > TAMANHO_MAXIMO_CHAVE:
        raise validacao(
            [ErroCampo(campo, f"deve ser um texto de 1 a {TAMANHO_MAXIMO_CHAVE} caracteres")]
        )
    return bruta.strip()


class Idempotencia:
    """Guarda de idempotência apoiado em `EventosRepo`."""

    def __init__(self, eventos: EventosRepo, agora: Callable[[], datetime]) -> None:
        self._eventos = eventos
        self._agora = agora

    def primeira_vez(self, escopo: str, chave: str | None) -> bool:
        """True se (escopo, chave) nunca foi vista. Sem chave: True (nada a deduplicar)."""
        if not chave:
            return True
        evento = Evento(
            jornada_id=f"{PREFIXO_PARTICAO}{escopo}",
            evento_id=ulid_da_chave(chave),
            tipo=TIPO_EVENTO,
            em=self._agora(),
        )
        return self._eventos.registrar(evento)
