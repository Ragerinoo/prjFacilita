"""Script `scripts/criar_usuarios_cs.py`: usuários iniciais com a senha vinda do ambiente."""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import pytest

from repositorios.memoria import criar_repositorios_memoria
from servicos import senhas

CAMINHO = Path(__file__).resolve().parents[3] / "scripts" / "criar_usuarios_cs.py"
SENHA = "senha-inicial-bem-longa-9"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("criar_usuarios_cs", CAMINHO)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo  # dataclasses precisa achar o módulo
    try:
        spec.loader.exec_module(modulo)
        yield modulo
    finally:
        sys.modules.pop(spec.name, None)


def executar(script, argv, ambiente, repo):
    saida = io.StringIO()
    codigo = script.main(argv, ambiente, repo=repo, saida=saida)
    return codigo, saida.getvalue()


def test_cria_usuarios_padrao_com_hash_forte_e_troca_obrigatoria(script, capsys):
    repo = criar_repositorios_memoria().usuarios_cs
    codigo, saida = executar(script, [], {"CS_SENHA_INICIAL": SENHA}, repo)
    assert codigo == 0
    atendente, gestor = repo.obter("atendente"), repo.obter("gestor")
    assert (atendente.perfil, gestor.perfil) == ("atendente", "gestor")
    for u in (atendente, gestor):
        assert u.deve_trocar_senha is True and u.falhas == () and u.bloqueado_ate is None
        assert SENHA not in u.hash_senha and senhas.verificar(SENHA, u.hash_senha)
        assert u.hash_senha.startswith("$argon2id$")
    # A senha e os hashes nunca saem no console.
    visto = saida + capsys.readouterr().out + capsys.readouterr().err
    assert SENHA not in visto and "$argon2" not in visto


def test_usuarios_informados_por_argumento(script):
    repo = criar_repositorios_memoria().usuarios_cs
    codigo, _ = executar(
        script, ["--usuario", "Ana:Atendente", "--usuario", "bruno:gestor"],
        {"CS_SENHA_INICIAL": SENHA}, repo,
    )  # fmt: skip
    assert codigo == 0
    assert repo.obter("ana").perfil == "atendente" and repo.obter("bruno").perfil == "gestor"
    assert repo.obter("atendente") is None


def test_idempotente_e_nao_redefine_a_senha_de_quem_ja_existe(script):
    repo = criar_repositorios_memoria().usuarios_cs
    executar(script, [], {"CS_SENHA_INICIAL": SENHA}, repo)
    antes = repo.obter("gestor")
    repo.definir_senha("gestor", senhas.gerar_hash("outra-senha-depois-da-troca"))
    codigo, saida = executar(script, [], {"CS_SENHA_INICIAL": "uma-senha-totalmente-nova"}, repo)
    assert codigo == 0 and "já existia" in saida
    depois = repo.obter("gestor")
    assert depois.hash_senha != antes.hash_senha
    assert senhas.verificar("outra-senha-depois-da-troca", depois.hash_senha)
    assert depois.deve_trocar_senha is False


@pytest.mark.parametrize("ambiente", [{}, {"CS_SENHA_INICIAL": ""}, {"CS_SENHA_INICIAL": "curta"}])
def test_senha_ausente_ou_curta_aborta_sem_criar_nada(script, capsys, ambiente):
    repo = criar_repositorios_memoria().usuarios_cs
    codigo = script.main([], ambiente, repo=repo)
    assert codigo == 2 and repo.obter("atendente") is None
    assert "curta" not in capsys.readouterr().err  # nunca ecoa o valor


@pytest.mark.parametrize(
    "argv",
    [["--usuario", "ana"], ["--usuario", "ana:admin"], ["--usuario", ":gestor"],
     ["--usuario", "ana:gestor", "--usuario", "ANA:atendente"]],
)  # fmt: skip
def test_usuario_invalido_aborta_antes_de_gravar(script, argv):
    repo = criar_repositorios_memoria().usuarios_cs
    assert script.main(argv, {"CS_SENHA_INICIAL": SENHA}, repo=repo) == 2
    assert repo.obter("ana") is None


def test_usuario_criado_pelo_script_consegue_entrar_pelo_login(script):
    from datetime import UTC, datetime

    from servicos.autenticacao import ServicoAutenticacao

    repos = criar_repositorios_memoria()
    executar(script, [], {"CS_SENHA_INICIAL": SENHA}, repos.usuarios_cs)
    agora = datetime(2025, 1, 1, tzinfo=UTC)
    resultado = ServicoAutenticacao(repos.usuarios_cs, repos.sessoes).login("gestor", SENHA, agora)
    assert resultado.usuario.perfil == "gestor" and resultado.usuario.deve_trocar_senha is True
