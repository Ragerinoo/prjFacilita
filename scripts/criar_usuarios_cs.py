#!/usr/bin/env python3
"""Cria os usuários iniciais do Painel_CS (Req 13, 20.5).

A senha inicial vem SOMENTE da variável de ambiente ``CS_SENHA_INICIAL`` (nunca de argumento de
linha de comando, arquivo versionado ou prompt gravado). O script não imprime nem registra a
senha nem o hash. Cada usuário nasce com ``deve_trocar_senha=True`` (troca forçada no primeiro
acesso) e o hash é Argon2id (ou scrypt, se o Argon2id não existir no ambiente), o mesmo
algoritmo do login (`servicos/senhas.py`).

Idempotente e sem efeito destrutivo: usuário que já existe NÃO é alterado (a senha dele não é
redefinida); o script só informa que ele já existia.

Uso:

    export CS_SENHA_INICIAL='...'          # mínimo de 12 caracteres
    python scripts/criar_usuarios_cs.py [--prefixo tres] [--regiao sa-east-1] \
        [--usuario ana:atendente] [--usuario bruno:gestor]

Sem ``--usuario``, cria ``atendente`` (perfil atendente) e ``gestor`` (perfil gestor), úteis
para a demo. As credenciais AWS vêm da cadeia padrão do boto3. Variáveis lidas (só nomes):
``CS_SENHA_INICIAL``, ``TRES_PREFIXO_TABELAS``, ``AWS_REGION``.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_RAIZ = Path(__file__).resolve().parent.parent
# O script roda fora de um pacote instalado: resolve a API e o domínio pelo repositório.
for _caminho in (_RAIZ / "services" / "api", _RAIZ / "packages" / "dominio" / "src"):
    if str(_caminho) not in sys.path:
        sys.path.insert(0, str(_caminho))

from repositorios.interfaces import UsuariosCSRepo  # noqa: E402
from repositorios.modelos import UsuarioCS  # noqa: E402
from servicos import senhas  # noqa: E402
from servicos.autenticacao import LIMITE_USUARIO, normalizar_usuario  # noqa: E402

VARIAVEL_SENHA = "CS_SENHA_INICIAL"
SENHA_TAMANHO_MINIMO = 12
PERFIS = ("atendente", "gestor")
USUARIOS_PADRAO: tuple[tuple[str, str], ...] = (("atendente", "atendente"), ("gestor", "gestor"))


class ErroUso(Exception):
    """Entrada inválida. A mensagem é segura para exibir (nunca contém a senha)."""


@dataclass(frozen=True)
class ResultadoUsuario:
    usuario: str
    perfil: str
    criado: bool  # False = já existia; nada foi alterado


def validar_senha_inicial(senha: str | None) -> str:
    if not senha:
        raise ErroUso(f"Defina a variável de ambiente {VARIAVEL_SENHA} com a senha inicial.")
    if len(senha) < SENHA_TAMANHO_MINIMO:
        raise ErroUso(f"{VARIAVEL_SENHA} precisa ter pelo menos {SENHA_TAMANHO_MINIMO} caracteres.")
    return senha


def interpretar_usuario(texto: str) -> tuple[str, str]:
    """``nome:perfil`` -> (nome normalizado, perfil)."""
    nome_bruto, separador, perfil = texto.partition(":")
    nome = normalizar_usuario(nome_bruto)
    if not separador or nome is None:
        raise ErroUso(
            f"Usuário inválido {texto!r}: use nome:perfil (nome de 1 a {LIMITE_USUARIO} letras)."
        )
    perfil = perfil.strip().lower()
    if perfil not in PERFIS:
        raise ErroUso(f"Perfil inválido para {nome!r}: use {' ou '.join(PERFIS)}.")
    return nome, perfil


def criar_usuarios(
    repo: UsuariosCSRepo,
    usuarios: Sequence[tuple[str, str]],
    senha: str,
    *,
    gerar_hash: Callable[[str], str] = senhas.gerar_hash,
) -> list[ResultadoUsuario]:
    """Cria cada usuário que ainda não existe, com troca de senha obrigatória.

    Valida tudo antes de gravar qualquer coisa. O hash é calculado só para quem será criado.
    """
    for _, perfil in usuarios:
        if perfil not in PERFIS:
            raise ErroUso(f"Perfil inválido: use {' ou '.join(PERFIS)}.")
    resultados: list[ResultadoUsuario] = []
    for nome, perfil in usuarios:
        if repo.obter(nome) is not None:
            resultados.append(ResultadoUsuario(nome, perfil, criado=False))
            continue
        resposta = repo.criar(
            UsuarioCS(
                usuario=nome,
                hash_senha=gerar_hash(senha),
                perfil=perfil,  # type: ignore[arg-type]
                deve_trocar_senha=True,
            )
        )
        resultados.append(ResultadoUsuario(nome, perfil, criado=resposta.aplicado))
    return resultados


def _argumentos(argv: Sequence[str] | None, ambiente: Mapping[str, str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Cria os usuários iniciais do Painel_CS.")
    p.add_argument("--prefixo", default=ambiente.get("TRES_PREFIXO_TABELAS", "tres"))
    p.add_argument("--regiao", default=ambiente.get("AWS_REGION") or None)
    p.add_argument(
        "--usuario",
        action="append",
        default=[],
        metavar="NOME:PERFIL",
        help="usuário a criar (repetível); padrão: atendente:atendente e gestor:gestor",
    )
    return p.parse_args(argv)


def _repositorio_dynamodb(prefixo: str, regiao: str | None) -> UsuariosCSRepo:
    import boto3
    from repositorios.dynamodb._base import config_cliente_curta
    from repositorios.dynamodb.painel import UsuariosCSDynamoDB

    recurso = boto3.resource("dynamodb", region_name=regiao, config=config_cliente_curta())
    return UsuariosCSDynamoDB(recurso, prefixo)


def main(
    argv: Sequence[str] | None = None,
    ambiente: Mapping[str, str] | None = None,
    *,
    repo: UsuariosCSRepo | None = None,
    saida: Any = None,
) -> int:
    env = os.environ if ambiente is None else ambiente
    saida = saida or sys.stdout
    try:
        args = _argumentos(argv, env)
        senha = validar_senha_inicial(env.get(VARIAVEL_SENHA))
        usuarios = [interpretar_usuario(t) for t in args.usuario] or list(USUARIOS_PADRAO)
        if len({nome for nome, _ in usuarios}) != len(usuarios):
            raise ErroUso("Há usuários repetidos na lista.")
        alvo = repo or _repositorio_dynamodb(args.prefixo, args.regiao)
        resultados = criar_usuarios(alvo, usuarios, senha)
    except ErroUso as erro:
        print(f"Erro: {erro}", file=sys.stderr)
        return 2
    except Exception as erro:  # noqa: BLE001 - só o tipo: a mensagem pode ter dados sensíveis
        print(f"Erro ao criar usuários: {type(erro).__name__}", file=sys.stderr)
        return 1
    for r in resultados:
        situacao = "criado" if r.criado else "já existia (não alterado)"
        print(f"{r.usuario} ({r.perfil}): {situacao}", file=saida)
    if any(r.criado for r in resultados):
        print("Os usuários criados precisam trocar a senha no primeiro acesso.", file=saida)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
