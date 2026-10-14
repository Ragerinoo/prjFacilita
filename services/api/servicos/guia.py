"""Instrução do Guia_Diagnostico: resolução determinística e texto dos passos (Req 3).

Sem IA, sem relógio e sem aleatoriedade (Req 3.6): a instrução vem do catálogo por
``(modelo_id, problema_id, variante)`` e passa por `dominio.guia.resolver_instrucao` e
`validar_instrucao`. Instrução fora das regras do Req 3.3 (mais de 10 passos, texto com mais de
140 caracteres...) não é exibida: conta como inexistente e o problema vai para o log.
"""

from __future__ import annotations

from typing import Any, Final

from dominio.guia import VARIANTE_EXTERNO, VARIANTE_PADRAO, resolver_instrucao, validar_instrucao
from repositorios.interfaces import Repositorios
from servicos.catalogo import obter_instrucao

PROBLEMA_MIN: Final = 1
PROBLEMA_MAX: Final = 13  # Req 3.1


def instrucao_publica(
    repos: Repositorios, modelo_id: str | None, problema_id: int, variante: str
) -> dict[str, Any] | None:
    """A instrução no formato da API, ou `None` se não existe (ou é inválida) para o modelo.

    Não há queda para outra variante (Req 3.11): `externo` só existe para Vazamento.
    """
    if not modelo_id or not PROBLEMA_MIN <= problema_id <= PROBLEMA_MAX:
        return None
    item = obter_instrucao(repos, modelo_id, problema_id, variante)
    if item is None:
        return None
    if validar_instrucao(item.dados):
        return None
    instrucao = resolver_instrucao([item.dados], modelo_id, problema_id, variante)
    if instrucao is None:
        return None
    brutos = {p.get("n"): p for p in item.dados.get("passos", ()) if isinstance(p, dict)}
    passos: list[dict[str, Any]] = []
    for passo in instrucao.passos:
        saida: dict[str, Any] = {
            "n": passo.n,
            "texto": passo.texto,
            "alt": passo.alt,
            "texto_equivalente": passo.texto_equivalente,
        }
        if passo.midia_url:
            saida["midia_url"] = passo.midia_url
        if passo.midia_tipo:
            saida["midia_tipo"] = passo.midia_tipo
        estatica = brutos.get(passo.n, {}).get("midia_estatica_url")
        if isinstance(estatica, str) and estatica:
            saida["midia_estatica_url"] = estatica
        passos.append(saida)
    return {
        "modelo_id": modelo_id,
        "problema_id": problema_id,
        "variante": variante,
        "passos": passos,
    }


def texto_do_passo(
    repos: Repositorios,
    modelo_id: str | None,
    problema_id: int,
    passo: int,
    variante: str | None,
) -> str | None:
    """Texto do passo `passo` da instrução, para o histórico "já tentado" (Req 10.2).

    Sem `variante` informada, tenta `padrao` e depois `externo` (o evento do cliente não diz
    qual das duas o Consumidor viu). `None` se a instrução ou o passo não existem.
    """
    candidatas = (variante,) if variante else (VARIANTE_PADRAO, VARIANTE_EXTERNO)
    for candidata in candidatas:
        instrucao = instrucao_publica(repos, modelo_id, problema_id, candidata)
        if instrucao is None:
            continue
        for item in instrucao["passos"]:
            if item["n"] == passo:
                return str(item["texto"])
    return None
