"""Testes de asserção da borda (CloudFront) e do autorizador de origem (tarefa 8.3)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from stacks.api_stack import CABECALHO_ORIGEM as CABECALHO_API
from stacks.api_stack import ApiStack
from stacks.armazenamento_stack import ArmazenamentoStack
from stacks.borda_stack import (
    CABECALHO_ORIGEM,
    ORIGEM_TIMEOUT_S,
    BordaStack,
    montar_csp,
)
from stacks.dados_stack import DadosStack

PREMISSAS = Path(__file__).resolve().parents[2] / "services" / "agente" / "premissas.py"
AUTORIZADOR = Path(__file__).resolve().parents[1] / "lambdas" / "autorizador_origem" / "index.py"


def _carregar(nome: str, caminho: Path):
    spec = importlib.util.spec_from_file_location(nome, caminho)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture(scope="module")
def pilha() -> dict:
    app = cdk.App()
    dados = DadosStack(app, "teste-dados")
    armaz = ArmazenamentoStack(app, "teste-armazenamento", chave=dados.chave)
    api = ApiStack(app, "teste-api", dados=dados, armazenamento=armaz)
    borda = BordaStack(
        app,
        "teste-borda",
        bucket_site=armaz.bucket_site,
        bucket_fotos=armaz.bucket_fotos,
        dominio_api=api.dominio_api,
        nome_segredo_origem=api.nome_segredo_origem,
    )
    return {
        "borda": Template.from_stack(borda),
        "armazenamento": Template.from_stack(armaz),
        "api": Template.from_stack(api),
    }


def _distribuicao(t: Template) -> dict:
    achadas = t.find_resources("AWS::CloudFront::Distribution")
    assert len(achadas) == 1
    return next(iter(achadas.values()))["Properties"]["DistributionConfig"]


def _comportamentos(t: Template) -> list[dict]:
    cfg = _distribuicao(t)
    return [cfg["DefaultCacheBehavior"], *cfg["CacheBehaviors"]]


# --- Req 18.7: HTTPS ---------------------------------------------------------------------------
def test_todo_comportamento_redireciona_http_para_https(pilha) -> None:
    comportamentos = _comportamentos(pilha["borda"])
    assert len(comportamentos) == 3
    for c in comportamentos:
        assert c["ViewerProtocolPolicy"] == "redirect-to-https"


def test_hsts_csp_nosniff_e_referrer_policy_na_politica_de_resposta(pilha) -> None:
    t = pilha["borda"]
    t.has_resource_properties(
        "AWS::CloudFront::ResponseHeadersPolicy",
        {
            "ResponseHeadersPolicyConfig": {
                "SecurityHeadersConfig": {
                    "StrictTransportSecurity": {
                        "AccessControlMaxAgeSec": Match.any_value(),
                        "IncludeSubdomains": True,
                        "Override": True,
                    },
                    "ContentSecurityPolicy": {
                        "ContentSecurityPolicy": Match.any_value(),
                        "Override": True,
                    },
                    "ContentTypeOptions": {"Override": True},
                    "ReferrerPolicy": {"ReferrerPolicy": "no-referrer", "Override": True},
                    "FrameOptions": {"FrameOption": "DENY", "Override": True},
                },
            }
        },
    )
    politica = next(iter(t.find_resources("AWS::CloudFront::ResponseHeadersPolicy").values()))[
        "Properties"
    ]["ResponseHeadersPolicyConfig"]["SecurityHeadersConfig"]
    assert politica["StrictTransportSecurity"]["AccessControlMaxAgeSec"] >= 31_536_000
    # Todos os comportamentos (site, catálogo e API) usam a mesma política.
    ids = {json.dumps(c["ResponseHeadersPolicyId"]) for c in _comportamentos(t)}
    assert len(ids) == 1


def test_csp_restritiva() -> None:
    csp = montar_csp("fotos.s3.sa-east-1.amazonaws.com")
    diretivas = {d.split(" ", 1)[0]: d for d in csp.split("; ")}
    assert diretivas["default-src"] == "default-src 'self'"
    assert diretivas["script-src"] == "script-src 'self'"
    assert diretivas["object-src"] == "object-src 'none'"
    assert diretivas["frame-ancestors"] == "frame-ancestors 'none'"
    assert "upgrade-insecure-requests" in diretivas
    assert "https://fotos.s3.sa-east-1.amazonaws.com" in diretivas["connect-src"]
    assert "https://fotos.s3.sa-east-1.amazonaws.com" in diretivas["img-src"]
    assert "'unsafe-eval'" not in csp and "*" not in csp
    assert "'unsafe-inline'" not in diretivas["script-src"]


# --- Mesma origem para site e /api/* ----------------------------------------------------------
def test_site_e_api_na_mesma_distribuicao_com_origem_de_30s_ou_mais(pilha) -> None:
    cfg = _distribuicao(pilha["borda"])
    padroes = [c["PathPattern"] for c in cfg["CacheBehaviors"]]
    assert padroes == ["/api/pub/modelos*", "/api/*"]  # o mais específico primeiro
    assert len(cfg["Origins"]) == 2
    s3 = next(o for o in cfg["Origins"] if "S3OriginConfig" in o)
    assert s3["OriginAccessControlId"]
    api = next(o for o in cfg["Origins"] if "CustomOriginConfig" in o)
    assert api["CustomOriginConfig"]["OriginProtocolPolicy"] == "https-only"
    assert api["CustomOriginConfig"]["OriginReadTimeout"] == ORIGEM_TIMEOUT_S >= 30
    premissas = _carregar("premissas", PREMISSAS)
    assert ORIGEM_TIMEOUT_S >= premissas.API_GATEWAY_HTTP_TIMEOUT_MAX_S
    assert cfg["DefaultRootObject"] == "index.html"


def test_api_sem_cache_com_todos_os_metodos_e_sem_repassar_o_host(pilha) -> None:
    api = next(
        c for c in _distribuicao(pilha["borda"])["CacheBehaviors"] if c["PathPattern"] == "/api/*"
    )
    assert set(api["AllowedMethods"]) == {
        "GET",
        "HEAD",
        "OPTIONS",
        "PUT",
        "PATCH",
        "POST",
        "DELETE",
    }
    assert api["CachePolicyId"] == "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"  # CachingDisabled
    assert api["OriginRequestPolicyId"] == "b689b0a8-53d0-40ab-baf2-68738e2966ac"  # sem Host


def test_catalogo_com_cache_curto_so_para_leitura_e_sem_cookies(pilha) -> None:
    t = pilha["borda"]
    cat = next(
        c for c in _distribuicao(t)["CacheBehaviors"] if c["PathPattern"] == "/api/pub/modelos*"
    )
    assert cat["AllowedMethods"] == ["GET", "HEAD"]
    assert "OriginRequestPolicyId" not in cat
    t.has_resource_properties(
        "AWS::CloudFront::CachePolicy",
        {
            "CachePolicyConfig": Match.object_like(
                {
                    "MaxTTL": 60,
                    "DefaultTTL": 30,
                    "MinTTL": 0,
                    "ParametersInCacheKeyAndForwardedToOrigin": Match.object_like(
                        {"CookiesConfig": {"CookieBehavior": "none"}}
                    ),
                }
            )
        },
    )


def test_spa_reescreve_rotas_so_no_comportamento_do_site(pilha) -> None:
    t = pilha["borda"]
    cfg = _distribuicao(t)
    assert cfg["DefaultCacheBehavior"]["FunctionAssociations"][0]["EventType"] == "viewer-request"
    for c in cfg["CacheBehaviors"]:
        assert "FunctionAssociations" not in c
    # Nada de tratamento global de erro (trocaria 403/404 da API pelo index.html).
    assert "CustomErrorResponses" not in cfg
    t.has_resource_properties(
        "AWS::CloudFront::Function", {"FunctionConfig": {"Runtime": "cloudfront-js-2.0"}}
    )


# --- Req 20.5: nenhum segredo no template -----------------------------------------------------
def test_cabecalho_de_origem_vem_do_secrets_manager_por_referencia_dinamica(pilha) -> None:
    assert CABECALHO_ORIGEM == CABECALHO_API == "x-origem-cloudfront"
    api = next(o for o in _distribuicao(pilha["borda"])["Origins"] if "CustomOriginConfig" in o)
    cabecalhos = api["OriginCustomHeaders"]
    assert [c["HeaderName"] for c in cabecalhos] == ["x-origem-cloudfront"]
    assert cabecalhos[0]["HeaderValue"] == (
        "{{resolve:secretsmanager:tres/segredo-origem:SecretString:valor::}}"
    )


# --- Sem ciclos: a leitura do site é liberada na stack de armazenamento -----------------------
def test_bucket_do_site_permite_leitura_ao_cloudfront_sem_ciclo(pilha) -> None:
    pilha["armazenamento"].has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Sid": "PermitirCloudFrontLerSite",
                                "Effect": "Allow",
                                "Principal": {"Service": "cloudfront.amazonaws.com"},
                                "Action": "s3:GetObject",
                                "Condition": {"ArnLike": {"aws:SourceArn": Match.any_value()}},
                            }
                        )
                    ]
                )
            }
        },
    )
    # O OAC não pode ter criado política de bucket na stack de borda.
    pilha["borda"].resource_count_is("AWS::S3::BucketPolicy", 0)
    pilha["armazenamento"].resource_count_is("AWS::S3::BucketPolicy", 3)


# --- Autorizador de origem (Req 18.7) ---------------------------------------------------------
@pytest.fixture
def autorizador(monkeypatch):
    modulo = _carregar("autorizador_origem_index", AUTORIZADOR)
    monkeypatch.setattr(modulo, "_buscar_segredo", lambda: "valor-do-segredo-de-teste")
    modulo._cache.update({"valor": None, "expira": 0.0})
    return modulo


def test_autorizador_aceita_so_o_cabecalho_correto(autorizador) -> None:
    ok = {"headers": {"x-origem-cloudfront": "valor-do-segredo-de-teste"}}
    assert autorizador.handler(ok) == {"isAuthorized": True}
    for evento in (
        {"headers": {"x-origem-cloudfront": "outro"}},
        {"headers": {"x-origem-cloudfront": ""}},
        {"headers": {}},
        {},
        {"headers": None},
    ):
        assert autorizador.handler(evento) == {"isAuthorized": False}


def test_autorizador_nega_quando_nao_consegue_ler_o_segredo(autorizador, monkeypatch) -> None:
    def falha() -> str:
        raise RuntimeError("sem acesso")

    monkeypatch.setattr(autorizador, "_buscar_segredo", falha)
    autorizador._cache.update({"valor": None, "expira": 0.0})
    evento = {"headers": {"x-origem-cloudfront": "valor-do-segredo-de-teste"}}
    assert autorizador.handler(evento) == {"isAuthorized": False}
    assert autorizador.CABECALHO == CABECALHO_ORIGEM
