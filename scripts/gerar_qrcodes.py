#!/usr/bin/env python3
"""Gerador de QR codes da demo (Req 1.1, 1.2).

Para cada modelo ativo do ``seed/catalogo.json`` gera um QR code cuja URL tem o formato
``<URL_BASE>/m/{modelo_id}?s={serie}`` (design, Q15). A série é um exemplo determinístico por
modelo (``DEMO001``, ``DEMO002``, ...), pois o seed não traz números de série reais.

Toda URL gerada é conferida com ``dominio.qr.interpretar_qr`` antes de virar imagem: se o
formato divergir do que o app sabe ler, o script falha em vez de produzir um QR inútil.

A URL base (domínio do CloudFront, desconhecido até o deploy) vem do argumento ou do ambiente:

    python scripts/gerar_qrcodes.py --url-base https://dxxxx.cloudfront.net --formato ambos
    TRES_URL_BASE=https://dxxxx.cloudfront.net python scripts/gerar_qrcodes.py

``--formato`` aceita ``svg`` (padrão), ``png`` ou ``ambos``.

Saída (padrão ``scripts/saida/``, fora do git): ``<modelo_id>.svg`` (e/ou ``.png``) e
``urls.txt`` com a URL de cada QR, para conferência.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit

_RAIZ = Path(__file__).resolve().parent.parent

# O script roda fora de um pacote instalado: resolve ``dominio`` pelo repositório.
_DOMINIO_SRC = _RAIZ / "packages" / "dominio" / "src"
if str(_DOMINIO_SRC) not in sys.path:
    sys.path.insert(0, str(_DOMINIO_SRC))

from dominio.qr import PADRAO_SERIE, interpretar_qr  # noqa: E402

CATALOGO_PADRAO = _RAIZ / "seed" / "catalogo.json"
SAIDA_PADRAO = Path(__file__).resolve().parent / "saida"
FORMATOS = ("svg", "png", "ambos")
PREFIXO_SERIE_DEMO = "DEMO"
ESCALA_PNG = 10  # pixels por módulo
BORDA_MODULOS = 4  # zona de silêncio mínima do padrão QR


class ErroQR(Exception):
    """Entrada inválida ou URL que o app não saberia interpretar."""


@dataclass(frozen=True, slots=True)
class QRDemo:
    modelo_id: str
    serie: str
    url: str


def normalizar_url_base(url_base: str | None) -> str:
    """Valida a URL base (http/https com host) e remove barras finais."""
    if not url_base or not url_base.strip():
        raise ErroQR("informe --url-base ou a variável TRES_URL_BASE")
    base = url_base.strip().rstrip("/")
    partes = urlsplit(base)
    if partes.scheme not in ("http", "https") or not partes.netloc:
        raise ErroQR(f"URL base inválida (use http:// ou https:// com o domínio): {url_base!r}")
    if partes.path or partes.query or partes.fragment:
        raise ErroQR(f"URL base deve conter só esquema e domínio, sem caminho: {url_base!r}")
    return base


def serie_de_exemplo(indice: int) -> str:
    """Série de exemplo determinística (1 a 30 alfanuméricos), p.ex. ``DEMO001``."""
    serie = f"{PREFIXO_SERIE_DEMO}{indice:03d}"
    if PADRAO_SERIE.fullmatch(serie) is None:
        raise ErroQR(f"série de exemplo inválida: {serie!r}")
    return serie


def montar_url(url_base: str, modelo_id: str, serie: str) -> str:
    """Monta ``<base>/m/{modelo_id}?s={serie}`` e confere que ``interpretar_qr`` a lê de volta."""
    url = f"{normalizar_url_base(url_base)}/m/{quote(modelo_id, safe='')}?s={quote(serie, safe='')}"
    lido = interpretar_qr(url)
    if not (lido.legivel and lido.modelo_id == modelo_id and lido.numero_serie == serie):
        raise ErroQR(
            f"URL não interpretável pelo app (modelo {modelo_id!r}, série {serie!r}): {url}"
        )
    return url


def ler_modelos_ativos(catalogo: Path) -> list[str]:
    """``modelo_id`` dos modelos ativos do catálogo, na ordem do arquivo."""
    try:
        dados = json.loads(Path(catalogo).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ErroQR(f"não foi possível ler {catalogo}: {exc}") from exc
    modelos = dados.get("modelos") if isinstance(dados, dict) else None
    if not isinstance(modelos, list):
        raise ErroQR(f'{catalogo}: esperado um objeto com a lista "modelos"')
    ids = [
        m["modelo_id"]
        for m in modelos
        if isinstance(m, dict) and m.get("ativo") is True and isinstance(m.get("modelo_id"), str)
    ]
    if not ids:
        raise ErroQR(f"{catalogo}: nenhum modelo ativo")
    return ids


def planejar(catalogo: Path, url_base: str) -> list[QRDemo]:
    """Uma entrada por modelo ativo, com série de exemplo e URL já validada."""
    return [
        QRDemo(mid, serie_de_exemplo(i), montar_url(url_base, mid, serie_de_exemplo(i)))
        for i, mid in enumerate(ler_modelos_ativos(catalogo), start=1)
    ]


def gravar(qrs: list[QRDemo], saida: Path, formato: str = "svg") -> list[Path]:
    """Grava as imagens (e ``urls.txt``) em ``saida``. Devolve os arquivos criados."""
    if formato not in FORMATOS:
        raise ErroQR(f"formato inválido: {formato!r} (use {', '.join(FORMATOS)})")
    import segno

    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    arquivos: list[Path] = []
    for qr in qrs:
        # Correção de erro M: legível mesmo impresso pequeno ou com pequenos danos.
        codigo = segno.make(qr.url, error="m", micro=False)
        if formato in ("svg", "ambos"):
            caminho = saida / f"{qr.modelo_id}.svg"
            codigo.save(
                caminho, kind="svg", scale=ESCALA_PNG, border=BORDA_MODULOS, title=qr.modelo_id
            )
            arquivos.append(caminho)
        if formato in ("png", "ambos"):
            caminho = saida / f"{qr.modelo_id}.png"
            codigo.save(caminho, kind="png", scale=ESCALA_PNG, border=BORDA_MODULOS)
            arquivos.append(caminho)
    indice = saida / "urls.txt"
    indice.write_text(
        "".join(f"{qr.modelo_id}\t{qr.serie}\t{qr.url}\n" for qr in qrs), encoding="utf-8"
    )
    arquivos.append(indice)
    return arquivos


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gera os QR codes da demo (/m/{modelo_id}?s={serie}).")
    p.add_argument(
        "--url-base",
        default=os.environ.get("TRES_URL_BASE"),
        help="URL base do app, p.ex. https://dxxxx.cloudfront.net (env TRES_URL_BASE)",
    )
    p.add_argument("--catalogo", type=Path, default=CATALOGO_PADRAO, help="seed/catalogo.json")
    p.add_argument("--saida", type=Path, default=SAIDA_PADRAO, help="diretório de saída")
    p.add_argument("--formato", choices=FORMATOS, default="svg", help="formato da imagem")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    try:
        qrs = planejar(args.catalogo, args.url_base)
        arquivos = gravar(qrs, args.saida, args.formato)
    except ErroQR as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    for qr in qrs:
        print(f"{qr.modelo_id}: {qr.url}")
    print(f"{len(arquivos)} arquivos gravados em {args.saida}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
