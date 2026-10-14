"""Rota do Dashboard do Painel_CS (Req 21, 22, 23). Gestor e Atendente.
``GET /api/cs/dashboard`` -> 200 | 401 | 403
    ``{"modo_local", "gerado_em", "visao_geral", "em_foco"}`` (conjunto fechado de chaves):
    - ``visao_geral``: ``abertos``, ``em_atendimento``, ``encerrados``, ``p1_risco_abertos``,
      ``sem_responsavel``, ``respostas_nao_lidas`` (inteiros; repositório vazio dá zeros);
    - ``em_foco``: ``total``, ``limite`` (10) e ``itens`` (no máximo 10), cada item com
      ``numero``, ``prioridade``, ``status``, ``modelo``, ``problema``, ``idade_min``, ``risco``,
      ``sem_responsavel``, ``resposta_nao_lida``, ``parado`` e ``motivos``.
    Nunca saem: ``jornada_id``, nome ou usuário do responsável, telefone, CEP, texto de
    mensagens, resumo do Pacote, anexos e encerramento. O número do Chamado sai.
    O relógio é lido uma só vez (`gerado_em` e as idades usam o mesmo instante). Os Chamados vêm
    de ``listar_todos`` (uma vez) e cada Jornada é lida uma vez por requisição. Qualquer
    ``ErroRepositorio`` (inclusive ``ErroIndisponivelForaDoModoLocal``, pois ``listar_todos`` só
    existe no Modo_Local) sobe sem captura e vira erro 5xx, sem dados parciais. Só a falha do
    catálogo é tolerada: os títulos ficam vazios e o problema aparece como "Problema <id>".
Autorização: a rota declara ``Rota.perfis = {gestor, atendente}``, que tem precedência sobre a
matriz (`servicos/autorizacao.py`); a ``MATRIZ`` não é editada. O decorator repete a regra como
defesa em profundidade. A ``/api/cs/metricas`` continua exclusiva do Gestor.
"""
from __future__ import annotations
from typing import Any
from core.app import MODO_LOCAL
from core.contexto import Contexto
from core.roteador import Rota
from repositorios.erros import ErroRepositorio
from repositorios.modelos import Jornada
from servicos.autorizacao import exigir_perfil
from servicos.dashboard import ChamadoDashboard, montar_dashboard
@exigir_perfil("gestor", "atendente")
def dashboard(ctx: Contexto) -> dict[str, Any]:
    agora = ctx.app.agora()  # uma única leitura do relógio
    chamados = ctx.repos.chamados.listar_todos()  # ErroRepositorio sobe: 5xx, sem dados parciais
    # Cache por requisição: vários Chamados da mesma Jornada leem o repositório uma vez só.
    jornadas: dict[str, Jornada | None] = {}
    def jornada(jornada_id: str) -> Jornada | None:
        if jornada_id not in jornadas:
            jornadas[jornada_id] = ctx.repos.jornadas.obter(jornada_id)
        return jornadas[jornada_id]
    try:
        titulos = {p.problema_id: p.titulo for p in ctx.repos.catalogo.listar_problemas()}
    except ErroRepositorio as exc:  # catálogo indisponível não derruba o Dashboard
        ctx.log.aviso("catalogo_indisponivel_dashboard", erro=exc)
        titulos = {}
    return montar_dashboard(
        agora,
        modo_local=ctx.app.modo == MODO_LOCAL,
        titulos=titulos,
        chamados=[ChamadoDashboard.de(c, jornada(c.jornada_id)) for c in chamados],
    )
ROTAS = [
    Rota(
        "GET",
        "/dashboard",
        dashboard,
        escopo="cs",
        nome="cs_dashboard",
        perfis=frozenset({"gestor", "atendente"}),
    )
]
