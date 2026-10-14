"""Rotas do Painel_CS de fechamento do ciclo: encerrar o Chamado e alimentar o Cache_Respostas
(Req 16.1 a 16.8). Exigem sessão (atendente ou gestor).

Formas das requisições e respostas (consumidas pelo front-end, tarefa 15.4)
===========================================================================

``POST /api/cs/chamados/{numero}/encerrar`` -> 200 | 404 | 409 | 422
    Corpo: ``{"desfecho": "falso_defeito" | "defeito_real",
    "solucao_tipo": "instrução do manual" | "outra", "solucao": str (1 a 500)}``.
    (``"falso defeito"``/``"defeito real"`` com espaço também são aceitos.)
    Desfecho/tipo ausentes ou inválidos e solução vazia/longa -> 422 com ``campos``
    (``desfecho``, ``tipo_solucao``, ``descricao_solucao``); o Chamado continua aberto e nada é
    gravado (Req 16.6). Chamado já encerrado -> 409 ``chamado_encerrado`` (o primeiro vence).
    Sucesso: ``{"numero", "status": "encerrado", "desfecho", "solucao_tipo", "solucao",
    "em": ISO, "por": usuario, "oferecer_cache": bool}``. ``oferecer_cache`` é verdadeiro para
    "falso defeito" resolvido com "instrução do manual" (Req 16.2): o front então oferece
    "Adicionar ao Cache_Respostas". A Jornada é marcada como resolvida na camada ``humano`` com o
    Desfecho pela porta de encerramento (fila SQS; Req 16.4). Falha dessa porta NÃO desfaz o
    encerramento do Chamado: no modo local ou sem fila, grava direto (idempotente).

``POST /api/cs/cache`` -> 201 | 200 | 404 | 422 | 503
    Corpo: ``{"numero": "TRES-...", "pergunta": str (1 a 300), "resposta": str (1 a 1000)}``.
    O modelo vem da Jornada do Chamado (a entrada fica vinculada ao modelo, Req 16.3); o
    aprovador e a data/hora vêm da sessão e do relógio do servidor. Pergunta ou resposta
    vazia/longa -> 422 (``pergunta``/``resposta``); texto com Dados_Pessoais (telefone, CPF,
    e-mail, CEP) -> 422 no campo correspondente (nada é gravado e o front preserva os textos).
    Chamado sem modelo -> 422 (``numero``). Falha do armazenamento -> 503 ``cache_indisponivel``.
    Em nenhum caso o Chamado é reaberto (Req 16.7).
    Criada: 201 ``{"criada": true, "ja_existe": false, "chave", "modelo_id", "aprovador_id",
    "aprovado_em": ISO}``. Já existe (mesmo modelo e pergunta normalizada): 200
    ``{"criada": false, "ja_existe": true, "aviso": "...", "chave", ...}`` com a entrada
    EXISTENTE inalterada (Req 16.8).
"""

from __future__ import annotations

from typing import Any, Final

from core.contexto import Contexto
from core.erros import ErroApi, nao_encontrado, validacao
from core.http import Resposta
from core.roteador import Rota
from core.validacao import exigir_objeto
from dominio import (
    EntradaCache,
    ErroCampo,
    StatusInsercao,
    chave_cache,
    validar_encerramento,
    validar_entrada_cache,
)
from dominio.pii import mascarar_pii
from repositorios.erros import ErroRepositorio
from repositorios.modelos import Chamado, EncerramentoChamado

AVISO_JA_EXISTE: Final = "Já existe uma resposta para esta pergunta neste modelo. Nada foi alterado."


def _obter(ctx: Contexto) -> Chamado:
    chamado = ctx.repos.chamados.obter(ctx.req.params["numero"])
    if chamado is None:
        raise nao_encontrado("Chamado não encontrado.")
    return chamado


def _texto(corpo: Any, campo: str) -> Any:
    return corpo.get(campo)


def _desfecho_canonico(valor: Any) -> str | None:
    """`falso_defeito` (modelo/fila) a partir de `falso_defeito` ou `falso defeito` (domínio)."""
    return valor.strip().replace("_", " ") if isinstance(valor, str) else None


def _registrar_na_jornada(ctx: Contexto, chamado: Chamado, desfecho: str) -> None:
    """Marca a Jornada como resolvida na camada humano (Req 16.4). Nunca levanta."""
    try:
        jornada = ctx.repos.jornadas.obter(chamado.jornada_id)
        problema_id = jornada.problema_id if jornada is not None else None
        enfileirado = False
        if ctx.app.encerrador is not None:
            enfileirado = ctx.app.encerrador.encerrar_jornada(
                chamado.jornada_id,
                "humano",
                problema_id=problema_id,
                desfecho=desfecho,
                em=ctx.app.agora(),
            ).enfileirado
        if ctx.app.modo == "local" or not enfileirado:
            # Local não tem consumidor da fila; sem fila, grava direto (idempotente, Req 17.1).
            ctx.repos.jornadas.encerrar(
                chamado.jornada_id,
                "humano",
                ctx.app.agora(),
                problema_id=problema_id,
                desfecho=desfecho,
            )
    except Exception as exc:  # noqa: BLE001 - o registro nunca desfaz o encerramento (Req 17.12)
        ctx.log.erro("encerramento_humano_falhou", numero=chamado.numero, erro=exc)


