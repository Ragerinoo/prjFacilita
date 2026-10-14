"""Lambda `varredura` (EventBridge Scheduler a cada 5 min): marca Jornadas abandonadas (Req 17.2).
Procura no `gsi_ativas` as Jornadas ativas, sem Chamado e sem interação há 30 min ou mais e as
marca ``abandonada`` (condicional e terminal). A lógica fica em `servicos.varredura`; aqui só há
a montagem das dependências por container e o orçamento de tempo da Lambda (timeout de 60 s).
Se a rodada não terminar tudo, o que sobrar continua na execução seguinte.
Variáveis de ambiente: ``TRES_MODO`` (``local`` usa fakes em memória), ``TRES_PREFIXO``
(prefixo das tabelas, padrão ``tres``) e ``TRES_LOG_NIVEL``.
O cliente do DynamoDB usa `config_cliente_curta()` (timeouts curtos, Req 20.6). A falha da
listagem sobe como exceção: o Scheduler tenta de novo e o erro aparece nas métricas da Lambda.
Falhas por item não sobem; ficam no resumo (``falhas``) e no log.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from core.contexto import agora_utc
from core.logs import Log, configurar_logging
from repositorios.interfaces import JornadasRepo
from servicos.varredura import varrer_abandonadas

_jornadas: JornadasRepo | None = None
def _obter_jornadas() -> JornadasRepo:
    """Cria (na partida a frio) e reaproveita o repositório de Jornadas."""
    global _jornadas
    if _jornadas is None:
        if os.environ.get("TRES_MODO") == "local":
            from repositorios.memoria import criar_repositorios_memoria
            _jornadas = criar_repositorios_memoria().jornadas
        else:
            from repositorios.dynamodb import (
                JornadasDynamoDB,
                config_cliente_curta,
                criar_recurso_dynamodb,
            )
            recurso = criar_recurso_dynamodb(config=config_cliente_curta())
            _jornadas = JornadasDynamoDB(recurso, os.environ.get("TRES_PREFIXO", "tres"))
    return _jornadas
def redefinir() -> None:
    """Só para testes: descarta o repositório em cache do container."""
    global _jornadas
    _jornadas = None
def _tempo_restante(contexto: Any) -> Callable[[], float] | None:
    """Segundos que restam à invocação, ou None fora da Lambda (sem corte por tempo)."""
    obter = getattr(contexto, "get_remaining_time_in_millis", None)
    if not callable(obter):
        return None
    return lambda: float(obter()) / 1000.0
def lambda_handler(evento: dict[str, Any], contexto: Any = None) -> dict[str, Any]:
    configurar_logging(os.environ.get("TRES_LOG_NIVEL", "INFO"))
    log = Log()
    try:
        jornadas = _obter_jornadas()
        return varrer_abandonadas(
            jornadas, agora_utc(), restante_s=_tempo_restante(contexto), log=log
        )
    except Exception as exc:  # noqa: BLE001 - registra e sobe para o Scheduler repetir
        log.erro("varredura_falhou", erro=exc)
        raise
