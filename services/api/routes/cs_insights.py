"""Rota do Painel_CS de Insights do Gestor (Req 1, 2, 7.10, 8, 11). Somente Gestor.

``GET /api/cs/insights?periodo=hoje|7d|30d|personalizado[&inicio=AAAA-MM-DD&fim=AAAA-MM-DD]``
-> 200 | 400 | 401 | 403 | 5xx
    Resposta fechada de 9 chaves: ``periodo``, ``modo_local``, ``satisfacao``, ``comentarios``,
    ``atendimento``, ``desfecho``, ``p1_risco``, ``ranking_problemas`` e ``funil`` (ver
    ``servicos/insights.py``). Decimais saem como texto e ``"sem dados"`` ocupa o lugar do número
    quando o denominador é zero. Nunca saem ``jornada_id``, número de Chamado, telefone, CEP,
    texto de mensagem, resumo do Pacote nem custo.

Período (datas em UTC, intervalo semiaberto ``[inicio, fim)``): ``periodo`` ausente vale ``7d``.
``inicio`` e ``fim`` só valem em ``personalizado`` (no máximo 90 dias inclusivos) e são
ignorados nos demais. Período inválido responde 400 com ``erro.campos`` apontando ``periodo``,
``inicio`` ou ``fim``. O relógio é lido uma só vez (``ctx.app.agora()``).

Leituras obrigatórias, sem captura de erro: ``chamados.listar_todos`` (uma vez),
``jornadas.obter`` (uma vez por Jornada e só dos Chamados que interessam ao período),
``avaliacoes.listar_periodo`` e ``agregados.listar``. Qualquer ``ErroRepositorio`` (inclusive
``ErroIndisponivelForaDoModoLocal``, pois ``listar_todos`` só existe no Modo_Local) sobe e vira
erro 5xx (502 ``dependencia_indisponivel`` no pipeline atual; exceção inesperada vira 500),
sem indicadores parciais.

Leituras opcionais, com degradação: ``catalogo.listar_problemas`` (falha: títulos vazios e aviso
``catalogo_indisponivel_insights``) e ``jornadas.listar_encerradas`` (falha: ``funil`` vira
``null`` e aviso ``funil_indisponivel_insights``). Nenhum método novo foi criado nos Protocols.

Autorização: a rota declara ``Rota.perfis = {gestor}``, que tem precedência sobre a matriz
(`servicos/autorizacao.py`); a ``MATRIZ`` não é editada. O decorator repete a regra como defesa
em profundidade.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from core.app import MODO_LOCAL
from core.contexto import Contexto
from core.erros import VALIDACAO, ErroApi
from core.roteador import Rota
from dominio import ErroCampo
from repositorios.erros import ErroRepositorio
from repositorios.modelos import Jornada
from servicos.autorizacao import exigir_perfil
from servicos.insights import (
    ChamadoInsights,
    ErroPeriodoInsights,
    JornadaInsights,
    PeriodoInsights,
    montar_insights,
    resolver_periodo,
)


def _no_periodo(periodo: PeriodoInsights, instante: Any) -> bool:
    return instante is not None and periodo.inicio <= instante < periodo.fim


@exigir_perfil("gestor")
def insights(ctx: Contexto) -> dict[str, Any]:
    agora = ctx.app.agora()  # uma única leitura do relógio
    consulta = ctx.req.consulta
    try:
        periodo = resolver_periodo(
            agora, consulta.get("periodo"), consulta.get("inicio"), consulta.get("fim")
        )
    except ErroPeriodoInsights as exc:
        raise ErroApi(
            400, VALIDACAO, "Período inválido.", [ErroCampo(exc.campo, exc.motivo)]
        ) from exc

    # Leituras obrigatórias: ErroRepositorio sobe (5xx), sem indicadores parciais.
    chamados = ctx.repos.chamados.listar_todos()
    avaliacoes = ctx.repos.avaliacoes.listar_periodo(periodo.inicio, periodo.fim)
    # Contadores diários cobrem dias inteiros: do dia de `inicio` ao dia do último instante.
    agregados = ctx.repos.agregados.listar(
        periodo.inicio.date(), (periodo.fim - timedelta(microseconds=1)).date()
    )

    # Cache por requisição; só os Chamados criados ou encerrados no período leem a Jornada.
    jornadas: dict[str, Jornada | None] = {}

    def jornada(jornada_id: str) -> Jornada | None:
        if jornada_id not in jornadas:
            jornadas[jornada_id] = ctx.repos.jornadas.obter(jornada_id)
        return jornadas[jornada_id]

    projecoes: list[ChamadoInsights] = []
    for c in chamados:
        interessa = _no_periodo(periodo, c.criado_em) or (
            c.encerramento is not None and _no_periodo(periodo, c.encerramento.em)
        )
        projecoes.append(ChamadoInsights.de(c, jornada(c.jornada_id) if interessa else None))

    try:
        titulos = {p.problema_id: p.titulo for p in ctx.repos.catalogo.listar_problemas()}
    except ErroRepositorio as exc:  # catálogo indisponível não derruba os Insights
        ctx.log.aviso("catalogo_indisponivel_insights", erro=exc)
        titulos = {}

    funil: list[JornadaInsights] | None
    try:
        encerradas = ctx.repos.jornadas.listar_encerradas(periodo.inicio, periodo.fim)
        funil = [p for j in encerradas if (p := JornadaInsights.de(j)) is not None]
    except ErroRepositorio as exc:  # sem as Jornadas encerradas, só o funil some
        ctx.log.aviso("funil_indisponivel_insights", erro=exc)
        funil = None

    return montar_insights(
        periodo,
        modo_local=ctx.app.modo == MODO_LOCAL,
        chamados=projecoes,
        avaliacoes=avaliacoes,
        agregados=agregados,
        titulos=titulos,
        jornadas_encerradas=funil,
    )


ROTAS = [
    Rota(
        "GET",
        "/insights",
        insights,
        escopo="cs",
        nome="cs_insights",
        perfis=frozenset({"gestor"}),
    )
]
