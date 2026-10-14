"""Testes de asserção transversais do CDK (tarefa 8.4).

Valida políticas que atravessam as quatro stacks, sobre o app completo (montado como o
``app.py``, sem empacotar dependências): KMS em tabelas, buckets, filas e segredos (Req 18.2,
20.1), redirecionamento HTTPS e cabeçalhos de segurança (Req 18.7), DLQ da fila de
encerramentos (Req 17.12), IAM de privilégio mínimo (Req 18.6) e ausência de segredos nos
templates (Req 20.5). Os testes por stack (8.1 a 8.3) cobrem o detalhe de cada recurso; aqui
ficam as regras que valem para *todos* os recursos de um tipo.

Cada teste roda com e sem ``agente_runtime_arn``, pois esse contexto acrescenta permissões IAM.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Template

from stacks.api_stack import (
    CABECALHO_ORIGEM as CABECALHO_API,
)
from stacks.api_stack import (
    ROTAS_PADRAO,
    TABELAS_DO_ENDPOINT_DE_DADOS_PESSOAIS,
    ApiStack,
)
from stacks.armazenamento_stack import ENCERRAMENTO_MAX_TENTATIVAS, ArmazenamentoStack
from stacks.borda_stack import CABECALHO_ORIGEM as CABECALHO_BORDA
from stacks.borda_stack import BordaStack
from stacks.dados_stack import TABELAS, DadosStack

APP_PY = Path(__file__).resolve().parents[1] / "app.py"
ARN_RUNTIME = "arn:aws:bedrock-agentcore:sa-east-1:123456789012:runtime/tres_agente-AbC123"

# Jamais pode aparecer em nenhum papel, política ou política de recurso do app.
ACOES_PROIBIDAS = {"dynamodb:Scan", "dynamodb:BatchWriteItem"}


# --- Montagem do app completo -----------------------------------------------------------------
def _montar_app(agente_runtime_arn: str | None) -> dict[str, dict]:
    """Mesma ligação entre stacks do ``app.py``, sem empacotar dependências (sem rede)."""
    app = cdk.App()
    prefixo = "tres"
    dados = DadosStack(app, f"{prefixo}-dados", prefixo=prefixo)
    armaz = ArmazenamentoStack(
        app,
        f"{prefixo}-armazenamento",
        chave=dados.chave,
        prefixo=prefixo,
        origens_cors_fotos=("https://*.cloudfront.net",),
    )
    api = ApiStack(
        app,
        f"{prefixo}-api",
        dados=dados,
        armazenamento=armaz,
        prefixo=prefixo,
        agente_runtime_arn=agente_runtime_arn,
        empacotar_dependencias=False,
    )
    borda = BordaStack(
        app,
        f"{prefixo}-borda",
        bucket_site=armaz.bucket_site,
        bucket_fotos=armaz.bucket_fotos,
        dominio_api=api.dominio_api,
        nome_segredo_origem=api.nome_segredo_origem,
        prefixo=prefixo,
    )
    return {
        "dados": Template.from_stack(dados).to_json(),
        "armazenamento": Template.from_stack(armaz).to_json(),
        "api": Template.from_stack(api).to_json(),
        "borda": Template.from_stack(borda).to_json(),
    }


@pytest.fixture(scope="module", params=[None, ARN_RUNTIME], ids=["sem-agente", "com-agente"])
def modelo(request: pytest.FixtureRequest) -> dict[str, dict]:
    """Templates sintetizados de todas as stacks, por nome curto."""
    return _montar_app(request.param)


def _recursos(modelo: dict[str, dict], tipo: str) -> Iterator[tuple[str, str, dict]]:
    """(stack, id lógico, recurso) de todos os recursos do tipo, em todas as stacks."""
    for stack, template in modelo.items():
        for id_logico, recurso in template.get("Resources", {}).items():
            if recurso["Type"] == tipo:
                yield stack, id_logico, recurso


def _lista(valor: Any) -> list:
    return valor if isinstance(valor, list) else [valor]


# --- Coleta de instruções de política de qualquer origem --------------------------------------
def _instrucoes(modelo: dict[str, dict]) -> list[tuple[str, str, str, dict]]:
    """(tipo, stack, id lógico, instrução) de todas as políticas do app.

    Inclui políticas de identidade (inline, gerenciadas e em papéis), políticas de recurso
    (bucket, fila, segredo) e a política da chave KMS. Políticas de confiança dos papéis ficam
    em ``_confiancas``.
    """
    achadas: list[tuple[str, str, str, dict]] = []

    def _doc(tipo: str, stack: str, id_logico: str, doc: dict) -> None:
        for st in _lista(doc["Statement"]):
            achadas.append((tipo, stack, id_logico, st))

    for stack, template in modelo.items():
        for id_logico, r in template.get("Resources", {}).items():
            tipo, props = r["Type"], r.get("Properties", {})
            if tipo in {"AWS::IAM::Policy", "AWS::IAM::ManagedPolicy"}:
                _doc(tipo, stack, id_logico, props["PolicyDocument"])
            elif tipo == "AWS::IAM::Role":
                for pol in props.get("Policies", []):
                    _doc(tipo, stack, id_logico, pol["PolicyDocument"])
            elif tipo in {"AWS::S3::BucketPolicy", "AWS::SQS::QueuePolicy"}:
                _doc(tipo, stack, id_logico, props["PolicyDocument"])
            elif tipo == "AWS::SecretsManager::ResourcePolicy":
                _doc(tipo, stack, id_logico, props["ResourcePolicy"])
            elif tipo == "AWS::KMS::Key":
                _doc(tipo, stack, id_logico, props["KeyPolicy"])
    return achadas


def _acoes(st: dict) -> list[str]:
    return _lista(st.get("Action", []))


def _recursos_da_instrucao(st: dict) -> list:
    return _lista(st.get("Resource", []))


def test_o_app_tem_as_quatro_stacks_do_app_py(modelo: dict[str, dict]) -> None:
    assert set(modelo) == {"dados", "armazenamento", "api", "borda"}
    fonte = APP_PY.read_text(encoding="utf-8")
    for classe in ("DadosStack", "ArmazenamentoStack", "ApiStack", "BordaStack"):
        assert f"{classe}(" in fonte, f"app.py deixou de instanciar {classe}"


# =================================================================================================
# KMS (Req 18.2, 20.1)
# =================================================================================================
def _usa_chave_do_cliente(valor: Any) -> bool:
    """A chave é a ``ChaveDados`` (recurso ou exportação), nunca ``alias/aws/...``."""
    texto = json.dumps(valor)
    return "ChaveDados" in texto and "alias/aws" not in texto


def test_chave_do_cliente_com_rotacao_e_unica(modelo: dict[str, dict]) -> None:
    chaves = list(_recursos(modelo, "AWS::KMS::Key"))
    assert len(chaves) == 1
    assert chaves[0][2]["Properties"]["EnableKeyRotation"] is True


def test_toda_tabela_dynamodb_usa_sse_kms_com_a_chave_do_cliente(modelo: dict[str, dict]) -> None:
    tabelas = list(_recursos(modelo, "AWS::DynamoDB::Table"))
    assert len(tabelas) == len(TABELAS)
    for _, id_logico, t in tabelas:
        sse = t["Properties"]["SSESpecification"]
        assert sse["SSEEnabled"] is True, id_logico
        assert sse["SSEType"] == "KMS", id_logico
        assert _usa_chave_do_cliente(sse["KMSMasterKeyId"]), id_logico


def test_todo_bucket_s3_usa_sse_kms_com_a_chave_do_cliente(modelo: dict[str, dict]) -> None:
    buckets = list(_recursos(modelo, "AWS::S3::Bucket"))
    assert len(buckets) == 3  # site, fotos e manuais
    for _, id_logico, b in buckets:
        regras = b["Properties"]["BucketEncryption"]["ServerSideEncryptionConfiguration"]
        assert len(regras) == 1, id_logico
        padrao = regras[0]["ServerSideEncryptionByDefault"]
        assert padrao["SSEAlgorithm"] == "aws:kms", id_logico
        assert _usa_chave_do_cliente(padrao["KMSMasterKeyID"]), id_logico


def test_toda_fila_e_todo_segredo_usam_a_chave_do_cliente(modelo: dict[str, dict]) -> None:
    filas = list(_recursos(modelo, "AWS::SQS::Queue"))
    assert len(filas) == 2
    for _, id_logico, f in filas:
        assert _usa_chave_do_cliente(f["Properties"]["KmsMasterKeyId"]), id_logico
    segredos = list(_recursos(modelo, "AWS::SecretsManager::Secret"))
    assert len(segredos) == 2  # segredo da aplicação e segredo de origem
    for _, id_logico, s in segredos:
        assert _usa_chave_do_cliente(s["Properties"]["KmsKeyId"]), id_logico


def test_dados_em_repouso_nao_ficam_fora_do_kms(modelo: dict[str, dict]) -> None:
    """Tipos de armazenamento que o MVP não usa não podem aparecer sem revisão de criptografia."""
    # Os únicos armazenamentos do MVP são DynamoDB, S3, SQS e Secrets Manager (todos cobertos
    # pelos testes acima), mais SSM (configuração não sensível) e logs sem PII (Req 18).
    fora_do_escopo = {
        r["Type"]
        for t in modelo.values()
        for r in t.get("Resources", {}).values()
        if re.match(
            r"AWS::(RDS|Kinesis|KinesisFirehose|SNS|EFS|FSx|OpenSearch\w*|Elasticsearch|DocDB"
            r"|Neptune|Redshift\w*|ElastiCache|MemoryDB|DynamoDB::GlobalTable)\b",
            r["Type"],
        )
    }
    assert not fora_do_escopo, fora_do_escopo


# =================================================================================================
# S3: nenhum acesso público (Req 18.2, 18.7)
# =================================================================================================
def test_nenhum_bucket_e_publico(modelo: dict[str, dict]) -> None:
    for _, id_logico, b in _recursos(modelo, "AWS::S3::Bucket"):
        props = b["Properties"]
        assert props["PublicAccessBlockConfiguration"] == {
            "BlockPublicAcls": True,
            "BlockPublicPolicy": True,
            "IgnorePublicAcls": True,
            "RestrictPublicBuckets": True,
        }, id_logico
        assert "AccessControl" not in props, id_logico  # sem ACL canned (ex.: PublicRead)
        assert "WebsiteConfiguration" not in props, id_logico
        propriedade = props["OwnershipControls"]["Rules"][0]["ObjectOwnership"]
        assert propriedade == "BucketOwnerEnforced", id_logico


def test_politicas_de_bucket_negam_http_e_nao_concedem_a_principal_publico(
    modelo: dict[str, dict],
) -> None:
    politicas = list(_recursos(modelo, "AWS::S3::BucketPolicy"))
    assert len(politicas) == 3
    for _, id_logico, p in politicas:
        sts = _lista(p["Properties"]["PolicyDocument"]["Statement"])
        negam_http = [
            s
            for s in sts
            if s["Effect"] == "Deny"
            and s.get("Condition", {}).get("Bool", {}).get("aws:SecureTransport") == "false"
        ]
        assert negam_http, id_logico
        for s in sts:
            if s["Effect"] == "Allow":
                assert s["Principal"] != "*" and s["Principal"].get("AWS") != "*", id_logico


def test_so_o_cloudfront_le_o_site_e_so_com_condicao_de_origem(modelo: dict[str, dict]) -> None:
    permitem_servico = [
        (id_logico, s)
        for tipo, _, id_logico, s in _instrucoes(modelo)
        if tipo == "AWS::S3::BucketPolicy"
        and s["Effect"] == "Allow"
        and "Service" in s["Principal"]
    ]
    assert len(permitem_servico) == 1
    _, s = permitem_servico[0]
    assert s["Principal"] == {"Service": "cloudfront.amazonaws.com"}
    assert _acoes(s) == ["s3:GetObject"]
    assert "aws:SourceArn" in json.dumps(s["Condition"])


# =================================================================================================
# CloudFront: HTTPS e cabeçalhos de segurança (Req 18.7)
# =================================================================================================
def _distribuicao(modelo: dict[str, dict]) -> dict:
    achadas = list(_recursos(modelo, "AWS::CloudFront::Distribution"))
    assert len(achadas) == 1
    return achadas[0][2]["Properties"]["DistributionConfig"]


def _comportamentos(config: dict) -> list[dict]:
    return [config["DefaultCacheBehavior"], *config.get("CacheBehaviors", [])]


def test_todo_comportamento_redireciona_http_para_https_e_aplica_os_cabecalhos(
    modelo: dict[str, dict],
) -> None:
    config = _distribuicao(modelo)
    comportamentos = _comportamentos(config)
    assert len(comportamentos) == 3  # site, catálogo e /api/*
    politicas = list(_recursos(modelo, "AWS::CloudFront::ResponseHeadersPolicy"))
    assert len(politicas) == 1
    id_politica = politicas[0][1]
    for c in comportamentos:
        assert c["ViewerProtocolPolicy"] == "redirect-to-https", c.get("PathPattern", "padrão")
        assert c["ResponseHeadersPolicyId"] == {"Ref": id_politica}
    assert config["Enabled"] is True
    assert config["HttpVersion"] in {"http2", "http2and3"}


def test_politica_de_cabecalhos_tem_hsts_csp_nosniff_referrer_e_frame(
    modelo: dict[str, dict],
) -> None:
    ((_, _, politica),) = list(_recursos(modelo, "AWS::CloudFront::ResponseHeadersPolicy"))
    seg = politica["Properties"]["ResponseHeadersPolicyConfig"]["SecurityHeadersConfig"]
    hsts = seg["StrictTransportSecurity"]
    assert hsts["AccessControlMaxAgeSec"] >= 31_536_000  # pelo menos 1 ano
    assert hsts["Override"] is True and hsts["IncludeSubdomains"] is True
    assert seg["ContentTypeOptions"] == {"Override": True}  # X-Content-Type-Options: nosniff
    assert seg["ReferrerPolicy"]["ReferrerPolicy"] in {"no-referrer", "same-origin"}
    assert seg["FrameOptions"]["FrameOption"] == "DENY"
    csp = seg["ContentSecurityPolicy"]["ContentSecurityPolicy"]
    assert seg["ContentSecurityPolicy"]["Override"] is True
    # O CSP referencia o domínio do bucket de fotos (Fn::Join); só as diretivas literais importam.
    texto = json.dumps(csp)
    assert "default-src 'self'" in texto
    assert "frame-ancestors 'none'" in texto and "object-src 'none'" in texto
    assert "unsafe-eval" not in texto
    script = re.search(r"script-src ([^;]*?)(?:;|\")", texto)
    assert script and "'unsafe-inline'" not in script.group(1)


def test_origens_do_cloudfront_so_por_https_e_o_site_por_oac(modelo: dict[str, dict]) -> None:
    config = _distribuicao(modelo)
    origens = config["Origins"]
    assert len(origens) == 2
    de_api = [o for o in origens if "CustomOriginConfig" in o]
    de_site = [o for o in origens if "S3OriginConfig" in o]
    assert len(de_api) == len(de_site) == 1
    assert de_api[0]["CustomOriginConfig"]["OriginProtocolPolicy"] == "https-only"
    # OAC (não OAI): sem identidade de acesso legada e sem bucket público.
    assert de_site[0]["OriginAccessControlId"]
    assert de_site[0]["S3OriginConfig"]["OriginAccessIdentity"] == ""
    assert not list(_recursos(modelo, "AWS::CloudFront::CloudFrontOriginAccessIdentity"))


# =================================================================================================
# DLQ da fila de encerramentos (Req 17.12)
# =================================================================================================
def test_fila_de_encerramentos_tem_dlq_com_max_receive_count_3(modelo: dict[str, dict]) -> None:
    filas = {id_logico: f["Properties"] for _, id_logico, f in _recursos(modelo, "AWS::SQS::Queue")}
    com_redrive = {k: v for k, v in filas.items() if "RedrivePolicy" in v}
    sem_redrive = {k: v for k, v in filas.items() if "RedrivePolicy" not in v}
    assert len(com_redrive) == len(sem_redrive) == 1
    (id_fila, fila), (id_dlq, dlq) = (
        next(iter(com_redrive.items())),
        next(iter(sem_redrive.items())),
    )
    assert "Dlq" in id_dlq and "Dlq" not in id_fila
    assert fila["RedrivePolicy"]["maxReceiveCount"] == ENCERRAMENTO_MAX_TENTATIVAS == 3
    assert fila["RedrivePolicy"]["deadLetterTargetArn"] == {"Fn::GetAtt": [id_dlq, "Arn"]}
    assert dlq["MessageRetentionPeriod"] >= fila.get("MessageRetentionPeriod", 345_600)
    assert "tres-encerramentos-dlq" == dlq["QueueName"]


def test_apenas_a_fila_principal_alimenta_a_lambda_de_encerramento(modelo: dict[str, dict]) -> None:
    mapeamentos = list(_recursos(modelo, "AWS::Lambda::EventSourceMapping"))
    assert len(mapeamentos) == 1
    origem = mapeamentos[0][2]["Properties"]["EventSourceArn"]["Fn::ImportValue"]
    assert "Dlq" not in origem and "FilaEncerramentos" in origem


# =================================================================================================
# IAM de privilégio mínimo (Req 18.6, 20.1)
# =================================================================================================
# Exceções explícitas e documentadas à regra "nenhum Action/Resource curinga".
# Cada uma é inevitável porque o próprio serviço exige a forma:
#   - Política da chave KMS: ``Resource: "*"`` significa "esta chave" (o KMS não aceita outro
#     valor numa política de chave). Vale para a instrução padrão do CDK (``kms:*`` para a raiz da
#     conta, que delega o acesso ao IAM) e para a leitura do CloudFront (``kms:Decrypt`` com
#     ``aws:SourceArn``, ver armazenamento_stack).
#   - ``Deny`` de ``s3:*``/``sqs:*`` sobre HTTP puro (``enforce_ssl``): ver ``_eh_negacao_de_http``.
EXCECOES_CURINGA: tuple[tuple[str, str], ...] = (
    ("AWS::KMS::Key", "Resource"),
    ("AWS::KMS::Key", "Action"),
)


def _eh_curinga_de_acao(acao: str) -> bool:
    return acao == "*" or acao.endswith(":*")


def _eh_negacao_de_http(st: dict) -> bool:
    """``Deny`` de ``s3:*``/``sqs:*`` com ``aws:SecureTransport=false`` (``enforce_ssl``).

    Segunda exceção documentada: o curinga aqui só *restringe* (nega tudo sobre HTTP puro).
    """
    return (
        st["Effect"] == "Deny"
        and st.get("Condition", {}).get("Bool", {}).get("aws:SecureTransport") == "false"
        and all(_eh_curinga_de_acao(a) for a in _acoes(st))
    )


def test_nenhuma_politica_com_action_ou_resource_curinga_fora_da_lista_de_excecoes(
    modelo: dict[str, dict],
) -> None:
    permitidas = 0
    for tipo, stack, id_logico, st in _instrucoes(modelo):
        onde = (stack, id_logico)
        if _eh_negacao_de_http(st):
            assert tipo in {"AWS::S3::BucketPolicy", "AWS::SQS::QueuePolicy"}, (onde, st)
            assert "*" not in _recursos_da_instrucao(st), (onde, st)  # só o bucket/fila
            continue
        curinga_acao = any(_eh_curinga_de_acao(a) for a in _acoes(st))
        curinga_recurso = any(r == "*" for r in _recursos_da_instrucao(st))
        if curinga_acao:
            assert (tipo, "Action") in EXCECOES_CURINGA, (onde, st)
            # ``kms:*`` só para a raiz da conta (delegação ao IAM), nunca para um serviço.
            assert _acoes(st) == ["kms:*"] and st["Effect"] == "Allow", (onde, st)
            assert "root" in json.dumps(st["Principal"]), (onde, st)
            permitidas += 1
        if curinga_recurso:
            assert (tipo, "Resource") in EXCECOES_CURINGA, (onde, st)
            permitidas += 1
        # Nenhum ``NotAction``/``NotResource`` (equivalem a "tudo menos").
        assert "NotAction" not in st and "NotResource" not in st, (onde, st)
    # A chave tem a instrução padrão e a do CloudFront; se alguma sumir, revise a lista acima.
    assert permitidas >= 3


def test_sem_curinga_em_politicas_de_identidade(modelo: dict[str, dict]) -> None:
    """Papéis e políticas gerenciadas (tudo menos política de recurso) não têm nenhuma exceção."""
    identidade = [
        (stack, id_logico, st)
        for tipo, stack, id_logico, st in _instrucoes(modelo)
        if tipo in {"AWS::IAM::Policy", "AWS::IAM::ManagedPolicy", "AWS::IAM::Role"}
    ]
    assert identidade
    for stack, id_logico, st in identidade:
        assert st["Effect"] == "Allow", (stack, id_logico)
        assert not any(_eh_curinga_de_acao(a) for a in _acoes(st)), (stack, id_logico, st)
        assert "*" not in _recursos_da_instrucao(st), (stack, id_logico, st)
        assert not (set(_acoes(st)) & ACOES_PROIBIDAS), (stack, id_logico, st)
        # Nunca todas as tabelas/filas/buckets da conta por ARN literal com curinga.
        assert not re.search(r':(table|[a-z0-9-]+)/\*"', json.dumps(st["Resource"])), (
            id_logico,
            st,
        )


def test_nenhuma_politica_gerenciada_e_nenhum_administrator_access(modelo: dict[str, dict]) -> None:
    for _, id_logico, papel in _recursos(modelo, "AWS::IAM::Role"):
        assert "ManagedPolicyArns" not in papel["Properties"], id_logico
    tudo = json.dumps(modelo)
    assert "iam::aws:policy/" not in tudo
    assert "AdministratorAccess" not in tudo and "PowerUserAccess" not in tudo
    assert not list(_recursos(modelo, "AWS::IAM::ManagedPolicy"))
    assert not list(_recursos(modelo, "AWS::IAM::User"))
    assert not list(_recursos(modelo, "AWS::IAM::AccessKey"))


def test_politicas_de_confianca_so_para_servicos_da_aplicacao(modelo: dict[str, dict]) -> None:
    servicos = set()
    for _, id_logico, papel in _recursos(modelo, "AWS::IAM::Role"):
        for st in _lista(papel["Properties"]["AssumeRolePolicyDocument"]["Statement"]):
            principal = st["Principal"]
            assert principal != "*" and "AWS" not in principal, id_logico
            servicos.update(_lista(principal["Service"]))
    assert servicos == {"lambda.amazonaws.com", "scheduler.amazonaws.com"}


def test_permissoes_de_invocacao_de_lambda_so_do_api_gateway(modelo: dict[str, dict]) -> None:
    permissoes = list(_recursos(modelo, "AWS::Lambda::Permission"))
    assert permissoes
    for _, id_logico, p in permissoes:
        props = p["Properties"]
        assert props["Action"] in {"lambda:InvokeFunction"}, id_logico
        if props["Principal"] == "apigateway.amazonaws.com":
            assert "SourceArn" in props, id_logico  # limitada à própria API
        else:
            assert props["Principal"] != "*", id_logico
    assert not list(_recursos(modelo, "AWS::Lambda::Url"))  # sem URL de função pública


def _id_logico_da_tabela(nome: str) -> str:
    return "Tabela" + nome.replace("_", "")


def test_dados_pessoais_e_acessos_pii_so_no_papel_dedicado(modelo: dict[str, dict]) -> None:
    marcas = {_id_logico_da_tabela(n) for n in TABELAS_DO_ENDPOINT_DE_DADOS_PESSOAIS}
    assert marcas == {"Tabeladadospessoais", "Tabelaacessospii"}
    com_acesso: set[str] = set()
    for tipo, stack, id_logico, st in _instrucoes(modelo):
        referencia = [m for m in marcas if m in json.dumps(_recursos_da_instrucao(st))]
        if not referencia:
            continue
        # Ninguém, nem políticas de recurso, concede essas tabelas a outro papel.
        assert tipo == "AWS::IAM::Policy", (tipo, stack, id_logico)
        papeis = {
            r["Ref"]
            for _, pid, pol in _recursos(modelo, "AWS::IAM::Policy")
            if pid == id_logico
            for r in pol["Properties"]["Roles"]
        }
        com_acesso |= papeis
    assert len(com_acesso) == 1 and next(iter(com_acesso)).startswith("RoleDadosPessoais")


def test_so_o_papel_de_dados_pessoais_recebe_o_nome_das_tabelas_sensiveis_no_ambiente(
    modelo: dict[str, dict],
) -> None:
    for _, id_logico, f in _recursos(modelo, "AWS::Lambda::Function"):
        variaveis = f["Properties"].get("Environment", {}).get("Variables", {})
        sensiveis = {"TRES_TABELA_DADOS_PESSOAIS", "TRES_TABELA_ACESSOS_PII"} & set(variaveis)
        if id_logico.startswith("FuncaoDadosPessoais"):
            assert sensiveis == {"TRES_TABELA_DADOS_PESSOAIS", "TRES_TABELA_ACESSOS_PII"}
        else:
            assert not sensiveis, id_logico


def test_tabelas_nao_tem_politica_de_recurso_aberta(modelo: dict[str, dict]) -> None:
    for _, id_logico, t in _recursos(modelo, "AWS::DynamoDB::Table"):
        assert "ResourcePolicy" not in t["Properties"], id_logico


# =================================================================================================
# API alcançável só pelo CloudFront (Req 18.7)
# =================================================================================================
def test_toda_rota_exige_o_autorizador_e_nao_ha_rota_curinga_nem_api_rest(
    modelo: dict[str, dict],
) -> None:
    rotas = list(_recursos(modelo, "AWS::ApiGatewayV2::Route"))
    assert len(rotas) == len(ROTAS_PADRAO)
    autorizadores = {
        id_logico for _, id_logico, _ in _recursos(modelo, "AWS::ApiGatewayV2::Authorizer")
    }
    assert len(autorizadores) == 1
    for _, _, r in rotas:
        props = r["Properties"]
        assert props["AuthorizationType"] == "CUSTOM", props["RouteKey"]
        assert props["AuthorizerId"] == {"Ref": next(iter(autorizadores))}, props["RouteKey"]
        assert not props["RouteKey"].startswith("$default"), props["RouteKey"]
        assert "ANY " not in props["RouteKey"], props["RouteKey"]
        assert props["RouteKey"].split(" ", 1)[1].startswith(("/api/pub", "/api/cs"))
    assert not list(_recursos(modelo, "AWS::ApiGateway::RestApi"))
    assert list(_recursos(modelo, "AWS::ApiGatewayV2::Integration"))


def test_cloudfront_envia_o_mesmo_cabecalho_que_o_autorizador_exige(
    modelo: dict[str, dict],
) -> None:
    assert CABECALHO_API == CABECALHO_BORDA
    ((_, _, autorizador),) = list(_recursos(modelo, "AWS::ApiGatewayV2::Authorizer"))
    assert autorizador["Properties"]["IdentitySource"] == [f"$request.header.{CABECALHO_API}"]
    origem_api = next(o for o in _distribuicao(modelo)["Origins"] if "CustomOriginConfig" in o)
    cabecalhos = {h["HeaderName"]: h["HeaderValue"] for h in origem_api["OriginCustomHeaders"]}
    assert set(cabecalhos) == {CABECALHO_API}
    # Valor vem do Secrets Manager por referência dinâmica (nunca literal).
    assert "{{resolve:secretsmanager:" in json.dumps(cabecalhos[CABECALHO_API])


def test_api_http_sem_cors_aberto_e_sem_dominio_alternativo(modelo: dict[str, dict]) -> None:
    for _, id_logico, a in _recursos(modelo, "AWS::ApiGatewayV2::Api"):
        assert "CorsConfiguration" not in a["Properties"], id_logico
    assert not list(_recursos(modelo, "AWS::ApiGatewayV2::DomainName"))
    assert not list(_recursos(modelo, "AWS::ApiGatewayV2::ApiMapping"))


# =================================================================================================
# Nenhum segredo ou credencial em texto claro nos templates (Req 20.5)
# =================================================================================================
PADROES_SEGREDO: dict[str, re.Pattern[str]] = {
    "chave de acesso AWS": re.compile(r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA)[0-9A-Z]{16}\b"),
    "chave secreta AWS": re.compile(r"aws_secret_access_key\s*[=:]\s*\S+", re.IGNORECASE),
    "chave privada": re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
    "token JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}"),
    "token de GitHub": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "token do Slack": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "senha literal": re.compile(
        r"[\"']?(?:password|passwd|senha|secret|api[_-]?key|token)[\"']?\s*[:=]\s*[\"'][^\"'{$]{6,}[\"']",
        re.IGNORECASE,
    ),
    "URL com credenciais": re.compile(r"\b[a-z][a-z0-9+.-]*://[^/\s:@\"]+:[^/\s@\"]+@"),
}


def _varrer(texto: str) -> list[str]:
    return [nome for nome, padrao in PADROES_SEGREDO.items() if padrao.search(texto)]


@pytest.mark.parametrize(
    ("amostra", "esperado"),
    [
        ("AKIAABCDEFGHIJKLMNOP", "chave de acesso AWS"),
        ("aws_secret_access_key = abc123", "chave secreta AWS"),
        ("-----BEGIN RSA PRIVATE KEY-----", "chave privada"),
        ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefg", "token JWT"),
        ("ghp_" + "a" * 36, "token de GitHub"),
        ("xoxb-1234567890-abcdef", "token do Slack"),
        ('"password": "hunter2hunter2"', "senha literal"),
        ("postgres://admin:s3nha@host/db", "URL com credenciais"),
    ],
)
def test_o_detector_de_segredos_reconhece_exemplos_conhecidos(amostra: str, esperado: str) -> None:
    assert esperado in _varrer(amostra)


def test_nenhum_template_contem_segredo_ou_credencial(modelo: dict[str, dict]) -> None:
    for stack, template in modelo.items():
        achados = _varrer(json.dumps(template, indent=1))
        assert not achados, (stack, achados)


def test_segredos_sao_gerados_no_deploy_e_nunca_literais(modelo: dict[str, dict]) -> None:
    for _, id_logico, s in _recursos(modelo, "AWS::SecretsManager::Secret"):
        props = s["Properties"]
        assert "SecretString" not in props, id_logico
        assert "GenerateSecretString" in props, id_logico
        assert props["GenerateSecretString"]["PasswordLength"] >= 32, id_logico


def test_parametros_ssm_sao_texto_simples_sem_valores_sensiveis(modelo: dict[str, dict]) -> None:
    for _, id_logico, p in _recursos(modelo, "AWS::SSM::Parameter"):
        assert p["Properties"]["Type"] == "String", id_logico  # nunca SecureString com valor
        assert not _varrer(json.dumps(p["Properties"]["Value"])), id_logico


NOME_SENSIVEL = re.compile(r"PASSWORD|SENHA|PASSWD|TOKEN|API_?KEY|HMAC|PRIVATE|CREDENTIAL", re.I)


def test_variaveis_de_ambiente_das_lambdas_nao_carregam_segredos(modelo: dict[str, dict]) -> None:
    for _, id_logico, f in _recursos(modelo, "AWS::Lambda::Function"):
        variaveis = f["Properties"].get("Environment", {}).get("Variables", {})
        for nome, valor in variaveis.items():
            assert not NOME_SENSIVEL.search(nome), (id_logico, nome)
            assert "{{resolve" not in json.dumps(valor), (id_logico, nome)
            if nome.endswith(("_ARN", "_URL")) or "SEGREDO" in nome:
                # Só referência (ARN/URL), nunca o valor do segredo.
                assert isinstance(valor, dict) or valor.startswith(("arn:", "https://")), nome


def test_o_valor_do_segredo_de_origem_so_aparece_como_referencia_dinamica(
    modelo: dict[str, dict],
) -> None:
    texto = json.dumps(modelo["borda"])
    referencias = re.findall(r"\{\{resolve:[^}]+\}\}", texto)
    assert len(referencias) == 1 and referencias[0].startswith("{{resolve:secretsmanager:")
    assert not re.findall(r"\{\{resolve:(?:ssm-secure|ssm):", json.dumps(modelo))
