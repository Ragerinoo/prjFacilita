"""Rotas públicas de resolução, vazamento, escalada e avaliação (tarefa 12.3).

  * ``POST /jornadas/{id}/resolucao`` ``{resolvido, problema_id, evento_id}`` (Req 5.1 a 5.3):
    "Sim" encerra a Jornada na camada ``guia`` pela porta ``encerrar_jornada`` (falha de
    encerramento NÃO falha a resposta; em modo local, ou se a fila recusar, grava direto, de forma
    idempotente). "Não" marca ``guia_respondeu_nao`` e escala com o gatilho
    ``instrucao_sem_solucao`` (P2, ou P1 se há risco) sem passar pelo assistente; devolve o corpo
    da escalada (``chamado``, ``numero``, ``novo``, ``jornada``).
  * ``POST /jornadas/{id}/vazamento`` ``{tipo: externo|interno, evento_id}`` (Req 3.7, 3.8, 8.7):
    externo devolve ``{variante: "externo"}`` sem escalar; interno marca risco com origem
    ``guia`` e escala (P1).
  * ``POST /jornadas/{id}/escalar`` ``{motivo, evento_id}`` (Req 9.3, 9.8): idempotente. ``risco``
    é o "Tentar novamente" do alerta de risco (marca, se faltar, e repassa como P1);
    ``pedido_humano`` é o pedido explícito do Consumidor.
  * ``POST /jornadas/{id}/avaliacao`` ``{nota 1-5, comentario <= 500, evento_id}`` (Req 5.5 a
    5.7): uma por Jornada. A segunda NÃO sobrescreve: responde 200 com ``registrada: false`` e a
    avaliação original (idempotente, sem 409).

Toda resposta de mutação traz o envelope ``jornada`` (``servicos/escalada.envelope_jornada``).
Idempotência: ``Idempotency-Key`` ou ``evento_id``; as operações subjacentes também são
idempotentes por Jornada (um Chamado, um encerramento, uma avaliação).
"""

from __future__ import annotations

import re
from typing import Any, Final

from core.contexto import Contexto
from core.erros import conflito, dependencia_indisponivel, nao_encontrado, validacao
from core.http import Resposta
from core.idempotencia import ulid_da_chave
from core.roteador import Rota
from core.validacao import Validador, exigir_objeto
from dominio import ErroCampo
from repositorios.ids import eh_ulid, novo_ulid
from repositorios.modelos import Avaliacao, Evento, Jornada
from servicos.escalada import (
    TIPO_EVENTO_RESOLUCAO_GUIA,
    ServicoEscalada,
    envelope_jornada,
)

MAX_COMENTARIO: Final = 500
MOTIVOS_ESCALAR: Final = ("risco", "pedido_humano")
_INTEIRO: Final = re.compile(r"\d{1,6}")


def _jornada_ou_404(ctx: Contexto) -> Jornada:
    jornada = ctx.repos.jornadas.obter(ctx.req.params["id"])
    if jornada is None:
        raise nao_encontrado("Jornada não encontrada.")
    return jornada


def _servico_escalada(ctx: Contexto) -> ServicoEscalada:
    if ctx.app.escalada is None:
        raise dependencia_indisponivel("Escalada indisponível no momento.")
    return ctx.app.escalada


def _resposta_escalada(resultado: Any) -> Resposta:
    corpo = resultado.para_dict()
    chamado = corpo.get("chamado")
    if chamado:
        corpo["numero"] = chamado["numero"]
    return Resposta.ok(corpo)


def _problema_id(valor: Any, validador: Validador) -> int | None:
    if isinstance(valor, str) and _INTEIRO.fullmatch(valor):
        valor = int(valor)
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < 1:
        validador.erros.append(ErroCampo("problema_id", "deve ser um número inteiro positivo"))
        return None
    return valor


# ------------------------------------------------------------------------------- resolução


def _encerrar_no_guia(ctx: Contexto, jornada: Jornada, problema_id: int) -> None:
    """Encerra na camada guia (Req 5.2). Nunca levanta: o Consumidor não espera por isso."""
    try:
        enfileirado = False
        if ctx.app.encerrador is not None:
            enfileirado = ctx.app.encerrador.encerrar_jornada(
                jornada.jornada_id, "guia", problema_id=problema_id, em=ctx.app.agora()
            ).enfileirado
        if ctx.app.modo == "local" or not enfileirado:
            # Local não tem consumidor da fila; sem fila, grava direto (idempotente, Req 17.1).
            ctx.repos.jornadas.encerrar(
                jornada.jornada_id, "guia", ctx.app.agora(), problema_id=problema_id
            )
    except Exception as exc:  # noqa: BLE001 - o registro nunca derruba a resposta (Req 17.12)
        ctx.log.erro("encerramento_guia_falhou", jornada_id=jornada.jornada_id, erro=exc)


def _registrar_evento_resolucao(
    ctx: Contexto, corpo: Any, jornada: Jornada, problema_id: int, resolvido: bool
) -> None:
    agora = ctx.app.agora()
    chave = ctx.chave_idempotencia(corpo)
    if chave is None:
        evento_id = novo_ulid(agora)
    else:
        evento_id = chave if eh_ulid(chave) else ulid_da_chave(f"resolucao:{chave}")
    ctx.repos.eventos.registrar(
        Evento(
            jornada_id=jornada.jornada_id,
            evento_id=evento_id,
            tipo=TIPO_EVENTO_RESOLUCAO_GUIA,
            em=agora,
            dados={"problema_id": problema_id, "resolvido": resolvido},
        )
    )


