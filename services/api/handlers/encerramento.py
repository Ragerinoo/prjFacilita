"""Lambda `encerramento` (consumidora da fila SQS de encerramentos, Req 17.1 e 17.12).

Recebe 1 mensagem por invocação (``batch_size=1``) e grava o `encerramento` na Jornada via
`JornadasRepo.encerrar` (idempotente, condição `estado <> encerrada`). Falha de uma mensagem
sai em ``batchItemFailures``: o SQS a reentrega após a visibilidade (cerca de 10 s), no máximo 3
recebimentos, e depois a envia à DLQ, que o Painel_Metricas exibe como falha de registro.
A lógica fica em `servicos.encerramento`; aqui só há a montagem das dependências por container.

Variáveis de ambiente: ``TRES_MODO`` (``local`` usa fakes em memória), ``TRES_PREFIXO``
(prefixo das tabelas, padrão ``tres``) e ``TRES_LOG_NIVEL``.
"""

from __future__ import annotations

import os
from typing import Any

from botocore.config import Config

from core.logs import Log, configurar_logging
from repositorios.interfaces import JornadasRepo
from servicos.encerramento import processar_lote

# O timeout da função é 8 s (menor que a visibilidade de 10 s da fila): o cliente do DynamoDB
# precisa caber nisso. Pior caso por chamada: 2 x (1 + 2) s + espera < 8 s.
_CONFIG_DYNAMODB = Config(
    connect_timeout=1,
    read_timeout=2,
    retries={"total_max_attempts": 2, "mode": "standard"},
)

_jornadas: JornadasRepo | None = None


def _obter_jornadas() -> JornadasRepo:
    """Cria (na partida a frio) e reaproveita o repositório de Jornadas."""
    global _jornadas
    if _jornadas is None:
        if os.environ.get("TRES_MODO") == "local":
            from repositorios.memoria import criar_repositorios_memoria

            _jornadas = criar_repositorios_memoria().jornadas
        else:
            from repositorios.dynamodb import JornadasDynamoDB, criar_recurso_dynamodb

            recurso = criar_recurso_dynamodb(config=_CONFIG_DYNAMODB)
            _jornadas = JornadasDynamoDB(recurso, os.environ.get("TRES_PREFIXO", "tres"))
    return _jornadas


def redefinir() -> None:
    """Só para testes: descarta o repositório em cache do container."""
    global _jornadas
    _jornadas = None


def lambda_handler(evento: dict[str, Any], contexto: Any = None) -> dict[str, Any]:
    configurar_logging(os.environ.get("TRES_LOG_NIVEL", "INFO"))
    log = Log()
    try:
        jornadas = _obter_jornadas()
    except Exception as exc:  # noqa: BLE001 - sem repositório, todas as mensagens voltam à fila
        log.erro("encerramento_sem_repositorio", erro=exc)
        raise
    return processar_lote(evento, jornadas, log)
