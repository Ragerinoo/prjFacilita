"""Rota do Seletor_Visual: POST /jornadas/{id}/seletor/resolver (tarefa 21.1, Req 4.2 a 4.6)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from core import criar_app, criar_roteador, processar
from dominio.seletor import resolver_seletor
from repositorios import criar_repositorios_memoria
from repositorios.catalogo import CatalogoMemoria
from repositorios.ids import novo_ulid
from repositorios.modelos import Jornada

AGORA = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)
ROTEADOR = criar_roteador()
SEED = Path(__file__).resolve().parents[3] / "seed"
JID = "01JSELET0000000000000000A"
CAMINHO = "/api/pub/jornadas/{}/seletor/resolver"


def _sem_comentarios(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {k: _sem_comentarios(v) for k, v in valor.items() if not k.startswith("_")}
    if isinstance(valor, list):
        return [_sem_comentarios(v) for v in valor]
    return valor


def _json(*partes: str) -> Any:
    return _sem_comentarios(json.loads(SEED.joinpath(*partes).read_text(encoding="utf-8")))


MAPA = _json("seletor", "tres-passione.json")


def _app(mapa: dict | None = MAPA, problemas: list[dict] | None = None):
    repos = criar_repositorios_memoria()
    modelos = _json("catalogo.json")["modelos"]
    for m in modelos:  # o carregador do seed embute o mapa no modelo; aqui só no da demo
        if m["modelo_id"] == "tres-passione" and mapa is not None:
            m["seletor"] = mapa
    object.__setattr__(
        repos,
        "catalogo",
        CatalogoMemoria.de_itens(modelos, problemas or _json("problemas.json")["problemas"], []),
    )
    return criar_app({}, modo="local", repos=repos, relogio=lambda: AGORA)


def _jornada(app, jid: str = JID, modelo_id: str | None = "tres-passione") -> None:
    app.repos.jornadas.criar(
        Jornada(
            jornada_id=jid,
            criada_em=AGORA,
            ultima_interacao=AGORA,
            origem="qr",
            origem_inicial="qr",
            modelo_id=modelo_id,
        )
    )


@pytest.fixture
def app():
    app = _app()
    _jornada(app)
    return app


def post(app, corpo: Any, jid: str = JID, cabecalhos: dict | None = None):
    evento: dict[str, Any] = {
        "rawPath": CAMINHO.format(jid),
        "headers": cabecalhos or {},
        "requestContext": {"requestId": "req-1", "http": {"method": "POST"}},
        "body": json.dumps(corpo),
    }
    resposta = processar(app, ROTEADOR, evento)
    return resposta, (json.loads(resposta["body"]) if resposta["body"] else None)


def _titulos(app) -> dict[int, str]:
    return {p.problema_id: p.titulo for p in app.repos.catalogo.listar_problemas()}


# --------------------------------------------------------------------------- resultados


def test_unico_devolve_um_problema_com_titulo_e_ordem(app):
    resposta, corpo = post(app, {"area": "luz_alerta", "estado": "piscando"})
    assert resposta["statusCode"] == 200
    assert corpo["resultado"] == "unico"
    assert corpo["problemas"] == [
        {"problema_id": 3, "titulo": _titulos(app)[3], "ordem": 3},
    ]
    assert (corpo["area"], corpo["estado"]) == ("luz_alerta", "piscando")
    assert corpo["jornada"]["jornada_id"] == JID


def test_multiplos_lista_ate_cinco_na_ordem_do_catalogo(app):
    resposta, corpo = post(app, {"area": "alavanca", "estado": "travada"})
    assert resposta["statusCode"] == 200
    assert corpo["resultado"] == "multiplos"
    assert [p["problema_id"] for p in corpo["problemas"]] == [9, 13]
    assert 2 <= len(corpo["problemas"]) <= 5
    assert all(p["titulo"] for p in corpo["problemas"])


def test_nenhum_quando_o_par_nao_tem_regra_e_preserva_area_e_estado(app):
    # luz_amarela/piscando existe no mapa, mas não tem regra no seed.
    resposta, corpo = post(app, {"area": "luz_amarela", "estado": "piscando"})
    assert resposta["statusCode"] == 200
    assert corpo["resultado"] == "nenhum"
    assert corpo["problemas"] == []
    jornada = app.repos.jornadas.obter(JID)
    assert (jornada.seletor_area, jornada.seletor_estado) == ("luz_amarela", "piscando")


def test_todas_as_regras_do_seed_batem_com_a_funcao_pura(app):
    titulos = _titulos(app)
    for regra in MAPA["regras"]:
        _, corpo = post(app, {"area": regra["area"], "estado": regra["estado"]})
        esperado = resolver_seletor(MAPA, regra["area"], regra["estado"])
        assert corpo["resultado"] == esperado.tipo
        assert {p["problema_id"] for p in corpo["problemas"]} == set(esperado.problemas)
        assert all(p["titulo"] == titulos[p["problema_id"]] for p in corpo["problemas"])


def test_problema_do_mapa_fora_do_catalogo_e_descartado(app):
    mapa = {**MAPA, "regras": [{"area": "bico", "estado": "travada", "problemas": [12, 99]}]}
    app2 = _app(mapa)
    _jornada(app2)
    _, corpo = post(app2, {"area": "bico", "estado": "travada"})
    assert corpo["resultado"] == "unico"
    assert [p["problema_id"] for p in corpo["problemas"]] == [12]


# --------------------------------------------------------------------------- registro


def test_registra_selecao_e_interacao_na_jornada(app):
    resposta, _ = post(app, {"area": "bico", "estado": "vazando"})
    assert resposta["statusCode"] == 200
    jornada = app.repos.jornadas.obter(JID)
    assert (jornada.seletor_area, jornada.seletor_estado) == ("bico", "vazando")
    assert jornada.ultima_interacao >= AGORA


def test_nova_selecao_substitui_a_anterior(app):
    post(app, {"area": "bico", "estado": "vazando"})
    post(app, {"area": "luz_alerta", "estado": "apagada"})
    jornada = app.repos.jornadas.obter(JID)
    assert (jornada.seletor_area, jornada.seletor_estado) == ("luz_alerta", "apagada")


# --------------------------------------------------------------------------- entradas ruins


@pytest.mark.parametrize(
    ("corpo", "campo"),
    [
        ({"estado": "piscando"}, "area"),
        ({"area": "luz_alerta"}, "estado"),
        ({"area": 3, "estado": "piscando"}, "area"),
        ({"area": "luz_alerta", "estado": ["piscando"]}, "estado"),
        ({"area": "", "estado": "piscando"}, "area"),
        ({"area": "nao_existe", "estado": "piscando"}, "area"),
        ({"area": "luz_alerta", "estado": "nao_existe"}, "estado"),
        # estado válido, mas de outra área
        ({"area": "luz_amarela", "estado": "apagada"}, "estado"),
    ],
)
def test_entrada_invalida_e_422_com_campos_e_nao_registra(app, corpo, campo):
    resposta, resp = post(app, corpo)
    assert resposta["statusCode"] == 422
    assert campo in json.dumps(resp, ensure_ascii=False)
    jornada = app.repos.jornadas.obter(JID)
    assert jornada.seletor_area is None and jornada.seletor_estado is None


def test_corpo_que_nao_e_objeto_e_rejeitado(app):
    resposta, _ = post(app, ["luz_alerta"])
    assert resposta["statusCode"] in (400, 422)


# --------------------------------------------------------------------------- Jornada/modelo


def test_jornada_inexistente_e_404(app):
    resposta, _ = post(app, {"area": "bico", "estado": "vazando"}, jid="01JNAOEXISTE00000000000000")
    assert resposta["statusCode"] == 404


def test_jornada_sem_modelo_e_404():
    app = _app()
    _jornada(app, modelo_id=None)
    resposta, _ = post(app, {"area": "bico", "estado": "vazando"})
    assert resposta["statusCode"] == 404


def test_modelo_sem_mapa_e_404_e_jornada_intacta():
    app = _app()
    _jornada(app, modelo_id="tres-circo")
    resposta, _ = post(app, {"area": "bico", "estado": "vazando"})
    assert resposta["statusCode"] == 404
    assert app.repos.jornadas.obter(JID).seletor_area is None


def test_jornada_encerrada_e_409_e_nao_muda(app):
    app.repos.jornadas.encerrar(JID, "guia", AGORA)
    resposta, _ = post(app, {"area": "bico", "estado": "vazando"})
    assert resposta["statusCode"] == 409
    assert app.repos.jornadas.obter(JID).seletor_area is None


# --------------------------------------------------------------------------- idempotência


def test_reenvio_com_idempotency_key_devolve_o_mesmo_sem_repetir_efeitos(app):
    cab = {"Idempotency-Key": novo_ulid(AGORA)}
    corpo = {"area": "alavanca", "estado": "travada"}
    r1, c1 = post(app, corpo, cabecalhos=cab)
    antes = app.repos.jornadas.obter(JID)
    r2, c2 = post(app, corpo, cabecalhos=cab)
    assert (r1["statusCode"], r2["statusCode"]) == (200, 200)
    assert c1 == c2
    assert app.repos.jornadas.obter(JID) == antes


def test_reenvio_com_evento_id_no_corpo_tambem_e_idempotente(app):
    corpo = {"area": "bico", "estado": "travada", "evento_id": novo_ulid(AGORA)}
    _, c1 = post(app, corpo)
    antes = app.repos.jornadas.obter(JID)
    _, c2 = post(app, corpo)
    assert c1 == c2
    assert app.repos.jornadas.obter(JID) == antes
