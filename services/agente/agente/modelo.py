"""Chamada ao modelo de linguagem: UMA por requisição, via Strands `Agent` + `BedrockModel`.

Postura contra injeção de prompt:
  - o prompt de sistema vive no código (`prompts.py`); o texto do Consumidor e dos manuais entra
    só como DADO (JSON) na mensagem do usuário;
  - o `Agent` é criado sem ferramentas (`tools=[]`): nada de efeito colateral nem acesso a dados;
  - cada chamada usa um `Agent` novo (sem memória entre Jornadas) e sem retentativas, para que
    "uma chamada" seja exatamente uma chamada e o custo seja previsível;
  - a saída é só texto; quem a interpreta valida contra JSON Schema (`contratos.py`).

A fábrica do `Agent` é injetável: os testes passam um fake e não tocam rede nem a AWS.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import premissas

from . import erros
from .config import CONNECT_TIMEOUT_S, MODELO_READ_TIMEOUT_S
from .erros import ErroAgente


@dataclass(frozen=True)
class RespostaModelo:
    """Texto bruto do modelo e o uso de tokens da chamada (base do custo, Req 7.3)."""

    texto: str
    tokens_entrada: int
    tokens_saida: int
    modelo_id: str


class ClienteModelo(Protocol):
    def gerar(self, *, sistema: str, usuario: str) -> RespostaModelo:
        """Faz exatamente uma chamada ao modelo. Levanta `ErroAgente(modelo_indisponivel)`."""
        ...


# Fábrica do agente: (model_id, regiao, sistema, max_tokens, temperatura) -> chamável(prompt)
FabricaAgente = Callable[[str, str, str, int, float], Callable[[str], Any]]


def fabrica_agente_strands(
    modelo_id: str, regiao: str, sistema: str, max_tokens: int, temperatura: float
) -> Callable[[str], Any]:
    """Fábrica real: `strands.Agent` sobre `BedrockModel`, sem ferramentas e sem retentativa."""
    # Importações tardias: o resto do pacote (e os testes) não depende do Strands carregado.
    from botocore.config import Config
    from strands import Agent
    from strands.event_loop._retry import ModelRetryStrategy
    from strands.models import BedrockModel

    modelo = BedrockModel(
        model_id=modelo_id,
        region_name=regiao,
        max_tokens=max_tokens,
        temperature=temperatura,
        streaming=False,
        boto_client_config=Config(
            connect_timeout=CONNECT_TIMEOUT_S,
            read_timeout=MODELO_READ_TIMEOUT_S,
            retries={"max_attempts": premissas.AGENTE_MAX_TENTATIVAS, "mode": "standard"},
        ),
    )
    return Agent(
        model=modelo,
        system_prompt=sistema,
        tools=[],
        callback_handler=None,
        retry_strategy=ModelRetryStrategy(max_attempts=1),
    )


def _inteiro_nao_negativo(valor: Any) -> int:
    return valor if isinstance(valor, int) and not isinstance(valor, bool) and valor >= 0 else 0


class ClienteModeloStrands:
    """Adaptador `ClienteModelo` sobre o Strands."""

    def __init__(
        self,
        modelo_id: str,
        regiao: str,
        *,
        max_tokens: int = premissas.LLM_MAX_TOKENS_SAIDA,
        temperatura: float = premissas.LLM_TEMPERATURA,
        fabrica: FabricaAgente = fabrica_agente_strands,
    ) -> None:
        self._modelo_id = modelo_id
        self._regiao = regiao
        self._max_tokens = max_tokens
        self._temperatura = temperatura
        self._fabrica = fabrica

    def gerar(self, *, sistema: str, usuario: str) -> RespostaModelo:
        try:
            agente = self._fabrica(
                self._modelo_id, self._regiao, sistema, self._max_tokens, self._temperatura
            )
            resultado = agente(usuario)
            texto = str(resultado)
            uso = resultado.metrics.accumulated_usage
        except Exception as exc:  # throttling, acesso negado, timeout, resposta malformada
            raise ErroAgente(erros.MODELO_INDISPONIVEL, "Modelo de linguagem indisponível.") from exc
        return RespostaModelo(
            texto=texto,
            tokens_entrada=_inteiro_nao_negativo(uso.get("inputTokens")),
            tokens_saida=_inteiro_nao_negativo(uso.get("outputTokens")),
            modelo_id=self._modelo_id,
        )
