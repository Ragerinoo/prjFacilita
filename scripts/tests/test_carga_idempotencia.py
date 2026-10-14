"""Testes da carga do seed: idempotência, atomicidade por grupo e mensagens de erro.

Cobre os Req 20.3 (carga do seed) e 20.7 (carga idempotente, sem registros parciais e com erro
indicando o item e o motivo). Usa ``moto`` e, para o teste de consistência, lê
``infra/stacks/dados_stack.py`` com ``ast`` (sem precisar do ``aws_cdk``).
"""

from __future__ import annotations

import ast
import copy
import json
import re
import shutil
from pathlib import Path

import boto3
import pytest
from boto3.dynamodb.types import TypeDeserializer
from botocore.exceptions import ClientError
from moto import mock_aws

import carregar_seed as cs

REGIAO = "sa-east-1"
BUCKET = "tres-manuais-teste"
PREFIXO = "tres"
MANUAL_PASSIONE = "manuais/tres-passione/manual-exemplo.md"
MANUAL_CIRCO = "manuais/tres-circo/manual-circo.md"
CHAVES_S3_DOIS_MODELOS = {
    MANUAL_PASSIONE,
    f"{MANUAL_PASSIONE}.metadata.json",
    MANUAL_CIRCO,
    f"{MANUAL_CIRCO}.metadata.json",
}
# Ordem de gravação dos grupos (``montar_grupos``): problemas, catálogo, instruções por modelo.
GRUPOS = ["problemas", "catalogo", "instrucoes:tres-circo", "instrucoes:tres-passione"]
STACK_DADOS = Path(__file__).resolve().parents[2] / "infra" / "stacks" / "dados_stack.py"


# --------------------------------------------------------------------------------------------
# Tabelas da stack (fonte única), lidas sem importar aws_cdk
# --------------------------------------------------------------------------------------------


def _tabelas_da_stack() -> dict[str, dict[str, str | None]]:
    """``nome -> {pk, sk, pk_tipo}`` a partir da constante ``TABELAS`` de ``dados_stack.py``."""
    arvore = ast.parse(STACK_DADOS.read_text(encoding="utf-8"))
    for no in arvore.body:
        alvo = no.target if isinstance(no, ast.AnnAssign) else None
        if isinstance(alvo, ast.Name) and alvo.id == "TABELAS":
            valor = no.value
            break
    else:  # pragma: no cover
        raise AssertionError("TABELAS não encontrada em dados_stack.py")
    assert isinstance(valor, ast.Tuple)
    tabelas: dict[str, dict[str, str | None]] = {}
    for chamada in valor.elts:
        assert isinstance(chamada, ast.Call)
        nome = ast.literal_eval(chamada.args[0])
        spec: dict[str, str | None] = {"pk": None, "sk": None, "pk_tipo": "S"}
        for kw in chamada.keywords:
            if kw.arg in ("pk", "sk"):
                spec[kw.arg] = ast.literal_eval(kw.value)
            elif kw.arg == "pk_tipo":
                assert isinstance(kw.value, ast.Name)
                spec["pk_tipo"] = kw.value.id  # "S" ou "N"
        tabelas[nome] = spec
    return tabelas


