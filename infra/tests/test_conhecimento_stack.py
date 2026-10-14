"""Testes de asserção da stack da Base_Conhecimento (tarefa 17.2).

Cobrem o S3 Vectors (float32, 1024, cosseno), a Knowledge Base, o data source com chunking
FIXED_SIZE sobre o prefixo das seções e o papel de serviço com privilégio mínimo
(Req 6.2, 6.3, 20.2, 20.3). Não dão acesso à AWS: só o template sintetizado é conferido.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any

import aws_cdk as cdk
from aws_cdk.assertions import Match, Template
from stacks import conhecimento_stack
from stacks.armazenamento_stack import ArmazenamentoStack
from stacks.conhecimento_stack import ConhecimentoStack
from stacks.dados_stack import DadosStack

RAIZ = Path(__file__).resolve().parents[2]
PREMISSAS = RAIZ / "services" / "agente" / "premissas.py"
PREPROCESSAR = RAIZ / "scripts" / "preprocessar_manuais.py"
APP_PY = RAIZ / "infra" / "app.py"


def _template(**kwargs) -> Template:
    app = cdk.App()
    dados = DadosStack(app, "teste-dados")
    armaz = ArmazenamentoStack(app, "teste-armazenamento", chave=dados.chave)
    stack = ConhecimentoStack(
        app,
        "teste-conhecimento",
        chave=dados.chave,
        bucket_manuais=armaz.bucket_manuais,
        **kwargs,
    )
    return Template.from_stack(stack)


def _premissas():
    spec = importlib.util.spec_from_file_location("premissas", PREMISSAS)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo  # @dataclass precisa achar o módulo em sys.modules
    spec.loader.exec_module(modulo)
    return modulo


def _unico(t: Template, tipo: str) -> dict[str, Any]:
    recursos = t.find_resources(tipo)
    assert len(recursos) == 1, f"esperado 1 {tipo}, há {len(recursos)}"
    return next(iter(recursos.values()))


def _declaracoes(t: Template) -> dict[str, dict[str, Any]]:
    politica = _unico(t, "AWS::IAM::Policy")["Properties"]["PolicyDocument"]["Statement"]
    return {s["Sid"]: s for s in politica}


# --------------------------------------------------------------------------------------------
# Vector store
# --------------------------------------------------------------------------------------------


def test_indice_s3_vectors_float32_1024_cosseno_com_chaves_do_bedrock_nao_filtraveis() -> None:
    t = _template()
    t.resource_count_is("AWS::S3Vectors::VectorBucket", 1)
    t.has_resource_properties(
        "AWS::S3Vectors::Index",
        {
            "IndexName": "tres-manuais",
            "DataType": "float32",
            "Dimension": 1024,
            "DistanceMetric": "cosine",
            "VectorBucketArn": Match.any_value(),
            "MetadataConfiguration": {
                "NonFilterableMetadataKeys": ["AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA"]
            },
        },
    )
    # modelo_id, manual e secao precisam continuar filtráveis (filtro do Req 6.2).
    nao_filtraveis = json.dumps(_unico(t, "AWS::S3Vectors::Index")["Properties"])
    for chave in _premissas().METADADOS_OBRIGATORIOS:
        assert f'"{chave}"' not in nao_filtraveis


def test_vector_store_retem_dados_por_padrao_e_apaga_no_ambiente_descartavel() -> None:
    for tipo in ("AWS::S3Vectors::VectorBucket", "AWS::S3Vectors::Index"):
        assert _unico(_template(), tipo)["DeletionPolicy"] == "Retain"
        assert _unico(_template(destruir_ao_remover=True), tipo)["DeletionPolicy"] == "Delete"


# --------------------------------------------------------------------------------------------
# Knowledge Base e data source
# --------------------------------------------------------------------------------------------


def test_knowledge_base_vetorial_com_cohere_multilingue_e_s3_vectors() -> None:
    t = _template()
    t.has_resource_properties(
        "AWS::Bedrock::KnowledgeBase",
        {
            "Name": "tres-manuais",
            "RoleArn": Match.any_value(),
            "KnowledgeBaseConfiguration": {
                "Type": "VECTOR",
                "VectorKnowledgeBaseConfiguration": {
                    "EmbeddingModelArn": Match.any_value(),
                    "EmbeddingModelConfiguration": {
                        "BedrockEmbeddingModelConfiguration": {"EmbeddingDataType": "FLOAT32"}
                    },
                },
            },
            "StorageConfiguration": {
                "Type": "S3_VECTORS",
                "S3VectorsConfiguration": {
                    "IndexArn": Match.any_value(),
                    "VectorBucketArn": Match.any_value(),
                },
            },
        },
    )
    base = _unico(t, "AWS::Bedrock::KnowledgeBase")["Properties"]
    modelo = base["KnowledgeBaseConfiguration"]["VectorKnowledgeBaseConfiguration"]
    assert json.dumps(modelo["EmbeddingModelArn"]).endswith(
        'foundation-model/cohere.embed-multilingual-v3"]]}'
    )
    # O embedding é fixo em 1024 dimensões: não se envia `Dimensions` ao Cohere.
    assert "Dimensions" not in json.dumps(base)


def test_data_source_le_so_o_prefixo_das_secoes_com_chunking_fixed_size() -> None:
    t = _template()
    t.has_resource_properties(
        "AWS::Bedrock::DataSource",
        {
            "KnowledgeBaseId": Match.any_value(),
            "DataSourceConfiguration": {
                "Type": "S3",
                "S3Configuration": Match.object_like(
                    {"BucketArn": Match.any_value(), "InclusionPrefixes": ["secoes/"]}
                ),
            },
            "VectorIngestionConfiguration": {
                "ChunkingConfiguration": {
                    "ChunkingStrategy": "FIXED_SIZE",
                    "FixedSizeChunkingConfiguration": {"MaxTokens": 300, "OverlapPercentage": 20},
                }
            },
            "DataDeletionPolicy": "RETAIN",
        },
    )
    fonte = json.dumps(_unico(t, "AWS::Bedrock::DataSource")["Properties"])
    assert "HIERARCHICAL" not in fonte and "SEMANTIC" not in fonte
    descartavel = _unico(_template(destruir_ao_remover=True), "AWS::Bedrock::DataSource")
    assert descartavel["Properties"]["DataDeletionPolicy"] == "DELETE"


def test_constantes_da_stack_batem_com_as_premissas_e_com_o_script_de_pre_processamento() -> None:
    p = _premissas()
    c = conhecimento_stack
    assert c.MODELO_EMBEDDINGS_ID == p.MODELO_EMBEDDINGS_ID
    assert c.EMBEDDINGS_DIMENSOES == p.EMBEDDINGS_DIMENSOES
    assert c.EMBEDDINGS_TIPO_VETOR == p.EMBEDDINGS_TIPO_VETOR
    assert c.EMBEDDINGS_METRICA == p.EMBEDDINGS_METRICA
    assert c.CHUNKING_ESTRATEGIA == p.CHUNKING_ESTRATEGIA
    assert c.CHUNKING_MAX_TOKENS == p.CHUNKING_MAX_TOKENS
    assert c.CHUNKING_SOBREPOSICAO_PERCENTUAL == p.CHUNKING_SOBREPOSICAO_PERCENTUAL
    # O prefixo indexado é o que o script grava, e é diferente do prefixo do manual inteiro.
    fonte = PREPROCESSAR.read_text(encoding="utf-8")
    achou = re.search(r'^PREFIXO_S3_SECOES = "([^"]+)"', fonte, re.MULTILINE)
    assert achou is not None and achou.group(1) == c.PREFIXO_S3_SECOES
    assert c.PREFIXO_S3_SECOES != p.PREFIXO_S3_MANUAIS


# --------------------------------------------------------------------------------------------
# Papel de serviço (privilégio mínimo)
# --------------------------------------------------------------------------------------------


def test_papel_so_e_assumido_pelo_bedrock_da_conta_para_knowledge_bases() -> None:
    t = _template()
    papel = _unico(t, "AWS::IAM::Role")["Properties"]["AssumeRolePolicyDocument"]["Statement"]
    assert len(papel) == 1
    assert papel[0]["Principal"] == {"Service": "bedrock.amazonaws.com"}
    condicao = papel[0]["Condition"]
    assert "aws:SourceAccount" in condicao["StringEquals"]
    assert json.dumps(condicao["ArnLike"]).endswith(':knowledge-base/*"]]}}')


def test_papel_le_so_o_prefixo_das_secoes_e_decifra_so_via_s3() -> None:
    declaracoes = _declaracoes(_template())
    leitura = declaracoes["LerSecoesDosManuais"]
    assert leitura["Action"] == "s3:GetObject"
    assert json.dumps(leitura["Resource"]).count("/secoes/*") == 1
    assert declaracoes["ListarBucketDeManuais"]["Action"] == "s3:ListBucket"
    kms = declaracoes["DecifrarManuais"]
    assert kms["Action"] == "kms:Decrypt"
    assert "kms:ViaService" in kms["Condition"]["StringEquals"]


def test_papel_invoca_so_o_modelo_de_embeddings_e_acessa_so_o_indice() -> None:
    declaracoes = _declaracoes(_template())
    modelo = declaracoes["InvocarModeloDeEmbeddings"]
    assert modelo["Action"] == "bedrock:InvokeModel"
    assert json.dumps(modelo["Resource"]).endswith('cohere.embed-multilingual-v3"]]}')
    indice = declaracoes["AcessarIndiceDeVetores"]
    assert sorted(indice["Action"]) == sorted(
        [
            "s3vectors:PutVectors",
            "s3vectors:GetVectors",
            "s3vectors:DeleteVectors",
            "s3vectors:QueryVectors",
            "s3vectors:GetIndex",
        ]
    )
    assert "Fn::GetAtt" in json.dumps(indice["Resource"])  # ARN do índice, não curinga


def test_politica_sem_curinga_em_acoes_ou_recursos() -> None:
    for s in _declaracoes(_template()).values():
        acoes = s["Action"] if isinstance(s["Action"], list) else [s["Action"]]
        recursos = s["Resource"] if isinstance(s["Resource"], list) else [s["Resource"]]
        assert all("*" not in a for a in acoes), s["Sid"]
        for r in recursos:
            # O único `*` permitido é o do final do prefixo das seções.
            texto = json.dumps(r)
            assert texto != '"*"' and ("*" not in texto or s["Sid"] == "LerSecoesDosManuais"), s[
                "Sid"
            ]


def test_knowledge_base_so_e_criada_depois_da_politica_do_papel() -> None:
    t = _template()
    politica = next(iter(t.find_resources("AWS::IAM::Policy")))
    assert politica in _unico(t, "AWS::Bedrock::KnowledgeBase")["DependsOn"]


# --------------------------------------------------------------------------------------------
# Configuração publicada
# --------------------------------------------------------------------------------------------


def test_publica_ids_da_knowledge_base_em_ssm_e_nas_saidas() -> None:
    t = _template()
    for nome, valor in (
        ("/tres/config/knowledge-base-id", Match.any_value()),
        ("/tres/config/knowledge-base-data-source-id", Match.any_value()),
        ("/tres/config/secoes-prefixo", "secoes/"),
    ):
        t.has_resource_properties(
            "AWS::SSM::Parameter", {"Name": nome, "Type": "String", "Value": valor}
        )
    saidas = t.to_json()["Outputs"]
    assert {
        "KnowledgeBaseId",
        "KnowledgeBaseArn",
        "KnowledgeBaseDataSourceId",
        "IndiceVetoresArn",
    } <= set(saidas)


def test_prefixo_personalizado_nos_nomes_e_parametros() -> None:
    t = _template(prefixo="demo")
    t.has_resource_properties("AWS::Bedrock::KnowledgeBase", {"Name": "demo-manuais"})
    t.has_resource_properties("AWS::S3Vectors::Index", {"IndexName": "demo-manuais"})
    t.has_resource_properties("AWS::SSM::Parameter", {"Name": "/demo/config/knowledge-base-id"})


def test_app_py_instancia_a_stack_do_conhecimento() -> None:
    fonte = APP_PY.read_text(encoding="utf-8")
    assert "ConhecimentoStack(" in fonte and '"{prefixo}-conhecimento"' in fonte.replace("f", "", 1)
