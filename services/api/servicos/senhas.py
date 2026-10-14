"""Hash e verificação de senha do Painel_CS (Req 13, 20.5; decisão Q14 em `premissas.py`).

Algoritmo principal: Argon2id (`argon2-cffi`, versão fixa no `pyproject.toml`) com os
parâmetros mínimos recomendados pela OWASP (m=19456 KiB, t=2, p=1). Fallback: scrypt da
biblioteca padrão (`hashlib.scrypt`, N=2^17, r=8, p=1), usado só se o `argon2-cffi` não puder
ser importado no runtime.

O texto guardado carrega o algoritmo e os parâmetros, então hashes antigos continuam
verificáveis depois de uma troca de parâmetros e `precisa_rehash` indica quando regravar:

  * Argon2id: formato PHC padrão (``$argon2id$v=19$m=19456,t=2,p=1$<sal>$<hash>``);
  * scrypt:   ``scrypt$<N>$<r>$<p>$<sal b64>$<hash b64>`` (base64 url-safe, sem preenchimento).

Nunca levanta exceção por senha errada ou hash ilegível: `verificar` devolve False. A
comparação é em tempo constante (a do Argon2 e `hmac.compare_digest` no scrypt). Este módulo não
loga nada e não guarda a senha.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
from functools import lru_cache
from typing import Final

try:  # pragma: no branch - o caminho sem argon2 é exercitado nos testes via parâmetro
    from argon2 import PasswordHasher
    from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
except ImportError:  # pragma: no cover - depende do ambiente de execução
    PasswordHasher = None  # type: ignore[assignment,misc]

    class InvalidHashError(Exception):  # type: ignore[no-redef]
        """Substituto: nunca levantado sem `argon2-cffi`."""

    class VerificationError(Exception):  # type: ignore[no-redef]
        """Substituto: nunca levantado sem `argon2-cffi`."""

    class VerifyMismatchError(VerificationError):  # type: ignore[no-redef]
        """Substituto: nunca levantado sem `argon2-cffi`."""


ALGORITMO_ARGON2ID: Final = "argon2id"
ALGORITMO_SCRYPT: Final = "scrypt"

# --- Parâmetros (mesmos valores de services/agente/premissas.py, Q14) -------------------------
ARGON2_MEMORIA_KIB: Final = 19456
ARGON2_TEMPO: Final = 2
ARGON2_PARALELISMO: Final = 1
SCRYPT_N: Final = 2**17
SCRYPT_R: Final = 8
SCRYPT_P: Final = 1
SCRYPT_TAMANHO: Final = 32
SCRYPT_SAL_BYTES: Final = 16
SCRYPT_MAXMEM_BYTES: Final = 256 * 1024 * 1024

# Limites aceitos ao LER um hash scrypt (defesa contra um item adulterado pedir memória demais).
_SCRYPT_N_MIN: Final = 2**10
_SCRYPT_N_MAX: Final = 2**18
_SCRYPT_R_MAX: Final = 16
_SCRYPT_P_MAX: Final = 4

_ARGON2: Final = (
    PasswordHasher(
        time_cost=ARGON2_TEMPO,
        memory_cost=ARGON2_MEMORIA_KIB,
        parallelism=ARGON2_PARALELISMO,
    )
    if PasswordHasher is not None
    else None
)


def argon2_disponivel() -> bool:
    return _ARGON2 is not None


def algoritmo_preferido() -> str:
    """Algoritmo usado para novos hashes neste runtime."""
    return ALGORITMO_ARGON2ID if argon2_disponivel() else ALGORITMO_SCRYPT


# --------------------------------------------------------------------------- scrypt


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).decode("ascii").rstrip("=")


def _desb64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


def _maxmem(n: int, r: int, p: int) -> int:
    return 128 * n * r + 128 * r * p + 1024 * 1024


def _scrypt_bruto(senha: str, sal: bytes, n: int, r: int, p: int, tamanho: int) -> bytes:
    return hashlib.scrypt(
        senha.encode("utf-8"),
        salt=sal,
        n=n,
        r=r,
        p=p,
        maxmem=min(SCRYPT_MAXMEM_BYTES, _maxmem(n, r, p)),
        dklen=tamanho,
    )


def _gerar_scrypt(senha: str) -> str:
    sal = secrets.token_bytes(SCRYPT_SAL_BYTES)
    derivado = _scrypt_bruto(senha, sal, SCRYPT_N, SCRYPT_R, SCRYPT_P, SCRYPT_TAMANHO)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(sal)}${_b64(derivado)}"


def _ler_scrypt(armazenado: str) -> tuple[int, int, int, bytes, bytes] | None:
    partes = armazenado.split("$")
    if len(partes) != 6 or partes[0] != ALGORITMO_SCRYPT:
        return None
    try:
        n, r, p = int(partes[1]), int(partes[2]), int(partes[3])
        sal, esperado = _desb64(partes[4]), _desb64(partes[5])
    except (ValueError, binascii.Error):
        return None
    potencia_de_dois = n > 0 and n & (n - 1) == 0
    if not (potencia_de_dois and _SCRYPT_N_MIN <= n <= _SCRYPT_N_MAX):
        return None
    if not (1 <= r <= _SCRYPT_R_MAX and 1 <= p <= _SCRYPT_P_MAX):
        return None
    if not sal or not esperado or _maxmem(n, r, p) > SCRYPT_MAXMEM_BYTES + 1024 * 1024:
        return None
    return n, r, p, sal, esperado


def _verificar_scrypt(senha: str, armazenado: str) -> bool:
    lido = _ler_scrypt(armazenado)
    if lido is None:
        return False
    n, r, p, sal, esperado = lido
    try:
        calculado = _scrypt_bruto(senha, sal, n, r, p, len(esperado))
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(calculado, esperado)


# --------------------------------------------------------------------------- API pública


def gerar_hash(senha: str, *, algoritmo: str | None = None) -> str:
    """Hash novo da senha. `algoritmo` só existe para testes e migrações; padrão = preferido."""
    escolhido = algoritmo or algoritmo_preferido()
    if escolhido == ALGORITMO_ARGON2ID:
        if _ARGON2 is None:
            raise RuntimeError("Argon2id indisponível neste runtime")
        return _ARGON2.hash(senha)
    if escolhido == ALGORITMO_SCRYPT:
        return _gerar_scrypt(senha)
    raise ValueError(f"Algoritmo de hash desconhecido: {escolhido!r}")


def verificar(senha: str, armazenado: str) -> bool:
    """True se a senha confere com o hash. Falha (senha errada, hash ilegível) devolve False."""
    try:
        if armazenado.startswith("$argon2id$"):
            if _ARGON2 is None:
                return False
            return bool(_ARGON2.verify(armazenado, senha))
        if armazenado.startswith("scrypt$"):
            return _verificar_scrypt(senha, armazenado)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False
    return False


def precisa_rehash(armazenado: str) -> bool:
    """True se o hash deve ser regravado (algoritmo não preferido, parâmetros antigos ou lixo)."""
    if armazenado.startswith("$argon2id$"):
        if _ARGON2 is None:
            return False  # não dá para gerar Argon2id aqui; mantém o hash atual
        try:
            return bool(_ARGON2.check_needs_rehash(armazenado))
        except InvalidHashError:
            return True
    if armazenado.startswith("scrypt$"):
        if argon2_disponivel():
            return True  # migra para o algoritmo principal
        lido = _ler_scrypt(armazenado)
        return lido is None or lido[:3] != (SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return True


@lru_cache(maxsize=1)
def hash_ficticio() -> str:
    """Hash descartável (algoritmo e custo atuais) para equalizar o tempo do login.

    Usado quando o usuário não existe: a verificação contra ele custa o mesmo que contra um
    hash real, então o tempo de resposta não revela se o usuário existe (Req 13.7).
    """
    return gerar_hash(secrets.token_urlsafe(24))
