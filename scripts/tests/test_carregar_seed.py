"""Testes de fumaça da carga do seed (Req 20.3, 20.7) com moto."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import boto3
import pytest
from boto3.dynamodb.types import TypeDeserializer
from moto import mock_aws

import carregar_seed as cs

REGIAO = "sa-east-1"
BUCKET = "tres-manuais-teste"
PREFIXO = "tres"
CHAVE_MANUAL = "manuais/tres-passione/manual-exemplo.md"


@pytest.fixture(autouse=True)
def _credenciais_falsas(monkeypatch):
    for nome in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(nome, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGIAO)


@pytest.fixture
def aws():
    with mock_aws():
        dynamodb = boto3.client("dynamodb", region_name=REGIAO)
        for nome, pk, tipo, sk in (
            ("modelos", "modelo_id", "S", None),
            ("problemas", "problema_id", "N", None),
            ("instrucoes", "modelo_id", "S", "problema_variante"),
        ):
            chaves = [{"AttributeName": pk, "KeyType": "HASH"}]
            attrs = [{"AttributeName": pk, "AttributeType": tipo}]
            if sk:
                chaves.append({"AttributeName": sk, "KeyType": "RANGE"})
                attrs.append({"AttributeName": sk, "AttributeType": "S"})
            dynamodb.create_table(
                TableName=f"{PREFIXO}-{nome}",
                KeySchema=chaves,
                AttributeDefinitions=attrs,
                BillingMode="PAY_PER_REQUEST",
            )
        s3 = boto3.client("s3", region_name=REGIAO)
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGIAO})
        yield dynamodb, s3


def _tabela(dynamodb, nome):
    itens = dynamodb.scan(TableName=f"{PREFIXO}-{nome}")["Items"]
    des = TypeDeserializer()
    return sorted(
        ({k: des.deserialize(v) for k, v in i.items()} for i in itens),
        key=lambda i: json.dumps(i, sort_keys=True, default=str),
    )


def _estado(dynamodb, s3):
    objetos = s3.list_objects_v2(Bucket=BUCKET).get("Contents", [])
    return (
        [_tabela(dynamodb, t) for t in ("modelos", "problemas", "instrucoes")],
        sorted(o["Key"] for o in objetos),
    )


def _carregar(aws, seed_dir=cs.SEED_PADRAO, dynamodb=None, s3=None):
    d, s = aws
    return cs.carregar(
        seed_dir, dynamodb=dynamodb or d, s3=s3 or s, bucket_manuais=BUCKET, prefixo=PREFIXO
    )


@pytest.fixture
def seed_copia(tmp_path) -> Path:
    destino = tmp_path / "seed"
    shutil.copytree(cs.SEED_PADRAO, destino, ignore=shutil.ignore_patterns("midia"))
    return destino


class _Proxy:
    """Cliente boto3 que repassa tudo, exceto métodos que falham de propósito."""

    def __init__(self, real, **falhas):
        self._real, self._falhas = real, falhas

    def __getattr__(self, nome):
        if nome in self._falhas:
            return self._falhas[nome]
        return getattr(self._real, nome)


def test_seed_do_repositorio_e_valido():
    seed = cs.validar(cs.SEED_PADRAO)
    assert len(seed.problemas) == 13


def test_carga_grava_tudo(aws):
    resultado = _carregar(aws)
    dynamodb, s3 = aws

    assert resultado.grupos == {
        "problemas": 13,
        "catalogo": 3,
        "instrucoes:tres-passione": 14,
    }
    modelos, problemas, instrucoes = (
        _tabela(dynamodb, t) for t in ("modelos", "problemas", "instrucoes")
    )
    assert sorted(int(p["problema_id"]) for p in problemas) == list(range(1, 14))
    passione = next(m for m in modelos if m["modelo_id"] == "tres-passione")
    assert passione["manuais"] == [CHAVE_MANUAL]
    assert {m["catalogo_pk"] for m in modelos} == {"CATALOGO"}  # partição do gsi_catalogo
    assert "areas" in passione["seletor"] and not any(k.startswith("_") for k in passione)
    assert {i["problema_variante"] for i in instrucoes} >= {"1#padrao", "10#externo"}
    chaves = {o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET)["Contents"]}
    assert chaves == {CHAVE_MANUAL, f"{CHAVE_MANUAL}.metadata.json"}


def test_duas_execucoes_dao_o_mesmo_conjunto(aws):
    _carregar(aws)
    primeiro = _estado(*aws)
    segundo_resultado = _carregar(aws)

    assert _estado(*aws) == primeiro
    assert segundo_resultado.manuais_enviados == ()
    assert len(segundo_resultado.manuais_inalterados) == 2


def test_validacao_falha_sem_escrever_e_indica_item_e_motivo(aws, seed_copia):
    # 12 problemas, áreas sobrepostas e manual ausente, tudo de uma vez.
    problemas = json.loads((seed_copia / "problemas.json").read_text(encoding="utf-8"))
    problemas["problemas"].pop()
    (seed_copia / "problemas.json").write_text(json.dumps(problemas), encoding="utf-8")
    caminho = seed_copia / "seletor" / "tres-passione.json"
    mapa = json.loads(caminho.read_text(encoding="utf-8"))
    mapa["areas"][1]["forma"].update(x=10, y=8)  # em cima de luz_alerta
    caminho.write_text(json.dumps(mapa), encoding="utf-8")
    (seed_copia / CHAVE_MANUAL).unlink()

    with pytest.raises(cs.ErroCarga) as info:
        _carregar(aws, seed_copia)

    itens = {f.item: f.motivo for f in info.value.falhas}
    assert "devem existir exatamente 13 problemas" in itens["problemas.json"]
    assert any("se sobrepõem" in m for i, m in itens.items() if i.startswith("seletor/"))
    assert itens[f"manuais > tres-passione > {CHAVE_MANUAL}"] == "arquivo do manual não encontrado"
    assert _estado(*aws) == ([[], [], []], [])


def test_falha_de_um_grupo_nao_deixa_registros_parciais(aws):
    dynamodb, s3 = aws

    real = dynamodb.transact_write_items

    def transacao(TransactItems):
        if TransactItems[0]["Put"]["TableName"] == f"{PREFIXO}-instrucoes":
            raise RuntimeError("falha injetada")
        return real(TransactItems=TransactItems)

    proxy = _Proxy(dynamodb, transact_write_items=transacao)
    with pytest.raises(cs.ErroCarga) as info:
        _carregar(aws, dynamodb=proxy)

    [falha] = info.value.falhas
    assert "instrucoes:tres-passione" in falha.item and "tres-instrucoes" in falha.item
    assert "falha injetada" in falha.motivo
    modelos, problemas, instrucoes = (
        _tabela(dynamodb, t) for t in ("modelos", "problemas", "instrucoes")
    )
    assert (
        instrucoes == [] and len(problemas) == 13 and len(modelos) == 3
    )  # grupos anteriores completos
    assert s3.list_objects_v2(Bucket=BUCKET).get("Contents") is None  # manuais não enviados


def test_falha_no_s3_remove_os_manuais_enviados_na_execucao(aws):
    dynamodb, s3 = aws
    real = s3.put_object

    def put(**kw):
        if kw["Key"].endswith(".metadata.json"):
            raise RuntimeError("falha injetada no S3")
        return real(**kw)

    with pytest.raises(cs.ErroCarga) as info:
        _carregar(aws, s3=_Proxy(s3, put_object=put))

    [falha] = info.value.falhas
    assert falha.item == f"manual {CHAVE_MANUAL}.metadata.json"
    assert "falha injetada no S3" in falha.motivo
    assert s3.list_objects_v2(Bucket=BUCKET).get("Contents") is None


def test_falha_no_s3_restaura_manual_sobrescrito(aws, seed_copia):
    _, s3 = aws
    s3.put_object(Bucket=BUCKET, Key=CHAVE_MANUAL, Body=b"versao anterior")
    real = s3.put_object

    def put(**kw):
        if kw["Key"].endswith(".metadata.json"):
            raise RuntimeError("falha injetada no S3")
        return real(**kw)

    with pytest.raises(cs.ErroCarga):
        _carregar(aws, s3=_Proxy(s3, put_object=put))

    assert s3.get_object(Bucket=BUCKET, Key=CHAVE_MANUAL)["Body"].read() == b"versao anterior"
    assert [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET)["Contents"]] == [CHAVE_MANUAL]
