"""Rota do Painel_CS de métricas simples (Req 9.1, 9.8, 9.11, 9.12, 9.15). Somente Gestor.

``GET /api/cs/metricas`` -> 200 | 401 | 403
    ``{"totais": {"abertos", "encerrados"},
    "por_problema" | "por_modelo" | "por_prioridade" | "por_desfecho":
    [{"chave", "rotulo", "quantidade"}]}``. Só contagens: sem telefone, CEP, texto de mensagens
    nem resumo do Pacote. As contagens vêm dos Chamados e Jornadas presentes nos repositórios
    (inclusive os recarregados do snapshot da demo). `listar_todos` só existe no Modo_Local; no
    adaptador DynamoDB ele levanta `ErroIndisponivelForaDoModoLocal` (subclasse de
    `ErroRepositorio`) e a API responde 500 genérico, como nas demais rotas.

Autorização: `Rota.perfis` fica `None`, então a matriz (`servicos/autorizacao.py`) classifica
``("GET", "/metricas")`` como exclusiva do perfil `gestor`. O decorator repete a regra como defesa
em profundidade.
"""

from __future__ import annotations

from typing import Any

from core.contexto import Contexto
from core.roteador import Rota
from repositorios.erros import ErroRepositorio
from repositorios.modelos import Jornada
from servicos.autorizacao import exigir_perfil
from servicos.metricas_chamados import calcular_metricas


@exigir_perfil("gestor")
def metricas(ctx: Contexto) -> dict[str, Any]:
    # Cache por requisição: vários Chamados da mesma Jornada leem o repositório uma vez só.
    jornadas: dict[str, Jornada | None] = {}

    def jornada(jornada_id: str) -> Jornada | None:
        if jornada_id not in jornadas:
            jornadas[jornada_id] = ctx.repos.jornadas.obter(jornada_id)
        return jornadas[jornada_id]

    try:
        titulos = {p.problema_id: p.titulo for p in ctx.repos.catalogo.listar_problemas()}
    except ErroRepositorio as exc:  # catálogo indisponível não derruba as contagens
        ctx.log.aviso("catalogo_indisponivel_metricas", erro=exc)
        titulos = {}

    return calcular_metricas(ctx.repos.chamados.listar_todos(), jornada, titulos)


ROTAS = [Rota("GET", "/metricas", metricas, escopo="cs", nome="cs_metricas")]
