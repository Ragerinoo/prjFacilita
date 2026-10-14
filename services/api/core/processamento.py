"""Processa um evento do API Gateway: roteia, trata erros e devolve o envelope padrão.

Mapeamento de falhas (sem vazar detalhes internos nem dados do usuário):
  ErroApi                   -> o status e o código do próprio erro
  repositorios.ErroNaoEncontrado -> 404 ``nao_encontrado``
  repositorios.ErroRepositorio   -> 502 ``dependencia_indisponivel``
  TimeoutError              -> 504 ``tempo_esgotado``
  qualquer outra exceção    -> 500 ``erro_interno`` (log só com o nome da classe)
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any

from core import erros
from core.contexto import Aplicacao, Contexto
from core.http import Requisicao, Resposta, de_evento_v2, para_evento_v2
from core.roteador import Roteador
from repositorios import ErroNaoEncontrado, ErroRepositorio


def _resposta_de_excecao(exc: Exception) -> tuple[Resposta, str]:
    """Resposta de erro e o nível de log ('aviso' para erro do cliente, 'erro' para falha)."""
    if isinstance(exc, erros.ErroApi):
        return Resposta.de_erro(exc), "aviso" if exc.status < 500 else "erro"
    if isinstance(exc, ErroNaoEncontrado):
        return Resposta.de_erro(erros.nao_encontrado()), "aviso"
    if isinstance(exc, ErroRepositorio):
        return Resposta.de_erro(erros.dependencia_indisponivel()), "erro"
    if isinstance(exc, TimeoutError):
        return Resposta.de_erro(erros.tempo_esgotado()), "erro"
    return (
        Resposta.de_erro(
            erros.ErroApi(500, erros.ERRO_INTERNO, "Algo deu errado. Tente de novo em instantes.")
        ),
        "erro",
    )


def processar(app: Aplicacao, roteador: Roteador, evento: Mapping[str, Any]) -> dict[str, Any]:
    """Nunca levanta: sempre devolve uma resposta no formato do payload v2."""
    inicio = time.perf_counter()
    requisicao: Requisicao | None = None
    log = app.log
    try:
        requisicao = de_evento_v2(evento)
        log = app.log.com(request_id=requisicao.request_id)
        resposta = roteador.despachar(Contexto(req=requisicao, app=app, log=log))
        nivel, status, codigo = "info", resposta.status, None
    except Exception as exc:  # noqa: BLE001 - fronteira da Lambda: tudo vira resposta
        resposta, nivel = _resposta_de_excecao(exc)
        status = resposta.status
        codigo = resposta.corpo["erro"]["codigo"]
        # Só o nome da classe: `str(exc)` pode carregar dados do usuário.
        log = log.com(excecao=type(exc).__name__)
    getattr(log, nivel)(
        "requisicao",
        metodo=requisicao.metodo if requisicao else None,
        caminho=requisicao.caminho if requisicao else None,
        status=status,
        codigo=codigo,
        duracao_ms=round((time.perf_counter() - inicio) * 1000, 1),
    )
    return para_evento_v2(resposta)
