"""Rotas públicas de início e consulta da Jornada (Req 1.2 a 1.7, 2.4).

  * ``POST /jornadas`` ``{origem: "qr"|"busca", modelo_id?, numero_serie?}`` cria a Jornada:
      - modelo reconhecido: grava o modelo; o número de série entra só se tiver de 1 a 30
        caracteres alfanuméricos, senão é descartado em silêncio (Req 1.2, 1.5);
      - modelo ausente, ilegível, inexistente ou inativo: cria a Jornada SEM modelo (e sem
        série), mantendo a origem pedida (Req 1.4);
      - catálogo sem resposta em 5 s: 504 e nenhuma Jornada é criada (Req 1.7).
    Com ``Idempotency-Key``, repetir a chamada devolve a mesma Jornada (200 em vez de 201).
  * ``PUT /jornadas/{id}/modelo`` ``{modelo_id, numero_serie?}`` associa o modelo escolhido na
    busca; a ``origem`` vira ``busca`` e ``origem_inicial`` fica (Req 2.4). Modelo inexistente
    é 422; Jornada inexistente, 404; Jornada encerrada, 409.
  * ``GET /jornadas/{id}`` devolve ``{"jornada": {...}}`` (envelope do alerta de risco).

Toda resposta traz o envelope ``jornada`` (ver `servicos/envelope_jornada.py`).
"""

from __future__ import annotations

from typing import Any

from core.contexto import Contexto
from core.erros import conflito, nao_encontrado, validacao
from core.http import Resposta
from core.idempotencia import ulid_da_chave
from core.roteador import Rota
from core.validacao import Validador, exigir_objeto
from dominio import ErroCampo
from dominio.qr import PADRAO_SERIE
from repositorios.ids import novo_ulid
from repositorios.modelos import Jornada
from servicos.catalogo import obter_modelo_ativo
from servicos.envelope_jornada import envelope_jornada

ORIGENS = ("qr", "busca")
ESCOPO_IDEMPOTENCIA = "criar_jornada"


def _serie_valida(valor: Any) -> str | None:
    """A série, se válida (Req 1.2); qualquer outra coisa é descartada em silêncio."""
    if isinstance(valor, str) and PADRAO_SERIE.fullmatch(valor):
        return valor
    return None


def _resposta_jornada(jornada: Jornada) -> dict[str, Any]:
    return {
        "jornada_id": jornada.jornada_id,
        "origem": jornada.origem,
        "modelo_id": jornada.modelo_id,
        "jornada": envelope_jornada(jornada),
    }


def criar_jornada(ctx: Contexto) -> Resposta:
    corpo = exigir_objeto(ctx.json())
    validador = Validador(corpo)
    origem = validador.escolha("origem", ORIGENS)
    validador.levantar_se_erros()
    assert origem is not None  # garantido por `levantar_se_erros`

    # Falha ou atraso do catálogo sobe como erro ANTES de criar qualquer coisa (Req 1.7).
    modelo = None
    if corpo.get("modelo_id") is not None:
        modelo = obter_modelo_ativo(ctx.repos, corpo.get("modelo_id"))
    numero_serie = _serie_valida(corpo.get("numero_serie")) if modelo else None

    agora = ctx.app.agora()
    chave = ctx.chave_idempotencia(corpo)
    jornada_id = ulid_da_chave(f"jornada:{chave}") if chave else novo_ulid(agora)
    resultado = ctx.repos.jornadas.criar(
        Jornada(
            jornada_id=jornada_id,
            criada_em=agora,
            ultima_interacao=agora,
            origem=origem,  # type: ignore[arg-type]
            origem_inicial=origem,  # type: ignore[arg-type]
            modelo_id=modelo.modelo_id if modelo else None,
            numero_serie=numero_serie,
        )
    )
    ctx.log.info(
        "jornada_criada",
        jornada_id=resultado.registro.jornada_id,
        origem=origem,
        modelo_reconhecido=modelo is not None,
        repetida=not resultado.aplicado,
    )
    resposta = {**_resposta_jornada(resultado.registro), "modelo_reconhecido": modelo is not None}
    if not resultado.aplicado:
        return Resposta.ok(resposta)
    return Resposta.criado(resposta)


def associar_modelo(ctx: Contexto) -> Resposta:
    corpo = exigir_objeto(ctx.json())
    validador = Validador(corpo)
    modelo_id = validador.texto("modelo_id", maximo=200)
    validador.levantar_se_erros()

    jornada = ctx.repos.jornadas.obter(ctx.req.params["id"])
    if jornada is None:
        raise nao_encontrado("Jornada não encontrada.")
    if jornada.estado == "encerrada":
        raise conflito("Esta jornada já foi encerrada.")
    modelo = obter_modelo_ativo(ctx.repos, modelo_id)
    if modelo is None:
        raise validacao([ErroCampo("modelo_id", "modelo não encontrado")])

    ctx.repos.jornadas.associar_modelo(
        jornada.jornada_id, modelo.modelo_id, _serie_valida(corpo.get("numero_serie"))
    )
    atualizada = ctx.repos.jornadas.registrar_interacao(jornada.jornada_id, ctx.app.agora())
    return Resposta.ok(_resposta_jornada(atualizada))


def obter_jornada(ctx: Contexto) -> dict[str, Any]:
    jornada = ctx.repos.jornadas.obter(ctx.req.params["id"])
    if jornada is None:
        raise nao_encontrado("Jornada não encontrada.")
    envelope = envelope_jornada(jornada)
    envelope["origem"] = jornada.origem
    envelope["modelo_id"] = jornada.modelo_id
    return {"jornada": envelope}


ROTAS = [
    Rota("POST", "/jornadas", criar_jornada, escopo="pub", nome="criar_jornada"),
    Rota("PUT", "/jornadas/{id}/modelo", associar_modelo, escopo="pub", nome="associar_modelo"),
    Rota("GET", "/jornadas/{id}", obter_jornada, escopo="pub", nome="obter_jornada"),
]
