#!/usr/bin/env python3
"""Pré-processamento dos manuais: um arquivo por seção + metadados (Req 6.3, 20.2, 20.3).

Por quê: o ``Retrieve`` da Knowledge Base NÃO devolve o nome da seção, e o chunking FIXED_SIZE
(escolhido para o S3 Vectors) não o preserva (``services/agente/premissas.py``, Q2). Então cada
manual em Markdown é dividido em uma seção por arquivo, e cada arquivo ganha um sidecar
``<arquivo>.metadata.json`` com ``modelo_id``, ``manual`` e ``secao``. Todo trecho herda esses
metadados, e o agente monta as fontes (manual e seção) a partir deles, nunca do texto do modelo.

Layout gerado (``PREFIXO_S3_SECOES``, indexado pela Knowledge Base):

    secoes/<modelo_id>/<arquivo-do-manual>/<slug-da-secao>.md
    secoes/<modelo_id>/<arquivo-do-manual>/<slug-da-secao>.md.metadata.json

O manual inteiro continua em ``manuais/<modelo_id>/`` (``premissas.PREFIXO_S3_MANUAIS``) como
fonte da verdade e NÃO é indexado: indexá-lo duplicaria o conteúdo sem o nome da seção.

Regras da divisão (função pura, sem I/O, idempotente):

* Seção = cada título ATX (``#`` a ``######``) com texto próprio. Título que só contém
  subtítulos (por exemplo ``## 3. Painel e luzes``) não vira arquivo, mas aparece no caminho
  das seções filhas.
* O primeiro título de nível 1 é o título do documento (o nome do manual vem dos metadados).
  O texto que vem antes do primeiro subtítulo vira a seção "Introdução", exceto se tiver só
  citações (``>``), que no seed são avisos como "conteúdo de exemplo".
* Cabeçalhos dentro de blocos de código (``` ou ~~~) não contam.
* O arquivo de cada seção começa com ``# <manual> > <caminho>`` para dar contexto ao embedding.
* ``secao`` = texto do título (por exemplo ``3.1 Luz vermelha fixa``). O slug do nome do arquivo
  é derivado dele e fica estável; títulos repetidos recebem ``-2``, ``-3``...
* Os metadados nunca passam de 1 KB (limite do S3 Vectors com Knowledge Bases): ``manual`` e
  ``secao`` são truncados em fronteira de caractere UTF-8, com reticências, se for preciso.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path

_RAIZ = Path(__file__).resolve().parent.parent

# O script roda fora de um pacote instalado: resolve ``dominio`` e ``premissas`` pelo repositório.
for _caminho in (_RAIZ / "packages" / "dominio" / "src", _RAIZ / "services" / "agente"):
    if str(_caminho) not in sys.path:
        sys.path.insert(0, str(_caminho))

from dominio.qr import PADRAO_MODELO_ID, TAMANHO_MAX_MODELO_ID  # noqa: E402
from premissas import (  # noqa: E402
    S3_VECTORS_METADADOS_CHAVES_MAX,
    S3_VECTORS_METADADOS_CUSTOM_MAX_BYTES,
    sidecar_metadados,
)

# Prefixo das seções indexadas. Igual a ``infra/stacks/conhecimento_stack.PREFIXO_S3_SECOES``
# (o teste da stack confere).
PREFIXO_S3_SECOES = "secoes/"

TITULO_INTRODUCAO = "Introdução"
SLUG_PADRAO = "secao"
SLUG_MAX_CARACTERES = 60
# Teto de cada campo de texto livre dos metadados, bem abaixo de 1 KB para sobrar folga.
CAMPO_METADADO_MAX_BYTES = 240
RETICENCIAS = "…"

_TITULO = re.compile(r"^ {0,3}(#{1,6})[ \t]+(.*?)[ \t]*$")
_CERCA = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_FECHAMENTO_TITULO = re.compile(r"[ \t]+#+$")
_MARCAS_INLINE = re.compile(r"[*`]")


class ErroPreprocessamento(ValueError):
    """O manual não pôde ser dividido em seções (mensagem em pt-BR, indica o motivo)."""


@dataclass(frozen=True, slots=True)
class SecaoManual:
    """Uma seção pronta para envio: conteúdo, metadados e chaves S3 determinísticas."""

    modelo_id: str
    arquivo: str  # nome do arquivo do manual sem extensão, já como slug
    manual: str  # nome do manual (metadado), possivelmente truncado
    secao: str  # título da seção (metadado), possivelmente truncado
    slug: str
    caminho: tuple[str, ...]  # títulos do ancestral mais alto até a própria seção
    corpo: bytes
    corpo_sidecar: bytes

    @property
    def chave_s3(self) -> str:
        return f"{PREFIXO_S3_SECOES}{self.modelo_id}/{self.arquivo}/{self.slug}.md"

    @property
    def chave_sidecar(self) -> str:
        return f"{self.chave_s3}.metadata.json"


# --------------------------------------------------------------------------------------------
# Texto
# --------------------------------------------------------------------------------------------


def slugificar(texto: str, *, maximo: int = SLUG_MAX_CARACTERES) -> str:
    """``"3.1 Luz vermelha fixa"`` -> ``"3-1-luz-vermelha-fixa"`` (sem acento, a-z, 0-9, hífen)."""
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", sem_acento.lower()).strip("-")
    return slug[:maximo].strip("-") or SLUG_PADRAO


def _limpar_titulo(titulo: str) -> str:
    titulo = _FECHAMENTO_TITULO.sub("", titulo)
    titulo = _MARCAS_INLINE.sub("", titulo)
    return " ".join(titulo.split())


def _truncar_bytes(texto: str, maximo: int) -> str:
    """Corta em fronteira de caractere para caber em ``maximo`` bytes UTF-8, com reticências."""
    if len(texto.encode("utf-8")) <= maximo:
        return texto
    limite = maximo - len(RETICENCIAS.encode("utf-8"))
    cortado = texto.encode("utf-8")[:limite].decode("utf-8", errors="ignore").rstrip()
    return cortado + RETICENCIAS


def _so_citacoes(linhas: list[str]) -> bool:
    return all(not linha.strip() or linha.lstrip().startswith(">") for linha in linhas)


# --------------------------------------------------------------------------------------------
# Divisão
# --------------------------------------------------------------------------------------------


@dataclass(slots=True)
class _Bloco:
    caminho: tuple[str, ...]
    titulo: str
    linhas: list[str]


def _blocos(markdown: str) -> list[_Bloco]:
    texto = markdown.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    blocos: list[_Bloco] = [_Bloco((), TITULO_INTRODUCAO, [])]
    pilha: list[tuple[int, str]] = []  # (nível, título) dos ancestrais; o título do doc fica fora
    titulo_do_documento_visto = False
    cerca: str | None = None

    for linha in texto.split("\n"):
        achou_cerca = _CERCA.match(linha)
        if achou_cerca:
            marca = achou_cerca.group(1)
            if cerca is None:
                cerca = marca[0]
            elif marca[0] == cerca:
                cerca = None
            blocos[-1].linhas.append(linha)
            continue
        achou = _TITULO.match(linha) if cerca is None else None
        if achou is None:
            blocos[-1].linhas.append(linha)
            continue

        nivel, titulo = len(achou.group(1)), _limpar_titulo(achou.group(2))
        if not titulo:
            blocos[-1].linhas.append(linha)
            continue
        if nivel == 1 and not titulo_do_documento_visto:
            titulo_do_documento_visto = True  # nome do manual: não entra no caminho
            continue
        titulo_do_documento_visto = True
        while pilha and pilha[-1][0] >= nivel:
            pilha.pop()
        pilha.append((nivel, titulo))
        blocos.append(_Bloco(tuple(t for _, t in pilha), titulo, []))
    return blocos


def _sidecar(modelo_id: str, manual: str, secao: str) -> tuple[bytes, str, str]:
    """Sidecar em JSON compacto e os textos finais (truncados) de ``manual`` e ``secao``."""
    manual = _truncar_bytes(manual, CAMPO_METADADO_MAX_BYTES)
    secao = _truncar_bytes(secao, CAMPO_METADADO_MAX_BYTES)
    corpo = json.dumps(
        sidecar_metadados(modelo_id, manual, secao), ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    if len(corpo) > S3_VECTORS_METADADOS_CUSTOM_MAX_BYTES:  # pragma: no cover (defensivo)
        raise ErroPreprocessamento(
            f"metadados da seção '{secao}' com {len(corpo)} bytes "
            f"(limite {S3_VECTORS_METADADOS_CUSTOM_MAX_BYTES})"
        )
    return corpo, manual, secao


def dividir_manual(
    markdown: str, *, modelo_id: str, manual: str, arquivo: str
) -> list[SecaoManual]:
    """Divide um manual em Markdown em uma ``SecaoManual`` por seção com texto.

    ``manual`` é o nome legível (metadado ``manual``); ``arquivo`` é o nome do arquivo do manual
    (com ou sem extensão), usado só para compor a chave S3. Levanta ``ErroPreprocessamento`` se
    ``modelo_id`` for inválido, se ``manual`` estiver vazio ou se não houver nenhuma seção.
    """
    if (
        not isinstance(modelo_id, str)
        or len(modelo_id) > TAMANHO_MAX_MODELO_ID
        or PADRAO_MODELO_ID.fullmatch(modelo_id) is None
    ):
        raise ErroPreprocessamento("modelo_id deve ser um slug (a-z, 0-9 e hífens)")
    nome_manual = " ".join(str(manual).split())
    if not nome_manual:
        raise ErroPreprocessamento("o nome do manual (metadado 'manual') está vazio")
    pasta = slugificar(Path(arquivo).stem or str(arquivo))

    secoes: list[SecaoManual] = []
    usados: dict[str, int] = {}
    for indice, bloco in enumerate(_blocos(markdown)):
        linhas = bloco.linhas
        if indice == 0 and _so_citacoes(linhas):
            continue  # avisos antes da primeira seção não são conteúdo do manual
        texto = "\n".join(linhas).strip()
        if not texto:
            continue  # título só com subtítulos, ou seção vazia

        base = slugificar(bloco.titulo)
        usados[base] = usados.get(base, 0) + 1
        slug = base if usados[base] == 1 else f"{base}-{usados[base]}"

        cabecalho = " > ".join((nome_manual, *bloco.caminho))
        conteudo = f"# {cabecalho}\n\n{texto}\n"
        sidecar, manual_final, secao_final = _sidecar(modelo_id, nome_manual, bloco.titulo)
        secoes.append(
            SecaoManual(
                modelo_id=modelo_id,
                arquivo=pasta,
                manual=manual_final,
                secao=secao_final,
                slug=slug,
                caminho=bloco.caminho,
                corpo=conteudo.encode("utf-8"),
                corpo_sidecar=sidecar,
            )
        )
    if not secoes:
        raise ErroPreprocessamento("o manual não tem nenhuma seção com texto")
    return secoes


def preprocessar_manual_local(
    *, modelo_id: str, nome_arquivo: str, corpo: bytes, corpo_sidecar: bytes
) -> list[SecaoManual]:
    """Divide um manual do seed (conteúdo e sidecar em bytes), lendo ``manual`` do sidecar.

    Se o sidecar não trouxer ``manual``, usa o nome do arquivo sem extensão.
    """
    try:
        markdown = corpo.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ErroPreprocessamento(f"o manual não está em UTF-8: {exc}") from exc
    try:
        atributos = json.loads(corpo_sidecar).get("metadataAttributes", {})
        nome = atributos.get("manual") if isinstance(atributos, dict) else None
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError):
        nome = None
    if not isinstance(nome, str) or not nome.strip():
        nome = Path(nome_arquivo).stem
    return dividir_manual(markdown, modelo_id=modelo_id, manual=nome, arquivo=nome_arquivo)


def validar_conjunto(secoes: list[SecaoManual]) -> list[str]:
    """Confere o conjunto: chaves S3 únicas e metadados dentro dos limites do S3 Vectors."""
    erros: list[str] = []
    chaves: set[str] = set()
    for s in secoes:
        if s.chave_s3 in chaves:
            erros.append(f"chave repetida: {s.chave_s3}")
        chaves.add(s.chave_s3)
        if len(s.corpo_sidecar) > S3_VECTORS_METADADOS_CUSTOM_MAX_BYTES:
            erros.append(f"{s.chave_sidecar}: metadados acima de 1 KB")
        atributos = json.loads(s.corpo_sidecar)["metadataAttributes"]
        if len(atributos) > S3_VECTORS_METADADOS_CHAVES_MAX:
            erros.append(f"{s.chave_sidecar}: mais de {S3_VECTORS_METADADOS_CHAVES_MAX} chaves")
    return erros


# --------------------------------------------------------------------------------------------
# CLI de inspeção
# --------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Divide um manual em Markdown em uma seção por arquivo."
    )
    p.add_argument("manual", type=Path, help="arquivo .md do manual (com .metadata.json ao lado)")
    p.add_argument("--modelo-id", required=True)
    p.add_argument("--saida", type=Path, help="diretório onde gravar as seções (opcional)")
    args = p.parse_args(argv)

    sidecar = args.manual.with_name(args.manual.name + ".metadata.json")
    try:
        secoes = preprocessar_manual_local(
            modelo_id=args.modelo_id,
            nome_arquivo=args.manual.name,
            corpo=args.manual.read_bytes(),
            corpo_sidecar=sidecar.read_bytes() if sidecar.exists() else b"{}",
        )
    except (OSError, ErroPreprocessamento) as exc:
        print(f"Falha ao dividir {args.manual}: {exc}", file=sys.stderr)
        return 1
    for s in secoes:
        print(f"{s.chave_s3}  <-  {s.secao}")
        if args.saida:
            destino = args.saida / s.chave_s3
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(s.corpo)
            destino.with_name(destino.name + ".metadata.json").write_bytes(s.corpo_sidecar)
    return 0


if __name__ == "__main__":
    sys.exit(main())
