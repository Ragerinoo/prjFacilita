"""Rota pública do Seletor_Visual (Req 4.2, 4.3, 4.4, 4.6).

``POST /jornadas/{id}/seletor/resolver`` ``{area, estado}`` (o caminho é o do contrato do design
e do API Gateway em ``infra/stacks/api_stack.py``).

Entrada: ``area`` e ``estado`` são os identificadores do mapa do modelo da Jornada
(``seed/seletor/<modelo_id>.json``: ``areas[].area`` e ``areas[].estados[].estado``). Área
desconhecida ou estado que não pertence à área são 422 com ``campos`` (``area`` / ``estado``).

Resposta 200 (contrato para o componente do front-end, tarefa 21.2)::

    {"resultado": "unico" | "multiplos" | "nenhum",
     "area": "luz_alerta", "estado": "piscando",
     "problemas": [{"problema_id": 3, "titulo": "...", "ordem": 3}],
     "jornada": <envelope da Jornada>}

  * ``unico``: ``problemas`` tem 1 item; o cliente abre a instrução dele (Req 4.3).
  * ``multiplos``: de 2 a 5 itens, na ordem do catálogo (``ordem``); o Consumidor escolhe (Req 4.6).
  * ``nenhum``: ``problemas`` vazio; o cliente leva ao Assistente_IA com área e estado
    preservados (Req 4.4). A seleção já está registrada na Jornada (``seletor_area`` e
    ``seletor_estado``) e é exibida ao assistente e ao Pacote.

``titulo`` e ``ordem`` vêm do catálogo de Problemas_Catalogados. Um problema do mapa que não
existe no catálogo é descartado e o ``resultado`` é calculado sobre o que sobrou.

Erros: 404 se a Jornada não existe, se não tem modelo ou se o modelo não tem mapa (o cliente
mostra a indisponibilidade com acesso ao assistente, Req 4.8); 409 se a Jornada já foi
encerrada (Req 17.2); 422 para corpo inválido.

Idempotência: com ``Idempotency-Key`` (ou ``evento_id`` no corpo) o reenvio devolve 200 com a
mesma resposta e não repete o registro nem a contagem de interação.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from core.contexto import Contexto
from core.erros import conflito, nao_encontrado, validacao
from core.http import Resposta
from core.roteador import Rota
from core.validacao import Validador, exigir_objeto
from dominio import ErroCampo
from dominio.seletor import resolver_seletor
from repositorios.catalogo import ProblemaCatalogo
from repositorios.modelos import Jornada
from servicos.catalogo import carregar_pagina_maquina
from servicos.envelope_jornada import envelope_jornada

TAMANHO_MAX_ID: Final = 64
INDISPONIVEL: Final = "O seletor visual não está disponível para esta máquina."


def _estados_por_area(mapa: Mapping[str, Any]) -> dict[str, set[str]]:
    """``{area: {estados}}`` do mapa, ignorando entradas malformadas."""
    resultado: dict[str, set[str]] = {}
    areas = mapa.get("areas")
    if not isinstance(areas, (list, tuple)):
        return resultado
    for area in areas:
        if not isinstance(area, Mapping) or not isinstance(area.get("area"), str):
            continue
        estados = area.get("estados")
        ids = {
            e["estado"]
            for e in (estados if isinstance(estados, (list, tuple)) else ())
            if isinstance(e, Mapping) and isinstance(e.get("estado"), str)
        }
        resultado.setdefault(area["area"], set()).update(ids)
    return resultado


def _problemas_do_resultado(
    ids: tuple[int | str, ...], catalogo: list[ProblemaCatalogo]
) -> list[dict[str, Any]]:
    por_id = {p.problema_id: p for p in catalogo}
    encontrados: list[ProblemaCatalogo] = []
    for bruto in ids:
        try:
            problema = por_id.get(int(bruto))
        except (TypeError, ValueError):
            problema = None
        if problema is not None and problema not in encontrados:
            encontrados.append(problema)
    encontrados.sort(key=lambda p: (p.ordem, p.problema_id))
    return [
        {"problema_id": p.problema_id, "titulo": p.titulo, "ordem": p.ordem} for p in encontrados
    ]


def _jornada_ou_404(ctx: Contexto) -> Jornada:
    jornada = ctx.repos.jornadas.obter(ctx.req.params["id"])
    if jornada is None:
        raise nao_encontrado("Jornada não encontrada.")
    return jornada


def resolver(ctx: Contexto) -> Resposta:
    corpo = exigir_objeto(ctx.json())
    validador = Validador(corpo)
    area = validador.texto("area", maximo=TAMANHO_MAX_ID)
    estado = validador.texto("estado", maximo=TAMANHO_MAX_ID)
    validador.levantar_se_erros()
    assert area is not None and estado is not None

    jornada = _jornada_ou_404(ctx)
    if jornada.estado == "encerrada":
        raise conflito("Esta jornada já foi encerrada.")
    pagina = carregar_pagina_maquina(ctx.repos, jornada.modelo_id)
    if pagina is None or not pagina[0].seletor:
        raise nao_encontrado(INDISPONIVEL)
    modelo, catalogo = pagina
    mapa = modelo.seletor
    assert mapa is not None

    estados_por_area = _estados_por_area(mapa)
    erros: list[ErroCampo] = []
    if area not in estados_por_area:
        erros.append(ErroCampo("area", "área inexistente no mapa deste modelo"))
    elif estado not in estados_por_area[area]:
        erros.append(ErroCampo("estado", "estado inexistente nesta área"))
    if erros:
        raise validacao(erros)

    resolucao = resolver_seletor(mapa, area, estado)
    problemas = _problemas_do_resultado(resolucao.problemas, catalogo)
    resultado = "nenhum" if not problemas else "unico" if len(problemas) == 1 else "multiplos"

    atual = jornada
    if ctx.primeira_vez(f"seletor:{jornada.jornada_id}", corpo):
        ctx.repos.jornadas.registrar_seletor(jornada.jornada_id, area, estado)
        atual = ctx.repos.jornadas.registrar_interacao(jornada.jornada_id, ctx.app.agora())
        ctx.log.info(
            "seletor_resolvido",
            jornada_id=jornada.jornada_id,
            resultado=resultado,
            area=area,
            estado=estado,
        )
    return Resposta.ok(
        {
            "resultado": resultado,
            "area": area,
            "estado": estado,
            "problemas": problemas,
            "jornada": envelope_jornada(atual),
        }
    )


ROTAS = [
    Rota(
        "POST", "/jornadas/{id}/seletor/resolver", resolver, escopo="pub", nome="resolver_seletor"
    ),
]
