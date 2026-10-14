"""Logs estruturados em JSON, sem PII e sem corpos de mensagens (Req 18.3, 18.7, 20.5).

Regras, aplicadas em TODA linha emitida:
  * Campos cujo nome indica conteúdo sensível (corpo, mensagem, texto, telefone, cep, cpf,
    e-mail, senha, token, cookie, comentário...) nunca são gravados: o valor vira "[omitido]".
  * Valores de texto passam por `dominio.mascarar_pii` e são truncados; se o mascaramento
    falhar, o valor é omitido (nunca grava o original).
  * Estruturas (dict, lista, objetos) não são serializadas: só entra o nome do tipo.
  * Exceções entram só pelo nome da classe (`str(exc)` pode carregar dados do usuário).
Prefira passar identificadores opacos (`jornada_id`, `numero`) e contagens.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any, Final

from dominio import ErroMascaramento, mascarar_pii

OMITIDO: Final = "[omitido]"
LIMITE_TEXTO: Final = 200

# Qualquer nome de campo que CONTENHA um destes trechos é omitido.
TRECHOS_SENSIVEIS: Final[tuple[str, ...]] = (
    "corpo",
    "body",
    "mensagem",
    "message",
    "texto",
    "text",
    "pergunta",
    "resposta",
    "comentario",
    "resumo",
    "telefone",
    "phone",
    "cep",
    "cpf",
    "email",
    "senha",
    "password",
    "token",
    "cookie",
    "authorization",
    "segredo",
    "secret",
    "hash",
    "chave",
    "key",
)
# Exceções à lista acima (identificadores opacos e contagens são seguros).
CAMPOS_PERMITIDOS: Final[frozenset[str]] = frozenset(
    {"idempotency_key", "mensagens_total", "tamanho_corpo_bytes", "chave_config"}
)

# Identificadores gerados por nós (ULID, UUID, número do Chamado): o mascaramento de PII os
# estragaria (uma sequência de 8 dígitos num UUID viraria "[CEP]"). Só passam sem mascarar se
# tiverem o formato de identificador opaco e não forem puramente numéricos.
IDENTIFICADORES: Final[frozenset[str]] = frozenset(
    {"request_id", "jornada_id", "numero", "evento_id", "usuario_id"}
)
_FORMATO_ID: Final = re.compile(r"^(?=.*\D)[A-Za-z0-9_\-]{1,64}$")

_NIVEIS: Final = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "aviso": logging.WARNING,
    "erro": logging.ERROR,
}


def campo_sensivel(nome: str) -> bool:
    minusculo = nome.lower()
    if minusculo in CAMPOS_PERMITIDOS:
        return False
    return any(trecho in minusculo for trecho in TRECHOS_SENSIVEIS)


def higienizar(nome: str, valor: Any) -> Any:
    """Valor seguro para log: primitivo mascarado/truncado, ou o nome do tipo."""
    if campo_sensivel(nome):
        return OMITIDO
    if valor is None or isinstance(valor, bool | int | float):
        return valor
    if isinstance(valor, str):
        if nome in IDENTIFICADORES and _FORMATO_ID.match(valor):
            return valor
        try:
            texto = mascarar_pii(valor)
        except ErroMascaramento:
            return OMITIDO
        return texto if len(texto) <= LIMITE_TEXTO else texto[:LIMITE_TEXTO] + "…"
    if isinstance(valor, BaseException):
        return type(valor).__name__
    return f"<{type(valor).__name__}>"


def configurar_logging(nivel: str = "INFO") -> logging.Logger:
    """Ajusta o logger `tres` (o nível padrão da Lambda é WARNING, o que esconderia `info`).

    O handler da própria Lambda cuida da saída (CloudWatch); a linha já é JSON.
    """
    logger = logging.getLogger("tres")
    logger.setLevel(getattr(logging, nivel.upper(), logging.INFO))
    return logger


class Log:
    """Logger estruturado com contexto fixo (ex.: `request_id`), sem PII."""

    def __init__(
        self,
        logger: logging.Logger | None = None,
        contexto: Mapping[str, Any] | None = None,
        agora: Callable[[], datetime] | None = None,
    ) -> None:
        self._logger = logger or logging.getLogger("tres")
        self._agora = agora or (lambda: datetime.now(UTC))
        self._contexto = {k: higienizar(k, v) for k, v in (contexto or {}).items()}

    def com(self, **contexto: Any) -> Log:
        """Novo logger com mais contexto fixo."""
        mesclado = {**self._contexto, **contexto}
        return Log(self._logger, mesclado, self._agora)

    def linha(self, nivel: str, evento: str, **campos: Any) -> str:
        registro: dict[str, Any] = {
            "ts": self._agora().isoformat(timespec="milliseconds"),
            "nivel": nivel,
            "evento": evento,
            **self._contexto,
        }
        for nome, valor in campos.items():
            registro[nome] = higienizar(nome, valor)
        return json.dumps(registro, ensure_ascii=False, default=str, sort_keys=False)

    def _emitir(self, nivel: str, evento: str, campos: Mapping[str, Any]) -> None:
        if self._logger.isEnabledFor(_NIVEIS[nivel]):
            self._logger.log(_NIVEIS[nivel], self.linha(nivel, evento, **campos))

    def debug(self, evento: str, **campos: Any) -> None:
        self._emitir("debug", evento, campos)

    def info(self, evento: str, **campos: Any) -> None:
        self._emitir("info", evento, campos)

    def aviso(self, evento: str, **campos: Any) -> None:
        self._emitir("aviso", evento, campos)

    def erro(self, evento: str, **campos: Any) -> None:
        self._emitir("erro", evento, campos)
