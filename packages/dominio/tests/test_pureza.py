"""Regra de pureza do pacote `dominio` (Req 20.5).

O domínio não pode importar `boto3` (nem `botocore`) nem usar rede.
Duas verificações complementares:
  1. Estática: varre o AST de todos os módulos em `src/dominio`.
  2. Dinâmica: importa o pacote num processo limpo e confere `sys.modules`.
"""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

RAIZ_PACOTE = Path(__file__).resolve().parents[1] / "src" / "dominio"

# Módulos de AWS e de rede que o domínio nunca pode importar.
PROIBIDOS = frozenset(
    {
        "boto3",
        "botocore",
        "aiobotocore",
        "requests",
        "httpx",
        "urllib3",
        "aiohttp",
        "socket",
        "ssl",
        "http.client",
        "urllib.request",
        "ftplib",
        "smtplib",
        "telnetlib",
        "xmlrpc.client",
    }
)

# Subconjunto verificado em tempo de execução (módulos que não são carregados
# de forma transitiva pela biblioteca padrão num `import dominio`).
PROIBIDOS_EM_EXECUCAO = ("boto3", "botocore", "requests", "httpx", "urllib3", "aiohttp")


def _eh_proibido(nome: str) -> bool:
    return any(nome == p or nome.startswith(p + ".") for p in PROIBIDOS)


def importacoes_proibidas(codigo: str) -> list[str]:
    """Devolve os módulos proibidos importados por `codigo` (inclui imports dinâmicos)."""
    achados: list[str] = []
    for no in ast.walk(ast.parse(codigo)):
        if isinstance(no, ast.Import):
            achados += [a.name for a in no.names if _eh_proibido(a.name)]
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            if _eh_proibido(no.module):
                achados.append(no.module)
            # `from urllib import request` / `from http import client`
            achados += [
                f"{no.module}.{a.name}" for a in no.names if _eh_proibido(f"{no.module}.{a.name}")
            ]
        elif isinstance(no, ast.Call):
            # __import__("boto3") / importlib.import_module("boto3")
            func = no.func
            nome_func = getattr(func, "id", None) or getattr(func, "attr", None)
            if nome_func in {"__import__", "import_module"} and no.args:
                arg = no.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    if _eh_proibido(arg.value):
                        achados.append(arg.value)
    return achados


def _modulos_do_dominio() -> list[Path]:
    return sorted(RAIZ_PACOTE.rglob("*.py"))


def test_pacote_dominio_existe() -> None:
    assert (RAIZ_PACOTE / "__init__.py").is_file()


@pytest.mark.parametrize(
    "modulo", _modulos_do_dominio(), ids=lambda p: str(p.relative_to(RAIZ_PACOTE))
)
def test_modulo_nao_importa_boto3_nem_rede(modulo: Path) -> None:
    achados = importacoes_proibidas(modulo.read_text(encoding="utf-8"))
    assert achados == [], f"{modulo.name} importa módulos proibidos: {achados}"


def test_importar_dominio_nao_carrega_boto3_nem_clientes_de_rede() -> None:
    script = (
        "import sys, pkgutil, importlib, dominio\n"
        "for m in pkgutil.walk_packages(dominio.__path__, 'dominio.'):\n"
        "    importlib.import_module(m.name)\n"
        f"proibidos = {PROIBIDOS_EM_EXECUCAO!r}\n"
        "carregados = sorted(n for n in sys.modules "
        "if any(n == p or n.startswith(p + '.') for p in proibidos))\n"
        "print(','.join(carregados))\n"
    )
    resultado = subprocess.run(
        [sys.executable, "-c", script],
        cwd=RAIZ_PACOTE.parents[1],
        env={"PYTHONPATH": str(RAIZ_PACOTE.parent), "PATH": ""},
        capture_output=True,
        text=True,
        check=True,
    )
    assert resultado.stdout.strip() == "", f"Módulos proibidos carregados: {resultado.stdout}"


# --- O detector em si precisa funcionar, senão a regra de pureza seria vácua. ---


@pytest.mark.parametrize(
    "codigo",
    [
        "import boto3",
        "import boto3.session as s",
        "from boto3 import client",
        "from botocore.exceptions import ClientError",
        "import requests",
        "import socket",
        "from urllib import request",
        "import urllib.request",
        "__import__('boto3')",
        "import importlib\nimportlib.import_module('botocore')",
    ],
)
def test_detector_encontra_importacoes_proibidas(codigo: str) -> None:
    assert importacoes_proibidas(codigo) != []


@given(st.sampled_from(["json", "re", "hashlib", "unicodedata", "dataclasses", "enum", "typing"]))
def test_detector_aceita_biblioteca_padrao_pura(modulo: str) -> None:
    assert importacoes_proibidas(f"import {modulo}") == []
