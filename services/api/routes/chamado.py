"""Rotas públicas do Chamado para o Consumidor (Req 12, 15.4, 15.5, 16.5, 18.1).

Contrato documentado em `apps/web/src/api/chamado.ts`. Todas indexadas pelo número do Chamado
(`TRES-...`); número desconhecido é 404 `chamado_nao_encontrado`, sem dado de nenhum Chamado.

  * ``GET  /chamados/{numero}``: status, prioridade, mensagens, agendamento, `dados_solicitados`
    e `anexos_total`. NUNCA devolve telefone, CEP nem `jornada_id`.
  * ``POST /chamados/{numero}/contato``: telefone/CEP com consentimento (Lambda `dados_pessoais`,
    sem idempotência por evento: o upsert já é idempotente).
  * ``POST /chamados/{numero}/mensagens``: resposta do Consumidor (1 a 2000), PII mascarada.
  * ``POST /chamados/{numero}/avaliacao``: só Chamado `encerrado`; camada "humano".
  * Fotos: ``POST .../anexos`` (POST pré-assinado) e ``POST .../anexos/{anexo_id}/confirmacao``.
    Em modo local, ``POST .../anexos/{anexo_id}/arquivo`` é um destino STUB que descarta o arquivo.

Limitação conhecida: a Lambda `api` não lê a tabela `dados_pessoais` (Req 18.6); se a leitura
falhar, o GET devolve o que a prioridade exige (o Portal não perde a lista, só pode pedir de novo).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from core.contexto import Contexto
from core.erros import ErroApi, conflito, dependencia_indisponivel, validacao
from core.http import Resposta
from core.roteador import Rota
from core.validacao import Validador, exigir_objeto
from dominio import ErroCampo, mascarar_pii
from dominio.validadores import (
    FOTOS_MAX_POR_CHAMADO,
    FUSO_BRASILIA,
    dados_pessoais_solicitados,
    validar_cep,
    validar_comentario,
    validar_foto,
    validar_nota,
    validar_telefone,
)
from repositorios.ids import novo_ulid
from repositorios.modelos import AnexoChamado, Avaliacao, Chamado, Consentimento
from servicos.fotos import obter_armazenamento

VERSAO_FINALIDADE = "2025-01"
MAX_MENSAGEM = 2000
_ANEXO_ID = re.compile(r"[0-9A-HJKMNP-TV-Z]{26}")


def _iso(momento: datetime) -> str:
    return momento.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _chamado_ou_404(ctx: Contexto) -> Chamado:
    chamado = ctx.repos.chamados.obter(ctx.req.params["numero"])
    if chamado is None:
        raise ErroApi(404, "chamado_nao_encontrado", "Não encontramos este chamado.")
    return chamado


def _informados(ctx: Contexto, numero: str) -> list[str]:
    registro = ctx.repos.dados_pessoais.obter(numero)
    if registro is None:
        return []
    return [n for n in ("telefone", "cep") if getattr(registro, n)]


def _solicitados(chamado: Chamado, informados: list[str]) -> list[str]:
    return list(dados_pessoais_solicitados(chamado.prioridade, informados))


def obter_chamado(ctx: Contexto) -> dict[str, Any]:
    chamado = _chamado_ou_404(ctx)
    try:
        informados = _informados(ctx, chamado.numero)
    except Exception as exc:  # noqa: BLE001 - papel sem acesso à tabela (ver o docstring)
        ctx.log.aviso("dados_informados_indisponiveis", erro=exc)
        informados = []
    avaliacao_pendente = False
    if chamado.status == "encerrado":
        avaliacao_pendente = ctx.repos.avaliacoes.obter(chamado.jornada_id) is None
    mensagens = [
        {"autor": m.autor, "texto": m.texto, "em": _iso(m.em)}
        for m in ctx.repos.mensagens.listar(chamado.numero)
    ]
    return {
        "numero": chamado.numero,
        "status": chamado.status,
        "prioridade": chamado.prioridade,
        "canal": chamado.canal,
        "criado_em": _iso(chamado.criado_em),
        "dados_solicitados": _solicitados(chamado, informados),
        "anexos_total": len(chamado.anexos),
        "mensagens": mensagens,
        "agendamento": (
            {"data_hora": chamado.agendamento.astimezone(FUSO_BRASILIA).isoformat()}
            if chamado.agendamento
            else None
        ),
        "avaliacao_pendente": avaliacao_pendente,
    }


def enviar_contato(ctx: Contexto) -> Resposta:
    chamado = _chamado_ou_404(ctx)
    corpo = exigir_objeto(ctx.json())
    erros: list[ErroCampo] = []
    valores: dict[str, str | None] = {"telefone": None, "cep": None}
    for nome, valido in (("telefone", validar_telefone), ("cep", validar_cep)):
        bruto = corpo.get(nome)
        if bruto is None:
            continue
        if not isinstance(bruto, str) or not valido(bruto.strip()):
            erros.append(ErroCampo(nome, "valor inválido"))
        else:
            valores[nome] = bruto.strip()
    if corpo.get("consentimento") is not True:
        erros.append(ErroCampo("consentimento", "é preciso aceitar para enviar seus dados"))
    if not erros and valores["telefone"] is None and valores["cep"] is None:
        erros.append(ErroCampo("telefone", "informe o telefone ou o CEP"))
    if erros:
        raise validacao(erros)

    registro = ctx.repos.dados_pessoais.salvar(
        chamado.numero,
        Consentimento(ctx.app.agora(), VERSAO_FINALIDADE),
        telefone=valores["telefone"],
        cep=valores["cep"],
    )
    informados = [n for n in ("telefone", "cep") if getattr(registro, n)]
    ctx.log.info("contato_registrado", numero=chamado.numero)  # sem os valores (Req 18)
    return Resposta.ok({"dados_solicitados": _solicitados(chamado, informados)})


def enviar_mensagem(ctx: Contexto) -> Resposta:
    chamado = _chamado_ou_404(ctx)
    corpo = exigir_objeto(ctx.json())
    validador = Validador(corpo)
    texto = validador.texto("texto", maximo=MAX_MENSAGEM)
    validador.levantar_se_erros()
    assert texto is not None
    if not ctx.primeira_vez(f"mensagem_chamado:{chamado.numero}", corpo):
        return Resposta.ok({"registrada": False})
    try:
        mascarado = mascarar_pii(texto.strip())
    except Exception as exc:  # noqa: BLE001 - nada é gravado se o mascaramento falhar (Req 18.8)
        ctx.log.aviso("mascaramento_falhou", erro=exc)
        raise dependencia_indisponivel() from exc
    agora = ctx.app.agora()
    ctx.repos.mensagens.adicionar(chamado.numero, "consumidor", mascarado, agora)
    ctx.repos.chamados.definir_resposta_nao_lida(chamado.numero, True)
    return Resposta.criado({"registrada": True})


def enviar_avaliacao(ctx: Contexto) -> Resposta:
    chamado = _chamado_ou_404(ctx)
    corpo = exigir_objeto(ctx.json())
    nota = corpo.get("nota")
    comentario = corpo.get("comentario")
    validador = Validador(corpo)
    validador.adicionar(validar_nota(nota).erros)  # type: ignore[arg-type]
    validador.adicionar(validar_comentario(comentario).erros)
    validador.levantar_se_erros()
    if chamado.status != "encerrado":
        raise conflito("Você poderá avaliar quando o atendimento for encerrado.")
    try:
        texto = mascarar_pii(comentario) if comentario else ""
    except Exception as exc:  # noqa: BLE001
        raise dependencia_indisponivel() from exc
    resultado = ctx.repos.avaliacoes.registrar(
        Avaliacao(chamado.jornada_id, nota, "humano", ctx.app.agora(), texto)
    )
    return Resposta.ok({"registrada": resultado.aplicado})


def pedir_anexo(ctx: Contexto) -> Resposta:
    chamado = _chamado_ou_404(ctx)
    corpo = exigir_objeto(ctx.json())
    mime, tamanho = corpo.get("mime"), corpo.get("bytes")
    if (
        not isinstance(mime, str)
        or isinstance(tamanho, bool)
        or not isinstance(tamanho, int)
        or tamanho < 1
    ):
        raise ErroApi(422, "foto_invalida", "Envie uma foto JPEG ou PNG de até 5 MB.")
    mime = mime.strip().lower()
    formato = validar_foto(mime, tamanho, 0)
    if not formato:
        raise ErroApi(422, "foto_invalida", formato.motivo or "Foto inválida.")
    limite = validar_foto(mime, tamanho, len(chamado.anexos))
    if not limite:
        raise ErroApi(409, "limite_fotos", limite.motivo or "Limite de fotos atingido.")

    anexo_id = novo_ulid(ctx.app.agora())
    chave = f"chamados/{chamado.numero}/{anexo_id}"
    destino = obter_armazenamento(ctx.app.modo).destino_upload(chave, mime, tamanho)
    return Resposta.criado(
        {"anexo_id": anexo_id, "upload": {"url": destino.url, "campos": destino.campos}}
    )


def confirmar_anexo(ctx: Contexto) -> Resposta:
    chamado = _chamado_ou_404(ctx)
    anexo_id = ctx.req.params["anexo_id"]
    if not _ANEXO_ID.fullmatch(anexo_id):
        raise ErroApi(422, "foto_invalida", "Não foi possível confirmar a foto.")
    chave = f"chamados/{chamado.numero}/{anexo_id}"
    if any(a.chave == chave for a in chamado.anexos):  # repetição: já vinculada
        return Resposta.ok({"anexos_total": len(chamado.anexos)})
    armazenamento = obter_armazenamento(ctx.app.modo)
    objeto = armazenamento.inspecionar(chave)
    verificacao = validar_foto(objeto.mime, objeto.bytes, 0) if objeto else None
    if objeto is None or not verificacao or objeto.bytes < 1:
        if objeto is not None:
            armazenamento.descartar(chave)
        raise ErroApi(422, "foto_invalida", "Não foi possível confirmar a foto. Envie de novo.")
    resultado = ctx.repos.chamados.adicionar_anexo(
        chamado.numero,
        AnexoChamado(chave, objeto.mime.lower(), objeto.bytes),  # type: ignore[arg-type]
        maximo=FOTOS_MAX_POR_CHAMADO,
    )
    if not resultado.aplicado:
        armazenamento.descartar(chave)
        raise ErroApi(409, "limite_fotos", "Limite de 3 fotos por chamado atingido.")
    return Resposta.ok({"anexos_total": len(resultado.registro.anexos)})


def receber_arquivo_local(ctx: Contexto) -> Resposta:
    """STUB do destino de envio em modo local: aceita e descarta o arquivo."""
    _chamado_ou_404(ctx)
    if ctx.app.modo != "local":
        raise ErroApi(404, "nao_encontrado", "Não encontramos o que você procurou.")
    return Resposta.sem_conteudo()


ROTAS = [
    Rota("GET", "/chamados/{numero}", obter_chamado, escopo="pub", nome="obter_chamado"),
    Rota(
        "POST",
        "/chamados/{numero}/contato",
        enviar_contato,
        escopo="pub",
        destino="dados_pessoais",
        nome="enviar_contato",
    ),
    Rota(
        "POST",
        "/chamados/{numero}/mensagens",
        enviar_mensagem,
        escopo="pub",
        nome="mensagem_consumidor",
    ),
    Rota(
        "POST",
        "/chamados/{numero}/avaliacao",
        enviar_avaliacao,
        escopo="pub",
        nome="avaliar_chamado",
    ),
    Rota("POST", "/chamados/{numero}/anexos", pedir_anexo, escopo="pub", nome="pedir_anexo"),
    Rota(
        "POST",
        "/chamados/{numero}/anexos/{anexo_id}/confirmacao",
        confirmar_anexo,
        escopo="pub",
        nome="confirmar_anexo",
    ),
    Rota(
        "POST",
        "/chamados/{numero}/anexos/{anexo_id}/arquivo",
        receber_arquivo_local,
        escopo="pub",
        nome="arquivo_local",
    ),
]
