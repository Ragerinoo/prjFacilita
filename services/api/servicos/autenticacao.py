"""Autenticação do Painel_CS: login, sessão opaca e o autenticador do roteador (Req 13).

Login (Req 13.6, 13.7, 13.8):
  * usuário inexistente e senha errada dão EXATAMENTE a mesma resposta (401
    ``credenciais_invalidas``), e o tempo é equalizado: sem usuário, a senha é verificada contra
    um hash fictício de mesmo custo;
  * 5 falhas dentro de 15 minutos bloqueiam o usuário por 15 minutos (resposta 429
    ``login_bloqueado``, com a mensagem de bloqueio temporário). Durante o bloqueio nem a senha
    certa entra e nenhuma falha nova é contada. Login válido zera as falhas ("consecutivas").
    Limite assumido do Req 13.8: só usuário que existe pode ficar bloqueado, então a mensagem de
    bloqueio é a única forma de distinguir um usuário real; o Requisito pede essa mensagem.

Sessão (Req 13.2, 13.5):
  * token opaco de 256 bits (``secrets.token_urlsafe(32)``); só o SHA-256 dele é gravado;
  * cada requisição autenticada renova a atividade (`SessoesCSRepo.renovar`); passou de 30
    minutos sem atividade, a sessão deixa de valer (401);
  * o perfil vem do cadastro do usuário a cada requisição, então rebaixar ou remover um usuário
    vale na hora.

O autenticador (`criar_autenticador`) é plugado no roteador: 401 para credencial ausente,
malformada, expirada ou encerrada; 403 para perfil sem permissão (matriz em `autorizacao.py`) ou
mutação sem ``X-Requested-With``.
"""

from __future__ import annotations

import hashlib
import math
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from core.erros import ErroApi, nao_autenticado
from repositorios.interfaces import SessoesCSRepo, UsuariosCSRepo
from repositorios.modelos import PerfilCS, SessaoCS
from servicos import senhas
from servicos.autorizacao import (
    CABECALHO_CSRF,
    decidir_acesso,
    exigir_acesso,
    exigir_cabecalho_csrf,
)

if TYPE_CHECKING:
    from core.contexto import Contexto
    from core.roteador import Rota

MAX_FALHAS: Final = 5
JANELA_FALHAS: Final = timedelta(minutes=15)
DURACAO_BLOQUEIO: Final = timedelta(minutes=15)
INATIVIDADE_MAXIMA: Final = timedelta(minutes=30)

TAMANHO_TOKEN_BYTES: Final = 32  # 256 bits
COOKIE_SESSAO: Final = "tres_cs_sessao"
CAMINHO_COOKIE: Final = "/api/cs"
_FORMATO_TOKEN: Final = re.compile(r"^[A-Za-z0-9_-]{43}$")  # base64 url-safe de 32 bytes

LIMITE_USUARIO: Final = 64
LIMITE_SENHA: Final = 1024  # evita pedir hash de uma "senha" gigante

MENSAGEM_CREDENCIAIS: Final = "Usuário ou senha inválidos."
MENSAGEM_BLOQUEIO: Final = (
    "Acesso temporariamente bloqueado por excesso de tentativas. "
    "Tente de novo em {minutos} minutos."
)


@dataclass(frozen=True, slots=True)
class UsuarioAutenticado:
    """Quem está na sessão (vai em `Contexto.usuario`). Sem senha, sem token."""

    usuario: str
    perfil: PerfilCS
    deve_trocar_senha: bool
    token_hash: str


@dataclass(frozen=True, slots=True)
class ResultadoLogin:
    token: str  # valor do cookie; é a única vez que o token em claro existe
    usuario: UsuarioAutenticado


def credenciais_invalidas() -> ErroApi:
    return ErroApi(401, "credenciais_invalidas", MENSAGEM_CREDENCIAIS)


def login_bloqueado(ate: datetime, agora: datetime) -> ErroApi:
    segundos = max(1, math.ceil((ate - agora).total_seconds()))
    minutos = max(1, math.ceil(segundos / 60))
    return ErroApi(
        429,
        "login_bloqueado",
        MENSAGEM_BLOQUEIO.format(minutos=minutos),
        cabecalhos={"Retry-After": str(segundos)},
    )


def normalizar_usuario(usuario: object) -> str | None:
    """Nome de usuário em minúsculas e sem espaços nas pontas; None se não for utilizável."""
    if not isinstance(usuario, str):
        return None
    nome = usuario.strip().lower()
    return nome if 0 < len(nome) <= LIMITE_USUARIO else None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def gerar_token() -> str:
    return secrets.token_urlsafe(TAMANHO_TOKEN_BYTES)


