"""Interpretação da URL do Codigo_QR (Req 1.2, 1.4, 1.5, 1.6).

Formato da URL: `/m/{modelo_id}?s={serie}` (design, Q15), com ou sem esquema e domínio.

Regras:
  - O `modelo_id` só é extraído se casar com `PADRAO_MODELO_ID` (slug em minúsculas,
    como `tres-passione`). Se não casar, a URL é "não legível".
  - A série só é devolvida se tiver de 1 a 30 caracteres alfanuméricos ASCII.
    Série inválida é descartada, sem invalidar o modelo.
  - A função nunca lança exceção: qualquer entrada inesperada vira "não legível".

Pura: usa apenas `urllib.parse` (sem rede) e `re`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

PADRAO_MODELO_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TAMANHO_MAX_MODELO_ID = 64
PADRAO_SERIE = re.compile(r"[A-Za-z0-9]{1,30}")
_PREFIXO_CAMINHO = "/m/"
_PARAMETRO_SERIE = "s"
_CARACTERES_DE_CONTROLE = re.compile(r"[\x00-\x20\x7f]")


@dataclass(frozen=True)
class InterpretacaoQR:
    """Resultado de `interpretar_qr`.

    `legivel=False` significa "não legível" (Req 1.6): `modelo_id` e `numero_serie`
    são `None`. Com `legivel=True`, `modelo_id` está sempre preenchido e
    `numero_serie` é `None` quando ausente ou inválido (Req 1.5).
    """

    legivel: bool
    modelo_id: str | None = None
    numero_serie: str | None = None


NAO_LEGIVEL = InterpretacaoQR(legivel=False)


def _modelo_id_valido(valor: str) -> bool:
    return len(valor) <= TAMANHO_MAX_MODELO_ID and PADRAO_MODELO_ID.fullmatch(valor) is not None


def _extrair_serie(consulta: str) -> str | None:
    valores = parse_qs(consulta, keep_blank_values=True).get(_PARAMETRO_SERIE)
    if not valores:
        return None
    candidata = valores[0]
    return candidata if PADRAO_SERIE.fullmatch(candidata) else None


def interpretar_qr(url: object) -> InterpretacaoQR:
    """Extrai `modelo_id` e `numero_serie` da URL do QR. Nunca lança exceção."""
    try:
        if not isinstance(url, str):
            return NAO_LEGIVEL
        texto = url.strip()
        if not texto or _CARACTERES_DE_CONTROLE.search(texto):
            return NAO_LEGIVEL

        partes = urlsplit(texto)
        caminho = partes.path
        if not caminho.startswith(_PREFIXO_CAMINHO):
            return NAO_LEGIVEL

        modelo_id = caminho[len(_PREFIXO_CAMINHO) :]
        if modelo_id.endswith("/"):
            modelo_id = modelo_id[:-1]
        if not _modelo_id_valido(modelo_id):
            return NAO_LEGIVEL

        return InterpretacaoQR(
            legivel=True,
            modelo_id=modelo_id,
            numero_serie=_extrair_serie(partes.query),
        )
    except Exception:  # noqa: BLE001 - contrato: nunca lança exceção (Property 25)
        return NAO_LEGIVEL