# --------------------------------------------------------------------------------------------
# Fixtures e utilitários
# --------------------------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _credenciais_falsas(monkeypatch):
    for nome in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
        monkeypatch.setenv(nome, "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGIAO)


@pytest.fixture
def aws():
    """Tabelas criadas a partir da stack (não de valores copiados) e o bucket de manuais."""
    with mock_aws():
        dynamodb = boto3.client("dynamodb", region_name=REGIAO)
        for nome, spec in _tabelas_da_stack().items():
            chaves = [{"AttributeName": spec["pk"], "KeyType": "HASH"}]
            attrs = {spec["pk"]: spec["pk_tipo"]}
            if spec["sk"]:
                chaves.append({"AttributeName": spec["sk"], "KeyType": "RANGE"})
                attrs[spec["sk"]] = "S"
            dynamodb.create_table(
                TableName=f"{PREFIXO}-{nome}",
                KeySchema=chaves,
                AttributeDefinitions=[
                    {"AttributeName": a, "AttributeType": t} for a, t in attrs.items()
                ],
                BillingMode="PAY_PER_REQUEST",
            )
        s3 = boto3.client("s3", region_name=REGIAO)
        s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": REGIAO})
        yield dynamodb, s3


def _tabela(dynamodb, nome):
    itens, token = [], {}
    while True:
        pagina = dynamodb.scan(TableName=f"{PREFIXO}-{nome}", **token)
        itens += pagina["Items"]
        if "LastEvaluatedKey" not in pagina:
            break
        token = {"ExclusiveStartKey": pagina["LastEvaluatedKey"]}
    des = TypeDeserializer()
    return sorted(
        ({k: des.deserialize(v) for k, v in i.items()} for i in itens),
        key=lambda i: json.dumps(i, sort_keys=True, default=str),
    )


def _dump_dynamo(dynamodb):
    return {t: _tabela(dynamodb, t) for t in ("modelos", "problemas", "instrucoes")}


def _dump_s3(s3):
    """``chave -> (conteúdo, content-type)`` de todos os objetos do bucket."""
    saida = {}
    for obj in s3.list_objects_v2(Bucket=BUCKET).get("Contents", []):
        resposta = s3.get_object(Bucket=BUCKET, Key=obj["Key"])
        saida[obj["Key"]] = (resposta["Body"].read(), resposta["ContentType"])
    return saida


def _estado(aws):
    dynamodb, s3 = aws
    return _dump_dynamo(dynamodb), _dump_s3(s3)


def _itens_do_grupo(dump, grupo):
    if grupo == "problemas":
        return dump["problemas"]
    if grupo == "catalogo":
        return dump["modelos"]
    modelo_id = grupo.split(":", 1)[1]
    return [i for i in dump["instrucoes"] if i["modelo_id"] == modelo_id]


def _carregar(aws, seed_dir=cs.SEED_PADRAO, dynamodb=None, s3=None):
    d, s = aws
    return cs.carregar(
        seed_dir, dynamodb=dynamodb or d, s3=s3 or s, bucket_manuais=BUCKET, prefixo=PREFIXO
    )


def _ler(caminho: Path):
    return json.loads(caminho.read_text(encoding="utf-8"))


def _gravar(caminho: Path, dados) -> None:
    caminho.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")


@pytest.fixture
def seed_copia(tmp_path) -> Path:
    destino = tmp_path / "seed"
    shutil.copytree(cs.SEED_PADRAO, destino, ignore=shutil.ignore_patterns("midia"))
    return destino


@pytest.fixture
def seed_dois(seed_copia) -> Path:
    """Seed com dois modelos com instruções e manuais: ``tres-passione`` e ``tres-circo``."""
    instrucoes = _ler(seed_copia / "instrucoes" / "tres-passione.json")
    for ins in instrucoes["instrucoes"]:
        ins["modelo_id"] = "tres-circo"
    _gravar(seed_copia / "instrucoes" / "tres-circo.json", instrucoes)

    pasta = seed_copia / "manuais" / "tres-circo"
    pasta.mkdir(parents=True)
    (pasta / "manual-circo.md").write_text("# Manual do Circo\n\nTexto.\n", encoding="utf-8")
    _gravar(
        pasta / "manual-circo.md.metadata.json",
        {"metadataAttributes": {"modelo_id": "tres-circo", "manual": "Manual do Circo"}},
    )
    catalogo = _ler(seed_copia / "catalogo.json")
    circo = next(m for m in catalogo["modelos"] if m["modelo_id"] == "tres-circo")
    circo["manuais"] = [MANUAL_CIRCO]
    _gravar(seed_copia / "catalogo.json", catalogo)
    return seed_copia


def _seed_alterado(origem: Path, destino: Path) -> Path:
    """Cópia do seed com conteúdo diferente em TODOS os grupos (mesmas chaves)."""
    shutil.copytree(origem, destino)
    problemas = _ler(destino / "problemas.json")
    for p in problemas["problemas"]:
        p["icone_alt"] += " (v2)"
    _gravar(destino / "problemas.json", problemas)
    catalogo = _ler(destino / "catalogo.json")
    for m in catalogo["modelos"]:
        m["voltagens"] = ["220V"]
    _gravar(destino / "catalogo.json", catalogo)
    for arquivo in (destino / "instrucoes").glob("*.json"):
        dados = _ler(arquivo)
        for ins in dados["instrucoes"]:
            for passo in ins["passos"]:
                passo["texto_equivalente"] += " (v2)"
        _gravar(arquivo, dados)
    return destino


class _Proxy:
    """Cliente boto3 que repassa tudo, exceto métodos que falham de propósito."""

    def __init__(self, real, **substitutos):
        self._real, self._substitutos = real, substitutos

    def __getattr__(self, nome):
        if nome in self._substitutos:
            return self._substitutos[nome]
        return getattr(self._real, nome)


def _nome_do_grupo(transact_items) -> str:
    primeiro = transact_items[0]["Put"]
    tabela = primeiro["TableName"].removeprefix(f"{PREFIXO}-")
    if tabela == "problemas":
        return "problemas"
    if tabela == "modelos":
        return "catalogo"
    return f"instrucoes:{primeiro['Item']['modelo_id']['S']}"


def _dynamo_que_falha_no_grupo(dynamodb, grupo: str) -> _Proxy:
    """Torna inválida a transação do ``grupo`` (duas operações no mesmo item).

    A falha é do próprio DynamoDB (o moto rejeita a transação inteira), então prova a
    atomicidade do grupo e não só o tratamento de erro do script.
    """
    real = dynamodb.transact_write_items

    def transacao(TransactItems):
        if _nome_do_grupo(TransactItems) == grupo:
            TransactItems = [*TransactItems, copy.deepcopy(TransactItems[-1])]
        return real(TransactItems=TransactItems)

    return _Proxy(dynamodb, transact_write_items=transacao)


# --------------------------------------------------------------------------------------------
# Idempotência (Req 20.7)
# --------------------------------------------------------------------------------------------


def test_duas_execucoes_dao_o_mesmo_conjunto_de_itens_e_objetos(aws, seed_dois):
    primeira = _carregar(aws, seed_dois)
    dynamo_1, s3_1 = _estado(aws)
    segunda = _carregar(aws, seed_dois)
    dynamo_2, s3_2 = _estado(aws)

    assert dynamo_2 == dynamo_1
    assert s3_2 == s3_1
    assert set(s3_1) == CHAVES_S3_DOIS_MODELOS
    assert segunda.grupos == primeira.grupos
    assert len(primeira.manuais_enviados) == 4 and primeira.manuais_inalterados == ()
    assert segunda.manuais_enviados == () and len(segunda.manuais_inalterados) == 4
    # Nenhum registro duplicado: quantidades batem com o seed (13 + 3 + 14 + 14).
    assert (len(dynamo_2["problemas"]), len(dynamo_2["modelos"])) == (13, 3)
    assert len(dynamo_2["instrucoes"]) == 28


def test_recarregar_seed_alterado_sobrescreve_sem_duplicar(aws, seed_dois, tmp_path):
    _carregar(aws, seed_dois)
    antes, _ = _estado(aws)
    _carregar(aws, _seed_alterado(seed_dois, tmp_path / "v2"))
    depois, _ = _estado(aws)

    assert depois != antes
    assert {k: len(v) for k, v in depois.items()} == {k: len(v) for k, v in antes.items()}


def test_nova_execucao_apos_falha_completa_a_carga_como_uma_execucao_limpa(aws, seed_dois):
    dynamodb, _ = aws
    with pytest.raises(cs.ErroCarga):
        _carregar(aws, seed_dois, dynamodb=_dynamo_que_falha_no_grupo(dynamodb, GRUPOS[2]))
    _carregar(aws, seed_dois)
    apos_falha = _estado(aws)

    chaves_por_tabela = _tabelas_da_stack()
    for tabela in ("modelos", "problemas", "instrucoes"):  # esvazia e repete do zero
        for item in dynamodb.scan(TableName=f"{PREFIXO}-{tabela}")["Items"]:
            chaves = chaves_por_tabela[tabela]
            alvo = {chaves["pk"]: item[chaves["pk"]]}
            if chaves["sk"]:
                alvo[chaves["sk"]] = item[chaves["sk"]]
            dynamodb.delete_item(TableName=f"{PREFIXO}-{tabela}", Key=alvo)
    _carregar(aws, seed_dois)
    assert _estado(aws) == apos_falha


# --------------------------------------------------------------------------------------------
# Falha injetada por grupo (Req 20.7)
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("grupo", GRUPOS)
def test_falha_em_um_grupo_nao_deixa_registros_parciais_em_tabelas_vazias(aws, seed_dois, grupo):
    dynamodb, s3 = aws
    with pytest.raises(cs.ErroCarga) as info:
        _carregar(aws, seed_dois, dynamodb=_dynamo_que_falha_no_grupo(dynamodb, grupo))

    # Grupos anteriores completos; o grupo que falhou e os seguintes, vazios.
    posicao = GRUPOS.index(grupo)
    esperado = {"problemas": 13, "catalogo": 3, "instrucoes:tres-circo": 14}
    esperado["instrucoes:tres-passione"] = 14
    dump = _dump_dynamo(dynamodb)
    for i, g in enumerate(GRUPOS):
        quantidade = len(_itens_do_grupo(dump, g))
        assert quantidade == (esperado[g] if i < posicao else 0), g
    assert _dump_s3(s3) == {}  # manuais só são enviados depois de todos os grupos

    [falha] = info.value.falhas
    assert grupo in falha.item and f"{PREFIXO}-" in falha.item
    assert falha.motivo.strip()
    assert str(info.value) == f"- {falha.item}: {falha.motivo}"


@pytest.mark.parametrize("grupo", GRUPOS)
def test_falha_em_um_grupo_preserva_inteiro_o_estado_anterior_do_grupo(
    aws, seed_dois, grupo, tmp_path
):
    dynamodb, _ = aws
    novo_dir = _seed_alterado(seed_dois, tmp_path / "v2")
    _carregar(aws, seed_dois)
    base, s3_base = _estado(aws)
    _carregar(aws, novo_dir)
    novo, _ = _estado(aws)
    _carregar(aws, seed_dois)  # volta ao estado anterior (mesmas chaves, sobrescreve tudo)
    assert _dump_dynamo(dynamodb) == base
    for g in GRUPOS:
        assert _itens_do_grupo(novo, g) != _itens_do_grupo(base, g), g  # a carga muda o grupo

    with pytest.raises(cs.ErroCarga) as info:
        _carregar(aws, novo_dir, dynamodb=_dynamo_que_falha_no_grupo(dynamodb, grupo))

    atual = _dump_dynamo(dynamodb)
    posicao = GRUPOS.index(grupo)
    for i, g in enumerate(GRUPOS):
        # Cada grupo está inteiro na versão nova (já gravado) ou inteiro na antiga. Nunca misturado.
        fonte = novo if i < posicao else base
        assert _itens_do_grupo(atual, g) == _itens_do_grupo(fonte, g), g
    assert _dump_s3(aws[1]) == s3_base
    assert grupo in info.value.falhas[0].item


def test_falha_em_grupo_nao_atinge_manuais_ja_existentes_no_s3(aws, seed_dois):
    dynamodb, s3 = aws
    _carregar(aws, seed_dois)
    antes = _dump_s3(s3)
    with pytest.raises(cs.ErroCarga):
        _carregar(aws, seed_dois, dynamodb=_dynamo_que_falha_no_grupo(dynamodb, "catalogo"))
    assert _dump_s3(s3) == antes


def test_erro_do_dynamodb_e_reportado_com_grupo_tabela_e_motivo(aws, seed_dois):
    dynamodb, _ = aws

    def transacao(TransactItems):
        raise ClientError(
            {
                "Error": {"Code": "TransactionCanceledException", "Message": "cancelada"},
                "CancellationReasons": [
                    {"Code": "None"},
                    {"Code": "ValidationError", "Message": "item grande demais"},
                ],
            },
            "TransactWriteItems",
        )

    with pytest.raises(cs.ErroCarga) as info:
        _carregar(aws, seed_dois, dynamodb=_Proxy(dynamodb, transact_write_items=transacao))

    [falha] = info.value.falhas
    assert falha.item == f"grupo problemas (tabela {PREFIXO}-problemas)"
    assert "TransactionCanceledException" in falha.motivo
    assert "ValidationError: item grande demais" in falha.motivo
    assert "None" not in falha.motivo.replace("TransactionCanceledException", "")
    assert _dump_dynamo(dynamodb) == {"modelos": [], "problemas": [], "instrucoes": []}


# --------------------------------------------------------------------------------------------
# Falhas de validação: nada é escrito e cada item sai com o motivo (Req 20.3, 20.7)
# --------------------------------------------------------------------------------------------


def _doze_problemas(seed: Path) -> None:
    dados = _ler(seed / "problemas.json")
    dados["problemas"].pop()
    _gravar(seed / "problemas.json", dados)


def _onze_passos(seed: Path) -> None:
    caminho = seed / "instrucoes" / "tres-passione.json"
    dados = _ler(caminho)
    ins = dados["instrucoes"][0]
    ins["passos"] = [{**ins["passos"][i % 4], "n": i + 1} for i in range(11)]
    _gravar(caminho, dados)


def _texto_longo(seed: Path) -> None:
    caminho = seed / "instrucoes" / "tres-passione.json"
    dados = _ler(caminho)
    dados["instrucoes"][0]["passos"][0]["texto"] = "x" * 141
    _gravar(caminho, dados)


def _alt_longo(seed: Path) -> None:
    caminho = seed / "instrucoes" / "tres-passione.json"
    dados = _ler(caminho)
    dados["instrucoes"][0]["passos"][1]["alt"] = "y" * 126
    _gravar(caminho, dados)


def _areas_sobrepostas(seed: Path) -> None:
    caminho = seed / "seletor" / "tres-passione.json"
    mapa = _ler(caminho)
    mapa["areas"][1]["forma"].update(x=10, y=8)  # em cima de luz_alerta
    _gravar(caminho, mapa)


def _sem_manual(seed: Path) -> None:
    (seed / MANUAL_PASSIONE).unlink()


def _sem_metadados_do_manual(seed: Path) -> None:
    (seed / f"{MANUAL_PASSIONE}.metadata.json").unlink()


def _titulo_longo(seed: Path) -> None:
    dados = _ler(seed / "problemas.json")
    dados["problemas"][2]["titulo"] = "t" * 41
    _gravar(seed / "problemas.json", dados)


def _json_quebrado(seed: Path) -> None:
    (seed / "catalogo.json").write_text("{ nao e json", encoding="utf-8")


CASOS_INVALIDOS = {
    "12 problemas": (_doze_problemas, "problemas.json", "exatamente 13 problemas (há 12)"),
    "11 passos": (
        _onze_passos,
        "instrucoes/tres-passione.json > problema 1 (padrao) > passos",
        "de 1 a 10 passos (tem 11)",
    ),
    "texto com mais de 140": (
        _texto_longo,
        "instrucoes/tres-passione.json > problema 1 (padrao) > passos[0].texto",
        "no máximo 140 caracteres (tem 141)",
    ),
    "alt com mais de 125": (
        _alt_longo,
        "instrucoes/tres-passione.json > problema 1 (padrao) > passos[1].alt",
        "no máximo 125 caracteres (tem 126)",
    ),
    "áreas sobrepostas": (
        _areas_sobrepostas,
        "seletor/tres-passione.json > areas",
        "se sobrepõem",
    ),
    "manual ausente": (
        _sem_manual,
        f"manuais > tres-passione > {MANUAL_PASSIONE}",
        "arquivo do manual não encontrado",
    ),
    "metadados do manual ausentes": (
        _sem_metadados_do_manual,
        f"manuais > tres-passione > {MANUAL_PASSIONE}",
        "metadados ausentes (manual-exemplo.md.metadata.json)",
    ),
    "título com mais de 40": (
        _titulo_longo,
        "problemas.json > problema 3 > titulo",
        "no máximo 40 caracteres (tem 41)",
    ),
    "JSON inválido": (_json_quebrado, "catalogo.json", "JSON inválido"),
}


@pytest.mark.parametrize("caso", CASOS_INVALIDOS)
def test_seed_invalido_nao_escreve_nada_e_informa_item_e_motivo(aws, seed_copia, caso):
    mutar, item_esperado, motivo_esperado = CASOS_INVALIDOS[caso]
    mutar(seed_copia)

    with pytest.raises(cs.ErroCarga) as info:
        _carregar(aws, seed_copia)

    achadas = [f for f in info.value.falhas if f.item == item_esperado]
    assert achadas, f"item {item_esperado!r} não reportado: {info.value}"
    assert any(motivo_esperado in f.motivo for f in achadas), info.value
    assert f"- {item_esperado}: " in str(info.value)  # a mensagem traz item e motivo
    assert _estado(aws) == ({"modelos": [], "problemas": [], "instrucoes": []}, {})


def test_todas_as_falhas_de_validacao_saem_juntas_e_nada_e_escrito(aws, seed_copia):
    for mutar, _, _ in CASOS_INVALIDOS.values():
        if mutar is not _json_quebrado:  # o JSON quebrado esconderia o catálogo dos demais
            mutar(seed_copia)

    with pytest.raises(cs.ErroCarga) as info:
        _carregar(aws, seed_copia)

    itens = {f.item for f in info.value.falhas}
    esperados = {i for f, i, _ in CASOS_INVALIDOS.values() if f is not _json_quebrado}
    assert esperados <= itens
    assert _estado(aws) == ({"modelos": [], "problemas": [], "instrucoes": []}, {})


def test_bucket_nao_informado_nao_escreve_nada(aws):
    dynamodb, s3 = aws
    with pytest.raises(cs.ErroCarga) as info:
        cs.carregar(cs.SEED_PADRAO, dynamodb=dynamodb, s3=s3, bucket_manuais=None, prefixo=PREFIXO)
    assert [f.item for f in info.value.falhas] == ["configuração"]
    assert _estado(aws) == ({"modelos": [], "problemas": [], "instrucoes": []}, {})


# --------------------------------------------------------------------------------------------
# Falha no S3 (Req 20.7)
# --------------------------------------------------------------------------------------------


def _s3_que_falha_em(s3, chave: str, *, tambem_no_delete: bool = False) -> _Proxy:
    put_real = s3.put_object

    def put(**kw):
        if kw["Key"] == chave:
            raise RuntimeError(f"falha injetada em {chave}")
        return put_real(**kw)

    substitutos = {"put_object": put}
    if tambem_no_delete:

        def delete(**kw):
            raise RuntimeError("falha injetada no delete")

        substitutos["delete_object"] = delete
    return _Proxy(s3, **substitutos)


def test_falha_no_s3_remove_objetos_enviados_nesta_execucao_e_preserva_os_demais(aws, seed_dois):
    dynamodb, s3 = aws
    s3.put_object(Bucket=BUCKET, Key="manuais/outro/intocado.md", Body=b"outro")
    s3.put_object(Bucket=BUCKET, Key=MANUAL_PASSIONE, Body=b"versao anterior", ContentType="text/x")
    # Ordem de envio (por modelo_id): circo (.md, .metadata.json) e depois passione (idem).
    # A falha no último objeto força desfazer os dois de circo e restaurar o .md de passione.
    proxy = _s3_que_falha_em(s3, f"{MANUAL_PASSIONE}.metadata.json")

    with pytest.raises(cs.ErroCarga) as info:
        _carregar(aws, seed_dois, s3=proxy)

    [falha] = info.value.falhas
    assert falha.item == f"manual {MANUAL_PASSIONE}.metadata.json"
    assert "falha injetada em" in falha.motivo
    final = _dump_s3(s3)
    assert set(final) == {MANUAL_PASSIONE, "manuais/outro/intocado.md"}
    assert final[MANUAL_PASSIONE] == (b"versao anterior", "text/x")  # restaurado
    assert final["manuais/outro/intocado.md"][0] == b"outro"
    # Os registros do DynamoDB já estavam completos (cada grupo é atômico).
    assert len(_dump_dynamo(dynamodb)["instrucoes"]) == 28


@pytest.mark.parametrize(
    "chave",
    [MANUAL_PASSIONE, f"{MANUAL_PASSIONE}.metadata.json", MANUAL_CIRCO],
)
def test_falha_no_s3_em_qualquer_objeto_deixa_o_bucket_como_estava(aws, seed_dois, chave):
    _, s3 = aws
    with pytest.raises(cs.ErroCarga) as info:
        _carregar(aws, seed_dois, s3=_s3_que_falha_em(s3, chave))
    assert info.value.falhas[0].item == f"manual {chave}"
    assert _dump_s3(s3) == {}


def test_nova_execucao_apos_falha_no_s3_completa_a_carga(aws, seed_dois):
    _, s3 = aws
    with pytest.raises(cs.ErroCarga):
        _carregar(aws, seed_dois, s3=_s3_que_falha_em(s3, MANUAL_CIRCO))
    _carregar(aws, seed_dois)
    assert set(_dump_s3(s3)) == CHAVES_S3_DOIS_MODELOS


def test_falha_ao_desfazer_no_s3_e_reportada_com_o_objeto(aws, seed_dois):
    _, s3 = aws
    proxy = _s3_que_falha_em(s3, f"{MANUAL_CIRCO}.metadata.json", tambem_no_delete=True)

    with pytest.raises(cs.ErroCarga) as info:
        _carregar(aws, seed_dois, s3=proxy)

    itens = [f.item for f in info.value.falhas]
    assert itens[0] == f"manual {MANUAL_CIRCO}.metadata.json"
    assert "desfazer envio de manual" in itens[1:]
    assert any(MANUAL_CIRCO in f.motivo for f in info.value.falhas[1:])


# --------------------------------------------------------------------------------------------
# Consistência com infra/stacks/dados_stack.py
# --------------------------------------------------------------------------------------------


def test_nomes_de_tabela_do_script_existem_na_stack():
    tabelas = _tabelas_da_stack()
    for nome in (cs.TABELA_MODELOS, cs.TABELA_PROBLEMAS, cs.TABELA_INSTRUCOES):
        assert nome in tabelas, f"tabela {nome!r} do script não existe em dados_stack.py"
    assert PREFIXO == cs.PREFIXO_TABELAS_PADRAO


def test_itens_montados_trazem_as_chaves_e_tipos_definidos_na_stack():
    seed = cs.validar(cs.SEED_PADRAO)
    tabelas = _tabelas_da_stack()
    por_tabela = {}
    for grupo in cs.montar_grupos(seed, PREFIXO):
        nome = grupo.tabela.removeprefix(f"{PREFIXO}-")
        assert grupo.tabela == f"{PREFIXO}-{nome}" and nome in tabelas
        spec = tabelas[nome]
        for item in grupo.itens:
            tipo_pk = int if spec["pk_tipo"] == "N" else str
            assert type(item[spec["pk"]]) is tipo_pk, (nome, spec["pk"])
            if spec["sk"]:
                assert isinstance(item[spec["sk"]], str), (nome, spec["sk"])
        por_tabela.setdefault(nome, []).extend(grupo.itens)
    assert set(por_tabela) == {"modelos", "problemas", "instrucoes"}

    # A chave de ordenação das instruções é "<problema_id>#<variante>" (design, seção 3.10).
    for item in por_tabela["instrucoes"]:
        assert re.fullmatch(r"\d+#(padrao|externo)", item["problema_variante"])
        assert item["problema_variante"] == f"{item['problema_id']}#{item['variante']}"


def test_atributos_de_chave_da_stack_para_as_tabelas_da_carga():
    # Se a stack mudar uma chave, o script (que grava ``modelo_id``, ``problema_id`` e
    # ``problema_variante``) precisa mudar junto. Este teste falha para chamar a atenção.
    tabelas = _tabelas_da_stack()
    assert tabelas["modelos"] == {"pk": "modelo_id", "sk": None, "pk_tipo": "S"}
    assert tabelas["problemas"] == {"pk": "problema_id", "sk": None, "pk_tipo": "N"}
    assert tabelas["instrucoes"] == {"pk": "modelo_id", "sk": "problema_variante", "pk_tipo": "S"}