def cookie_sessao(token: str) -> str:
    """Set-Cookie da sessão. Sem `Max-Age`: o servidor expira a sessão (30 min deslizantes)."""
    return f"{COOKIE_SESSAO}={token}; Path={CAMINHO_COOKIE}; HttpOnly; Secure; SameSite=Strict"


def cookie_sessao_expirado() -> str:
    return (
        f"{COOKIE_SESSAO}=; Path={CAMINHO_COOKIE}; Max-Age=0; "
        "Expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly; Secure; SameSite=Strict"
    )


class ServicoAutenticacao:
    def __init__(self, usuarios: UsuariosCSRepo, sessoes: SessoesCSRepo) -> None:
        self._usuarios = usuarios
        self._sessoes = sessoes

    # -- login --------------------------------------------------------------------------------
    def login(self, usuario: object, senha: object, agora: datetime) -> ResultadoLogin:
        nome = normalizar_usuario(usuario)
        texto = senha if isinstance(senha, str) and 0 < len(senha) <= LIMITE_SENHA else None
        registro = self._usuarios.obter(nome) if nome else None

        if nome is None or registro is None or texto is None:
            # Mesmo custo de uma verificação real: o tempo não diz se o usuário existe.
            senhas.verificar(texto or "", senhas.hash_ficticio())
            raise credenciais_invalidas()
        senha = texto

        if registro.bloqueado_ate is not None and registro.bloqueado_ate > agora:
            raise login_bloqueado(registro.bloqueado_ate, agora)
        # Bloqueio cumprido: as falhas que o causaram (todas com mais de 15 minutos) saem da
        # janela em `registrar_falha`, então a contagem recomeça sozinha.

        if not senhas.verificar(senha, registro.hash_senha):
            atualizado = self._usuarios.registrar_falha(nome, agora, JANELA_FALHAS)
            if len(atualizado.falhas) >= MAX_FALHAS:
                ate = agora + DURACAO_BLOQUEIO
                self._usuarios.bloquear(nome, ate)
                raise login_bloqueado(ate, agora)
            raise credenciais_invalidas()

        if registro.falhas:
            self._usuarios.limpar_falhas(nome)
        if senhas.precisa_rehash(registro.hash_senha):
            self._usuarios.definir_senha(
                nome, senhas.gerar_hash(senha), deve_trocar_senha=registro.deve_trocar_senha
            )

        token = gerar_token()
        token_hash = hash_token(token)
        self._sessoes.criar(
            SessaoCS(
                token_hash=token_hash,
                usuario=nome,
                perfil=registro.perfil,
                ultima_atividade=agora,
                ttl=int((agora + INATIVIDADE_MAXIMA).timestamp()),
            )
        )
        return ResultadoLogin(
            token,
            UsuarioAutenticado(nome, registro.perfil, registro.deve_trocar_senha, token_hash),
        )

    # -- sessão -------------------------------------------------------------------------------
    def autenticar(self, token: str | None, agora: datetime) -> UsuarioAutenticado:
        """Valida e renova a sessão. 401 se ausente, malformada, expirada ou encerrada."""
        if not token or not _FORMATO_TOKEN.match(token):
            raise nao_autenticado()
        token_hash = hash_token(token)
        sessao = self._sessoes.renovar(token_hash, agora, INATIVIDADE_MAXIMA)
        if sessao is None:
            raise nao_autenticado()
        registro = self._usuarios.obter(sessao.usuario)
        if registro is None:
            self._sessoes.encerrar(token_hash)
            raise nao_autenticado()
        return UsuarioAutenticado(
            registro.usuario, registro.perfil, registro.deve_trocar_senha, token_hash
        )

    def logout(self, token: str | None) -> bool:
        """Encerra a sessão. Idempotente: token inválido ou já encerrado devolve False."""
        if not token or not _FORMATO_TOKEN.match(token):
            return False
        return self._sessoes.encerrar(hash_token(token))


def criar_autenticador() -> Any:
    """Autenticador para `Roteador`: `(ctx, rota) -> UsuarioAutenticado` ou `ErroApi` 401/403."""

    def autenticador(ctx: Contexto, rota: Rota) -> UsuarioAutenticado:
        servico = ServicoAutenticacao(ctx.repos.usuarios_cs, ctx.repos.sessoes)
        usuario = servico.autenticar(ctx.req.cookies.get(COOKIE_SESSAO), ctx.app.agora())
        exigir_acesso(decidir_acesso(True, usuario.perfil, rota.metodo, rota.caminho, rota.perfis))
        exigir_cabecalho_csrf(rota.metodo, ctx.req.cabecalho(CABECALHO_CSRF))
        return usuario

    return autenticador
