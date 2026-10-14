"""Testes de unidade do Guia_Diagnostico e do Seletor_Visual puros (Req 3, 4, 19.5)."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from dominio.guia import (
    Instrucao,
    instrucao_valida,
    resolver_instrucao,
    validar_instrucao,
    validar_titulo_problema,
)
from dominio.seletor import (
    resolver_seletor,
    validar_mapa,
    validar_tamanho_areas,
)

SEED = Path(__file__).resolve().parents[3] / "seed"


def _passo(n: int, **kw):
    base = {
        "n": n,
        "texto": f"Faça a ação {n}.",
        "midia_url": "/m.svg",
        "midia_tipo": "imagem",
        "alt": "Mão realizando a ação",
        "texto_equivalente": f"Passo {n}: faça a ação.",
    }
    base.update(kw)
    return base


def _instr(qtd: int = 2, **kw):
    base = {
        "modelo_id": "m1",
        "problema_id": 1,
        "variante": "padrao",
        "passos": [_passo(i) for i in range(1, qtd + 1)],
    }
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# resolver_instrucao
# --------------------------------------------------------------------------- #


def test_resolver_instrucao_variantes_e_determinismo():
    cat = {
        "instrucoes": [_instr(), _instr(problema_id=10, variante="externo"), _instr(problema_id=10)]
    }
    a = resolver_instrucao(cat, "m1", 10, "externo")
    assert isinstance(a, Instrucao) and a.variante == "externo"
    assert resolver_instrucao(cat, "m1", 10, "externo") == a
    assert resolver_instrucao(cat, "m1", 10, "padrao").variante == "padrao"
    assert [p.n for p in a.passos] == [1, 2]


def test_resolver_instrucao_inexistente_devolve_none():
    cat = [_instr()]
    assert resolver_instrucao(cat, "outro", 1, "padrao") is None
    assert resolver_instrucao(cat, "m1", 2, "padrao") is None
    assert resolver_instrucao(cat, "m1", 1, "externo") is None
    assert resolver_instrucao(cat, "m1", 1, "interno") is None
    assert resolver_instrucao([], "m1", 1, "padrao") is None


def test_resolver_instrucao_ordena_passos_e_aceita_mapa_por_chave():
    instr = _instr()
    instr["passos"].reverse()
    cat = {("m1", 1, "padrao"): instr}
    r = resolver_instrucao(cat, "m1", "1", "padrao")
    assert [p.n for p in r.passos] == [1, 2]


def test_resolver_instrucao_malformada_nao_lanca():
    assert (
        resolver_instrucao(
            [{"modelo_id": "m1", "problema_id": 1, "variante": "padrao"}], "m1", 1, "padrao"
        )
        is None
    )


# --------------------------------------------------------------------------- #
# validar_instrucao
# --------------------------------------------------------------------------- #


def test_instrucao_valida_nos_limites():
    i = _instr(10)
    i["passos"][0]["texto"] = "x" * 140
    i["passos"][0]["alt"] = "y" * 125
    assert validar_instrucao(i, "t" * 40) == []
    assert instrucao_valida(i)


@pytest.mark.parametrize(
    "mutar, campo",
    [
        (lambda i: i["passos"].clear(), "passos"),
        (lambda i: i.update(passos=[_passo(k) for k in range(1, 12)]), "passos"),
        (lambda i: i["passos"][0].update(texto="x" * 141), "passos[0].texto"),
        (lambda i: i["passos"][0].update(texto="  "), "passos[0].texto"),
        (lambda i: i["passos"][0].update(alt="y" * 126), "passos[0].alt"),
        (lambda i: i["passos"][0].update(alt=""), "passos[0].alt"),
        (lambda i: i["passos"][0].update(texto_equivalente=""), "passos[0].texto_equivalente"),
        (lambda i: i["passos"][0].pop("texto_equivalente"), "passos[0].texto_equivalente"),
        (lambda i: i["passos"][0].update(n=2), "passos[0].n"),
        (lambda i: i["passos"][1].update(n=1), "passos[1].n"),
        (lambda i: i.update(variante="interno"), "variante"),
        (lambda i: i.update(passos="abc"), "passos"),
    ],
)
def test_instrucao_invalida(mutar, campo):
    i = _instr(2)
    mutar(i)
    assert campo in {e.campo for e in validar_instrucao(i)}
    assert not instrucao_valida(i)


def test_titulo_ate_40():
    assert validar_titulo_problema("a" * 40) == []
    assert validar_titulo_problema("a" * 41)
    assert validar_titulo_problema("")
    assert validar_instrucao(_instr(), "a" * 41)[0].campo == "titulo"


def test_validar_instrucao_aceita_dataclass_e_nao_lanca_com_lixo():
    from dominio.guia import instrucao_de_dict

    assert validar_instrucao(instrucao_de_dict(_instr())) == []
    assert validar_instrucao(None)
    assert validar_instrucao({"passos": [None, 3]})


def test_seed_real_de_instrucoes_e_titulos_validam():
    dados = json.loads((SEED / "instrucoes" / "tres-passione.json").read_text("utf-8"))
    problemas = json.loads((SEED / "problemas.json").read_text("utf-8"))["problemas"]
    assert len(problemas) == 13
    for p in problemas:
        assert validar_titulo_problema(p["titulo"]) == [], p["titulo"]
    for i in dados["instrucoes"]:
        assert validar_instrucao(i) == [], (i["problema_id"], i["variante"])
    # 13 problemas "padrao" + vazamento "externo"; interno nunca tem passos (Req 3.8).
    for p in problemas:
        assert resolver_instrucao(dados, "tres-passione", p["problema_id"], "padrao")
    assert resolver_instrucao(dados, "tres-passione", 10, "externo")
    assert resolver_instrucao(dados, "tres-passione", 1, "externo") is None


# --------------------------------------------------------------------------- #
# resolver_seletor
# --------------------------------------------------------------------------- #


def _mapa():
    return {
        "areas": [
            {
                "area": "luz",
                "rotulo": "Luz",
                "forma": {"tipo": "retangulo", "x": 0, "y": 0, "largura": 20, "altura": 20},
                "estados": [
                    {"estado": "fixa", "rotulo": "Fixa"},
                    {"estado": "pisca", "rotulo": "P"},
                ],
            },
            {
                "area": "alavanca",
                "rotulo": "Alavanca",
                "forma": {"tipo": "retangulo", "x": 20, "y": 0, "largura": 20, "altura": 20},
                "estados": [
                    {"estado": "travada", "rotulo": "T"},
                    {"estado": "vaza", "rotulo": "V"},
                ],
            },
        ],
        "regras": [
            {"area": "luz", "estado": "fixa", "problemas": [2]},
            {"area": "alavanca", "estado": "travada", "problemas": [9, 13]},
        ],
    }


def test_resolver_seletor_unico_multiplos_nenhum():
    m = _mapa()
    u = resolver_seletor(m, "luz", "fixa")
    assert (u.tipo, u.problemas) == ("unico", (2,))
    mu = resolver_seletor(m, "alavanca", "travada")
    assert (mu.tipo, mu.problemas) == ("multiplos", (9, 13))
    n = resolver_seletor(m, "luz", "pisca")
    assert (n.tipo, n.problemas, n.area, n.estado) == ("nenhum", (), "luz", "pisca")
    assert resolver_seletor(m, "inexistente", "x").tipo == "nenhum"
    assert resolver_seletor(m, "luz", "fixa") == u


def test_resolver_seletor_limita_a_5_e_deduplica():
    m = _mapa()
    m["regras"] = [
        {"area": "luz", "estado": "fixa", "problemas": [1, 2, 3, 3]},
        {"area": "luz", "estado": "fixa", "problemas": [4, 5, 6, 7]},
    ]
    r = resolver_seletor(m, "luz", "fixa")
    assert r.tipo == "multiplos" and r.problemas == (1, 2, 3, 4, 5)
    assert resolver_seletor({}, "luz", "fixa").tipo == "nenhum"


# --------------------------------------------------------------------------- #
# validar_mapa
# --------------------------------------------------------------------------- #


def test_mapa_valido():
    assert validar_mapa(_mapa()) == []


def test_mapa_areas_que_se_tocam_nas_bordas_nao_se_sobrepoem():
    assert validar_mapa(_mapa()) == []  # x=0..20 e x=20..40


def test_mapa_sobreposicao():
    m = _mapa()
    m["areas"][1]["forma"]["x"] = 19
    assert any("sobrep" in e.motivo for e in validar_mapa(m))


@pytest.mark.parametrize("qtd", [1, 6])
def test_mapa_quantidade_de_estados(qtd):
    m = _mapa()
    m["areas"][0]["estados"] = [{"estado": f"e{k}", "rotulo": "r"} for k in range(qtd)]
    m["regras"] = []
    assert any(e.campo == "areas[0].estados" for e in validar_mapa(m))


@pytest.mark.parametrize("qtd", [2, 5])
def test_mapa_estados_nos_limites(qtd):
    m = _mapa()
    m["areas"][0]["estados"] = [{"estado": f"e{k}", "rotulo": "r"} for k in range(qtd)]
    m["regras"] = []
    assert validar_mapa(m) == []


def test_mapa_regras_invalidas_e_forma_invalida():
    m = _mapa()
    m["regras"].append({"area": "luz", "estado": "nao_existe", "problemas": [1]})
    m["regras"].append({"area": "fantasma", "estado": "x", "problemas": [1]})
    m["regras"].append({"area": "luz", "estado": "pisca", "problemas": [1, 2, 3, 4, 5, 6]})
    assert len(validar_mapa(m)) == 3
    m2 = _mapa()
    m2["areas"][0]["forma"] = {"tipo": "poligono", "pontos": []}
    assert any(e.campo == "areas[0].forma" for e in validar_mapa(m2))
    assert validar_mapa(None) and validar_mapa({}) and validar_mapa({"areas": [1]})


def test_tamanho_minimo_das_areas():
    m = _mapa()
    assert validar_tamanho_areas(m) == []
    m["areas"][0]["forma"]["largura"] = 15
    assert [e.campo for e in validar_tamanho_areas(m)] == ["areas[0].forma"]


def test_seed_real_do_seletor_valida_e_resolve():
    mapa = json.loads((SEED / "seletor" / "tres-passione.json").read_text("utf-8"))
    assert validar_mapa(mapa) == []
    assert validar_tamanho_areas(mapa) == []
    assert resolver_seletor(mapa, "luz_alerta", "piscando").problemas == (3,)
    assert resolver_seletor(mapa, "alavanca", "travada").tipo == "multiplos"
    assert resolver_seletor(mapa, "luz_amarela", "piscando").tipo == "nenhum"
    mapa_ruim = copy.deepcopy(mapa)
    mapa_ruim["areas"][1]["forma"]["x"] = 12
    assert validar_mapa(mapa_ruim)
