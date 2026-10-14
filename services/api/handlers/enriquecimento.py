"""Lambda `enriquecimento` (assíncrona): resumo, sentimento e próxima ação do Pacote_Repasse.

Disparada por `ServicoEscalada` com `InvocationType="Event"` e o evento ``{"numero": "TRES-..."}``
(`servicos.enriquecimento.DisparadorLambda`). Pede ao agente o modo `resumo_repasse` e grava
o resultado, ou o fallback do Req 10.4, no Chamado. A lógica fica em
`servicos.enriquecimento`; aqui há só a composição por container e o orçamento de tempo.

Orçamento de 15 s (Req 10.8; timeout da Lambda definido em `infra/stacks/api_stack.py`):

  leituras (Chamado, Jornada, eventos)     poucos ms
  agente                                   até 10 s (`min(10, restante - 4)`)
  gravação (`atualizar_campos_ia`)         reserva de 4 s (DynamoDB: 0,5 s + 1 s, 2 tentativas)

O Pacote já está disponível ao Painel desde a criação do Chamado (valores provisórios iguais ao
fallback), então até uma falha total desta Lambda mantém o requisito.

Variáveis de ambiente: ``TRES_MODO`` (``local``: repositórios em memória e agente fake),
``TRES_PREFIXO`` (tabelas, padrão ``tres``), ``TRES_AGENTE_RUNTIME_ARN`` (ARN do runtime; sem
ele, e fora do modo local, todo evento cai no fallback), ``TRES_LOG_NIVEL``.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from botocore.config import Config

from core.logs import Log, configurar_logging
from repositorios.interfaces import Repositorios
from servicos.agente import (
    AgenteClient,
    AgenteClientAgentCore,
    AgenteClientFake,
    ErroAgente,
    Modo,
    criar_clientes_agentcore,
)
from servicos.enriquecimento import (
    ENRIQUECIMENTO_TIMEOUT_S,
    PADRAO_NUMERO,
    RESERVA_GRAVACAO_S,
    enriquecer_pacote,
)

# Cliente DynamoDB: pior caso por chamada = 2 x (0,5 + 1) + 1 = 4 s = RESERVA_GRAVACAO_S.
_CONFIG_DYNAMODB: Final = Config(
    connect_timeout=0.5,
    read_timeout=1,
    retries={"total_max_attempts": 2, "mode": "standard"},
)


@dataclass(frozen=True, slots=True)
class Composicao:
    repos: Repositorios
    agente: AgenteClient


_composicao: Composicao | None = None


def montar(ambiente: Mapping[str, str]) -> Composicao:
    """Monta as dependências do ambiente (uma vez por container)."""
    if ambiente.get("TRES_MODO") == "local":
        from repositorios.memoria import criar_repositorios_memoria

        return Composicao(criar_repositorios_memoria(), AgenteClientFake())

    from repositorios.dynamodb import criar_recurso_dynamodb, criar_repositorios_dynamodb

    repos = criar_repositorios_dynamodb(
        criar_recurso_dynamodb(config=_CONFIG_DYNAMODB), prefixo=ambiente.get("TRES_PREFIXO", "tres")
    )
    arn = ambiente.get("TRES_AGENTE_RUNTIME_ARN", "")
    agente: AgenteClient = (
        AgenteClientAgentCore(arn, criar_clientes_agentcore()) if arn else _AgenteIndisponivel()
    )
    return Composicao(repos, agente)


class _AgenteIndisponivel:
    """Sem runtime configurado: toda chamada falha e o Chamado fica com o fallback."""

    def _falhar(self, modo: Modo) -> Any:
        raise ErroAgente(modo, "TRES_AGENTE_RUNTIME_ARN não configurado")

    def responder(self, pedido: Any, *, timeout_s: float | None = None) -> Any:
        return self._falhar("responder")

    def resumo_repasse(self, pedido: Any, *, timeout_s: float | None = None) -> Any:
        return self._falhar("resumo_repasse")

    def sugestao_atendente(self, pedido: Any, *, timeout_s: float | None = None) -> Any:
        return self._falhar("sugestao_atendente")


def _obter() -> Composicao:
    global _composicao
    if _composicao is None:
        _composicao = montar(os.environ)
    return _composicao


def redefinir(composicao: Composicao | None = None) -> None:
    """Só para testes: troca (ou descarta) a composição do container."""
    global _composicao
    _composicao = composicao


def orcamento_do_agente_s(contexto: Any) -> float:
    """Tempo para o agente: `min(10, restante - reserva de gravação)`; 10 s sem contexto."""
    restante_ms = getattr(contexto, "get_remaining_time_in_millis", None)
    if not callable(restante_ms):
        return ENRIQUECIMENTO_TIMEOUT_S
    restante_s = float(restante_ms()) / 1000.0
    return max(0.0, min(ENRIQUECIMENTO_TIMEOUT_S, restante_s - RESERVA_GRAVACAO_S))


def lambda_handler(evento: dict[str, Any], contexto: Any = None) -> dict[str, Any]:
    configurar_logging(os.environ.get("TRES_LOG_NIVEL", "INFO"))
    log = Log()
    numero = evento.get("numero") if isinstance(evento, dict) else None
    if not isinstance(numero, str) or not PADRAO_NUMERO.match(numero):
        log.aviso("enriquecimento_evento_invalido")
        return {"status": "evento_invalido"}
    try:
        composicao = _obter()
        resultado = enriquecer_pacote(
            numero,
            composicao.repos,
            composicao.agente,
            orcamento_agente_s=orcamento_do_agente_s(contexto),
            log=log,
        )
    except Exception as exc:
        # Falha de infraestrutura (DynamoDB): o Pacote provisório segue válido (Req 10.4).
        # Sobe para aparecer nas métricas de erro da Lambda; não há retentativa (infra).
        log.erro("enriquecimento_falhou", numero=numero, erro=exc)
        raise
    return resultado.para_dict()
