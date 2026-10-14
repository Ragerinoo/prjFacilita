"""Rotas do Painel_CS: fila, card do Chamado, assumir, Dados_Pessoais e anexos (Req 14.1 a 14.7,
18.6, 18.9). Todas exigem sessão (perfis atendente ou gestor, ver `servicos/autorizacao.py`).

Formas das respostas (consumidas pelo front-end do Painel, tarefas 15.2 a 15.4)
==============================================================================

``GET /api/cs/fila`` -> 200
    ``{"itens": [{"numero", "prioridade": "P1|P2|P3", "classificacao", "status",
    "responsavel": {"usuario", "nome"} | null, "tempo_espera_s": int, "criado_em": ISO-8601,
    "alerta_p1": bool, "alerta_p1_visto": bool, "resposta_nao_lida": bool, "resumo": str}]}``
    Ordem: prioridade, horário de criação, número (ChamadosRepo.listar_fila). ``alerta_p1`` é
    verdadeiro enquanto o Chamado é P1 e ninguém o abriu. SEM Dados_Pessoais; ``resumo`` é o
    resumo do Pacote, mascarado e cortado em 140 caracteres.

``GET /api/cs/chamados/{numero}`` -> 200 | 404
    Card: ``{"numero", "jornada_id", "status", "prioridade", "classificacao", "canal",
    "criado_em", "responsavel", "alerta_p1_visto", "resposta_nao_lida", "os_status",
    "agendamento": ISO | null, "pacote_ia_status", "decisao_criterio",
    "pacote": <pacote_para_dict>, "anexos": [{"indice", "mime", "bytes"}],
    "encerramento": {...} | null,
    "mensagens": [{"ts_ulid", "autor", "texto", "em", "lida"}],
    "historico": [{"evento_id", "tipo", "em", "dados"}]}``
    O resumo/Pacote aparece no topo (campo ``pacote``) e o histórico vem em ordem cronológica.
    Textos de mensagens e dados de eventos passam por ``mascarar_pii``. SEM telefone/CEP.
    EFEITO COLATERAL (decisão): abrir o card de um Chamado P1 grava ``alerta_p1_visto`` (o
    alerta da fila some para todos); é idempotente e a falha em gravar não impede o card.

``POST /api/cs/chamados/{numero}/assumir`` -> 200 (Chamado + responsável) | 404 | 409
    Condicional: só o primeiro vence. O 409 traz ``responsavel`` (nome do vencedor) ao lado de
    ``erro``. Chamado encerrado também responde 409 (``chamado_encerrado``).

``GET /api/cs/chamados/{numero}/dados-pessoais`` -> 200 | 403 | 404
    Atendida pela Lambda ``dados_pessoais``. Grava o acesso em ``acessos_pii`` ANTES de ler;
    se a gravação falhar responde 403 ``log_acesso_indisponivel`` sem nenhum dado.
    Corpo: ``{"numero", "telefone": str | null, "cep": str | null}``.

``GET /api/cs/chamados/{numero}/anexos/{indice}`` -> 200 | 404
    ``{"url": <URL pré-assinada de GET>, "expira_em_s": 60, "mime"}``. O índice (base 0) vem
    da lista ``anexos`` do card; a chave do objeto nunca é aceita do cliente.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final

from core.contexto import Contexto
from core.erros import ErroApi, nao_encontrado
from core.roteador import Rota
from dominio.pacote import pacote_para_dict
from dominio.pii import mascarar_pii
from repositorios.erros import ErroRepositorio
from repositorios.modelos import Chamado
from servicos.anexos import EXPIRACAO_PADRAO_S, criar_porta_anexos

TAMANHO_RESUMO: Final = 140


# --------------------------------------------------------------------------- apoio


def _iso(valor: datetime | None) -> str | None:
    return valor.isoformat() if valor is not None else None


def _mascarar(valor: Any) -> Any:
    """Mascara PII em qualquer string de uma estrutura JSON (histórico, mensagens)."""
    if isinstance(valor, str):
        return mascarar_pii(valor)
    if isinstance(valor, dict):
        return {k: _mascarar(v) for k, v in valor.items()}
    if isinstance(valor, (list, tuple)):
        return [_mascarar(v) for v in valor]
    return valor


def _responsavel(c: Chamado) -> dict[str, str] | None:
    r = c.responsavel
    return {"usuario": r.usuario, "nome": r.nome} if r is not None else None


def _resumo_curto(c: Chamado) -> str:
    texto = mascarar_pii(c.pacote.resumo or "")
    if len(texto) <= TAMANHO_RESUMO:
        return texto
    return texto[: TAMANHO_RESUMO - 1].rstrip() + "…"


def _alerta_p1(c: Chamado) -> bool:
    return c.prioridade == "P1" and not c.alerta_p1_visto and c.status != "encerrado"


def _numero(ctx: Contexto) -> str:
    return ctx.req.params["numero"]


def _obter(ctx: Contexto) -> Chamado:
    chamado = ctx.repos.chamados.obter(_numero(ctx))
    if chamado is None:
        raise nao_encontrado("Chamado não encontrado.")
    return chamado


def _item_fila(c: Chamado, agora: datetime) -> dict[str, Any]:
    espera = max(0, int((agora - c.criado_em).total_seconds()))
    return {
        "numero": c.numero,
        "prioridade": c.prioridade,
        "classificacao": c.classificacao,
        "status": c.status,
        "responsavel": _responsavel(c),
        "tempo_espera_s": espera,
        "criado_em": _iso(c.criado_em),
        "alerta_p1": _alerta_p1(c),
        "alerta_p1_visto": c.alerta_p1_visto,
        "resposta_nao_lida": c.resposta_nao_lida,
        "resumo": _resumo_curto(c),
    }


def _corpo_card(ctx: Contexto, c: Chamado) -> dict[str, Any]:
    mensagens = [
        {
            "ts_ulid": m.ts_ulid,
            "autor": m.autor,
            "texto": mascarar_pii(m.texto),
            "em": _iso(m.em),
            "lida": m.lida,
        }
        for m in ctx.repos.mensagens.listar(c.numero)
    ]
    try:
        eventos = sorted(ctx.repos.eventos.listar(c.jornada_id), key=lambda e: e.em)
    except ErroRepositorio as exc:
        ctx.log.aviso("historico_indisponivel", erro=exc)
        eventos = []
    historico = [
        {"evento_id": e.evento_id, "tipo": e.tipo, "em": _iso(e.em), "dados": _mascarar(e.dados)}
        for e in eventos
    ]
    enc = c.encerramento
    return {
        "numero": c.numero,
        "jornada_id": c.jornada_id,
        "status": c.status,
        "prioridade": c.prioridade,
        "classificacao": c.classificacao,
        "canal": c.canal,
        "criado_em": _iso(c.criado_em),
        "responsavel": _responsavel(c),
        "alerta_p1_visto": c.alerta_p1_visto,
        "resposta_nao_lida": c.resposta_nao_lida,
        "os_status": c.os_status,
        "agendamento": _iso(c.agendamento),
        "pacote_ia_status": c.pacote_ia_status,
        "decisao_criterio": c.decisao_criterio,
        "pacote": _mascarar(pacote_para_dict(c.pacote)),
        "anexos": [{"indice": i, "mime": a.mime, "bytes": a.bytes} for i, a in enumerate(c.anexos)],
        "encerramento": (
            {
                "desfecho": enc.desfecho,
                "solucao_tipo": enc.solucao_tipo,
                "solucao": mascarar_pii(enc.solucao),
                "em": _iso(enc.em),
                "por": enc.por,
            }
            if enc is not None
            else None
        ),
        "mensagens": mensagens,
        "historico": historico,
    }


# --------------------------------------------------------------------------- handlers


def fila(ctx: Contexto) -> dict[str, Any]:
    agora = ctx.app.agora()
    return {"itens": [_item_fila(c, agora) for c in ctx.repos.chamados.listar_fila()]}


def card(ctx: Contexto) -> dict[str, Any]:
    chamado = _obter(ctx)
    if chamado.prioridade == "P1" and not chamado.alerta_p1_visto:
        # Abrir o card reconhece o alerta P1 para todos. Falha aqui não impede o atendimento.
        try:
            chamado = ctx.repos.chamados.marcar_alerta_p1_visto(chamado.numero)
        except ErroRepositorio as exc:
            ctx.log.aviso("alerta_p1_nao_marcado", erro=exc, numero=chamado.numero)
    return _corpo_card(ctx, chamado)


def assumir(ctx: Contexto) -> dict[str, Any]:
    chamado = _obter(ctx)
    usuario = ctx.usuario.usuario
    resultado = ctx.repos.chamados.assumir(chamado.numero, usuario, usuario, ctx.app.agora())
    atual = resultado.registro
    if not resultado.aplicado:
        if atual.responsavel is None:  # encerrado e sem responsável
            raise ErroApi(409, "chamado_encerrado", "Este Chamado já foi encerrado.")
        nome = atual.responsavel.nome
        raise ErroApi(
            409,
            "ja_assumido",
            f"Este Chamado já foi assumido por {nome}.",
            extras={"responsavel": _responsavel(atual)},
        )
    ctx.log.info("chamado_assumido", numero=atual.numero, usuario_id=usuario)
    if atual.prioridade == "P1" and not atual.alerta_p1_visto:
        try:
            atual = ctx.repos.chamados.marcar_alerta_p1_visto(atual.numero)
        except ErroRepositorio as exc:
            ctx.log.aviso("alerta_p1_nao_marcado", erro=exc, numero=atual.numero)
    return {
        "numero": atual.numero,
        "status": atual.status,
        "responsavel": _responsavel(atual),
        "alerta_p1_visto": atual.alerta_p1_visto,
    }


def dados_pessoais(ctx: Contexto) -> dict[str, Any]:
    chamado = _obter(ctx)
    # Req 18.6 e 18.9: o acesso é gravado ANTES de ler/devolver qualquer dado pessoal.
    try:
        ctx.repos.acessos_pii.registrar(chamado.numero, ctx.usuario.usuario, ctx.app.agora())
    except Exception as exc:  # noqa: BLE001 - qualquer falha do log bloqueia os dados
        ctx.log.erro("log_acesso_pii_falhou", erro=exc, numero=chamado.numero)
        raise ErroApi(
            403,
            "log_acesso_indisponivel",
            "Não foi possível registrar o acesso. Por segurança, os dados não foram exibidos.",
        ) from exc
    registro = ctx.repos.dados_pessoais.obter(chamado.numero)
    ctx.log.info("dados_pessoais_acessados", numero=chamado.numero, usuario_id=ctx.usuario.usuario)
    return {
        "numero": chamado.numero,
        "telefone": registro.telefone if registro else None,
        "cep": registro.cep if registro else None,
    }


def anexo(ctx: Contexto) -> dict[str, Any]:
    chamado = _obter(ctx)
    bruto = ctx.req.params.get("indice", "")
    if not bruto.isdigit() or int(bruto) >= len(chamado.anexos):
        raise nao_encontrado("Anexo não encontrado.")
    item = chamado.anexos[int(bruto)]
    porta = criar_porta_anexos(ctx.app.modo)
    url = porta.url_leitura(item.chave, item.mime, EXPIRACAO_PADRAO_S)
    return {"url": url, "expira_em_s": EXPIRACAO_PADRAO_S, "mime": item.mime}


ROTAS = [
    Rota("GET", "/fila", fila, escopo="cs", nome="cs_fila"),
    Rota("GET", "/chamados/{numero}", card, escopo="cs", nome="cs_card"),
    Rota("POST", "/chamados/{numero}/assumir", assumir, escopo="cs", nome="cs_assumir"),
    Rota(
        "GET",
        "/chamados/{numero}/dados-pessoais",
        dados_pessoais,
        escopo="cs",
        destino="dados_pessoais",
        nome="cs_dados_pessoais",
    ),
    Rota("GET", "/chamados/{numero}/anexos/{indice}", anexo, escopo="cs", nome="cs_anexo"),
]
