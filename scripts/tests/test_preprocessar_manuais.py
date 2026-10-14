"""Testes do pré-processamento de manuais em seções (Req 6.3, 20.2, 20.3).

**Validates: Requirements 6.3, 20.2**
"""

from __future__ import annotations

import json

import carregar_seed as cs
import preprocessar_manuais as pm
import pytest
from hypothesis import given
from hypothesis import strategies as st
from premissas import (
    CHAVE_METADADO_MANUAL,
    CHAVE_METADADO_MODELO,
    CHAVE_METADADO_SECAO,
    METADADOS_OBRIGATORIOS,
    S3_VECTORS_METADADOS_CUSTOM_MAX_BYTES,
    sidecar_metadados,
)

MODELO = "tres-passione"
MANUAL = "Manual de teste"

TEXTO = """\
# Manual de teste

> Aviso: conteúdo de exemplo.

## 1. Segurança

### 1.1 Cuidados gerais
Use em superfície plana.

### 1.2 Risco
Desligue da tomada.

## 2. Preparo
Texto direto do capítulo.

### 2.1 Água
Use água limpa.
"""


def _dividir(texto: str = TEXTO, **kw) -> list[pm.SecaoManual]:
    args = {"modelo_id": MODELO, "manual": MANUAL, "arquivo": "manual.md"} | kw
    return pm.dividir_manual(texto, **args)


def test_divide_em_uma_secao_por_titulo_com_texto():
    secoes = _dividir()
    # "1. Segurança" só tem subtítulos; "2. Preparo" tem texto próprio; aviso inicial é ignorado.
    assert [s.secao for s in secoes] == [
        "1.1 Cuidados gerais",
        "1.2 Risco",
        "2. Preparo",
        "2.1 Água",
    ]
    assert [s.chave_s3 for s in secoes] == [
        "secoes/tres-passione/manual/1-1-cuidados-gerais.md",
        "secoes/tres-passione/manual/1-2-risco.md",
        "secoes/tres-passione/manual/2-preparo.md",
        "secoes/tres-passione/manual/2-1-agua.md",
    ]
    primeira = secoes[0].corpo.decode("utf-8")
    assert (
        primeira
        == "# Manual de teste > 1. Segurança > 1.1 Cuidados gerais\n\nUse em superfície plana.\n"
    )
    assert secoes[3].caminho == ("2. Preparo", "2.1 Água")


def test_sidecar_tem_modelo_manual_e_secao_no_formato_das_premissas():
    for s in _dividir():
        assert s.chave_sidecar == f"{s.chave_s3}.metadata.json"
        sidecar = json.loads(s.corpo_sidecar)
        assert sidecar == sidecar_metadados(MODELO, MANUAL, s.secao)
        assert set(sidecar["metadataAttributes"]) == set(METADADOS_OBRIGATORIOS)
        assert len(s.corpo_sidecar) <= S3_VECTORS_METADADOS_CUSTOM_MAX_BYTES


def test_texto_antes_do_primeiro_subtitulo_vira_introducao_se_nao_for_so_aviso():
    secoes = _dividir("# Doc\nApresentação do produto.\n## 1 A\nTexto.\n")
    assert [s.secao for s in secoes] == ["Introdução", "1 A"]
    assert "Apresentação do produto." in secoes[0].corpo.decode()


def test_titulos_dentro_de_bloco_de_codigo_nao_dividem():
    secoes = _dividir("# D\n## 1 A\n```\n## nao e titulo\n```\nFim.\n")
    assert [s.secao for s in secoes] == ["1 A"]
    assert "## nao e titulo" in secoes[0].corpo.decode()


def test_titulos_repetidos_ganham_sufixo_estavel():
    secoes = _dividir("# D\n## Passo\nA\n## Passo\nB\n## Passo\nC\n")
    assert [s.slug for s in secoes] == ["passo", "passo-2", "passo-3"]
    assert len({s.chave_s3 for s in secoes}) == 3


def test_crlf_e_lf_dao_o_mesmo_resultado():
    assert _dividir(TEXTO.replace("\n", "\r\n")) == _dividir(TEXTO)


def test_dividir_e_idempotente():
    assert _dividir() == _dividir()


