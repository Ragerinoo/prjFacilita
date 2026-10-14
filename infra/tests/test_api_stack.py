"""Testes de asserção da stack da API (tarefa 8.3): Lambdas, HTTP API, IAM e varredura."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template

from stacks import api_stack, empacotamento
from stacks.api_stack import (
    ACESSO_TABELAS,
    ROTAS_PADRAO,
    TABELAS_DO_ENDPOINT_DE_DADOS_PESSOAIS,
    ApiStack,
    validar_arn_runtime,
)
from stacks.armazenamento_stack import ENCERRAMENTO_VISIBILIDADE, ArmazenamentoStack
from stacks.dados_stack import TABELAS, DadosStack

PREMISSAS = Path(__file__).resolve().parents[2] / "services" / "agente" / "premissas.py"
ARN_RUNTIME = "arn:aws:bedrock-agentcore:sa-east-1:123456789012:runtime/tres_agente-AbC123"


def _premissas():
    spec = importlib.util.spec_from_file_location("premissas", PREMISSAS)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo  # @dataclass precisa achar o módulo em sys.modules
    spec.loader.exec_module(modulo)
    return modulo


def _construir(**kwargs) -> tuple[Template, ApiStack]:
    app = cdk.App()
    dados = DadosStack(app, "teste-dados")
    armaz = ArmazenamentoStack(app, "teste-armazenamento", chave=dados.chave)
    api = ApiStack(app, "teste-api", dados=dados, armazenamento=armaz, **kwargs)
    return Template.from_stack(api), api


@pytest.fixture(scope="module")
def t() -> Template:
    return _construir()[0]


def _funcoes_por_handler(t: Template, handler: str) -> dict:
    achadas = t.find_resources("AWS::Lambda::Function", {"Properties": {"Handler": handler}})
    assert len(achadas) == 1, handler
    return next(iter(achadas.values()))["Properties"]


def _politicas_por_papel(t: Template) -> dict[str, list[dict]]:
    """Instruções de política agrupadas pelo id lógico do papel (prefixo ``Role...``)."""
    por_papel: dict[str, list[dict]] = {}
    for pol in t.find_resources("AWS::IAM::Policy").values():
        for papel in pol["Properties"]["Roles"]:
            por_papel.setdefault(papel["Ref"], []).extend(
                pol["Properties"]["PolicyDocument"]["Statement"]
            )
    return por_papel


def _statements_do_papel(t: Template, prefixo_logico: str) -> list[dict]:
    achados = [v for k, v in _politicas_por_papel(t).items() if k.startswith(prefixo_logico)]
    assert len(achados) == 1, prefixo_logico
    return achados[0]


def _acoes(st: dict) -> list[str]:
    return [st["Action"]] if isinstance(st["Action"], str) else list(st["Action"])


# --- Lambdas e premissas ----------------------------------------------------------------------
def test_lambdas_python312_arm64_com_timeouts_e_memoria_das_premissas(t: Template) -> None:
    p = _premissas()
    handlers = api_stack.HANDLERS_PADRAO
    api = _funcoes_por_handler(t, handlers["api"])
    assert api["Timeout"] == p.LAMBDA_API_TIMEOUT_S == api_stack.API_TIMEOUT_S == 28
    assert api["MemorySize"] == p.LAMBDA_API_MEMORIA_MB >= 1024
    enr = _funcoes_por_handler(t, handlers["enriquecimento"])
    assert enr["Timeout"] == p.LAMBDA_ENRIQUECIMENTO_TIMEOUT_S == 15
    enc = _funcoes_por_handler(t, handlers["encerramento"])
    assert enc["Timeout"] <= ENCERRAMENTO_VISIBILIDADE.to_seconds()
    for h in handlers.values():
        f = _funcoes_por_handler(t, h)
        assert f["Runtime"] == "python3.12"
        assert f["Architectures"] == [p.LAMBDA_ARQUITETURA_PADRAO] == ["arm64"]
    assert api_stack.ARQUITETURA_PADRAO == p.LAMBDA_ARQUITETURA_PADRAO
    assert api_stack.INTEGRACAO_TIMEOUT_MS == p.API_GATEWAY_INTEGRACAO_TIMEOUT_MS
    assert api_stack.ENCERRAMENTO_TIMEOUT_S <= p.GRAVACAO_TIMEOUT_TOTAL_S
    assert api_stack.ACAO_IAM_INVOCAR_RUNTIME == p.ACAO_IAM_INVOCAR_RUNTIME


def test_versoes_do_argon2_empacotadas_sao_as_das_premissas() -> None:
    p = _premissas()
    assert empacotamento.ARGON2_CFFI_VERSAO == p.ARGON2_CFFI_VERSAO
    assert empacotamento.ARGON2_CFFI_BINDINGS_VERSAO == p.ARGON2_CFFI_BINDINGS_VERSAO
    assert empacotamento.PLATAFORMAS_PIP == p.LAMBDA_PLATAFORMAS_PIP
    comando = empacotamento.comando_pip("/saida", "arm64")
    assert "--only-binary=:all:" in comando
    assert comando[comando.index("--platform") + 1] == "manylinux2014_aarch64"
    assert comando[comando.index("--python-version") + 1] == "3.12"
    assert "argon2-cffi==25.1.0" in comando
    assert "argon2-cffi-bindings==21.2.0" in comando


def test_empacotador_copia_api_e_dominio_sem_testes(tmp_path: Path) -> None:
    api = tmp_path / "api"
    dominio = tmp_path / "dominio_src"
    (api / "tests").mkdir(parents=True)
    (api / "handlers").mkdir()
    (api / "handlers" / "api.py").write_text("x = 1\n")
    (api / "tests" / "test_x.py").write_text("")
    (api / "pyproject.toml").write_text("")
    (api / "__pycache__").mkdir()
    (api / "__pycache__" / "m.cpython-312.pyc").write_text("")
    (dominio / "dominio").mkdir(parents=True)
    (dominio / "dominio" / "__init__.py").write_text("")
    saida = tmp_path / "saida"
    empacotamento.EmpacotadorLocal([api, dominio], "arm64").copiar_fontes(saida)
    copiados = sorted(str(p.relative_to(saida)) for p in saida.rglob("*") if p.is_file())
    assert copiados == ["dominio/__init__.py", "handlers/api.py"]


def test_handlers_sao_configuraveis() -> None:
    template, _ = _construir(handlers={"api": "meu_modulo.entrada"})
    template.has_resource_properties("AWS::Lambda::Function", {"Handler": "meu_modulo.entrada"})


# --- Varredura de abandono --------------------------------------------------------------------
def test_varredura_agendada_a_cada_5_minutos_e_papel_do_scheduler_restrito(t: Template) -> None:
    t.has_resource_properties(
        "AWS::Scheduler::Schedule",
        {
            "ScheduleExpression": "rate(5 minutes)",
            "State": "ENABLED",
            "FlexibleTimeWindow": {"Mode": "OFF"},
            "Target": Match.object_like({"Arn": Match.any_value(), "RoleArn": Match.any_value()}),
        },
    )
    t.has_resource_properties(
        "AWS::IAM::Role",
        {
            "AssumeRolePolicyDocument": {
                "Statement": [
                    Match.object_like(
                        {
                            "Principal": {"Service": "scheduler.amazonaws.com"},
                            "Condition": {"StringEquals": {"aws:SourceAccount": Match.any_value()}},
                        }
                    )
                ]
            }
        },
    )
    politicas = _politicas_por_papel(t)
    agenda = next(v for k, v in politicas.items() if k.startswith("RoleAgendaVarredura"))
    # Só pode invocar a função de varredura.
    arns = json.dumps([st["Resource"] for st in agenda])
    assert "FuncaoVarredura" in arns
    assert all(_acoes(st) == ["lambda:InvokeFunction"] for st in agenda)


# --- Fila de encerramentos (Req 17.12) --------------------------------------------------------
def test_consumidor_da_fila_processa_uma_mensagem_por_vez_com_falha_parcial(t: Template) -> None:
    t.has_resource_properties(
        "AWS::Lambda::EventSourceMapping",
        {
            "BatchSize": 1,
            "FunctionResponseTypes": ["ReportBatchItemFailures"],
            "EventSourceArn": Match.any_value(),
            "ScalingConfig": {"MaximumConcurrency": 5},
        },
    )
    st = _statements_do_papel(t, "RoleEncerramento")
    sqs = [s for s in st if any(a.startswith("sqs:") for a in _acoes(s))]
    assert len(sqs) == 1
    assert "sqs:SendMessage" not in _acoes(sqs[0])


def test_api_envia_para_a_fila_e_le_atributos_da_dlq_sem_receber_mensagens(t: Template) -> None:
    st = _statements_do_papel(t, "RoleApi")
    acoes = [a for s in st for a in _acoes(s)]
    assert "sqs:SendMessage" in acoes
    assert "sqs:GetQueueAttributes" in acoes
    assert "sqs:ReceiveMessage" not in acoes and "sqs:DeleteMessage" not in acoes


# --- IAM de privilégio mínimo -----------------------------------------------------------------
def test_dados_pessoais_so_no_papel_do_endpoint_de_dados_pessoais(t: Template) -> None:
    # Id lógico da tabela no template (o nome vem do CDK: ``Tabela-<nome>`` sem símbolos).
    marcas = {n: "Tabela" + n.replace("_", "") for n in TABELAS_DO_ENDPOINT_DE_DADOS_PESSOAIS}
    assert marcas == {"dados_pessoais": "Tabeladadospessoais", "acessos_pii": "Tabelaacessospii"}
    for papel, statements in _politicas_por_papel(t).items():
        texto = json.dumps(statements)
        for tabela, marca in marcas.items():
            if papel.startswith("RoleDadosPessoais"):
                assert marca in texto, (papel, tabela)
            else:
                assert marca not in texto, (papel, tabela)
    # A matriz declarada diz o mesmo.
    for funcao, tabelas in ACESSO_TABELAS.items():
        tocam = TABELAS_DO_ENDPOINT_DE_DADOS_PESSOAIS & set(tabelas)
        assert bool(tocam) == (funcao == "dados_pessoais")
    # A função de dados pessoais só grava o acesso (não lê) e não remove nada.
    assert ACESSO_TABELAS["dados_pessoais"]["acessos_pii"] == frozenset({api_stack.ESCREVER})
    assert api_stack.REMOVER not in ACESSO_TABELAS["dados_pessoais"]["dados_pessoais"]


def test_matriz_usa_so_tabelas_existentes() -> None:
    existentes = {spec.nome for spec in TABELAS}
    for tabelas in ACESSO_TABELAS.values():
        assert set(tabelas) <= existentes


def test_nenhum_papel_com_curinga_scan_ou_politica_gerenciada(t: Template) -> None:
    for papel, statements in _politicas_por_papel(t).items():
        for st in statements:
            assert st["Effect"] == "Allow"
            assert st["Resource"] != "*", papel
            acoes = _acoes(st)
            assert "*" not in acoes, papel
            assert not any(a.endswith(":*") for a in acoes), papel
            assert "dynamodb:Scan" not in acoes, papel
            assert "dynamodb:BatchWriteItem" not in acoes, papel
    for papel in t.find_resources("AWS::IAM::Role").values():
        assert "ManagedPolicyArns" not in papel["Properties"]


def test_cada_funcao_tem_papel_proprio(t: Template) -> None:
    papeis = t.find_resources("AWS::Lambda::Function")
    refs = [f["Properties"]["Role"]["Fn::GetAtt"][0] for f in papeis.values()]
    assert len(refs) == len(set(refs)) == 6  # 5 funções de negócio + autorizador


def test_sem_arn_do_agente_nao_ha_permissao_nem_variavel(t: Template) -> None:
    assert "bedrock" not in json.dumps(t.to_json()).lower()


def test_invocar_runtime_restrito_ao_arn_informado_nas_funcoes_que_chamam_o_agente() -> None:
    template, _ = _construir(agente_runtime_arn=ARN_RUNTIME)
    com_permissao = []
    for papel, statements in _politicas_por_papel(template).items():
        for st in statements:
            if "bedrock-agentcore:InvokeAgentRuntime" in _acoes(st):
                assert st["Resource"] == [ARN_RUNTIME, f"{ARN_RUNTIME}/runtime-endpoint/*"]
                assert _acoes(st) == ["bedrock-agentcore:InvokeAgentRuntime"]
                com_permissao.append(papel)
    assert len(com_permissao) == 2
    assert any(p.startswith("RoleApi") for p in com_permissao)
    assert any(p.startswith("RoleEnriquecimento") for p in com_permissao)
    envs = [
        f["Properties"]["Environment"]["Variables"]
        for f in template.find_resources("AWS::Lambda::Function").values()
        if "TRES_AGENTE_RUNTIME_ARN" in f["Properties"].get("Environment", {}).get("Variables", {})
    ]
    assert len(envs) == 2


@pytest.mark.parametrize(
    "arn",
    [
        "*",
        "arn:aws:bedrock-agentcore:sa-east-1:123456789012:runtime/*",
        "arn:aws:bedrock-agentcore:*:*:runtime/x",
        "arn:aws:bedrock-agentcore:sa-east-1:123456789012:runtime/a/runtime-endpoint/DEFAULT",
        "",
    ],
)
def test_arn_do_runtime_com_curinga_ou_malformado_e_rejeitado(arn: str) -> None:
    with pytest.raises(ValueError):
        validar_arn_runtime(arn)
    if arn:
        with pytest.raises(ValueError):
            _construir(agente_runtime_arn=arn)


def test_arn_valido_do_runtime_e_aceito() -> None:
    assert validar_arn_runtime(ARN_RUNTIME) == ARN_RUNTIME


def test_variaveis_de_ambiente_sem_valores_secretos(t: Template) -> None:
    for f in t.find_resources("AWS::Lambda::Function").values():
        for nome, valor in f["Properties"].get("Environment", {}).get("Variables", {}).items():
            # Só nomes, ARNs e URLs: o segredo é lido em tempo de execução (Req 20.5).
            assert "SECRET" not in nome.upper() or nome.endswith("_ARN"), nome
            assert "{{resolve" not in json.dumps(valor)


# --- HTTP API ---------------------------------------------------------------------------------
def test_toda_rota_tem_throttling_proprio_e_autorizador_de_origem(t: Template) -> None:
    rotas = t.find_resources("AWS::ApiGatewayV2::Route")
    chaves = {r["Properties"]["RouteKey"] for r in rotas.values()}
    assert chaves == {r.chave for r in ROTAS_PADRAO}
    for r in rotas.values():
        assert r["Properties"]["AuthorizationType"] == "CUSTOM"
        assert "AuthorizerId" in r["Properties"]
    estagio = next(iter(t.find_resources("AWS::ApiGatewayV2::Stage").values()))["Properties"]
    assert set(estagio["RouteSettings"]) == chaves
    for cfg in estagio["RouteSettings"].values():
        assert (
            cfg["ThrottlingRateLimit"] > 0
            and cfg["ThrottlingBurstLimit"] >= cfg["ThrottlingRateLimit"]
        )
    assert estagio["DefaultRouteSettings"]["ThrottlingRateLimit"] > 0
    # Rotas sensíveis têm limite mais baixo que o padrão.
    login = estagio["RouteSettings"]["POST /api/cs/login"]["ThrottlingRateLimit"]
    ia = estagio["RouteSettings"]["POST /api/pub/jornadas/{id}/mensagens"]["ThrottlingRateLimit"]
    assert login < ia < api_stack.LIMITE_PADRAO.taxa


def test_integracao_abaixo_do_teto_de_30s_do_api_gateway(t: Template) -> None:
    integracoes = t.find_resources("AWS::ApiGatewayV2::Integration")
    assert len(integracoes) == 2  # api e dados_pessoais
    for i in integracoes.values():
        assert i["Properties"]["TimeoutInMillis"] == 29_000 < 30_000
        assert i["Properties"]["PayloadFormatVersion"] == "2.0"


def test_rotas_de_dados_pessoais_apontam_para_a_funcao_separada(t: Template) -> None:
    rotas = t.find_resources("AWS::ApiGatewayV2::Route")
    integracoes = t.find_resources("AWS::ApiGatewayV2::Integration")
    por_id = {k: json.dumps(v["Properties"]["IntegrationUri"]) for k, v in integracoes.items()}
    for r in rotas.values():
        alvo = r["Properties"]["Target"]["Fn::Join"][1][1]["Ref"]
        uri = por_id[alvo]
        eh_pessoal = r["Properties"]["RouteKey"] in {
            "POST /api/pub/chamados/{numero}/contato",
            "GET /api/cs/chamados/{numero}/dados-pessoais",
        }
        assert ("FuncaoDadosPessoais" in uri) == eh_pessoal, r["Properties"]["RouteKey"]
    assert {r.chave for r in ROTAS_PADRAO if r.destino == "dados_pessoais"} == {
        "POST /api/pub/chamados/{numero}/contato",
        "GET /api/cs/chamados/{numero}/dados-pessoais",
    }


def test_autorizador_simples_com_cabecalho_de_origem_e_segredo_gerado(t: Template) -> None:
    t.has_resource_properties(
        "AWS::ApiGatewayV2::Authorizer",
        {
            "AuthorizerType": "REQUEST",
            "AuthorizerPayloadFormatVersion": "2.0",
            "EnableSimpleResponses": True,
            "IdentitySource": ["$request.header.x-origem-cloudfront"],
        },
    )
    t.has_resource_properties(
        "AWS::SecretsManager::Secret",
        {
            "Name": "tres/segredo-origem",
            "KmsKeyId": Match.any_value(),
            "GenerateSecretString": Match.object_like({"GenerateStringKey": "valor"}),
        },
    )
    for s in t.find_resources("AWS::SecretsManager::Secret").values():
        assert "SecretString" not in s["Properties"]
    papel = _statements_do_papel(t, "RoleAutorizador")
    acoes = [a for s in papel for a in _acoes(s)]
    assert "secretsmanager:GetSecretValue" in acoes
    assert not any(a.startswith("dynamodb:") for a in acoes)


def test_api_http_sem_cors_porque_site_e_api_usam_a_mesma_origem(t: Template) -> None:
    for api in t.find_resources("AWS::ApiGatewayV2::Api").values():
        assert "CorsConfiguration" not in api["Properties"]


def test_dominio_da_api_e_exposto_sem_esquema() -> None:
    _, stack = _construir()
    resolvido = json.dumps(cdk.Stack.of(stack).resolve(stack.dominio_api))
    assert "execute-api" in resolvido and "https://" not in resolvido
