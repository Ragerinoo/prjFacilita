"""Rotas públicas do Guia_Diagnostico: instrução e eventos (Req 3.3, 3.5, 3.6, 3.9 a 3.12, 17.8).

  * ``GET /jornadas/{id}/instrucao?problema_id=&variante=`` devolve
    ``{"instrucao": {modelo_id, problema_id, variante, passos: [{n, texto, alt,
    texto_equivalente, midia_url?, midia_tipo?, midia_estatica_url?}]}}``. É determinístico
    (mesma Jornada, problema e variante dão sempre os mesmos passos, sem IA). ``variante`` vale
    ``padrao`` (omitida) ou ``externo`` (Vazamento externo, Req 3.11). Sem instrução para o
    modelo da Jornada (ou Jornada sem modelo), a resposta é 404 funcional ``nao_encontrado`` e a
    Jornada não é alterada (Req 3.10). ``problema_id`` ou ``variante`` malformados são 422.
  * ``POST /jornadas/{id}/eventos`` ``{tipo: selecionado|exibido|concluido, problema_id,
    passo?, ocorrido_em, evento_id, variante?}`` registra o evento do guia com problema, passo,
    tipo e horário (Req 3.9). É idempotente por ``evento_id`` / ``Idempotency-Key``: o reenvio
    da fila do navegador (Req 3.12) devolve 200 sem repetir efeitos; a primeira vez devolve 201.

Como o evento é gravado (``eventos``, ``dados`` sempre sem PII):

  * ``selecionado`` -> ``tipo="selecionado"``, ``dados={problema_id}``. Define o problema atual
    da Jornada e, SÓ quando é a primeira seleção daquele problema na Jornada, soma 1 em
    ``problema_sel#<id>`` no agregado do dia (UTC, Req 17.8).
  * ``exibido`` -> ``tipo="exibido"``, ``dados={problema_id, passo_n}``.
  * ``concluido`` -> persistido como ``tipo="passo_concluido"`` (contrato do histórico "já
    tentado" do Pacote, `servicos/escalada.py`): ``dados={problema_id, passo_n, passo, camada:
    "guia", resultado: "sem resposta"}``, onde ``passo`` é o TEXTO do passo, resolvido aqui no
    servidor a partir da instrução (se não houver, o campo é omitido e o item é ignorado no
    Pacote). O ``resultado`` real ("Sim/Não") é registrado em ``/resolucao``.

O horário do evento (``em``) é o ``ocorrido_em`` do cliente (com fuso; instante no futuro é
reduzido ao horário do servidor). Todo evento novo também conta como interação da Jornada.
Jornada encerrada não muda mais (Req 17.2): responde 409.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Final

from core.contexto import Contexto
from core.erros import conflito, nao_encontrado, validacao
from core.http import Resposta
from core.idempotencia import ulid_da_chave
from core.roteador import Rota
from core.validacao import Validador, exigir_objeto
from dominio import ErroCampo
from dominio.guia import VARIANTE_PADRAO, VARIANTES
from dominio.metricas import PREFIXO_PROBLEMA_SEL
from repositorios.ids import eh_ulid, novo_ulid
from repositorios.modelos import Evento, Jornada
from servicos.envelope_jornada import envelope_jornada
from servicos.guia import PROBLEMA_MAX, PROBLEMA_MIN, instrucao_publica, texto_do_passo

TIPOS_CLIENTE: Final = ("selecionado", "exibido", "concluido")
TIPO_PASSO_CONCLUIDO: Final = "passo_concluido"  # contrato com servicos/escalada.py
MAX_PASSO: Final = 10  # Req 3.3
_INTEIRO: Final = re.compile(r"\d{1,6}")


def _jornada_ou_404(ctx: Contexto) -> Jornada:
    jornada = ctx.repos.jornadas.obter(ctx.req.params["id"])
    if jornada is None:
        raise nao_encontrado("Jornada não encontrada.")
    return jornada


def obter_instrucao(ctx: Contexto) -> Resposta:
    jornada = _jornada_ou_404(ctx)
    bruto_problema = ctx.req.consulta.get("problema_id")
    variante = ctx.req.consulta.get("variante") or VARIANTE_PADRAO
    erros: list[ErroCampo] = []
    if bruto_problema is None:
        erros.append(ErroCampo("problema_id", "é obrigatório"))
    elif not _INTEIRO.fullmatch(bruto_problema):
        erros.append(ErroCampo("problema_id", "deve ser um número inteiro"))
    if variante not in VARIANTES:
        erros.append(ErroCampo("variante", f"deve ser uma de: {', '.join(VARIANTES)}"))
    if erros:
        raise validacao(erros)
    assert bruto_problema is not None
    problema_id = int(bruto_problema)

    instrucao = instrucao_publica(ctx.repos, jornada.modelo_id, problema_id, variante)
    if instrucao is None:
        # Req 3.10: sem instrução para este modelo. A Jornada fica intacta.
        raise nao_encontrado("Não há instrução disponível para este modelo e problema.")
    return Resposta.ok({"instrucao": instrucao})


def _instante(valor: str | None, agora: datetime, erros: list[ErroCampo]) -> datetime:
    """`ocorrido_em` em UTC (com segundos, Req 3.9); no futuro, vale o horário do servidor."""
    if valor is None:
        return agora
    try:
        instante = datetime.fromisoformat(valor)
    except ValueError:
        erros.append(ErroCampo("ocorrido_em", "deve ser data e hora ISO 8601"))
        return agora
    if instante.tzinfo is None or instante.utcoffset() is None:
        erros.append(ErroCampo("ocorrido_em", "deve informar o fuso horário"))
        return agora
    return min(instante.astimezone(UTC), agora)


def _evento_id(ctx: Contexto, corpo: Any, agora: datetime) -> str:
    chave = ctx.chave_idempotencia(corpo)
    if chave is None:
        return novo_ulid(agora)
    return chave if eh_ulid(chave) else ulid_da_chave(f"guia:{chave}")


def registrar_evento(ctx: Contexto) -> Resposta:
    corpo = exigir_objeto(ctx.json())
    validador = Validador(corpo)
    tipo = validador.escolha("tipo", TIPOS_CLIENTE)
    problema_id = validador.inteiro("problema_id", minimo=PROBLEMA_MIN, maximo=PROBLEMA_MAX)
    exige_passo = tipo in ("exibido", "concluido")
    passo = validador.inteiro("passo", obrigatorio=exige_passo, minimo=1, maximo=MAX_PASSO)
    variante = validador.escolha("variante", VARIANTES, obrigatorio=False)
    ocorrido_em = validador.texto("ocorrido_em", maximo=64)
    agora = ctx.app.agora()
    em = _instante(ocorrido_em, agora, validador.erros)
    validador.levantar_se_erros()
    assert tipo is not None and problema_id is not None

    jornada = _jornada_ou_404(ctx)
    if jornada.estado == "encerrada":
        raise conflito("Esta jornada já foi encerrada.")

    dados: dict[str, Any] = {"problema_id": problema_id}
    tipo_gravado = tipo
    if tipo != "selecionado":
        assert passo is not None
        dados["passo_n"] = passo
    if tipo == "concluido":
        tipo_gravado = TIPO_PASSO_CONCLUIDO
        texto = texto_do_passo(ctx.repos, jornada.modelo_id, problema_id, passo or 0, variante)
        if texto:
            dados["passo"] = texto
        dados["camada"] = "guia"
        dados["resultado"] = "sem resposta"

    novo = ctx.repos.eventos.registrar(
        Evento(
            jornada_id=jornada.jornada_id,
            evento_id=_evento_id(ctx, corpo, agora),
            tipo=tipo_gravado,
            em=em,
            dados=dados,
        )
    )
    if not novo:
        # Reenvio da fila (Req 3.12): o evento original permanece e nada se repete.
        return Resposta.ok({"registrado": False, "jornada": envelope_jornada(jornada)})

    if tipo == "selecionado" and ctx.repos.jornadas.registrar_problema_selecionado(
        jornada.jornada_id, problema_id
    ):
        # Só na primeira seleção do problema na Jornada (Req 17.8).
        metrica = f"{PREFIXO_PROBLEMA_SEL}{problema_id}"
        ctx.repos.agregados.incrementar(agora.astimezone(UTC).date(), metrica)
    atualizada = ctx.repos.jornadas.registrar_interacao(jornada.jornada_id, agora)
    ctx.log.info(
        "evento_guia_registrado",
        jornada_id=jornada.jornada_id,
        tipo=tipo_gravado,
        problema_id=problema_id,
        passo=passo,
    )
    return Resposta.criado({"registrado": True, "jornada": envelope_jornada(atualizada)})


ROTAS = [
    Rota("GET", "/jornadas/{id}/instrucao", obter_instrucao, escopo="pub", nome="obter_instrucao"),
    Rota("POST", "/jornadas/{id}/eventos", registrar_evento, escopo="pub", nome="registrar_evento"),
]
