"""Rotas de sessão do Painel_CS: ``POST /api/cs/login``, ``POST /api/cs/logout`` e
``GET /api/cs/sessao`` (Req 13.1 a 13.8).

  * login e logout não exigem sessão (`autenticada=False`), mas, como toda mutação do CS, exigem
    o cabeçalho ``X-Requested-With``;
  * ``/sessao`` passa pelo autenticador: serve ao front-end para saber, ao abrir o Painel, se há
    sessão viva (401 manda para o login), qual é o perfil (esconder métricas do Atendente) e se
    a troca de senha é obrigatória.
"""

from __future__ import annotations

from typing import Any

from core.contexto import Contexto
from core.erros import ErroApi
from core.http import Resposta
from core.roteador import Rota
from core.validacao import exigir_objeto
from servicos.autenticacao import (
    COOKIE_SESSAO,
    INATIVIDADE_MAXIMA,
    ServicoAutenticacao,
    UsuarioAutenticado,
    cookie_sessao,
    cookie_sessao_expirado,
)
from servicos.autorizacao import CABECALHO_CSRF, exigir_cabecalho_csrf


def _servico(ctx: Contexto) -> ServicoAutenticacao:
    return ServicoAutenticacao(ctx.repos.usuarios_cs, ctx.repos.sessoes)


def _corpo_sessao(usuario: UsuarioAutenticado) -> dict[str, Any]:
    return {
        "usuario": usuario.usuario,
        "perfil": usuario.perfil,
        "deve_trocar_senha": usuario.deve_trocar_senha,
        "inatividade_maxima_s": int(INATIVIDADE_MAXIMA.total_seconds()),
    }


def login(ctx: Contexto) -> Resposta:
    exigir_cabecalho_csrf(ctx.req.metodo, ctx.req.cabecalho(CABECALHO_CSRF))
    corpo = exigir_objeto(ctx.json())
    try:
        resultado = _servico(ctx).login(corpo.get("usuario"), corpo.get("senha"), ctx.app.agora())
    except ErroApi as erro:
        # Nada do que o usuário digitou entra no log: só o código do motivo.
        ctx.log.aviso("login_recusado", codigo=erro.codigo)
        raise
    ctx.log.info("login_ok", usuario_id=resultado.usuario.usuario)
    return Resposta(200, _corpo_sessao(resultado.usuario), cookies=[cookie_sessao(resultado.token)])


def logout(ctx: Contexto) -> Resposta:
    exigir_cabecalho_csrf(ctx.req.metodo, ctx.req.cabecalho(CABECALHO_CSRF))
    _servico(ctx).logout(ctx.req.cookies.get(COOKIE_SESSAO))
    # Sempre 204 e cookie expirado: idempotente, não revela se a sessão ainda existia.
    return Resposta(204, cookies=[cookie_sessao_expirado()])


def sessao(ctx: Contexto) -> dict[str, Any]:
    return _corpo_sessao(ctx.usuario)


ROTAS = [
    Rota("POST", "/login", login, escopo="cs", autenticada=False, nome="cs_login"),
    Rota("POST", "/logout", logout, escopo="cs", autenticada=False, nome="cs_logout"),
    Rota("GET", "/sessao", sessao, escopo="cs", nome="cs_sessao"),
]
