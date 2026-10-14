"""Testes do gerador de QR codes da demo (Req 1.1, 1.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dominio.qr import interpretar_qr
from gerar_qrcodes import (
    CATALOGO_PADRAO,
    ErroQR,
    gravar,
    main,
    montar_url,
    normalizar_url_base,
    planejar,
)

BASE = "https://d111111abcdef8.cloudfront.net"


def test_urls_do_seed_passam_por_interpretar_qr() -> None:
    qrs = planejar(CATALOGO_PADRAO, BASE)
    assert "tres-passione" in {q.modelo_id for q in qrs}
    for qr in qrs:
        lido = interpretar_qr(qr.url)
        assert lido.legivel
        assert lido.modelo_id == qr.modelo_id
        assert lido.numero_serie == qr.serie
        assert qr.url == f"{BASE}/m/{qr.modelo_id}?s={qr.serie}"


def test_base_com_barra_final_nao_duplica_barra() -> None:
    assert montar_url(BASE + "/", "tres-mimo", "ABC1") == f"{BASE}/m/tres-mimo?s=ABC1"


@pytest.mark.parametrize(
    "base", [None, "", "  ", "cloudfront.net", "ftp://x.com", "https://x.com/app"]
)
def test_url_base_invalida(base: str | None) -> None:
    with pytest.raises(ErroQR):
        normalizar_url_base(base)


def test_serie_invalida_nao_gera_url() -> None:
    with pytest.raises(ErroQR):
        montar_url(BASE, "tres-mimo", "x" * 31)
    with pytest.raises(ErroQR):
        montar_url(BASE, "TRES Mimo", "ABC1")


def test_so_modelos_ativos(tmp_path: Path) -> None:
    catalogo = tmp_path / "catalogo.json"
    catalogo.write_text(
        json.dumps(
            {"modelos": [{"modelo_id": "a-1", "ativo": True}, {"modelo_id": "b-2", "ativo": False}]}
        ),
        encoding="utf-8",
    )
    assert [q.modelo_id for q in planejar(catalogo, BASE)] == ["a-1"]


def test_gravar_svg_e_png(tmp_path: Path) -> None:
    qrs = planejar(CATALOGO_PADRAO, BASE)
    arquivos = gravar(qrs, tmp_path / "saida", "ambos")
    for qr in qrs:
        svg = tmp_path / "saida" / f"{qr.modelo_id}.svg"
        png = tmp_path / "saida" / f"{qr.modelo_id}.png"
        assert svg.read_text(encoding="utf-8").lstrip().startswith(("<?xml", "<svg"))
        assert png.read_bytes().startswith(b"\x89PNG")
    indice = (tmp_path / "saida" / "urls.txt").read_text(encoding="utf-8")
    assert all(qr.url in indice for qr in qrs)
    assert len(arquivos) == 2 * len(qrs) + 1


def test_main_sem_url_base_falha(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("TRES_URL_BASE", raising=False)
    assert main(["--saida", str(tmp_path)]) == 1
    assert "TRES_URL_BASE" in capsys.readouterr().err


def test_main_gera_arquivos(tmp_path: Path) -> None:
    assert main(["--url-base", BASE, "--saida", str(tmp_path)]) == 0
    assert (tmp_path / "tres-passione.svg").exists()
