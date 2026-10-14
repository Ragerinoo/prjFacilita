"""Defesa em profundidade para PII (Req 18.3, 18.8).

A API deve enviar tudo já mascarado. Mesmo assim o agente mascara de novo todo texto livre
antes de montar o prompt. Se o mascaramento falhar, o agente RECUSA a requisição: nada vai ao
modelo (`ErroAgente(mascaramento)`). `mascarar_pii` é idempotente, então texto já mascarado
não muda.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from dominio.erros import ErroMascaramento
from dominio.pii import mascarar_pii

from . import erros
from .contratos import Requisicao
from .erros import ErroAgente


def mascarar_texto(texto: str) -> str:
    try:
        return mascarar_pii(texto)
    except ErroMascaramento as exc:
        raise ErroAgente(
            erros.MASCARAMENTO, "Não foi possível mascarar dados pessoais; requisição recusada."
        ) from exc


def mascarar_requisicao(req: Requisicao) -> Requisicao:
    """Mascara todo texto livre da requisição. `numero_serie` não é mascarado nem vai ao prompt."""
    pacote: dict[str, Any] | None = None
    if req.pacote is not None:
        pacote = dict(req.pacote)
        for chave in ("resumo", "categoria", "proxima_acao"):
            if chave in pacote:
                pacote[chave] = mascarar_texto(pacote[chave])
        if "ja_tentado" in pacote:
            pacote["ja_tentado"] = [
                {**item, "passo": mascarar_texto(item["passo"])} for item in pacote["ja_tentado"]
            ]
    return replace(
        req,
        mensagem=mascarar_texto(req.mensagem),
        historico=tuple({**h, "texto": mascarar_texto(h["texto"])} for h in req.historico),
        passos_registrados=tuple(
            {**p, "passo": mascarar_texto(p["passo"])} for p in req.passos_registrados
        ),
        solucoes_anteriores=tuple(
            {**s, "resumo": mascarar_texto(s["resumo"])} for s in req.solucoes_anteriores
        ),
        problemas_catalogados=tuple(
            {**p, "titulo": mascarar_texto(p["titulo"])} for p in req.problemas_catalogados
        ),
        pacote=pacote,
    )
