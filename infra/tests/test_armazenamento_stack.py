"""Testes de asserção da stack de armazenamento (tarefa 8.2)."""

import importlib.util
import json
import sys
from pathlib import Path

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from stacks import armazenamento_stack
from stacks.armazenamento_stack import ArmazenamentoStack
from stacks.dados_stack import DadosStack

PREMISSAS = Path(__file__).resolve().parents[2] / "services" / "agente" / "premissas.py"


def _stacks(**kwargs) -> tuple[Template, Template]:
    app = cdk.App()
    dados = DadosStack(app, "teste-dados")
    armaz = ArmazenamentoStack(app, "teste-armazenamento", chave=dados.chave, **kwargs)
    return Template.from_stack(armaz), Template.from_stack(dados)


def _premissas():
    spec = importlib.util.spec_from_file_location("premissas", PREMISSAS)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo  # @dataclass precisa achar o módulo em sys.modules
    spec.loader.exec_module(modulo)
    return modulo


def test_tres_buckets_com_sse_kms_e_sem_acesso_publico() -> None:
    t, _ = _stacks()
    t.resource_count_is("AWS::S3::Bucket", 3)
    for bucket in t.find_resources("AWS::S3::Bucket").values():
        props = bucket["Properties"]
        regra = props["BucketEncryption"]["ServerSideEncryptionConfiguration"][0]
        assert regra["ServerSideEncryptionByDefault"]["SSEAlgorithm"] == "aws:kms"
        assert "KMSMasterKeyID" in regra["ServerSideEncryptionByDefault"]
        assert regra["BucketKeyEnabled"] is True
        assert props["PublicAccessBlockConfiguration"] == {
            "BlockPublicAcls": True,
            "BlockPublicPolicy": True,
            "IgnorePublicAcls": True,
            "RestrictPublicBuckets": True,
        }
        assert bucket["DeletionPolicy"] == "Retain"
    # enforce_ssl: política negando acesso sem TLS em cada bucket.
    t.resource_count_is("AWS::S3::BucketPolicy", 3)
    t.has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Effect": "Deny",
                                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                            }
                        )
                    ]
                )
            }
        },
    )


def test_manuais_com_versionamento_e_prefixo_igual_ao_das_premissas() -> None:
    t, _ = _stacks()
    versionados = [
        b
        for b in t.find_resources("AWS::S3::Bucket").values()
        if b["Properties"].get("VersioningConfiguration") == {"Status": "Enabled"}
    ]
    assert len(versionados) == 1
    assert armazenamento_stack.PREFIXO_S3_MANUAIS == _premissas().PREFIXO_S3_MANUAIS
    t.has_resource_properties(
        "AWS::SSM::Parameter",
        {"Name": "/tres/config/manuais-prefixo", "Value": "manuais/"},
    )


def test_fila_de_encerramentos_com_dlq_3_tentativas_e_visibilidade_10s() -> None:
    t, _ = _stacks()
    t.resource_count_is("AWS::SQS::Queue", 2)
    t.has_resource_properties(
        "AWS::SQS::Queue",
        {
            "QueueName": "tres-encerramentos",
            "VisibilityTimeout": 10,
            "KmsMasterKeyId": Match.any_value(),
            "RedrivePolicy": {
                "maxReceiveCount": 3,
                "deadLetterTargetArn": Match.any_value(),
            },
        },
    )
    t.has_resource_properties(
        "AWS::SQS::Queue",
        {
            "QueueName": "tres-encerramentos-dlq",
            "KmsMasterKeyId": Match.any_value(),
            "MessageRetentionPeriod": 14 * 24 * 3600,
        },
    )


def test_segredo_gerado_no_deploy_sem_valor_no_template() -> None:
    t, _ = _stacks()
    t.has_resource_properties(
        "AWS::SecretsManager::Secret",
        {
            "Name": "tres/segredo-app",
            "KmsKeyId": Match.any_value(),
            "GenerateSecretString": Match.object_like({"GenerateStringKey": "hmac_chave"}),
        },
    )
    segredos = t.find_resources("AWS::SecretsManager::Secret")
    assert all("SecretString" not in s["Properties"] for s in segredos.values())


def test_parametro_ssm_do_modelo_e_igual_as_premissas_e_nao_ha_segredo_em_ssm() -> None:
    t, _ = _stacks()
    t.has_resource_properties(
        "AWS::SSM::Parameter",
        {
            "Name": "/tres/config/modelo-llm-id",
            "Type": "String",
            "Value": _premissas().MODELO_LLM_ID_PADRAO,
        },
    )
    for p in t.find_resources("AWS::SSM::Parameter").values():
        assert p["Properties"]["Type"] == "String"
        assert "segredo" not in json.dumps(p["Properties"]["Name"]).lower()


def test_chave_permite_decifrar_ao_cloudfront_sem_ciclo_entre_stacks() -> None:
    # Template.from_stack já falharia com ciclo; aqui conferimos a política na stack de dados.
    _, dados = _stacks()
    dados.has_resource_properties(
        "AWS::KMS::Key",
        {
            "KeyPolicy": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Sid": "PermitirCloudFrontDecifrarSite",
                                "Principal": {"Service": "cloudfront.amazonaws.com"},
                                "Action": "kms:Decrypt",
                                "Condition": {"ArnLike": {"aws:SourceArn": Match.any_value()}},
                            }
                        )
                    ]
                )
            }
        },
    )


def test_cors_do_bucket_de_fotos_so_quando_ha_origem_e_destruicao_opcional() -> None:
    sem, _ = _stacks()
    assert all(
        "CorsConfiguration" not in b["Properties"]
        for b in sem.find_resources("AWS::S3::Bucket").values()
    )
    com, _ = _stacks(origens_cors_fotos=("https://exemplo.cloudfront.net",))
    cors = [
        b["Properties"]["CorsConfiguration"]["CorsRules"]
        for b in com.find_resources("AWS::S3::Bucket").values()
        if "CorsConfiguration" in b["Properties"]
    ]
    assert len(cors) == 1
    assert cors[0][0]["AllowedOrigins"] == ["https://exemplo.cloudfront.net"]
    assert cors[0][0]["AllowedMethods"] == ["POST"]

    descartavel, _ = _stacks(destruir_ao_remover=True)
    for b in descartavel.find_resources("AWS::S3::Bucket").values():
        assert b["DeletionPolicy"] == "Delete"
