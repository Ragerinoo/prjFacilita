"""ULID (26 caracteres Crockford base32) usado como chave de ordenação `ts_ulid`.

Os 48 bits iniciais são o horário em milissegundos, então a ordem lexicográfica é a
ordem cronológica. Dentro do mesmo milissegundo (de um mesmo processo), o gerador
incrementa a parte aleatória para manter a ordem de criação (mensagens do mesmo instante
não se invertem). Entre processos/instâncias Lambda essa ordem fina não é garantida.

O relógio entra por parâmetro (`em`), sem relógio global.
"""

from __future__ import annotations

import os
import re
import threading
from collections.abc import Callable
from datetime import datetime
from typing import Final

_ALFABETO: Final = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_PADRAO: Final = re.compile(r"^[0-7][0-9A-HJKMNP-TV-Z]{25}$")
_LIMITE_ALEATORIO: Final = 1 << 80
_MEMORIA_MS: Final = 1024


def eh_ulid(valor: str) -> bool:
    """Verdadeiro se `valor` tem o formato de um ULID (Crockford, maiúsculas)."""
    return bool(_PADRAO.match(valor))


def _codificar(numero: int) -> str:
    caracteres = []
    for _ in range(26):
        caracteres.append(_ALFABETO[numero & 0x1F])
        numero >>= 5
    return "".join(reversed(caracteres))


class GeradorUlid:
    """Gerador monotônico e seguro entre threads."""

    def __init__(self, aleatorio: Callable[[int], bytes] = os.urandom) -> None:
        self._aleatorio = aleatorio
        self._trava = threading.Lock()
        # Último valor aleatório por milissegundo (só os mais recentes são lembrados).
        self._ultimos: dict[int, int] = {}

    def novo(self, em: datetime) -> str:
        if em.tzinfo is None or em.utcoffset() is None:
            raise ValueError("em deve ter fuso horário (datetime ciente de fuso)")
        ms = int(em.timestamp() * 1000)
        with self._trava:
            anterior = self._ultimos.get(ms)
            if anterior is None:
                valor = int.from_bytes(self._aleatorio(10), "big")
            else:
                valor = anterior + 1
                if valor >= _LIMITE_ALEATORIO:
                    raise OverflowError("ULIDs demais no mesmo milissegundo")
            self._ultimos[ms] = valor
            if len(self._ultimos) > _MEMORIA_MS:
                for antigo in sorted(self._ultimos)[: len(self._ultimos) - _MEMORIA_MS]:
                    del self._ultimos[antigo]
        return _codificar((ms << 80) | valor)


_GERADOR_PADRAO = GeradorUlid()


def novo_ulid(em: datetime) -> str:
    """ULID novo com o horário `em`, a partir do gerador compartilhado do processo."""
    return _GERADOR_PADRAO.novo(em)
