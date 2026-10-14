"""Testes do roteador, do envelope de erro, da validação e dos handlers da Lambda `api`."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime

import pytest

from core import ErroApi, Resposta, Rota, Roteador, criar_app, criar_roteador, descobrir_rotas
from core.erros import ErroConfiguracao, conflito
from core.processamento import processar
from core.validacao import Validador, exigir_objeto
from handlers import _comum
from repositorios import ErroNaoEncontrado, ErroRepositorio

AGORA = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)


def evento(metodo: str, caminho: str, corpo=None, cabecalhos=None, **extra):
    ev = {
        "rawPath": caminho,
        "headers": cabecalhos or {},
        "requestContext": {"requestId": "req-abc", "http": {"method": metodo}},
        **extra,
    }
    if corpo is not None:
        ev["body"] = corpo if isinstance(corpo, str) else json.dumps(corpo)
    return ev


@pytest.fixture
def app():
    return criar_app({}, modo="local", relogio=lambda: AGORA)


def chamar(app, rotas, metodo, caminho, corpo=None, autenticador=None, **kw):
    resposta = processar(app, Roteador(rotas, autenticador), evento(metodo, caminho, corpo, **kw))
    corpo_resp = json.loads(resposta["body"]) if resposta["body"] else None
    return resposta, corpo_resp


# --------------------------------------------------------------------------- descoberta
def test_descobre_rota_de_saude_em_routes():
    chaves = {r.chave for r in descobrir_rotas()}
    assert "GET /api/pub/saude" in chaves


def test_descoberta_exige_rotas_no_modulo(tmp_path, monkeypatch):
    pacote = tmp_path / "rotas_ruins"
    pacote.mkdir()
    (pacote / "__init__.py").write_text("")
    (pacote / "sem_rotas.py").write_text("X = 1\n")
    (pacote / "_ignorado.py").write_text("raise RuntimeError('não deve importar')\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(ErroConfiguracao, match="sem ROTAS"):
        descobrir_rotas("rotas_ruins")


def test_descobre_varios_modulos(tmp_path, monkeypatch):
    pacote = tmp_path / "rotas_ok"
    pacote.mkdir()
    (pacote / "__init__.py").write_text("")
    for nome in ("a", "b"):
        (pacote / f"{nome}.py").write_text(
            "from core.roteador import Rota\n"
            f"ROTAS = [Rota('GET', '/{nome}', lambda ctx: {{'n': '{nome}'}})]\n"
        )
    monkeypatch.syspath_prepend(str(tmp_path))
    assert [r.caminho for r in descobrir_rotas("rotas_ok")] == ["/a", "/b"]


def test_rota_duplicada_e_erro_de_configuracao():
    h = lambda ctx: {}  # noqa: E731
    with pytest.raises(ErroConfiguracao, match="duplicada"):
        Roteador([Rota("GET", "/x/{a}", h), Rota("GET", "/x/{b}", h)])


# --------------------------------------------------------------------------- despacho
def test_saude_responde_200_json_utf8(app):
    resp = processar(app, criar_roteador(), evento("GET", "/api/pub/saude"))
    assert resp["statusCode"] == 200
    assert resp["headers"]["Content-Type"] == "application/json; charset=utf-8"
    assert resp["headers"]["Cache-Control"] == "no-store"
    assert json.loads(resp["body"])["status"] == "ok"


def test_parametros_de_caminho_e_literal_tem_precedencia(app):
    rotas = [
        Rota("GET", "/modelos/{modelo_id}", lambda c: {"id": c.req.params["modelo_id"]}),
        Rota("GET", "/modelos/busca", lambda c: {"id": "literal"}),
    ]
    assert chamar(app, rotas, "GET", "/api/pub/modelos/busca")[1] == {"id": "literal"}
    assert chamar(app, rotas, "GET", "/api/pub/modelos/m1")[1] == {"id": "m1"}


def test_handler_pode_devolver_resposta_com_status_e_204(app):
    rotas = [
        Rota("POST", "/a", lambda c: Resposta.criado({"ok": True})),
        Rota("POST", "/b", lambda c: None),
    ]
    assert chamar(app, rotas, "POST", "/api/pub/a")[0]["statusCode"] == 201
    r, corpo = chamar(app, rotas, "POST", "/api/pub/b")
    assert r["statusCode"] == 204 and corpo is None


def test_404_e_405_no_envelope_padrao(app):
    rotas = [Rota("GET", "/a", lambda c: {})]
    r, corpo = chamar(app, rotas, "GET", "/api/pub/nada")
    assert r["statusCode"] == 404 and corpo["erro"]["codigo"] == "nao_encontrado"
    assert "campos" not in corpo["erro"]
    r, corpo = chamar(app, rotas, "DELETE", "/api/pub/a")
    assert r["statusCode"] == 405 and r["headers"]["Allow"] == "GET"
    assert corpo["erro"]["codigo"] == "metodo_nao_permitido"


def test_erro_api_vira_envelope_com_campos(app):
    def handler(ctx):
        v = Validador(exigir_objeto(ctx.json()))
        v.texto("nome", maximo=3)
        v.inteiro("nota", minimo=1, maximo=5)
        v.levantar_se_erros()

    r, corpo = chamar(
        app, [Rota("POST", "/v", handler)], "POST", "/api/pub/v", {"nome": "abcd", "nota": 9}
    )
    assert r["statusCode"] == 422
    assert corpo["erro"]["codigo"] == "validacao"
    assert {c["campo"] for c in corpo["erro"]["campos"]} == {"nome", "nota"}
    assert all(set(c) == {"campo", "motivo"} for c in corpo["erro"]["campos"])


def test_json_malformado_e_corpo_nao_objeto(app):
    rota = Rota("POST", "/v", lambda c: exigir_objeto(c.json()))
    r, corpo = chamar(app, [rota], "POST", "/api/pub/v", "{nao é json")
    assert r["statusCode"] == 400 and corpo["erro"]["codigo"] == "json_invalido"
    assert "nao é json" not in r["body"]  # o corpo nunca volta na mensagem de erro
    r, corpo = chamar(app, [rota], "POST", "/api/pub/v", "[1,2]")
    assert r["statusCode"] == 400
    r, _ = chamar(app, [rota], "POST", "/api/pub/v")  # sem corpo
    assert r["statusCode"] == 400


def test_corpo_base64_e_limite_de_tamanho(app):
    rota = Rota("POST", "/v", lambda c: c.json())
    ev = evento("POST", "/api/pub/v")
    ev["body"] = base64.b64encode(json.dumps({"a": "é"}).encode()).decode()
    ev["isBase64Encoded"] = True
    assert json.loads(processar(app, Roteador([rota]), ev)["body"]) == {"a": "é"}
    ev["body"] = "x" * (256 * 1024 + 1)
    ev["isBase64Encoded"] = False
    assert processar(app, Roteador([rota]), ev)["statusCode"] == 413


@pytest.mark.parametrize(
    ("excecao", "status", "codigo"),
    [
        (conflito("Já tem responsável."), 409, "conflito"),
        (ErroNaoEncontrado("jornadas", "x"), 404, "nao_encontrado"),
        (ErroRepositorio("falha com telefone 11987654321"), 502, "dependencia_indisponivel"),
        (TimeoutError("lento"), 504, "tempo_esgotado"),
        (RuntimeError("segredo 123.456.789-09"), 500, "erro_interno"),
    ],
)
def test_mapeamento_de_excecoes_sem_vazar_detalhes(app, excecao, status, codigo):
    def handler(ctx):
        raise excecao

    r, corpo = chamar(app, [Rota("GET", "/e", handler)], "GET", "/api/pub/e")
    assert r["statusCode"] == status and corpo["erro"]["codigo"] == codigo
    if status >= 500:
        assert "11987654321" not in r["body"] and "123.456" not in r["body"]


def test_excecao_nao_vaza_em_log(app, caplog):
    def handler(ctx):
        raise RuntimeError("telefone 11987654321")

    with caplog.at_level("INFO", logger="tres"):
        chamar(app, [Rota("GET", "/e", handler)], "GET", "/api/pub/e")
    saida = " ".join(r.getMessage() for r in caplog.records)
    assert "11987654321" not in saida and "RuntimeError" in saida


# --------------------------------------------------------------------------- autenticação
def test_rota_cs_sem_autenticador_falha_fechada(app):
    rotas = [Rota("GET", "/fila", lambda c: {"x": 1}, escopo="cs")]
    r, corpo = chamar(app, rotas, "GET", "/api/cs/fila")
    assert r["statusCode"] == 401 and corpo["erro"]["codigo"] == "nao_autenticado"


def test_rota_cs_com_autenticador_e_login_publico(app):
    def autenticador(ctx, rota):
        if ctx.req.cabecalho("x-teste") != "ok":
            raise ErroApi(403, "sem_permissao", "Sem permissão.")
        return {"nome": "ana"}

    rotas = [
        Rota("GET", "/fila", lambda c: {"quem": c.usuario["nome"]}, escopo="cs"),
        Rota("POST", "/login", lambda c: {"ok": True}, escopo="cs", autenticada=False),
    ]
    assert (
        chamar(app, rotas, "GET", "/api/cs/fila", autenticador=autenticador)[0]["statusCode"] == 403
    )
    ok = chamar(
        app, rotas, "GET", "/api/cs/fila", autenticador=autenticador, cabecalhos={"x-teste": "ok"}
    )
    assert ok[1] == {"quem": "ana"}
    assert chamar(app, rotas, "POST", "/api/cs/login")[0]["statusCode"] == 200


def test_filtro_por_destino():
    h = lambda c: {}  # noqa: E731
    roteador = Roteador([Rota("GET", "/a", h), Rota("GET", "/b", h, destino="dados_pessoais")])
    assert [r.caminho for r in roteador.filtrar("api").rotas] == ["/a"]
    assert [r.caminho for r in roteador.filtrar("dados_pessoais").rotas] == ["/b"]


# --------------------------------------------------------------------------- validação
def test_validador_tipos():
    v = Validador({"a": True, "b": "  ", "c": "x", "d": "z"})
    v.inteiro("a")  # bool não é inteiro
    v.texto("b")  # só espaços
    v.escolha("c", ["externo", "interno"])
    v.booleano("e")  # ausente e obrigatório
    assert v.texto("d", maximo=5) == "z"
    assert {e.campo for e in v.erros} == {"a", "b", "c", "e"}


# --------------------------------------------------------------------------- app e handlers
def test_criar_app_aws_sem_adaptador_falha_em_vez_de_usar_memoria(monkeypatch):
    monkeypatch.setattr("core.app.MODULO_DYNAMODB", "repositorios.modulo_inexistente")
    with pytest.raises(ErroConfiguracao, match="indisponíveis"):
        criar_app({}, modo="aws", ssm=object())


def test_criar_app_usa_fabrica_dynamodb_injetada_com_ambiente():
    from repositorios import criar_repositorios_memoria

    recebido = {}

    def fabrica(ambiente):
        recebido.update(ambiente)
        return criar_repositorios_memoria()

    app = criar_app(
        {"TRES_TABELA_JORNADAS": "t"}, modo="aws", fabrica_dynamodb=fabrica, ssm=object()
    )
    assert recebido == {"TRES_TABELA_JORNADAS": "t"} and app.modo == "aws"


def test_modo_invalido():
    with pytest.raises(ErroConfiguracao):
        criar_app({}, modo="outro")


def test_lambda_handler_api_e_dados_pessoais(monkeypatch):
    monkeypatch.setenv("TRES_MODO", "local")
    _comum.redefinir()
    from handlers.api import lambda_handler
    from handlers.dados_pessoais import lambda_handler as lambda_dados

    assert lambda_handler(evento("GET", "/api/pub/saude"), None)["statusCode"] == 200
    # A rota de saúde é da Lambda `api`; a de dados pessoais não a atende.
    assert lambda_dados(evento("GET", "/api/pub/saude"), None)["statusCode"] == 404
    _comum.redefinir()


def test_handlers_do_cdk_resolvem():
    import importlib

    from handlers import api  # noqa: F401

    for nome in ("api", "dados_pessoais", "enriquecimento", "encerramento", "varredura"):
        assert callable(importlib.import_module(f"handlers.{nome}").lambda_handler)