def test_metadados_longos_sao_truncados_em_utf8_e_cabem_em_1kb():
    titulo = "Açúcar " * 200
    secoes = _dividir(f"# D\n## {titulo}\nTexto.\n", manual="Ç" * 2000)
    s = secoes[0]
    assert len(s.corpo_sidecar) <= S3_VECTORS_METADADOS_CUSTOM_MAX_BYTES
    atributos = json.loads(s.corpo_sidecar.decode("utf-8"))["metadataAttributes"]
    assert atributos[CHAVE_METADADO_SECAO].endswith(pm.RETICENCIAS)
    assert atributos[CHAVE_METADADO_MANUAL].endswith(pm.RETICENCIAS)
    assert atributos[CHAVE_METADADO_MODELO] == MODELO
    assert len(s.slug) <= pm.SLUG_MAX_CARACTERES


@pytest.mark.parametrize(
    ("kwargs", "trecho"),
    [
        ({"modelo_id": "Modelo Inválido"}, "modelo_id"),
        ({"modelo_id": "../x"}, "modelo_id"),
        ({"manual": "   "}, "manual"),
    ],
)
def test_entradas_invalidas_levantam_erro_claro(kwargs, trecho):
    with pytest.raises(pm.ErroPreprocessamento, match=trecho):
        _dividir(**kwargs)


def test_manual_sem_secao_com_texto_e_erro():
    with pytest.raises(pm.ErroPreprocessamento, match="nenhuma seção"):
        _dividir("# Só o título\n\n> aviso\n## Vazio\n")


def test_manual_do_seed_se_divide_em_18_secoes_numeradas_com_metadados_validos():
    seed = cs.validar(cs.SEED_PADRAO)
    (manual,) = seed.manuais["tres-passione"]
    secoes = pm.preprocessar_manual_local(
        modelo_id="tres-passione",
        nome_arquivo="manual-exemplo.md",
        corpo=manual.corpo,
        corpo_sidecar=manual.corpo_sidecar,
    )
    assert len(secoes) == 18
    assert pm.validar_conjunto(secoes) == []
    assert {s.manual for s in secoes} == {"Manual de exemplo TRES Passione"}
    assert "3.1 Luz vermelha fixa" in {s.secao for s in secoes}
    assert not any("Não é o manual oficial" in s.corpo.decode() for s in secoes)


def test_sidecar_sem_manual_usa_o_nome_do_arquivo():
    secoes = pm.preprocessar_manual_local(
        modelo_id=MODELO,
        nome_arquivo="guia-rapido.md",
        corpo=b"# G\n## 1 A\nTexto.\n",
        corpo_sidecar=b"{}",
    )
    assert secoes[0].manual == "guia-rapido"


def test_manual_que_nao_e_utf8_e_erro():
    with pytest.raises(pm.ErroPreprocessamento, match="UTF-8"):
        pm.preprocessar_manual_local(
            modelo_id=MODELO, nome_arquivo="x.md", corpo=b"\xff\xfe", corpo_sidecar=b"{}"
        )


# --------------------------------------------------------------------------------------------
# Propriedades
# --------------------------------------------------------------------------------------------

_palavra = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs", "Cc", "Zl", "Zp"), blacklist_characters="#`~>*\\"
    ),
    min_size=1,
    max_size=40,
).filter(lambda t: t.strip() != "")

_bloco = st.tuples(st.integers(2, 4), _palavra, st.lists(_palavra, max_size=3))


def _montar(blocos) -> str:
    linhas = ["# Doc"]
    for nivel, titulo, corpo in blocos:
        linhas.append(f"{'#' * nivel} {titulo}")
        linhas.extend(corpo)
    return "\n".join(linhas) + "\n"


@given(blocos=st.lists(_bloco, min_size=1, max_size=12), manual=_palavra)
def test_propriedade_divisao_estavel_unica_e_dentro_do_limite_de_metadados(blocos, manual):
    """Mesma entrada, mesma saída; chaves únicas; metadados <= 1 KB e com 3 chaves."""
    texto = _montar(blocos)
    try:
        primeira = pm.dividir_manual(texto, modelo_id=MODELO, manual=manual, arquivo="m.md")
    except pm.ErroPreprocessamento:
        # Só pode falhar quando nenhum título tem texto.
        assert all(not corpo for _, _, corpo in blocos)
        return
    assert primeira == pm.dividir_manual(texto, modelo_id=MODELO, manual=manual, arquivo="m.md")
    assert pm.validar_conjunto(primeira) == []
    for s in primeira:
        atributos = json.loads(s.corpo_sidecar)["metadataAttributes"]
        assert set(atributos) == set(METADADOS_OBRIGATORIOS)
        assert s.chave_s3.startswith(f"{pm.PREFIXO_S3_SECOES}{MODELO}/m/")
        assert s.corpo.decode("utf-8").endswith("\n")
