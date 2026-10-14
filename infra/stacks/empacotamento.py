"""Empacotamento das Lambdas Python sem Docker (Q14, ajustes de infra da tarefa 17.1).

O pacote de cada Lambda reúne:
- o código de ``services/api`` (sem testes, caches e ``pyproject.toml``);
- o pacote puro ``dominio`` (``packages/dominio/src``), importado pela API;
- as dependências de terceiros, instaladas só como wheels binárias para a plataforma da Lambda
  (``pip install --only-binary=:all: --platform manylinux2014_<arch> --python-version 3.12``).
  Assim ``argon2-cffi`` e ``argon2-cffi-bindings`` entram sem compilar nada e na arquitetura
  certa (arm64 ou x86_64).

O empacotamento é local (``ILocalBundling``): nada de contêiner. Ele só roda quando a stack é
criada com ``empacotar_dependencias=True`` (o ``app.py`` liga por padrão); nos testes de
asserção fica desligado para não depender de rede.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

import jsii
from aws_cdk import AssetHashType, BundlingOptions, DockerImage, ILocalBundling
from aws_cdk import aws_lambda as lambda_

# Versões fixas (iguais às de ``services/agente/premissas.py``; o teste confere).
ARGON2_CFFI_VERSAO = "25.1.0"
ARGON2_CFFI_BINDINGS_VERSAO = "21.2.0"
JSONSCHEMA_VERSAO = "4.26.0"
PACOTES_PIP: tuple[str, ...] = (
    f"argon2-cffi=={ARGON2_CFFI_VERSAO}",
    f"argon2-cffi-bindings=={ARGON2_CFFI_BINDINGS_VERSAO}",
    f"jsonschema=={JSONSCHEMA_VERSAO}",
)

PLATAFORMAS_PIP = {
    "arm64": "manylinux2014_aarch64",
    "x86_64": "manylinux2014_x86_64",
}
PYTHON_LAMBDA = "3.12"

# Nunca vão para o pacote da Lambda (nem entram no hash do asset).
EXCLUIR = (
    "tests",
    ".venv",
    "venv",
    "__pycache__",
    "*.pyc",
    ".pytest_cache",
    ".hypothesis",
    ".ruff_cache",
    ".mypy_cache",
    "*.egg-info",
    "pyproject.toml",
    "node_modules",
    "cdk.out",
)


def _excluido(caminho: Path, raiz: Path) -> bool:
    relativo = caminho.relative_to(raiz)
    return any(
        parte == padrao or (padrao.startswith("*") and parte.endswith(padrao[1:]))
        for parte in relativo.parts
        for padrao in EXCLUIR
    )


def listar_fontes(raiz: Path) -> list[Path]:
    """Arquivos de uma árvore de código, em ordem estável, sem os itens excluídos."""
    return sorted(p for p in raiz.rglob("*") if p.is_file() and not _excluido(p, raiz))


def hash_das_fontes(raizes: Iterable[Path], extras: Sequence[str] = ()) -> str:
    """Hash do conteúdo das fontes e das versões fixadas, para o ``asset_hash``.

    Com empacotamento local o hash padrão olharia a saída do pip (e rodaria o pip a cada
    ``synth``). Este hash só muda quando o código ou as versões mudam.
    """
    resumo = hashlib.sha256()
    for raiz in raizes:
        for arquivo in listar_fontes(raiz):
            resumo.update(str(arquivo.relative_to(raiz)).encode())
            resumo.update(arquivo.read_bytes())
    for extra in extras:
        resumo.update(extra.encode())
    return resumo.hexdigest()


def comando_pip(destino: str | Path, arquitetura: str) -> list[str]:
    """Comando do pip que baixa só wheels binárias para a plataforma da Lambda."""
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--quiet",
        "--disable-pip-version-check",
        "--no-compile",
        "--only-binary=:all:",
        "--implementation",
        "cp",
        "--platform",
        PLATAFORMAS_PIP[arquitetura],
        "--python-version",
        PYTHON_LAMBDA,
        "--target",
        str(destino),
        *PACOTES_PIP,
    ]


@jsii.implements(ILocalBundling)
class EmpacotadorLocal:
    """Copia as fontes e instala as dependências binárias; falha alto se o pip falhar."""

    def __init__(self, raizes_de_codigo: Sequence[Path], arquitetura: str) -> None:
        if arquitetura not in PLATAFORMAS_PIP:
            raise ValueError(f"arquitetura desconhecida: {arquitetura}")
        self._raizes = list(raizes_de_codigo)
        self._arquitetura = arquitetura

    def copiar_fontes(self, destino: str | Path) -> None:
        destino = Path(destino)
        for raiz in self._raizes:
            for arquivo in listar_fontes(raiz):
                alvo = destino / arquivo.relative_to(raiz)
                alvo.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(arquivo, alvo)

    def try_bundle(self, output_dir: str, *, image=None, **_opcoes) -> bool:
        self.copiar_fontes(output_dir)
        # Sem ``check=False``: uma dependência faltando não pode virar um deploy quebrado.
        subprocess.run(comando_pip(output_dir, self._arquitetura), check=True)
        return True


def codigo_empacotado(
    raizes_de_codigo: Sequence[Path],
    arquitetura: str,
) -> lambda_.Code:
    """Código da Lambda com empacotamento local (a imagem do Docker nunca é usada)."""
    return lambda_.Code.from_asset(
        str(raizes_de_codigo[0]),
        asset_hash=hash_das_fontes(
            raizes_de_codigo, extras=(*PACOTES_PIP, arquitetura, PYTHON_LAMBDA)
        ),
        asset_hash_type=AssetHashType.CUSTOM,
        bundling=BundlingOptions(
            image=DockerImage.from_registry("scratch"),  # exigido pela API; não é usado
            local=EmpacotadorLocal(raizes_de_codigo, arquitetura),
        ),
    )


def codigo_simples(raiz: Path) -> lambda_.Code:
    """Só o código de ``raiz`` (sem dependências): serve para synth e testes sem rede."""
    return lambda_.Code.from_asset(str(raiz), exclude=list(EXCLUIR))
