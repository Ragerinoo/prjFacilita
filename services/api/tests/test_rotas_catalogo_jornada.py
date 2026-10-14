"""Rotas de catálogo e início da Jornada (tarefa 11.2): fake em memória e DynamoDB (moto)."""

from __future__ import annotations

import json
import string
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
import pytest
from hypothesis import given
from hypothesis import strategies as st
from moto import mock_aws

from core import criar_app, criar_roteador, processar
from core.app import _chamar_fabrica
from repositorios import criar_repositorios_memoria
from repositorios.catalogo import CatalogoMemoria, ModeloCatalogo
from repositorios.dynamodb import criar_repositorios_dynamodb
from repositorios.dynamodb._base import para_dynamo
from repositorios.modelos import Jornada
from servicos import catalogo as servico_catalogo

AGORA = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)
SEED = Path(__file__).resolve().parents[3] / "seed"
ROTEADOR = criar_roteador()


# --------------------------------------------------------------------------- apoio


def _sem_comentarios(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {k: _sem_comentarios(v) for k, v in valor.items() if not k.startswith("_")}
    if isinstance(valor, list):
        return [_sem_comentarios(v) for v in valor]
    return valor


def _json(*partes: str) -> Any:
    return _sem_comentarios(json.loads(SEED.joinpath(*partes).read_text(encoding="utf-8")))


def itens_do_seed() -> tuple[list[dict], list[dict], list[dict]]:
    """Modelos (com o seletor embutido, como o seed grava), problemas e instruções."""
    modelos = _json("catalogo.json")["modelos"]
    for modelo in modelos:
        arquivo = SEED / "seletor" / f"{modelo['modelo_id']}.json"
        if arquivo.exists():
            modelo["seletor"] = _json("seletor", arquivo.name)
    instrucoes = _json("instrucoes", "tres-passione.json")["instrucoes"]
    return modelos, _json("problemas.json")["problemas"], instrucoes


@pytest.fixture
def app():
    repos = criar_repositorios_memoria()
    modelos, problemas, instrucoes = itens_do_seed()
    object.__setattr__(repos, "catalogo", CatalogoMemoria.de_itens(modelos, problemas, instrucoes))
    return criar_app({}, modo="local", repos=repos, relogio=lambda: AGORA)


def chamar(app, metodo, caminho, corpo=None, cabecalhos=None):
    evento = {
        "rawPath": caminho,
        "headers": cabecalhos or {},
        "requestContext": {"requestId": "req-1", "http": {"method": metodo}},
    }
    if corpo is not None:
        evento["body"] = json.dumps(corpo)
    resposta = processar(app, ROTEADOR, evento)
    return resposta, (json.loads(resposta["body"]) if resposta["body"] else None)


def jornada_de(app, corpo) -> Jornada:
    return app.repos.jornadas.obter(corpo["jornada_id"])


# --------------------------------------------------------------------------- GET /modelos


def test_lista_modelos_ativos_em_ordem_alfabetica_com_cache_de_borda(app):
    resposta, corpo = chamar(app, "GET", "/api/pub/modelos")
    assert resposta["statusCode"] == 200
    nomes = [m["nome"] for m in corpo["modelos"]]
    assert nomes == ["TRES Circo", "TRES Mimo", "TRES Passione"]
    assert set(corpo["modelos"][0]) == {"modelo_id", "nome", "foto_url", "ativo"}
    assert "max-age" in resposta["headers"]["Cache-Control"]


def test_lista_omite_modelo_inativo(app):
    app.repos.catalogo._modelos["tres-mimo"] = ModeloCatalogo(
        "tres-mimo", "TRES Mimo", "tres mimo", ativo=False
    )
    _, corpo = chamar(app, "GET", "/api/pub/modelos")
    assert "tres-mimo" not in {m["modelo_id"] for m in corpo["modelos"]}


# --------------------------------------------------------------------------- GET /modelos/{id}


def test_modelo_traz_13_problemas_na_ordem_e_o_mapa_do_seletor(app):
    resposta, corpo = chamar(app, "GET", "/api/pub/modelos/tres-passione")
    assert resposta["statusCode"] == 200
    assert corpo["modelo"]["modelo_id"] == "tres-passione"
    assert corpo["modelo"]["nome"] == "TRES Passione"
    assert [p["problema_id"] for p in corpo["problemas"]] == list(range(1, 14))
    assert [p["ordem"] for p in corpo["problemas"]] == list(range(1, 14))
    assert set(corpo["problemas"][0]) == {"problema_id", "ordem", "titulo", "icone", "icone_alt"}
    assert corpo["problemas"][0]["titulo"] == "Máquina não está ligando"
    assert "areas" in corpo["seletor"] and "regras" in corpo["seletor"]


def test_modelo_sem_mapa_do_seletor_devolve_seletor_nulo(app):
    _, corpo = chamar(app, "GET", "/api/pub/modelos/tres-circo")
    assert corpo["seletor"] is None and len(corpo["problemas"]) == 13


@pytest.mark.parametrize("modelo_id", ["tres-inexistente", "Tres_Passione", "x" * 80, "-a"])
def test_modelo_inexistente_ou_ilegivel_e_404(app, modelo_id):
    resposta, corpo = chamar(app, "GET", f"/api/pub/modelos/{modelo_id}")
    assert resposta["statusCode"] == 404
    assert corpo["erro"]["codigo"] == "nao_encontrado"


def test_modelo_inativo_e_404(app):
    app.repos.catalogo._modelos["tres-mimo"] = ModeloCatalogo(
        "tres-mimo", "TRES Mimo", "tres mimo", ativo=False
    )
    resposta, _ = chamar(app, "GET", "/api/pub/modelos/tres-mimo")
    assert resposta["statusCode"] == 404


class _CatalogoLento(CatalogoMemoria):
    def obter_modelo(self, modelo_id):
        time.sleep(0.5)
        return super().obter_modelo(modelo_id)


def test_catalogo_sem_resposta_no_prazo_e_504_e_nao_cria_jornada(app, monkeypatch):
    monkeypatch.setattr(servico_catalogo, "PRAZO_CATALOGO_S", 0.05)
    modelos, problemas, _ = itens_do_seed()
    object.__setattr__(app.repos, "catalogo", _CatalogoLento.de_itens(modelos, problemas))

    resposta, corpo = chamar(app, "GET", "/api/pub/modelos/tres-passione")
    assert resposta["statusCode"] == 504 and corpo["erro"]["codigo"] == "tempo_esgotado"

    resposta, corpo = chamar(
        app, "POST", "/api/pub/jornadas", {"origem": "qr", "modelo_id": "tres-passione"}
    )
    assert resposta["statusCode"] == 504
    assert app.repos.jornadas._itens == {}  # Req 1.7: sem Jornada até resolver o modelo


def test_prazo_padrao_do_catalogo_e_5_segundos():
    assert servico_catalogo.PRAZO_CATALOGO_S == 5.0


# --------------------------------------------------------------------------- POST /jornadas


def test_jornada_por_qr_com_modelo_e_serie(app):
    resposta, corpo = chamar(
        app,
        "POST",
        "/api/pub/jornadas",
        {"origem": "qr", "modelo_id": "tres-passione", "numero_serie": "AB12345"},
    )
    assert resposta["statusCode"] == 201
    j = jornada_de(app, corpo)
    assert (j.origem, j.origem_inicial, j.modelo_id, j.numero_serie) == (
        "qr",
        "qr",
        "tres-passione",
        "AB12345",
    )
    assert corpo["modelo_reconhecido"] is True
    assert corpo["jornada"] == {
        "jornada_id": j.jornada_id,
        "estado": "ativa",
        "risco": {"marcado": False},
        "contato_cs": "pendente",
    }


def test_jornadas_tem_ids_unicos(app):
    ids = {
        chamar(app, "POST", "/api/pub/jornadas", {"origem": "busca"})[1]["jornada_id"]
        for _ in range(5)
    }
    assert len(ids) == 5


@pytest.mark.parametrize("serie", ["", "x" * 31, "AB-123", "AB 12", "açaí1", 12345, ["A"], None])
def test_serie_invalida_e_descartada_e_o_modelo_segue_valido(app, serie):
    resposta, corpo = chamar(
        app,
        "POST",
        "/api/pub/jornadas",
        {"origem": "qr", "modelo_id": "tres-passione", "numero_serie": serie},
    )
    assert resposta["statusCode"] == 201
    j = jornada_de(app, corpo)
    assert j.modelo_id == "tres-passione" and j.numero_serie is None


@given(serie=st.text(max_size=40))
def test_serie_so_e_gravada_se_tiver_1_a_30_alfanumericos(serie):
    app = criar_app({}, modo="local", relogio=lambda: AGORA)
    modelos, problemas, _ = itens_do_seed()
    object.__setattr__(app.repos, "catalogo", CatalogoMemoria.de_itens(modelos, problemas))
    _, corpo = chamar(
        app,
        "POST",
        "/api/pub/jornadas",
        {"origem": "qr", "modelo_id": "tres-passione", "numero_serie": serie},
    )
    valida = 1 <= len(serie) <= 30 and all(c in string.ascii_letters + string.digits for c in serie)
    assert jornada_de(app, corpo).numero_serie == (serie if valida else None)


def test_serie_sem_modelo_reconhecido_nao_e_gravada(app):
    _, corpo = chamar(
        app,
        "POST",
        "/api/pub/jornadas",
        {"origem": "qr", "modelo_id": "tres-inexistente", "numero_serie": "AB123"},
    )
    assert jornada_de(app, corpo).numero_serie is None


@pytest.mark.parametrize("modelo_id", ["tres-inexistente", "Tres Passione", 42, ""])
def test_modelo_inexistente_cria_jornada_qr_sem_modelo(app, modelo_id):
    resposta, corpo = chamar(
        app, "POST", "/api/pub/jornadas", {"origem": "qr", "modelo_id": modelo_id}
    )
    assert resposta["statusCode"] == 201 and corpo["modelo_reconhecido"] is False
    j = jornada_de(app, corpo)
    assert (j.origem, j.modelo_id) == ("qr", None)


def test_jornada_por_busca_sem_modelo_e_aceita(app):
    resposta, corpo = chamar(app, "POST", "/api/pub/jornadas", {"origem": "busca"})
    assert resposta["statusCode"] == 201
    assert jornada_de(app, corpo).origem == "busca"


@pytest.mark.parametrize("corpo", [{}, {"origem": "email"}, {"origem": 1}])
def test_origem_invalida_e_422_com_o_campo(app, corpo):
    resposta, resp = chamar(app, "POST", "/api/pub/jornadas", corpo)
    assert resposta["statusCode"] == 422
    assert resp["erro"]["campos"][0]["campo"] == "origem"
    assert app.repos.jornadas._itens == {}


def test_corpo_que_nao_e_objeto_e_400(app):
    resposta, _ = chamar(app, "POST", "/api/pub/jornadas", ["qr"])
    assert resposta["statusCode"] == 400


def test_idempotency_key_repetida_devolve_a_mesma_jornada(app):
    cab = {"Idempotency-Key": "chave-123"}
    corpo = {"origem": "qr", "modelo_id": "tres-passione"}
    r1, c1 = chamar(app, "POST", "/api/pub/jornadas", corpo, cab)
    r2, c2 = chamar(app, "POST", "/api/pub/jornadas", corpo, cab)
    assert (r1["statusCode"], r2["statusCode"]) == (201, 200)
    assert c1["jornada_id"] == c2["jornada_id"] and len(app.repos.jornadas._itens) == 1


# --------------------------------------------------------------------------- PUT modelo


def test_busca_associa_modelo_e_origem_vira_busca(app):
    _, criada = chamar(
        app, "POST", "/api/pub/jornadas", {"origem": "qr", "modelo_id": "tres-desconhecido"}
    )
    resposta, corpo = chamar(
        app, "PUT", f"/api/pub/jornadas/{criada['jornada_id']}/modelo", {"modelo_id": "tres-mimo"}
    )
    assert resposta["statusCode"] == 200 and corpo["modelo_id"] == "tres-mimo"
    j = jornada_de(app, criada)
    assert (j.modelo_id, j.origem, j.origem_inicial) == ("tres-mimo", "busca", "qr")
    assert corpo["origem"] == "busca" and corpo["jornada"]["jornada_id"] == j.jornada_id


def test_put_modelo_registra_interacao(app):
    _, criada = chamar(app, "POST", "/api/pub/jornadas", {"origem": "busca"})
    antes = jornada_de(app, criada).ultima_interacao
    app2 = criar_app({}, modo="local", repos=app.repos, relogio=lambda: AGORA.replace(hour=9))
    chamar(
        app2, "PUT", f"/api/pub/jornadas/{criada['jornada_id']}/modelo", {"modelo_id": "tres-mimo"}
    )
    assert jornada_de(app, criada).ultima_interacao > antes


def test_put_modelo_inexistente_e_422_e_nao_altera_a_jornada(app):
    _, criada = chamar(app, "POST", "/api/pub/jornadas", {"origem": "qr"})
    resposta, corpo = chamar(
        app, "PUT", f"/api/pub/jornadas/{criada['jornada_id']}/modelo", {"modelo_id": "nao-existe"}
    )
    assert resposta["statusCode"] == 422
    assert corpo["erro"]["campos"][0]["campo"] == "modelo_id"
    assert jornada_de(app, criada).modelo_id is None


def test_put_modelo_sem_modelo_id_e_422(app):
    _, criada = chamar(app, "POST", "/api/pub/jornadas", {"origem": "qr"})
    resposta, _ = chamar(app, "PUT", f"/api/pub/jornadas/{criada['jornada_id']}/modelo", {})
    assert resposta["statusCode"] == 422


def test_put_modelo_em_jornada_inexistente_e_404(app):
    resposta, corpo = chamar(
        app, "PUT", "/api/pub/jornadas/NAO-EXISTE/modelo", {"modelo_id": "tres-mimo"}
    )
    assert resposta["statusCode"] == 404 and corpo["erro"]["codigo"] == "nao_encontrado"


def test_put_modelo_em_jornada_encerrada_e_409(app):
    _, criada = chamar(app, "POST", "/api/pub/jornadas", {"origem": "qr"})
    app.repos.jornadas.encerrar(criada["jornada_id"], "guia", AGORA)
    resposta, _ = chamar(
        app, "PUT", f"/api/pub/jornadas/{criada['jornada_id']}/modelo", {"modelo_id": "tres-mimo"}
    )
    assert resposta["statusCode"] == 409
    assert jornada_de(app, criada).modelo_id is None


# --------------------------------------------------------------------------- GET /jornadas/{id}


def test_get_jornada_devolve_o_envelope(app):
    _, criada = chamar(
        app, "POST", "/api/pub/jornadas", {"origem": "qr", "modelo_id": "tres-passione"}
    )
    resposta, corpo = chamar(app, "GET", f"/api/pub/jornadas/{criada['jornada_id']}")
    assert resposta["statusCode"] == 200
    assert corpo == {
        "jornada": {
            "jornada_id": criada["jornada_id"],
            "estado": "ativa",
            "risco": {"marcado": False},
            "contato_cs": "pendente",
            "origem": "qr",
            "modelo_id": "tres-passione",
        }
    }


def test_get_jornada_reflete_risco_marcado_e_estado_terminal(app):
    _, criada = chamar(app, "POST", "/api/pub/jornadas", {"origem": "qr"})
    jid = criada["jornada_id"]
    app.repos.jornadas.marcar_risco(jid, "ia", AGORA)
    _, corpo = chamar(app, "GET", f"/api/pub/jornadas/{jid}")
    assert corpo["jornada"]["risco"] == {
        "marcado": True,
        "origem": "ia",
        "em": "2025-01-02T03:04:05Z",
    }
    app.repos.jornadas.encerrar(jid, "guia", AGORA)
    _, corpo = chamar(app, "GET", f"/api/pub/jornadas/{jid}")
    assert corpo["jornada"]["estado"] == "encerrada_guia"


def test_get_jornada_inexistente_e_404(app):
    resposta, _ = chamar(app, "GET", "/api/pub/jornadas/NAO-EXISTE")
    assert resposta["statusCode"] == 404


# --------------------------------------------------------------------------- DynamoDB (moto)


def _criar_tabelas_catalogo(recurso) -> None:
    def tabela(nome, chaves, atributos, indices=None):
        args = {
            "TableName": f"tres-{nome}",
            "KeySchema": chaves,
            "AttributeDefinitions": atributos,
            "BillingMode": "PAY_PER_REQUEST",
        }
        if indices:
            args["GlobalSecondaryIndexes"] = indices
        recurso.create_table(**args)

    hash_ = lambda n: {"AttributeName": n, "KeyType": "HASH"}  # noqa: E731
    range_ = lambda n: {"AttributeName": n, "KeyType": "RANGE"}  # noqa: E731
    attr = lambda n, t="S": {"AttributeName": n, "AttributeType": t}  # noqa: E731
    tabela(
        "modelos",
        [hash_("modelo_id")],
        [attr("modelo_id"), attr("catalogo_pk"), attr("nome_normalizado")],
        [
            {
                "IndexName": "gsi_catalogo",
                "KeySchema": [hash_("catalogo_pk"), range_("nome_normalizado")],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    )
    tabela("problemas", [hash_("problema_id")], [attr("problema_id", "N")])
    tabela(
        "instrucoes",
        [hash_("modelo_id"), range_("problema_variante")],
        [attr("modelo_id"), attr("problema_variante")],
    )
    tabela("jornadas", [hash_("jornada_id")], [attr("jornada_id")])


@pytest.fixture
def app_dynamodb(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        recurso = boto3.resource("dynamodb", region_name="us-east-1")
        _criar_tabelas_catalogo(recurso)
        modelos, problemas, instrucoes = itens_do_seed()
        for modelo in modelos:
            recurso.Table("tres-modelos").put_item(
                Item=para_dynamo({**modelo, "catalogo_pk": "CATALOGO"})
            )
        for problema in problemas:
            recurso.Table("tres-problemas").put_item(Item=para_dynamo(problema))
        for ins in instrucoes:
            item = {**ins, "problema_variante": f"{ins['problema_id']}#{ins['variante']}"}
            recurso.Table("tres-instrucoes").put_item(Item=para_dynamo(item))
        repos = criar_repositorios_dynamodb(recurso, "tres")
        yield criar_app({}, modo="aws", repos=repos, relogio=lambda: AGORA, ssm=object())


def test_dynamodb_lista_modelos_em_ordem_alfabetica(app_dynamodb):
    _, corpo = chamar(app_dynamodb, "GET", "/api/pub/modelos")
    assert [m["nome"] for m in corpo["modelos"]] == ["TRES Circo", "TRES Mimo", "TRES Passione"]


def test_dynamodb_modelo_com_13_problemas_e_seletor(app_dynamodb):
    resposta, corpo = chamar(app_dynamodb, "GET", "/api/pub/modelos/tres-passione")
    assert resposta["statusCode"] == 200
    assert [p["problema_id"] for p in corpo["problemas"]] == list(range(1, 14))
    assert len(corpo["seletor"]["areas"]) >= 4
    resposta, _ = chamar(app_dynamodb, "GET", "/api/pub/modelos/tres-inexistente")
    assert resposta["statusCode"] == 404


def test_dynamodb_le_instrucao_por_modelo_problema_e_variante(app_dynamodb):
    catalogo = app_dynamodb.repos.catalogo
    assert catalogo.obter_instrucao("tres-passione", 10, "externo").variante == "externo"
    assert catalogo.obter_instrucao("tres-passione", 1).dados["passos"][0]["n"] == 1
    assert catalogo.obter_instrucao("tres-circo", 1) is None


def test_dynamodb_fluxo_de_jornada_qr_e_busca(app_dynamodb):
    resposta, criada = chamar(
        app_dynamodb,
        "POST",
        "/api/pub/jornadas",
        {"origem": "qr", "modelo_id": "tres-inexistente", "numero_serie": "AB1"},
    )
    assert resposta["statusCode"] == 201
    jid = criada["jornada_id"]
    resposta, _ = chamar(
        app_dynamodb, "PUT", f"/api/pub/jornadas/{jid}/modelo", {"modelo_id": "tres-circo"}
    )
    assert resposta["statusCode"] == 200
    _, corpo = chamar(app_dynamodb, "GET", f"/api/pub/jornadas/{jid}")
    assert corpo["jornada"]["modelo_id"] == "tres-circo" and corpo["jornada"]["origem"] == "busca"


# --------------------------------------------------------------------------- composição


def test_fabrica_dynamodb_recebe_o_prefixo_de_tres_prefixo():
    recebido = {}

    def fabrica(recurso=None, prefixo="tres", *, recurso_leitura_cache=None):
        recebido["prefixo"] = prefixo
        return criar_repositorios_memoria()

    _chamar_fabrica(fabrica, {"TRES_PREFIXO": "demo"})
    assert recebido == {"prefixo": "demo"}
    _chamar_fabrica(fabrica, {})
    assert recebido == {"prefixo": "tres"}


def test_criar_app_aws_chama_a_fabrica_real_com_o_prefixo(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        app = criar_app({"TRES_PREFIXO": "demo"}, modo="aws", ssm=object())
    assert app.repos.catalogo is not None
    assert app.repos.jornadas._t.nome == "demo-jornadas"


def test_rotas_novas_estao_em_rotas_padrao_da_api_gateway():
    texto = (Path(__file__).resolve().parents[3] / "infra/stacks/api_stack.py").read_text()
    esperadas = {
        'Rota("GET", f"{_PUB}/saude")',
        'Rota("GET", f"{_PUB}/modelos")',
        'Rota("GET", f"{_PUB}/modelos/{{modelo_id}}")',
        'Rota("POST", f"{_PUB}/jornadas")',
        'Rota("PUT", f"{_PUB}/jornadas/{{id}}/modelo")',
        'Rota("GET", f"{_PUB}/jornadas/{{id}}")',
    }
    assert {e for e in esperadas if e not in texto} == set()
    chaves = {r.chave for r in ROTEADOR.rotas}
    for chave in (
        "GET /api/pub/saude",
        "GET /api/pub/modelos",
        "GET /api/pub/modelos/{modelo_id}",
        "POST /api/pub/jornadas",
        "PUT /api/pub/jornadas/{id}/modelo",
        "GET /api/pub/jornadas/{id}",
    ):
        assert chave in chaves
