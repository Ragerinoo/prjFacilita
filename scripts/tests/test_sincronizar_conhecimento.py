"""Testes da sincronização da Knowledge Base e da integração com a carga (Req 20.2, 20.3, 20.7).

O S3 e o DynamoDB são do ``moto``. O cliente ``bedrock-agent`` é um stub com respostas
roteirizadas (o ``moto`` não implementa jobs de ingestão), e o relógio é falso para o teste de
tempo limite não esperar de verdade.

**Validates: Requirements 20.2, 20.3**
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import boto3
import carregar_seed as cs
import pytest
import sincronizar_conhecimento as sk
from botocore.exceptions import ClientError
from moto import mock_aws
from premissas import CHAVE_METADADO_SECAO, PREFIXO_S3_MANUAIS

REGIAO = "sa-east-1"
BUCKET = "tres-manuais-teste"
PREFIXO = "tres"
KB = "KBTESTE123"
DS = "DSTESTE123"
CHAVE_MANUAL = "manuais/tres-passione/manual-exemplo.md"
PREFIXO_SECOES = "secoes/tres-passione/manual-exemplo/"


@pytest.fixture(autouse=True)
def _credenciais_falsas(monkeypatch):
    for nome in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(nome, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGIAO)


@pytest.fixture
def aws():
    with mock_aws():
        dynamodb = boto3.client("dynamodb", region_name=REGIAO)
        for nome, pk, tipo, sk_ in (
            ("modelos", "modelo_id", "S", None),
            ("problemas", "problema_id", "N", None),
            ("instrucoes", "modelo_id", "S", "problema_variante"),
        ):
            chaves = [{"AttributeName": pk, "KeyType": "HASH"}]
            attrs = [{"AttributeName": pk, "AttributeType": tipo}]
            if sk_:
                chaves.append({"AttributeName": sk_, "KeyType": "RANGE"})
                attrs.append({"AttributeName": sk_, "AttributeType": "S"})
            dynamodb.create_table(
                TableName=f"{PREFIXO}-{nome}",
                KeySchema=chaves,
                AttributeDefinitions=attrs,
                BillingMode="PAY_PER_REQUEST",
            )
        s3 = boto3.client("s3", region_name=REGIAO)
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGIAO})
        yield dynamodb, s3


class _Relogio:
    """Tempo falso: ``dormir`` avança o relógio, então nada espera de verdade."""

    def __init__(self) -> None:
        self.agora = 0.0
        self.dormidas: list[float] = []

    def __call__(self) -> float:
        return self.agora

    def dormir(self, segundos: float) -> None:
        self.dormidas.append(segundos)
        self.agora += segundos


class _BedrockAgent:
    """Stub do cliente ``bedrock-agent`` com os status do job em sequência."""

    def __init__(self, status=("COMPLETE",), estatisticas=None, motivos=None, fontes=(DS,)):
        self.status = list(status)
        self.estatisticas = estatisticas or {
            "numberOfDocumentsScanned": 18,
            "numberOfNewDocumentsIndexed": 18,
            "numberOfDocumentsFailed": 0,
        }
        self.motivos = motivos
        self.fontes = list(fontes)
        self.inicios: list[dict] = []
        self.consultas: list[dict] = []
        self.erro_ao_iniciar: ClientError | None = None

    def _job(self, status: str) -> dict:
        job = {
            "knowledgeBaseId": KB,
            "dataSourceId": DS,
            "ingestionJobId": "JOB1",
            "status": status,
        }
        if status in ("COMPLETE", "FAILED"):
            job["statistics"] = self.estatisticas
        if self.motivos:
            job["failureReasons"] = self.motivos
        return {"ingestionJob": job}

    def list_data_sources(self, **kw):
        return {"dataSourceSummaries": [{"dataSourceId": f} for f in self.fontes]}

    def start_ingestion_job(self, **kw):
        self.inicios.append(kw)
        if self.erro_ao_iniciar:
            raise self.erro_ao_iniciar
        return self._job(self.status.pop(0) if len(self.status) > 1 else self.status[0])

    def get_ingestion_job(self, **kw):
        self.consultas.append(kw)
        return self._job(self.status.pop(0) if len(self.status) > 1 else self.status[0])


class _Proxy:
    """Cliente boto3 que repassa tudo, exceto métodos que falham de propósito."""

    def __init__(self, real, **falhas):
        self._real, self._falhas = real, falhas

    def __getattr__(self, nome):
        return self._falhas.get(nome) or getattr(self._real, nome)


def _erro(codigo: str, mensagem: str = "falhou") -> ClientError:
    return ClientError({"Error": {"Code": codigo, "Message": mensagem}}, "Op")


def _secoes(seed_dir: Path = cs.SEED_PADRAO):
    return sk.secoes_dos_manuais(cs.validar(seed_dir).manuais)


def _chaves(s3, prefixo: str = "") -> set[str]:
    resposta = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefixo)
    return {o["Key"] for o in resposta.get("Contents", [])}


def _sincronizar(s3, bedrock, relogio=None, **kw):
    relogio = relogio or _Relogio()
    return sk.sincronizar(
        kw.pop("secoes", None) or _secoes(),
        s3=s3,
        bedrock_agent=bedrock,
        bucket_manuais=BUCKET,
        knowledge_base_id=KB,
        data_source_id=kw.pop("data_source_id", DS),
        dormir=relogio.dormir,
        relogio=relogio,
        **kw,
    )


@pytest.fixture
def seed_copia(tmp_path) -> Path:
    destino = tmp_path / "seed"
    shutil.copytree(cs.SEED_PADRAO, destino, ignore=shutil.ignore_patterns("midia"))
    return destino


# --------------------------------------------------------------------------------------------
# Envio das seções
# --------------------------------------------------------------------------------------------


def test_envia_uma_secao_por_arquivo_com_sidecar_no_prefixo_indexado(aws):
    _, s3 = aws
    resultado = _sincronizar(s3, _BedrockAgent())

    secoes = _secoes()
    assert resultado.secoes == len(secoes) == 18
    esperadas = {s.chave_s3 for s in secoes} | {s.chave_sidecar for s in secoes}
    assert _chaves(s3) == esperadas
    assert all(c.startswith(PREFIXO_SECOES) for c in esperadas)
    # O sidecar de uma seção traz modelo_id, manual e secao.
    corpo = s3.get_object(
        Bucket=BUCKET, Key=f"{PREFIXO_SECOES}3-1-luz-vermelha-fixa.md.metadata.json"
    )["Body"].read()
    assert json.loads(corpo)["metadataAttributes"] == {
        "modelo_id": "tres-passione",
        "manual": "Manual de exemplo TRES Passione",
        CHAVE_METADADO_SECAO: "3.1 Luz vermelha fixa",
    }


def test_segunda_execucao_nao_reenvia_nada(aws):
    _, s3 = aws
    _sincronizar(s3, _BedrockAgent())
    estado = _chaves(s3)

    resultado = _sincronizar(s3, _BedrockAgent())

    assert _chaves(s3) == estado
    assert resultado.enviados == () and resultado.removidos == ()
    assert len(resultado.inalterados) == 36


def test_secao_obsoleta_e_removida_so_dos_modelos_sincronizados(aws):
    _, s3 = aws
    s3.put_object(Bucket=BUCKET, Key=f"{PREFIXO_SECOES}velha.md", Body=b"x")
    s3.put_object(Bucket=BUCKET, Key="secoes/outro-modelo/m/x.md", Body=b"x")

    resultado = _sincronizar(s3, _BedrockAgent())

    assert resultado.removidos == (f"{PREFIXO_SECOES}velha.md",)
    assert f"{PREFIXO_SECOES}velha.md" not in _chaves(s3)
    assert "secoes/outro-modelo/m/x.md" in _chaves(s3)


def test_falha_no_envio_desfaz_a_execucao_e_restaura_o_sobrescrito(aws):
    _, s3 = aws
    secoes = _secoes()
    alvo = secoes[0]
    s3.put_object(Bucket=BUCKET, Key=alvo.chave_s3, Body=b"versao antiga")
    antes = _chaves(s3)
    real = s3.put_object
    ultima = secoes[-1].chave_sidecar

    def put(**kw):
        if kw["Key"] == ultima:
            raise _erro("AccessDenied", "sem permissão")
        return real(**kw)

    with pytest.raises(sk.ErroSincronizacao) as exc:
        _sincronizar(_Proxy(s3, put_object=put), _BedrockAgent())

    assert exc.value.falhas[0].item == f"seção {ultima}"
    assert "AccessDenied" in exc.value.falhas[0].motivo
    assert _chaves(s3) == antes
    corpo = s3.get_object(Bucket=BUCKET, Key=alvo.chave_s3)["Body"].read()
    assert corpo == b"versao antiga"


def test_manual_sem_secao_e_apontado_com_o_motivo():
    manual = cs.ManualLocal("tres-passione", CHAVE_MANUAL, b"# So titulo\n", b"{}")
    with pytest.raises(sk.ErroSincronizacao) as exc:
        sk.secoes_dos_manuais({"tres-passione": [manual]})
    assert exc.value.falhas[0].item == f"conhecimento > tres-passione > {CHAVE_MANUAL}"
    assert "nenhuma seção" in exc.value.falhas[0].motivo


# --------------------------------------------------------------------------------------------
# Ingestão
# --------------------------------------------------------------------------------------------


def test_inicia_a_ingestao_e_espera_ate_completar(aws):
    _, s3 = aws
    bedrock = _BedrockAgent(status=("STARTING", "IN_PROGRESS", "IN_PROGRESS", "COMPLETE"))
    relogio = _Relogio()

    resultado = _sincronizar(s3, bedrock, relogio)

    assert bedrock.inicios[0]["knowledgeBaseId"] == KB
    assert bedrock.inicios[0]["dataSourceId"] == DS
    assert len(bedrock.consultas) == 3
    assert all(c["ingestionJobId"] == "JOB1" for c in bedrock.consultas)
    assert relogio.dormidas == [sk.INTERVALO_CONSULTA_PADRAO_S] * 3
    assert resultado.status == "COMPLETE"
    assert resultado.ingestion_job_id == "JOB1"
    assert resultado.estatisticas["numberOfNewDocumentsIndexed"] == 18


def test_resolve_o_data_source_unico_quando_nao_informado(aws):
    _, s3 = aws
    bedrock = _BedrockAgent()
    _sincronizar(s3, bedrock, data_source_id=None)
    assert bedrock.inicios[0]["dataSourceId"] == DS


@pytest.mark.parametrize("fontes", [(), ("a", "b")])
def test_data_source_ambiguo_ou_ausente_pede_o_id(aws, fontes):
    _, s3 = aws
    with pytest.raises(sk.ErroSincronizacao, match="--data-source-id"):
        _sincronizar(s3, _BedrockAgent(fontes=fontes), data_source_id=None)


def test_tempo_esgotado_gera_erro_claro_com_o_job(aws):
    _, s3 = aws
    bedrock = _BedrockAgent(status=("IN_PROGRESS",))
    relogio = _Relogio()

    with pytest.raises(sk.ErroSincronizacao) as exc:
        _sincronizar(s3, bedrock, relogio, tempo_limite_s=12, intervalo_s=5)

    motivo = exc.value.falhas[0].motivo
    assert "tempo esgotado após 12 s" in motivo and "JOB1" in exc.value.falhas[0].item
    assert relogio.agora == 15  # 3 consultas de 5 s até passar de 12 s


@pytest.mark.parametrize("status", ["FAILED", "STOPPED"])
def test_job_que_falha_informa_status_e_motivos(aws, status):
    _, s3 = aws
    bedrock = _BedrockAgent(status=("IN_PROGRESS", status), motivos=["sem acesso ao modelo"])

    with pytest.raises(sk.ErroSincronizacao) as exc:
        _sincronizar(s3, bedrock)

    assert status in exc.value.falhas[0].motivo
    assert "sem acesso ao modelo" in exc.value.falhas[0].motivo


def test_job_completo_com_documentos_falhos_e_erro(aws):
    _, s3 = aws
    bedrock = _BedrockAgent(
        estatisticas={"numberOfDocumentsFailed": 2, "numberOfDocumentsScanned": 18},
        motivos=["metadados acima do limite"],
    )

    with pytest.raises(sk.ErroSincronizacao, match="2 documento"):
        _sincronizar(s3, bedrock)


def test_conflito_ao_iniciar_orienta_a_aguardar(aws):
    _, s3 = aws
    bedrock = _BedrockAgent()
    bedrock.erro_ao_iniciar = _erro("ConflictException", "job em andamento")

    with pytest.raises(sk.ErroSincronizacao) as exc:
        _sincronizar(s3, bedrock)

    assert "ConflictException" in exc.value.falhas[0].motivo
    assert "em andamento" in exc.value.falhas[0].motivo


def test_erro_ao_consultar_o_andamento_e_reportado(aws):
    _, s3 = aws
    bedrock = _BedrockAgent(status=("IN_PROGRESS",))

    def consultar(**_kw):
        raise _erro("ThrottlingException", "devagar")

    bedrock.get_ingestion_job = consultar
    with pytest.raises(sk.ErroSincronizacao, match="ThrottlingException"):
        _sincronizar(s3, bedrock)


# --------------------------------------------------------------------------------------------
# Integração com a carga do seed
# --------------------------------------------------------------------------------------------


def _carregar(aws, seed_dir=cs.SEED_PADRAO, **kw):
    dynamodb, s3 = aws
    return cs.carregar(
        seed_dir, dynamodb=dynamodb, s3=s3, bucket_manuais=BUCKET, prefixo=PREFIXO, **kw
    )


def test_carga_sem_a_opcao_nao_mexe_na_knowledge_base(aws):
    _, s3 = aws
    resultado = _carregar(aws)

    assert resultado.conhecimento is None
    assert _chaves(s3) == {CHAVE_MANUAL, f"{CHAVE_MANUAL}.metadata.json"}


def test_carga_com_a_opcao_envia_secoes_e_roda_a_ingestao(aws):
    _, s3 = aws
    bedrock = _BedrockAgent(status=("IN_PROGRESS", "COMPLETE"))
    relogio = _Relogio()

    resultado = _carregar(
        aws,
        bedrock_agent=bedrock,
        knowledge_base_id=KB,
        data_source_id=DS,
        dormir=relogio.dormir,
    )

    # O manual inteiro continua em ``manuais/`` e as seções vão para o prefixo indexado.
    assert {CHAVE_MANUAL, f"{CHAVE_MANUAL}.metadata.json"} <= _chaves(s3, PREFIXO_S3_MANUAIS)
    assert len(_chaves(s3, "secoes/")) == 36
    assert resultado.conhecimento is not None and resultado.conhecimento.status == "COMPLETE"
    assert resultado.grupos["problemas"] == 13


def test_carga_com_a_opcao_duas_vezes_da_o_mesmo_conjunto_no_s3(aws):
    _, s3 = aws
    kw = {"bedrock_agent": _BedrockAgent(), "knowledge_base_id": KB, "data_source_id": DS}
    _carregar(aws, **kw)
    estado = _chaves(s3)

    segunda = _carregar(aws, **kw)

    assert _chaves(s3) == estado
    assert segunda.conhecimento is not None and segunda.conhecimento.enviados == ()


def test_falha_na_ingestao_interrompe_a_carga_com_item_e_motivo(aws):
    bedrock = _BedrockAgent(status=("FAILED",), motivos=["modelo não liberado"])

    with pytest.raises(cs.ErroCarga) as exc:
        _carregar(aws, bedrock_agent=bedrock, knowledge_base_id=KB, data_source_id=DS)

    assert "job JOB1" in exc.value.falhas[0].item
    assert "modelo não liberado" in exc.value.falhas[0].motivo


def test_manual_sem_secoes_falha_na_fase_1_sem_escrever_nada(aws, seed_copia):
    dynamodb, s3 = aws
    (seed_copia / "manuais" / "tres-passione" / "manual-exemplo.md").write_text(
        "# Só o título\n", encoding="utf-8"
    )

    with pytest.raises(cs.ErroCarga) as exc:
        _carregar(
            aws, seed_copia, bedrock_agent=_BedrockAgent(), knowledge_base_id=KB, data_source_id=DS
        )

    assert any("nenhuma seção" in f.motivo for f in exc.value.falhas)
    assert _chaves(s3) == set()
    assert dynamodb.scan(TableName=f"{PREFIXO}-problemas")["Count"] == 0


def test_knowledge_base_sem_cliente_bedrock_falha_na_fase_1(aws):
    _, s3 = aws
    with pytest.raises(cs.ErroCarga, match="bedrock-agent"):
        _carregar(aws, knowledge_base_id=KB)
    assert _chaves(s3) == set()


def test_cli_exige_knowledge_base_id_ao_sincronizar(monkeypatch, capsys):
    monkeypatch.delenv("TRES_KNOWLEDGE_BASE_ID", raising=False)
    codigo = cs.main(["--bucket-manuais", BUCKET, "--sincronizar-conhecimento"])
    assert codigo == 1
    assert "--knowledge-base-id" in capsys.readouterr().err


def test_validar_apenas_com_conhecimento_confere_as_secoes(capsys):
    assert cs.main(["--validar-apenas", "--sincronizar-conhecimento"]) == 0
    assert "Seed válido" in capsys.readouterr().out
