"""Rotas públicas do catálogo: `GET /modelos` e `GET /modelos/{modelo_id}` (Req 1, 2, 3, 4).

Respostas (contrato do front-end, `apps/web/src/api/catalogo.ts` e `maquina.ts`):

    GET /modelos             -> {"modelos": [{modelo_id, nome, foto_url?, ativo}]}
    GET /modelos/{modelo_id} -> {"modelo": {modelo_id, nome, foto_url?},
                                 "problemas": [{problema_id, ordem, titulo, icone, icone_alt}],
                                 "seletor": <mapa do Seletor_Visual> | null}

A lista traz só modelos ativos, em ordem alfabética (Req 2.1). Modelo inexistente, inativo ou
com id ilegível responde 404 ``nao_encontrado`` (o QR de modelo desconhecido, Req 1.4). Se o
catálogo não responde em 5 s, 504 ``tempo_esgotado`` (Req 1.7). São dados públicos e iguais para
todos, então a resposta pode ficar em cache de borda por pouco tempo.
"""

from __future__ import annotations

from typing import Any

from core.contexto import Contexto
from core.erros import nao_encontrado
from core.http import Resposta
from core.roteador import Rota
from repositorios.catalogo import ModeloCatalogo
from servicos.catalogo import carregar_pagina_maquina, listar_modelos_ativos

CACHE_BORDA = {"Cache-Control": "public, max-age=60"}


def _modelo_publico(modelo: ModeloCatalogo, *, com_ativo: bool = False) -> dict[str, Any]:
    publico: dict[str, Any] = {"modelo_id": modelo.modelo_id, "nome": modelo.nome}
    if modelo.foto_url:
        publico["foto_url"] = modelo.foto_url
    if com_ativo:
        publico["ativo"] = modelo.ativo
    return publico


def listar_modelos(ctx: Contexto) -> Resposta:
    modelos = listar_modelos_ativos(ctx.repos)
    corpo = {"modelos": [_modelo_publico(m, com_ativo=True) for m in modelos]}
    return Resposta.ok(corpo, **CACHE_BORDA)


def obter_modelo(ctx: Contexto) -> Resposta:
    encontrado = carregar_pagina_maquina(ctx.repos, ctx.req.params.get("modelo_id"))
    if encontrado is None:
        raise nao_encontrado("Modelo não encontrado.")
    modelo, problemas = encontrado
    corpo = {
        "modelo": _modelo_publico(modelo),
        "problemas": [
            {
                "problema_id": p.problema_id,
                "ordem": p.ordem,
                "titulo": p.titulo,
                "icone": p.icone,
                "icone_alt": p.icone_alt,
            }
            for p in problemas
        ],
        "seletor": modelo.seletor,
    }
    return Resposta.ok(corpo, **CACHE_BORDA)


ROTAS = [
    Rota("GET", "/modelos", listar_modelos, escopo="pub", nome="listar_modelos"),
    Rota("GET", "/modelos/{modelo_id}", obter_modelo, escopo="pub", nome="obter_modelo"),
]
