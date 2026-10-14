"""Sugestão de resposta ao Atendente (Req 15.2, 15.7; design, modo `sugestao_atendente`).

`gerar_sugestao` NUNCA levanta: qualquer falha (agente fora do ar, prazo de 10 s, saída
inválida, texto vazio, mascaramento que falha) devolve `ResultadoSugestao(texto=None)`, e a
rota responde 200 com `sugestao: null` para o Atendente redigir à mão.

Fonte da sugestão:
  * agente injetado com `definir_agente` (testes);
  * modo "aws" com ``TRES_AGENTE_RUNTIME_ARN``: `AgenteClientAgentCore`;
  * modo "local": modelo determinístico (`sugestao_local`, sem rede), a partir do Pacote;
  * modo "aws" sem ARN: sem fonte -> indisponível.

O texto sai sempre por `mascarar_pii` e é cortado em 2000 caracteres (limite da mensagem).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from dominio import mascarar_pii
from dominio.pacote import PacoteRepasse, pacote_para_dict
from dominio.validadores import MENSAGEM_ATENDENTE_MAX
from servicos.agente import (
    MODO_SUGESTAO_ATENDENTE,
    AgenteClient,
    AgenteClientAgentCore,
    PedidoAgente,
    criar_clientes_agentcore,
)

TIMEOUT_SUGESTAO_S: Final = 10.0
MENSAGEM_INDISPONIVEL: Final = "sugestão indisponível"

_injetado: AgenteClient | None = None
_cache_agentcore: dict[str, AgenteClient] = {}


def definir_agente(agente: AgenteClient | None) -> None:
    """Injeta (ou remove, com None) o agente usado pela rota. Para testes."""
    global _injetado  # noqa: PLW0603
    _injetado = agente


@dataclass(frozen=True, slots=True)
class ResultadoSugestao:
    texto: str | None
    origem: str | None = None  # "ia" | "modelo_local"


def sugestao_local(pacote: PacoteRepasse) -> str:
    """Resposta-modelo determinística (sem PII: só categoria, "já tentado" e próxima ação)."""
    tentados = [i.passo for i in pacote.ja_tentado if i.resultado != "sim"]
    if tentados:
        ja = "Vi que você já tentou: " + "; ".join(tentados[:3]) + "."
    else:
        ja = "Obrigado por nos contar o que aconteceu."
    return (
        f"Olá! Sou da equipe de atendimento. {ja} "
        f"Sobre o problema de {pacote.categoria}, o próximo passo é: {pacote.proxima_acao} "
        "Se preferir, posso agendar uma ligação. Posso ajudar com mais alguma coisa?"
    )


def _agente(modo: str) -> tuple[AgenteClient | None, str]:
    if _injetado is not None:
        return _injetado, "ia"
    if modo == "local":
        return None, "modelo_local"
    arn = os.environ.get("TRES_AGENTE_RUNTIME_ARN", "")
    if not arn:
        return None, "indisponivel"
    if arn not in _cache_agentcore:
        _cache_agentcore[arn] = AgenteClientAgentCore(arn, criar_clientes_agentcore())
    return _cache_agentcore[arn], "ia"


def gerar_sugestao(
    pacote: PacoteRepasse, jornada_id: str, modelo_id: str | None, modo: str
) -> ResultadoSugestao:
    try:
        agente, origem = _agente(modo)
        if origem == "indisponivel":
            return ResultadoSugestao(None)
        if agente is None:
            texto = sugestao_local(pacote)
        else:
            pedido = PedidoAgente(
                jornada_id=jornada_id,
                modelo_id=modelo_id,
                numero_serie=pacote.numero_serie,
                pacote=pacote_para_dict(pacote),
            ).mascarado()
            texto = agente.sugestao_atendente(pedido, timeout_s=TIMEOUT_SUGESTAO_S).sugestao
        texto = mascarar_pii((texto or "").strip())[:MENSAGEM_ATENDENTE_MAX].strip()
        return ResultadoSugestao(texto or None, origem if texto else None)
    except Exception:  # noqa: BLE001 - a sugestão nunca bloqueia o Atendente (Req 15.7)
        return ResultadoSugestao(None)