def registrar_resolucao(ctx: Contexto) -> Resposta:
    corpo = exigir_objeto(ctx.json())
    validador = Validador(corpo)
    resolvido = validador.booleano("resolvido")
    bruto = corpo.get("problema_id")
    problema_id = _problema_id(bruto, validador) if bruto is not None else None
    if bruto is None:
        validador.erros.append(ErroCampo("problema_id", "é obrigatório"))
    validador.levantar_se_erros()
    assert resolvido is not None and problema_id is not None

    jornada = _jornada_ou_404(ctx)
    if resolvido:
        if jornada.estado == "ativa":
            _registrar_evento_resolucao(ctx, corpo, jornada, problema_id, True)
            _encerrar_no_guia(ctx, jornada, problema_id)
        atual = ctx.repos.jornadas.obter(jornada.jornada_id) or jornada
        return Resposta.ok({"resolvido": True, "jornada": envelope_jornada(atual)})

    # "Não": escala como P2 (P1 com risco) direto, sem assistente (Req 5.3).
    if jornada.estado == "encerrada" and jornada.escalada is None:
        raise conflito("Esta jornada já foi encerrada.")
    servico = _servico_escalada(ctx)
    if jornada.estado != "encerrada":
        _registrar_evento_resolucao(ctx, corpo, jornada, problema_id, False)
    ctx.repos.jornadas.marcar_guia_respondeu_nao(jornada.jornada_id)
    return _resposta_escalada(servico.escalar(jornada.jornada_id, "instrucao_sem_solucao"))


# ------------------------------------------------------------------------------- vazamento


def informar_vazamento(ctx: Contexto) -> Resposta:
    corpo = exigir_objeto(ctx.json())
    validador = Validador(corpo)
    tipo = validador.escolha("tipo", ("externo", "interno"))
    validador.levantar_se_erros()

    jornada = _jornada_ou_404(ctx)
    if tipo == "externo":
        return Resposta.ok({"variante": "externo", "jornada": envelope_jornada(jornada)})
    resultado = _servico_escalada(ctx).marcar_risco(jornada.jornada_id, "guia")
    return _resposta_escalada(resultado)


# --------------------------------------------------------------------------------- escalar


def escalar_jornada(ctx: Contexto) -> Resposta:
    corpo = exigir_objeto(ctx.json())
    validador = Validador(corpo)
    motivo = validador.escolha("motivo", MOTIVOS_ESCALAR)
    validador.levantar_se_erros()

    jornada = _jornada_ou_404(ctx)
    servico = _servico_escalada(ctx)
    if motivo == "risco":
        origem = jornada.risco.origem if jornada.risco is not None else "lista"
        return _resposta_escalada(servico.marcar_risco(jornada.jornada_id, origem))
    return _resposta_escalada(servico.escalar(jornada.jornada_id, "pedido_humano"))


# ------------------------------------------------------------------------------- avaliação


def _camada_da_avaliacao(jornada: Jornada) -> str:
    if jornada.encerramento is not None and jornada.encerramento.camada != "abandonada":
        return jornada.encerramento.camada
    return "humano" if jornada.escalada is not None else "guia"


def registrar_avaliacao(ctx: Contexto) -> Resposta:
    corpo = exigir_objeto(ctx.json())
    validador = Validador(corpo)
    nota = validador.inteiro("nota", minimo=1, maximo=5)
    comentario = validador.texto(
        "comentario", obrigatorio=False, minimo=0, maximo=MAX_COMENTARIO, padrao=""
    )
    validador.levantar_se_erros()
    assert nota is not None
    if comentario is not None and not isinstance(comentario, str):  # pragma: no cover
        raise validacao([ErroCampo("comentario", "deve ser um texto")])

    jornada = _jornada_ou_404(ctx)
    resultado = ctx.repos.avaliacoes.registrar(
        Avaliacao(
            jornada_id=jornada.jornada_id,
            nota=nota,
            camada=_camada_da_avaliacao(jornada),  # type: ignore[arg-type]
            em=ctx.app.agora(),
            comentario=comentario or "",
        )
    )
    registro = resultado.registro
    corpo_resposta = {
        "registrada": resultado.aplicado,
        "avaliacao": {"nota": registro.nota, "comentario": registro.comentario},
        "jornada": envelope_jornada(jornada),
    }
    # Segunda avaliação: 200 com a original (idempotente); a primeira cria (201).
    return Resposta.criado(corpo_resposta) if resultado.aplicado else Resposta.ok(corpo_resposta)


ROTAS = [
    Rota("POST", "/jornadas/{id}/resolucao", registrar_resolucao, escopo="pub", nome="resolucao"),
    Rota("POST", "/jornadas/{id}/vazamento", informar_vazamento, escopo="pub", nome="vazamento"),
    Rota("POST", "/jornadas/{id}/escalar", escalar_jornada, escopo="pub", nome="escalar"),
    Rota("POST", "/jornadas/{id}/avaliacao", registrar_avaliacao, escopo="pub", nome="avaliacao"),
]
