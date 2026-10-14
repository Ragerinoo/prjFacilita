"""Rotas do Painel_CS de comunicação e ação do Atendente: sugestão da IA, mensagens, Ordem_Servico
e agendamento de ligação (Req 11.4, 11.8, 15.1 a 15.9). Exigem sessão (atendente ou gestor).

Formas das respostas (consumidas pelo front-end, tarefa 15.4)
=============================================================

``GET /api/cs/chamados/{numero}/sugestao`` -> 200 | 404
    ``{"sugestao": str | null, "origem": "ia" | "modelo_local" | null, "mensagem": str | null}``.
    NUNCA é erro por falha da IA: falha, prazo de 10 s ou texto vazio -> ``sugestao: null`` e
    ``mensagem: "sugestão indisponível"`` (campo de resposta vazio e editável; Req 15.7). O texto
    não tem PII (mascarado) e nada é enviado ao Consumidor por esta rota (Req 15.2).

``POST /api/cs/chamados/{numero}/mensagens`` -> 201 | 404 | 409 | 422
    Corpo: ``{"texto": str (1 a 2000), "confirmada": true}``. Sem ``confirmada: true`` -> 422
    (campo ``confirmacao``) e NADA é gravado. Texto vazio/longo -> 422 (campo ``mensagem``).
    Sucesso: ``{"ts_ulid", "autor": "atendente", "texto", "em": ISO}``; limpa
    ``resposta_nao_lida`` do Chamado. 409 ``chamado_encerrado`` (Chamado encerrado) ou
    ``outro_responsavel`` (assumido por outro; ``responsavel`` vem junto). Em qualquer erro o
    front mantém o texto digitado (Req 15.8). Chamado sem responsável aceita a mensagem.
    A ação "Enviar instrução do manual" usa esta mesma rota, com o texto da instrução.

``POST /api/cs/chamados/{numero}/ordem-servico`` -> 200 | 404 | 409
    Sem corpo. Idempotente: cria o rascunho se faltar (dados do Pacote; vale para qualquer
    prioridade, ex.: P2 cuja criação automática falhou, Req 11.8) e o confirma (rascunho ->
    aberta). Repetir devolve 200 com ``criada_agora``/``confirmada_agora`` falsos.
    ``{"numero", "os_id", "status": "aberta", "criada_agora": bool, "confirmada_agora": bool}``.
    Chamado encerrado -> 409 ``chamado_encerrado``. ``os_status`` do Chamado passa a ``ok``.

``POST /api/cs/chamados/{numero}/agendamento`` -> 200 | 404 | 409 | 422
    Corpo: ``{"data": "AAAA-MM-DD", "hora": "HH:MM"}`` (horário de Brasília). Faltando, mal
    formatado, no passado ou além de 30 dias -> 422 com ``campos`` (``data`` ou ``hora``) e nada
    é gravado (Req 15.9). Sucesso: ``{"numero", "agendamento": ISO com -03:00}``; o Portal
    mostra o valor ao Consumidor. Reagendar substitui o valor anterior.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from core.contexto import Contexto
from core.erros import ErroApi, nao_encontrado, validacao
from core.http import Resposta
from core.roteador import Rota
from core.validacao import exigir_objeto
from dominio import ErroCampo
from dominio.validadores import (
    FUSO_BRASILIA,
    validar_agendamento,
    validar_mensagem_atendente,
)
from repositorios.modelos import Chamado, OrdemServico
from servicos.sugestao import MENSAGEM_INDISPONIVEL, gerar_sugestao


def _obter(ctx: Contexto) -> Chamado:
    chamado = ctx.repos.chamados.obter(ctx.req.params["numero"])
    if chamado is None:
        raise nao_encontrado("Chamado não encontrado.")
    return chamado


def _exigir_aberto(chamado: Chamado) -> None:
    if chamado.status == "encerrado":
        raise ErroApi(409, "chamado_encerrado", "Este Chamado já foi encerrado.")


def sugestao(ctx: Contexto) -> dict[str, Any]:
    chamado = _obter(ctx)
    modelo_id = None
    try:
        jornada = ctx.repos.jornadas.obter(chamado.jornada_id)
        modelo_id = jornada.modelo_id if jornada is not None else None
    except Exception as exc:  # noqa: BLE001 - sem Jornada a sugestão ainda sai do Pacote
        ctx.log.aviso("sugestao_sem_jornada", erro=exc, numero=chamado.numero)
    resultado = gerar_sugestao(chamado.pacote, chamado.jornada_id, modelo_id, ctx.app.modo)
    if resultado.texto is None:
        ctx.log.aviso("sugestao_indisponivel", numero=chamado.numero)
        return {"sugestao": None, "origem": None, "mensagem": MENSAGEM_INDISPONIVEL}
    return {"sugestao": resultado.texto, "origem": resultado.origem, "mensagem": None}


def mensagem(ctx: Contexto) -> Resposta:
    chamado = _obter(ctx)
    corpo = exigir_objeto(ctx.json())
    texto = corpo.get("texto")
    confirmada = corpo.get("confirmada") is True
    if not isinstance(texto, str):
        raise validacao([ErroCampo("mensagem", "A mensagem deve ser um texto.")])
    resultado = validar_mensagem_atendente(texto, confirmada)
    if not resultado.aceita:
        raise validacao(resultado.erros)
    if not texto.strip():  # só espaços não é uma resposta
        raise validacao([ErroCampo("mensagem", "Escreva a mensagem antes de enviar.")])
    _exigir_aberto(chamado)
    r = chamado.responsavel
    if r is not None and r.usuario != ctx.usuario.usuario:
        raise ErroApi(
            409,
            "outro_responsavel",
            f"Este Chamado está com {r.nome}.",
            extras={"responsavel": {"usuario": r.usuario, "nome": r.nome}},
        )
    agora = ctx.app.agora()
    msg = ctx.repos.mensagens.adicionar(chamado.numero, "atendente", texto, agora)
    ctx.repos.chamados.definir_resposta_nao_lida(chamado.numero, False)
    ctx.log.info("mensagem_atendente_enviada", numero=chamado.numero, usuario_id=ctx.usuario.usuario)
    return Resposta.criado(
        {
            "ts_ulid": msg.ts_ulid,
            "autor": "atendente",
            "texto": msg.texto,
            "em": msg.em.isoformat(),
        }
    )


def ordem_servico(ctx: Contexto) -> dict[str, Any]:
    chamado = _obter(ctx)
    _exigir_aberto(chamado)
    pacote = chamado.pacote
    rascunho = OrdemServico(
        numero=chamado.numero,
        modelo=pacote.modelo,
        numero_serie=pacote.numero_serie,
        categoria=pacote.categoria,
        ja_tentado=pacote.ja_tentado,
    )
    criada = ctx.repos.ordens_servico.criar_rascunho(rascunho).aplicado
    confirmada = ctx.repos.ordens_servico.confirmar(chamado.numero)
    if chamado.os_status != "ok":
        ctx.repos.chamados.definir_os_status(chamado.numero, "ok")
    ctx.log.info(
        "ordem_servico_confirmada",
        numero=chamado.numero,
        usuario_id=ctx.usuario.usuario,
        criada=criada,
    )
    return {
        "numero": chamado.numero,
        "os_id": confirmada.registro.os_id,
        "status": confirmada.registro.status,
        "criada_agora": criada,
        "confirmada_agora": confirmada.aplicado,
    }


def _ler_data(valor: Any) -> date | None:
    if isinstance(valor, str):
        try:
            return date.fromisoformat(valor.strip())
        except ValueError:
            return None
    return None


def _ler_hora(valor: Any) -> time | None:
    if isinstance(valor, str):
        try:
            return time.fromisoformat(valor.strip()).replace(tzinfo=None)
        except ValueError:
            return None
    return None


def agendamento(ctx: Contexto) -> dict[str, Any]:
    chamado = _obter(ctx)
    corpo = exigir_objeto(ctx.json())
    data = _ler_data(corpo.get("data"))
    hora = _ler_hora(corpo.get("hora"))
    erros: list[ErroCampo] = []
    if corpo.get("data") is not None and data is None:
        erros.append(ErroCampo("data", "Use o formato AAAA-MM-DD."))
    if corpo.get("hora") is not None and hora is None:
        erros.append(ErroCampo("hora", "Use o formato HH:MM."))
    if not erros:
        resultado = validar_agendamento(data, hora, ctx.app.agora())
        erros.extend(resultado.erros)
    if erros:
        raise validacao(erros)
    assert data is not None and hora is not None
    _exigir_aberto(chamado)
    alvo = datetime.combine(data, hora, tzinfo=FUSO_BRASILIA)
    atualizado = ctx.repos.chamados.definir_agendamento(chamado.numero, alvo)
    ctx.log.info("ligacao_agendada", numero=chamado.numero, usuario_id=ctx.usuario.usuario)
    return {
        "numero": atualizado.numero,
        "agendamento": atualizado.agendamento.isoformat() if atualizado.agendamento else None,
    }


ROTAS = [
    Rota("GET", "/chamados/{numero}/sugestao", sugestao, escopo="cs", nome="cs_sugestao"),
    Rota("POST", "/chamados/{numero}/mensagens", mensagem, escopo="cs", nome="cs_mensagem"),
    Rota(
        "POST",
        "/chamados/{numero}/ordem-servico",
        ordem_servico,
        escopo="cs",
        nome="cs_ordem_servico",
    ),
    Rota("POST", "/chamados/{numero}/agendamento", agendamento, escopo="cs", nome="cs_agendamento"),
]
