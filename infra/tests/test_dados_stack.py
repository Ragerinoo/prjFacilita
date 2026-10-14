"""Testes de asserção da stack de dados (tarefa 8.1)."""

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template

from stacks.dados_stack import TABELAS, DadosStack


def _template() -> Template:
    app = cdk.App()
    stack = DadosStack(app, "teste-dados")
    return Template.from_stack(stack)


def test_cria_chave_kms_com_rotacao() -> None:
    t = _template()
    t.resource_count_is("AWS::KMS::Key", 1)
    t.has_resource_properties("AWS::KMS::Key", {"EnableKeyRotation": True})


def test_cria_todas_as_tabelas_sob_demanda_com_kms_do_cliente() -> None:
    t = _template()
    nomes = {s.nome for s in TABELAS}
    assert len(nomes) == 16
    t.resource_count_is("AWS::DynamoDB::Table", 16)
    for nome in nomes:
        t.has_resource_properties(
            "AWS::DynamoDB::Table",
            {
                "TableName": f"tres-{nome}",
                "BillingMode": "PAY_PER_REQUEST",
                "SSESpecification": {
                    "SSEEnabled": True,
                    "SSEType": "KMS",
                    "KMSMasterKeyId": Match.any_value(),
                },
            },
        )


def test_indices_esparsos_e_ttl() -> None:
    t = _template()
    t.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "tres-jornadas",
            "GlobalSecondaryIndexes": Match.array_with(
                [
                    Match.object_like({"IndexName": "gsi_ativas"}),
                    Match.object_like({"IndexName": "gsi_encerradas"}),
                ]
            ),
        },
    )
    t.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "tres-chamados",
            "GlobalSecondaryIndexes": [Match.object_like({"IndexName": "gsi_fila"})],
        },
    )
    t.has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "tres-sessoes_cs",
            "TimeToLiveSpecification": {"AttributeName": "ttl", "Enabled": True},
        },
    )


def test_modelos_tem_indice_do_catalogo_para_listar_sem_scan() -> None:
    _template().has_resource_properties(
        "AWS::DynamoDB::Table",
        {
            "TableName": "tres-modelos",
            "GlobalSecondaryIndexes": [
                Match.object_like(
                    {
                        "IndexName": "gsi_catalogo",
                        "KeySchema": [
                            {"AttributeName": "catalogo_pk", "KeyType": "HASH"},
                            {"AttributeName": "nome_normalizado", "KeyType": "RANGE"},
                        ],
                    }
                )
            ],
        },
    )