def encerrar(ctx: Contexto) -> dict[str, Any]:
    chamado = _obter(ctx)
    corpo = exigir_objeto(ctx.json())
    desfecho_dominio = _desfecho_canonico(_texto(corpo, "desfecho"))
    tipo = _texto(corpo, "solucao_tipo")
    solucao = _texto(corpo, "solucao")
    resultado = validar_encerramento(desfecho_dominio, tipo, solucao)
    if not resultado.aceita:
        raise validacao(resultado.erros)
    assert isinstance(solucao, str) and desfecho_dominio is not None
    desfecho = desfecho_dominio.replace(" ", "_")
    agora = ctx.app.agora()
    encerramento = EncerramentoChamado(
        desfecho=desfecho,  # type: ignore[arg-type]
        solucao_tipo=tipo,
        solucao=solucao,
        em=agora,
        por=ctx.usuario.usuario,
    )
    r = ctx.repos.chamados.encerrar(chamado.numero, encerramento)
    if not r.aplicado:
        raise ErroApi(409, "chamado_encerrado", "Este Chamado já foi encerrado.")
    ctx.log.info("chamado_encerrado", numero=chamado.numero, usuario_id=ctx.usuario.usuario)
    _registrar_na_jornada(ctx, chamado, desfecho)
    return {
        "numero": chamado.numero,
        "status": "encerrado",
        "desfecho": desfecho,
        "solucao_tipo": tipo,
        "solucao": solucao,
        "em": agora.isoformat(),
        "por": ctx.usuario.usuario,
        "oferecer_cache": desfecho == "falso_defeito" and tipo == "instrução do manual",
    }


def adicionar_cache(ctx: Contexto) -> Resposta:
    corpo = exigir_objeto(ctx.json())
    numero = corpo.get("numero")
    if not isinstance(numero, str) or not numero:
        raise validacao([ErroCampo("numero", "Informe o número do Chamado.")])
    chamado = ctx.repos.chamados.obter(numero)
    if chamado is None:
        raise nao_encontrado("Chamado não encontrado.")
    pergunta = corpo.get("pergunta")
    resposta = corpo.get("resposta")
    erros: list[ErroCampo] = []
    if not isinstance(pergunta, str) or not isinstance(resposta, str):
        if not isinstance(pergunta, str):
            erros.append(ErroCampo("pergunta", "A pergunta não pode ficar vazia."))
        if not isinstance(resposta, str):
            erros.append(ErroCampo("resposta", "A resposta não pode ficar vazia."))
        raise validacao(erros)
    erros.extend(validar_entrada_cache(pergunta, resposta).erros)
    for campo, texto in (("pergunta", pergunta), ("resposta", resposta)):
        if texto and mascarar_pii(texto) != texto:
            erros.append(
                ErroCampo(campo, "Remova dados pessoais (telefone, CPF, e-mail ou CEP) do texto.")
            )
    modelo_id: str | None = None
    try:
        jornada = ctx.repos.jornadas.obter(chamado.jornada_id)
        modelo_id = jornada.modelo_id if jornada is not None else None
    except ErroRepositorio as exc:
        ctx.log.erro("cache_sem_jornada", numero=chamado.numero, erro=exc)
        raise ErroApi(
            503, "cache_indisponivel", "Não foi possível salvar agora. Tente de novo."
        ) from exc
    if modelo_id is None:
        erros.append(ErroCampo("numero", "Este Chamado não tem modelo de máquina associado."))
    if erros:
        raise validacao(erros)
    assert modelo_id is not None
    agora = ctx.app.agora()
    entrada = EntradaCache(
        modelo_id=modelo_id,
        pergunta=pergunta,
        resposta=resposta,
        aprovador_id=ctx.usuario.usuario,
        aprovado_em=agora,
    )
    try:
        resultado = ctx.repos.cache.inserir(entrada)
    except ErroRepositorio as exc:
        ctx.log.erro("cache_insercao_falhou", numero=chamado.numero, erro=exc)
        raise ErroApi(
            503,
            "cache_indisponivel",
            "Não foi possível salvar no cache agora. O Chamado continua encerrado; tente de novo.",
        ) from exc
    chave = chave_cache(modelo_id, pergunta)
    if resultado.status is StatusInsercao.DUPLICADA:
        ex = resultado.entrada
        return Resposta.ok(
            {
                "criada": False,
                "ja_existe": True,
                "aviso": AVISO_JA_EXISTE,
                "chave": chave,
                "modelo_id": modelo_id,
                "aprovador_id": ex.aprovador_id if ex else None,
                "aprovado_em": ex.aprovado_em.isoformat() if ex and ex.aprovado_em else None,
            }
        )
    if not resultado.aceita:  # sem aprovador: não ocorre com sessão válida; nunca grava
        raise ErroApi(422, "validacao", "Entrada sem aprovador não é aceita.")
    ctx.log.info("cache_adicionado", numero=chamado.numero, usuario_id=ctx.usuario.usuario)
    return Resposta.criado(
        {
            "criada": True,
            "ja_existe": False,
            "chave": chave,
            "modelo_id": modelo_id,
            "aprovador_id": ctx.usuario.usuario,
            "aprovado_em": agora.isoformat(),
        }
    )


ROTAS = [
    Rota("POST", "/chamados/{numero}/encerrar", encerrar, escopo="cs", nome="cs_encerrar"),
    Rota("POST", "/cache", adicionar_cache, escopo="cs", nome="cs_cache"),
]
