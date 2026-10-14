"""Rotas do Guia_Diagnostico: instrução e eventos (tarefa 11.3)."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core import criar_app, criar_roteador, processar
from dominio.guia import validar_instrucao
from repositorios import criar_repositorios_memoria
from repositorios.catalogo import CatalogoMemoria
from repositorios.ids import novo_ulid
from repositorios.modelos import Jornada
from servicos.escalada import ja_tentado_de_eventos

AGORA = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)
DIA = date(2025, 1, 2)
ROTEADOR = criar_roteador()
SEED = Path(__file__).resolve().parents[3] / "seed"
JID = "01JGUIA00000000000000000A"


def _sem_comentarios(valor: Any) -> Any:
    if isinstance(valor, dict):
        return {k: _sem_comentarios(v) for k, v in valor.items() if not k.startswith("_")}
    if isinstance(valor, list):
        return [_sem_comentarios(v) for v in valor]
    return valor


def _json(*partes: str) -> Any:
    return _sem_comentarios(json.loads(SEED.joinpath(*partes).read_text(encoding="utf-8")))


def itens_do_seed() -> tuple[list[dict], list[dict], list[dict]]:
    modelos = _json("catalogo.json")["modelos"]
    instrucoes = _json("instrucoes", "tres-passione.json")["instrucoes"]
    return modelos, _json("problemas.json")["problemas"], instrucoes


def _app(instrucoes_extra: list[dict] | None = None):
    repos = criar_repositorios_memoria()
    modelos, problemas, instrucoes = itens_do_seed()
    object.__setattr__(
        repos,
        "catalogo",
        CatalogoMemoria.de_itens(modelos, problemas, instrucoes + (instrucoes_extra or [])),
    )
    return criar_app({}, modo="local", repos=repos, relogio=lambda: AGORA)


@pytest.fixture
def app():
    app = _app()
    criar_jornada(app, JID, "tres-passione")
    return app


def criar_jornada(app, jid: str, modelo_id: str | None):
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


def chamar(app, metodo, caminho, corpo=None, cabecalhos=None, consulta=None):
    evento: dict[str, Any] = {
        "rawPath": caminho,
        "headers": cabecalhos or {},
        "requestContext": {"requestId": "req-1", "http": {"method": metodo}},
    }
    if consulta:
        evento["queryStringParameters"] = consulta
    if corpo is not None:
        evento["body"] = json.dumps(corpo)
    resposta = processar(app, ROTEADOR, evento)
    return resposta, (json.loads(resposta["body"]) if resposta["body"] else None)


def get_instrucao(app, jid=JID, **consulta):
    return chamar(app, "GET", f"/api/pub/jornadas/{jid}/instrucao", consulta=consulta)


def post_evento(app, corpo, jid=JID, cabecalhos=None):
    return chamar(app, "POST", f"/api/pub/jornadas/{jid}/eventos", corpo, cabecalhos)


def evento_corpo(tipo="selecionado", problema_id=1, **extra):
    corpo = {
        "tipo": tipo,
        "problema_id": problema_id,
        "ocorrido_em": "2025-01-02T03:04:00.123Z",
        "evento_id": novo_ulid(AGORA),
        **extra,
    }
    return corpo


def contador(app, problema_id: int) -> int:
    return app.repos.agregados.obter(DIA, f"problema_sel#{problema_id}")


# --------------------------------------------------------------------------- GET instrucao


def test_instrucao_devolve_passos_ordenados_no_formato_do_front(app):
    resposta, corpo = get_instrucao(app, problema_id="1")
    assert resposta["statusCode"] == 200
    ins = corpo["instrucao"]
    assert (ins["modelo_id"], ins["problema_id"], ins["variante"]) == ("tres-passione", 1, "padrao")
    assert [p["n"] for p in ins["passos"]] == list(range(1, len(ins["passos"]) + 1))
    assert {"n", "texto", "alt", "texto_equivalente", "midia_url", "midia_tipo"} <= set(
        ins["passos"][0]
    )
    assert validar_instrucao(ins) == []


def test_variante_externo_do_vazamento_e_padrao_sao_instrucoes_distintas_do_catalogo(app):
    _, padrao = get_instrucao(app, problema_id="10")
    resposta, externo = get_instrucao(app, problema_id="10", variante="externo")
    assert resposta["statusCode"] == 200
    assert padrao["instrucao"]["variante"] == "padrao"
    assert externo["instrucao"]["variante"] == "externo"


def test_variante_externo_sem_instrucao_nao_cai_para_padrao(app):
    resposta, corpo = get_instrucao(app, problema_id="1", variante="externo")
    assert resposta["statusCode"] == 404 and corpo["erro"]["codigo"] == "nao_encontrado"


def test_modelo_sem_instrucao_e_404_funcional_e_jornada_intacta(app):
    criar_jornada(app, "01JGUIA00000000000000000B", "tres-circo")
    antes = app.repos.jornadas.obter("01JGUIA00000000000000000B")
    resposta, corpo = get_instrucao(app, "01JGUIA00000000000000000B", problema_id="1")
    assert resposta["statusCode"] == 404 and corpo["erro"]["codigo"] == "nao_encontrado"
    assert app.repos.jornadas.obter("01JGUIA00000000000000000B") == antes


def test_jornada_sem_modelo_e_problema_fora_do_catalogo_sao_404(app):
    criar_jornada(app, "01JGUIA00000000000000000C", None)
    assert get_instrucao(app, "01JGUIA00000000000000000C", problema_id="1")[0]["statusCode"] == 404
    assert get_instrucao(app, problema_id="14")[0]["statusCode"] == 404
    assert get_instrucao(app, problema_id="0")[0]["statusCode"] == 404


def test_jornada_inexistente_e_404(app):
    resposta, _ = get_instrucao(app, "NAO-EXISTE", problema_id="1")
    assert resposta["statusCode"] == 404


@pytest.mark.parametrize(
    "consulta, campo",
    [
        ({}, "problema_id"),
        ({"problema_id": "abc"}, "problema_id"),
        ({"problema_id": "1.5"}, "problema_id"),
        ({"problema_id": "1", "variante": "interno"}, "variante"),
    ],
)
def test_consulta_malformada_e_422_com_o_campo(app, consulta, campo):
    resposta, corpo = get_instrucao(app, **consulta)
    assert resposta["statusCode"] == 422
    assert campo in {c["campo"] for c in corpo["erro"]["campos"]}


def test_instrucao_fora_das_regras_do_req_3_3_nao_e_exibida():
    passos = [{"n": n, "texto": "x", "alt": "x", "texto_equivalente": "x"} for n in range(1, 12)]
    app = _app(
        [{"modelo_id": "tres-circo", "problema_id": 1, "variante": "padrao", "passos": passos}]
    )
    criar_jornada(app, JID, "tres-circo")
    assert get_instrucao(app, problema_id="1")[0]["statusCode"] == 404  # 11 passos


def test_passo_com_midia_estatica_url_e_repassado():
    passos = [
        {
            "n": 1,
            "texto": "Faça isto.",
            "alt": "alt",
            "texto_equivalente": "eq",
            "midia_url": "/m.gif",
            "midia_tipo": "animacao",
            "midia_estatica_url": "/m.png",
        }
    ]
    app = _app(
        [{"modelo_id": "tres-circo", "problema_id": 1, "variante": "padrao", "passos": passos}]
    )
    criar_jornada(app, JID, "tres-circo")
    _, corpo = get_instrucao(app, problema_id="1")
    assert corpo["instrucao"]["passos"][0]["midia_estatica_url"] == "/m.png"


@given(problema_id=st.integers(1, 13), variante=st.sampled_from(["padrao", "externo"]))
def test_instrucao_e_deterministica(problema_id, variante):
    app = _app()
    criar_jornada(app, JID, "tres-passione")
    primeira = get_instrucao(app, problema_id=str(problema_id), variante=variante)
    segunda = get_instrucao(app, problema_id=str(problema_id), variante=variante)
    assert primeira[0]["statusCode"] == segunda[0]["statusCode"]
    assert primeira[1] == segunda[1]


# --------------------------------------------------------------------------- POST eventos


def test_selecionado_registra_evento_problema_horario_e_interacao(app):
    corpo = evento_corpo("selecionado", 6)
    resposta, resp = post_evento(app, corpo)
    assert resposta["statusCode"] == 201 and resp["registrado"] is True
    [evento] = app.repos.eventos.listar(JID)
    assert (evento.tipo, evento.dados, evento.evento_id) == (
        "selecionado",
        {"problema_id": 6},
        corpo["evento_id"],
    )
    assert evento.em == datetime(2025, 1, 2, 3, 4, 0, 123000, tzinfo=UTC)
    jornada = app.repos.jornadas.obter(JID)
    assert jornada.problema_id == 6 and jornada.ultima_interacao == AGORA
    assert contador(app, 6) == 1


def test_contador_so_na_primeira_selecao_do_problema_na_jornada(app):
    post_evento(app, evento_corpo("selecionado", 3))
    post_evento(app, evento_corpo("selecionado", 3))  # evento novo, mesmo problema
    assert contador(app, 3) == 1
    post_evento(app, evento_corpo("selecionado", 4))
    assert (contador(app, 3), contador(app, 4)) == (1, 1)
    criar_jornada(app, "01JGUIA00000000000000000D", "tres-passione")
    post_evento(app, evento_corpo("selecionado", 3), jid="01JGUIA00000000000000000D")
    assert contador(app, 3) == 2  # outra Jornada soma
    assert len(app.repos.eventos.listar(JID)) == 3  # os três eventos ficam registrados


def test_reenvio_com_o_mesmo_evento_id_e_idempotente(app):
    corpo = evento_corpo("selecionado", 2)
    r1, _ = post_evento(app, corpo)
    r2, c2 = post_evento(app, corpo)
    assert (r1["statusCode"], r2["statusCode"]) == (201, 200) and c2["registrado"] is False
    assert len(app.repos.eventos.listar(JID)) == 1 and contador(app, 2) == 1


def test_idempotency_key_vale_quando_o_corpo_nao_traz_evento_id(app):
    corpo = evento_corpo("exibido", 2, passo=1)
    del corpo["evento_id"]
    cab = {"Idempotency-Key": "chave-qualquer-1"}
    post_evento(app, corpo, cabecalhos=cab)
    r2, _ = post_evento(app, corpo, cabecalhos=cab)
    assert r2["statusCode"] == 200 and len(app.repos.eventos.listar(JID)) == 1


def test_evento_id_que_nao_e_ulid_ainda_deduplica(app):
    corpo = evento_corpo("exibido", 2, passo=1, evento_id="nao-e-ulid")
    post_evento(app, corpo)
    r2, _ = post_evento(app, corpo)
    assert r2["statusCode"] == 200 and len(app.repos.eventos.listar(JID)) == 1


def test_exibido_guarda_numero_do_passo(app):
    post_evento(app, evento_corpo("exibido", 1, passo=2))
    [evento] = app.repos.eventos.listar(JID)
    assert (evento.tipo, evento.dados) == ("exibido", {"problema_id": 1, "passo_n": 2})
    assert contador(app, 1) == 0 and app.repos.jornadas.obter(JID).problema_id is None


def test_concluido_vira_passo_concluido_com_o_texto_do_passo(app):
    _, ins = get_instrucao(app, problema_id="1")
    post_evento(app, evento_corpo("concluido", 1, passo=2))
    [evento] = app.repos.eventos.listar(JID)
    assert evento.tipo == "passo_concluido"
    assert evento.dados == {
        "problema_id": 1,
        "passo_n": 2,
        "passo": ins["instrucao"]["passos"][1]["texto"],
        "camada": "guia",
        "resultado": "sem resposta",
    }
    # Contrato com o Pacote (servicos/escalada.py): aparece no "já tentado".
    [item] = ja_tentado_de_eventos(app.repos.eventos.listar(JID))
    assert (item.passo, item.camada, item.resultado) == (
        ins["instrucao"]["passos"][1]["texto"],
        "guia",
        "sem resposta",
    )


def test_concluido_de_vazamento_externo_usa_a_variante_informada(app):
    _, ext = get_instrucao(app, problema_id="10", variante="externo")
    post_evento(app, evento_corpo("concluido", 10, passo=1, variante="externo"))
    [evento] = app.repos.eventos.listar(JID)
    assert evento.dados["passo"] == ext["instrucao"]["passos"][0]["texto"]


def test_concluido_sem_instrucao_grava_sem_texto_e_fica_fora_do_ja_tentado(app):
    criar_jornada(app, "01JGUIA00000000000000000E", "tres-circo")
    resposta, _ = post_evento(
        app, evento_corpo("concluido", 1, passo=1), jid="01JGUIA00000000000000000E"
    )
    assert resposta["statusCode"] == 201
    eventos = app.repos.eventos.listar("01JGUIA00000000000000000E")
    assert eventos[0].tipo == "passo_concluido" and "passo" not in eventos[0].dados
    assert ja_tentado_de_eventos(eventos) == ()


def test_ocorrido_em_com_fuso_e_convertido_para_utc_e_futuro_vira_horario_do_servidor(app):
    post_evento(app, evento_corpo("exibido", 1, passo=1, ocorrido_em="2025-01-02T00:00:10-03:00"))
    post_evento(app, evento_corpo("exibido", 1, passo=2, ocorrido_em="2999-01-01T00:00:00Z"))
    primeiro, segundo = sorted(app.repos.eventos.listar(JID), key=lambda e: e.dados["passo_n"])
    assert primeiro.em == datetime(2025, 1, 2, 3, 0, 10, tzinfo=UTC)
    assert segundo.em == AGORA


@pytest.mark.parametrize(
    "mudanca, campo",
    [
        ({"tipo": "visto"}, "tipo"),
        ({"tipo": None}, "tipo"),
        ({"problema_id": 14}, "problema_id"),
        ({"problema_id": "1"}, "problema_id"),
        ({"problema_id": True}, "problema_id"),
        ({"tipo": "exibido", "passo": None}, "passo"),
        ({"tipo": "concluido", "passo": 11}, "passo"),
        ({"tipo": "concluido", "passo": 0}, "passo"),
        ({"ocorrido_em": None}, "ocorrido_em"),
        ({"ocorrido_em": "ontem"}, "ocorrido_em"),
        ({"ocorrido_em": "2025-01-02T03:04:00"}, "ocorrido_em"),
        ({"variante": "interno"}, "variante"),
    ],
)
def test_corpo_invalido_e_422_e_nada_e_gravado(app, mudanca, campo):
    resposta, corpo = post_evento(app, {**evento_corpo("selecionado", 1), **mudanca})
    assert resposta["statusCode"] == 422
    assert campo in {c["campo"] for c in corpo["erro"]["campos"]}
    assert app.repos.eventos.listar(JID) == [] and contador(app, 1) == 0


def test_corpo_que_nao_e_objeto_e_400(app):
    assert post_evento(app, ["x"])[0]["statusCode"] == 400


def test_jornada_inexistente_e_404_e_encerrada_e_409(app):
    assert post_evento(app, evento_corpo(), jid="NAO-EXISTE")[0]["statusCode"] == 404
    app.repos.jornadas.encerrar(JID, "guia", AGORA)
    resposta, _ = post_evento(app, evento_corpo())
    assert resposta["statusCode"] == 409
    assert app.repos.eventos.listar(JID) == [] and contador(app, 1) == 0


@given(
    selecoes=st.lists(st.integers(1, 13), min_size=1, max_size=12),
    repeticoes=st.integers(1, 3),
)
def test_contador_diario_e_o_numero_de_problemas_distintos_selecionados(selecoes, repeticoes):
    app = _app()
    criar_jornada(app, JID, "tres-passione")
    for problema_id in selecoes:
        corpo = evento_corpo("selecionado", problema_id)
        for _ in range(repeticoes):  # reenvios do mesmo evento
            post_evento(app, corpo)
    for problema_id in set(selecoes):
        assert contador(app, problema_id) == 1


def test_rotas_estao_em_rotas_padrao_da_api_gateway():
    texto = (Path(__file__).resolve().parents[3] / "infra/stacks/api_stack.py").read_text()
    assert 'Rota("GET", f"{_PUB}/jornadas/{{id}}/instrucao")' in texto
    assert 'Rota("POST", f"{_PUB}/jornadas/{{id}}/eventos")' in texto
    chaves = {r.chave for r in ROTEADOR.rotas}
    assert "GET /api/pub/jornadas/{id}/instrucao" in chaves
    assert "POST /api/pub/jornadas/{id}/eventos" in chaves


# --------------------------------------------------------------------------- DynamoDB (moto)


def test_dynamodb_instrucao_e_eventos_com_contador(monkeypatch):
    import boto3
    from moto import mock_aws

    from repositorios.dynamodb import criar_repositorios_dynamodb
    from repositorios.dynamodb._base import para_dynamo

    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        recurso = boto3.resource("dynamodb", region_name="us-east-1")

        def tabela(nome, chaves, atributos, indices=None):
            args = {
                "TableName": f"tres-{nome}",
                "KeySchema": [{"AttributeName": n, "KeyType": t} for n, t in chaves],
                "AttributeDefinitions": [
                    {"AttributeName": n, "AttributeType": t} for n, t in atributos
                ],
                "BillingMode": "PAY_PER_REQUEST",
            }
            if indices:
                args["GlobalSecondaryIndexes"] = indices
            recurso.create_table(**args)

        def gsi(nome, pk, sk):
            return {
                "IndexName": nome,
                "KeySchema": [
                    {"AttributeName": pk, "KeyType": "HASH"},
                    {"AttributeName": sk, "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }

        tabela(
            "jornadas",
            [("jornada_id", "HASH")],
            [
                ("jornada_id", "S"),
                ("ativa_pk", "S"),
                ("ultima_interacao", "S"),
                ("encerrada_pk", "S"),
                ("encerrada_em", "S"),
            ],
            [
                gsi("gsi_ativas", "ativa_pk", "ultima_interacao"),
                gsi("gsi_encerradas", "encerrada_pk", "encerrada_em"),
            ],
        )
        tabela(
            "eventos",
            [("jornada_id", "HASH"), ("ts_ulid", "RANGE")],
            [("jornada_id", "S"), ("ts_ulid", "S")],
        )
        tabela(
            "agregados_dia",
            [("dia", "HASH"), ("metrica", "RANGE")],
            [("dia", "S"), ("metrica", "S")],
        )
        tabela(
            "instrucoes",
            [("modelo_id", "HASH"), ("problema_variante", "RANGE")],
            [("modelo_id", "S"), ("problema_variante", "S")],
        )
        modelos, problemas, instrucoes = itens_do_seed()
        for ins in instrucoes:
            item = {**ins, "problema_variante": f"{ins['problema_id']}#{ins['variante']}"}
            recurso.Table("tres-instrucoes").put_item(Item=para_dynamo(item))
        repos = criar_repositorios_dynamodb(recurso, "tres")
        app = criar_app({}, modo="aws", repos=repos, relogio=lambda: AGORA, ssm=object())
        criar_jornada(app, JID, "tres-passione")

        resposta, corpo = get_instrucao(app, problema_id="1")
        assert resposta["statusCode"] == 200 and corpo["instrucao"]["passos"][0]["n"] == 1

        selecionado = evento_corpo("selecionado", 5)
        assert post_evento(app, selecionado)[0]["statusCode"] == 201
        assert post_evento(app, selecionado)[0]["statusCode"] == 200
        assert post_evento(app, evento_corpo("concluido", 5, passo=1))[0]["statusCode"] == 201
        assert contador(app, 5) == 1
        tipos = [e.tipo for e in app.repos.eventos.listar(JID)]
        assert sorted(tipos) == ["passo_concluido", "selecionado"]
        [concluido] = [e for e in app.repos.eventos.listar(JID) if e.tipo == "passo_concluido"]
        assert concluido.dados["passo"] and concluido.dados["passo_n"] == 1
