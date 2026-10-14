"""Stack da API: Lambdas, HTTP API com throttling por rota e varredura de abandono.

Cobre os Req 18.2 e 20.1 (tudo com a chave KMS do cliente), 18.6 (dados pessoais só no papel
do endpoint de dados pessoais), 18.7 (API Gateway só alcançável pelo CloudFront), 17.12
(consumidor da fila de encerramentos) e 20.5 (nenhum segredo no código ou no template).

Funções (todas Python 3.12; o código é o de ``services/api``, com um *handler* por função):
- ``api``: roteador único das rotas ``/api/pub`` e ``/api/cs`` (timeout 28 s, 1024 MB).
- ``dados_pessoais``: mesmo código, papel separado. É a única com acesso às tabelas
  ``dados_pessoais`` e ``acessos_pii``; atende só as duas rotas que tocam em Dados_Pessoais.
- ``enriquecimento``: assíncrona, preenche resumo, sentimento e próxima ação (timeout 15 s).
- ``encerramento``: consome a fila de encerramentos (timeout menor que a visibilidade da fila).
- ``varredura``: EventBridge Scheduler a cada 5 min marca Jornadas abandonadas.

Notas de projeto:
- Sem ciclos entre stacks: esta stack só lê Dados e Armazenamento. A Borda (CloudFront) lê esta
  stack. O CORS do bucket de fotos não recebe o domínio do CloudFront por esse motivo (ver
  ``borda_stack.py``).
- O API Gateway HTTP API não tem política de recurso nem WAF. O acesso só pelo CloudFront é
  imposto por um autorizador Lambda que confere o cabeçalho ``x-origem-cloudfront`` contra um
  segredo gerado no deploy (padrão da AWS para HTTP API). O valor nunca aparece no template.
- O throttling do API Gateway é por rota e global (não por cliente). Os limites abaixo são
  pontos de partida; limite por cliente exigiria WAF (Q12, fora do MVP).
- Os caminhos de código (``services/api``) e os nomes dos *handlers* são configuráveis. Enquanto
  o código das tarefas 9 a 13 e 18 não existir, a stack sintetiza, mas a Lambda falharia ao ser
  invocada (módulo ausente).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from aws_cdk import Aws, CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_apigatewayv2 as apigw
from aws_cdk import aws_apigatewayv2_authorizers as authorizers
from aws_cdk import aws_apigatewayv2_integrations as integrations
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_scheduler as scheduler
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

from stacks.armazenamento_stack import ArmazenamentoStack
from stacks.dados_stack import DadosStack
from stacks.empacotamento import codigo_empacotado, codigo_simples

RAIZ = Path(__file__).resolve().parents[2]
CODIGO_API_PADRAO = RAIZ / "services" / "api"
CODIGO_DOMINIO_PADRAO = RAIZ / "packages" / "dominio" / "src"
CODIGO_AUTORIZADOR = RAIZ / "infra" / "lambdas" / "autorizador_origem"

# --- Premissas verificadas (iguais a ``services/agente/premissas.py``; o teste confere) -------
ARQUITETURA_PADRAO = "arm64"
API_TIMEOUT_S = 28  # Q18: abaixo do teto de 30 s do HTTP API
API_MEMORIA_MB = 1024  # Q14: hash de senha e CPU proporcional à memória
INTEGRACAO_TIMEOUT_MS = 29_000  # Q18: teto do serviço é 30 s e não é ajustável
ENRIQUECIMENTO_TIMEOUT_S = 15  # 10 s do agente + gravação (Req 10.4)
# Req 17.12: a Lambda precisa terminar antes da visibilidade da fila (10 s), senão a mensagem
# reaparece com a execução ainda em curso.
ENCERRAMENTO_TIMEOUT_S = 8
DADOS_PESSOAIS_TIMEOUT_S = 15  # gravações com teto de 10 s (Req 20.6) mais folga
VARREDURA_TIMEOUT_S = 60
AUTORIZADOR_TIMEOUT_S = 5
ACAO_IAM_INVOCAR_RUNTIME = "bedrock-agentcore:InvokeAgentRuntime"

CABECALHO_ORIGEM = "x-origem-cloudfront"
CAMPO_SEGREDO_ORIGEM = "valor"

# ARN de um AgentCore Runtime. Sem curingas: o ARN do runtime é o único recurso permitido.
_RE_ARN_RUNTIME = re.compile(
    r"^arn:aws[a-z-]*:bedrock-agentcore:[a-z0-9-]+:\d{12}:runtime/[A-Za-z0-9_-]+$"
)

# --- Handlers (configuráveis) -----------------------------------------------------------------
HANDLERS_PADRAO: Mapping[str, str] = {
    "api": "handlers.api.lambda_handler",
    "dados_pessoais": "handlers.dados_pessoais.lambda_handler",
    "enriquecimento": "handlers.enriquecimento.lambda_handler",
    "encerramento": "handlers.encerramento.lambda_handler",
    "varredura": "handlers.varredura.lambda_handler",
}

# --- Acesso às tabelas (privilégio mínimo) ----------------------------------------------------
LER = "ler"
ESCREVER = "escrever"
REMOVER = "remover"

ACOES_DYNAMODB: Mapping[str, tuple[str, ...]] = {
    LER: (
        "dynamodb:GetItem",
        "dynamodb:BatchGetItem",
        "dynamodb:Query",
        "dynamodb:ConditionCheckItem",
    ),
    ESCREVER: ("dynamodb:PutItem", "dynamodb:UpdateItem"),
    REMOVER: ("dynamodb:DeleteItem",),
}

# Sem ``Scan`` e sem ``BatchWriteItem`` em nenhum papel. As tabelas ``dados_pessoais`` e
# ``acessos_pii`` aparecem só em ``dados_pessoais`` (Req 18.6); a tabela ``modelos``,
# ``problemas`` e ``instrucoes`` são só leitura (o seed as carrega por fora da API).
ACESSO_TABELAS: Mapping[str, Mapping[str, frozenset[str]]] = {
    "api": {
        "modelos": frozenset({LER}),
        "problemas": frozenset({LER}),
        "instrucoes": frozenset({LER}),
        "jornadas": frozenset({LER, ESCREVER}),
        "eventos": frozenset({LER, ESCREVER}),
        "chamados": frozenset({LER, ESCREVER}),
        "mensagens_chamado": frozenset({LER, ESCREVER}),
        "ordens_servico": frozenset({LER, ESCREVER}),
        "cache_respostas": frozenset({LER, ESCREVER, REMOVER}),
        "avaliacoes": frozenset({LER, ESCREVER}),
        "agregados_dia": frozenset({LER, ESCREVER}),
        "usuarios_cs": frozenset({LER, ESCREVER}),
        "sessoes_cs": frozenset({LER, ESCREVER, REMOVER}),
        "config": frozenset({LER, ESCREVER}),
    },
    "dados_pessoais": {
        "dados_pessoais": frozenset({LER, ESCREVER}),
        # Primeiro grava o acesso, depois responde (Req 18.6, 18.9): só escrita.
        "acessos_pii": frozenset({ESCREVER}),
        "chamados": frozenset({LER}),
        "usuarios_cs": frozenset({LER}),
        "sessoes_cs": frozenset({LER, ESCREVER}),
    },
    "enriquecimento": {
        "jornadas": frozenset({LER}),
        "eventos": frozenset({LER, ESCREVER}),
        "mensagens_chamado": frozenset({LER}),
        "chamados": frozenset({LER, ESCREVER}),
        "config": frozenset({LER}),
    },
    "encerramento": {
        "jornadas": frozenset({LER, ESCREVER}),
        "eventos": frozenset({LER}),
        "chamados": frozenset({LER}),
    },
    "varredura": {
        "jornadas": frozenset({LER, ESCREVER}),
        "eventos": frozenset({ESCREVER}),
    },
}
TABELAS_DO_ENDPOINT_DE_DADOS_PESSOAIS = frozenset({"dados_pessoais", "acessos_pii"})


# --- Rotas e throttling -----------------------------------------------------------------------
@dataclass(frozen=True)
class Limite:
    taxa: int  # requisições por segundo, estável
    rajada: int  # pico permitido


LIMITE_PADRAO = Limite(taxa=50, rajada=100)


@dataclass(frozen=True)
class Rota:
    metodo: str
    caminho: str
    destino: str = "api"  # "api" ou "dados_pessoais"
    limite: Limite = LIMITE_PADRAO

    @property
    def chave(self) -> str:
        return f"{self.metodo} {self.caminho}"


_PUB = "/api/pub"
_CS = "/api/cs"
_LOGIN = Limite(taxa=5, rajada=10)  # força bruta; o bloqueio por usuário vem do Req 13.8
_IA = Limite(taxa=20, rajada=40)  # cada chamada pode custar tokens (Req 7.4)
_SENSIVEL = Limite(taxa=10, rajada=20)  # Dados_Pessoais, anexos e sugestão da IA
_ACOMPANHAMENTO = Limite(taxa=20, rajada=40)  # número do Chamado: reduz tentativa de adivinhação

# Contrato HTTP do design ("Components and Interfaces", seção 2). Rota fora da lista não chega
# à Lambda: o API Gateway responde 404. Ao criar uma rota nova, acrescente-a aqui.
ROTAS_PADRAO: tuple[Rota, ...] = (
    # Públicas
    Rota("GET", f"{_PUB}/saude"),
    Rota("GET", f"{_PUB}/modelos"),
    Rota("GET", f"{_PUB}/modelos/{{modelo_id}}"),
    Rota("POST", f"{_PUB}/jornadas"),
    Rota("GET", f"{_PUB}/jornadas/{{id}}"),
    Rota("PUT", f"{_PUB}/jornadas/{{id}}/modelo"),
    Rota("GET", f"{_PUB}/jornadas/{{id}}/instrucao"),
    Rota("POST", f"{_PUB}/jornadas/{{id}}/vazamento"),
    Rota("POST", f"{_PUB}/jornadas/{{id}}/seletor/resolver"),
    Rota("POST", f"{_PUB}/jornadas/{{id}}/eventos"),
    Rota("POST", f"{_PUB}/jornadas/{{id}}/resolucao"),
    Rota("POST", f"{_PUB}/jornadas/{{id}}/mensagens", limite=_IA),
    Rota("POST", f"{_PUB}/jornadas/{{id}}/solucoes/{{sid}}/resposta"),
    Rota("POST", f"{_PUB}/jornadas/{{id}}/escalar"),
    Rota("POST", f"{_PUB}/jornadas/{{id}}/avaliacao"),
    Rota("POST", f"{_PUB}/chamados/{{numero}}/contato", "dados_pessoais", _SENSIVEL),
    Rota("POST", f"{_PUB}/chamados/{{numero}}/anexos", limite=_SENSIVEL),
    Rota("POST", f"{_PUB}/chamados/{{numero}}/anexos/{{anexo_id}}/confirmacao", limite=_SENSIVEL),
    Rota("POST", f"{_PUB}/chamados/{{numero}}/avaliacao"),
    Rota("GET", f"{_PUB}/chamados/{{numero}}", limite=_ACOMPANHAMENTO),
    Rota("POST", f"{_PUB}/chamados/{{numero}}/mensagens"),
    # Painel_CS (autenticadas)
    Rota("POST", f"{_CS}/login", limite=_LOGIN),
    Rota("POST", f"{_CS}/logout"),
    Rota("GET", f"{_CS}/sessao"),
    Rota("GET", f"{_CS}/fila"),
    Rota("GET", f"{_CS}/chamados/{{numero}}"),
    Rota("POST", f"{_CS}/chamados/{{numero}}/assumir"),
    Rota("GET", f"{_CS}/chamados/{{numero}}/dados-pessoais", "dados_pessoais", _SENSIVEL),
    Rota("GET", f"{_CS}/chamados/{{numero}}/anexos/{{indice}}", limite=_SENSIVEL),
    Rota("GET", f"{_CS}/chamados/{{numero}}/sugestao", limite=_SENSIVEL),
    Rota("POST", f"{_CS}/chamados/{{numero}}/mensagens"),
    Rota("POST", f"{_CS}/chamados/{{numero}}/ordem-servico"),
    Rota("POST", f"{_CS}/chamados/{{numero}}/agendamento"),
    Rota("POST", f"{_CS}/chamados/{{numero}}/encerrar"),
    Rota("POST", f"{_CS}/cache"),
    Rota("GET", f"{_CS}/metricas"),
    Rota("PUT", f"{_CS}/config"),
)


def validar_arn_runtime(arn: str) -> str:
    """Aceita só o ARN completo de um runtime do AgentCore (nada de curingas)."""
    if not _RE_ARN_RUNTIME.match(arn):
        raise ValueError(
            "agente_runtime_arn inválido: esperado "
            "arn:aws:bedrock-agentcore:<região>:<conta>:runtime/<nome>, sem curingas"
        )
    return arn


class ApiStack(Stack):
    """Lambdas, HTTP API (com autorizador de origem), fila de encerramento e varredura."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        dados: DadosStack,
        armazenamento: ArmazenamentoStack,
        prefixo: str = "tres",
        destruir_ao_remover: bool = False,
        agente_runtime_arn: str | None = None,
        arquitetura: str = ARQUITETURA_PADRAO,
        codigo_api: Path | None = None,
        codigo_dominio: Path | None = None,
        empacotar_dependencias: bool = False,
        handlers: Mapping[str, str] | None = None,
        rotas: tuple[Rota, ...] = ROTAS_PADRAO,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._prefixo = prefixo
        self._dados = dados
        self._armazenamento = armazenamento
        self._arquitetura = (
            lambda_.Architecture.ARM_64 if arquitetura == "arm64" else lambda_.Architecture.X86_64
        )
        self._handlers = {**HANDLERS_PADRAO, **(handlers or {})}
        self._remocao = RemovalPolicy.DESTROY if destruir_ao_remover else RemovalPolicy.RETAIN
        self._runtime_arn = validar_arn_runtime(agente_runtime_arn) if agente_runtime_arn else None

        raiz_api = Path(codigo_api) if codigo_api else CODIGO_API_PADRAO
        raiz_dominio = Path(codigo_dominio) if codigo_dominio else CODIGO_DOMINIO_PADRAO
        self._codigo = (
            codigo_empacotado([raiz_api, raiz_dominio], arquitetura)
            if empacotar_dependencias
            else codigo_simples(raiz_api)
        )

        # --- Segredo de origem (CloudFront -> API Gateway), gerado no deploy (Req 20.5) ------
        self.nome_segredo_origem = f"{prefixo}/segredo-origem"
        self.segredo_origem = secretsmanager.Secret(
            self,
            "SegredoOrigem",
            secret_name=self.nome_segredo_origem,
            description="Valor do cabeçalho x-origem-cloudfront aceito pelo API Gateway",
            encryption_key=dados.chave,
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"descricao": "origem"}',
                generate_string_key=CAMPO_SEGREDO_ORIGEM,
                password_length=64,
                exclude_punctuation=True,
            ),
            removal_policy=self._remocao,
        )

        # --- Lambdas -------------------------------------------------------------------------
        self.funcao_api = self._criar_funcao(
            "Api",
            "api",
            descricao="Roteador único das rotas /api/pub e /api/cs",
            memoria_mb=API_MEMORIA_MB,
            timeout_s=API_TIMEOUT_S,
        )
        self.funcao_dados_pessoais = self._criar_funcao(
            "DadosPessoais",
            "dados_pessoais",
            descricao="Endpoints que tocam em Dados_Pessoais (contato e consulta do Atendente)",
            memoria_mb=512,
            timeout_s=DADOS_PESSOAIS_TIMEOUT_S,
        )
        self.funcao_enriquecimento = self._criar_funcao(
            "Enriquecimento",
            "enriquecimento",
            descricao="Preenche resumo, sentimento e próxima ação do Pacote_Handoff",
            memoria_mb=512,
            timeout_s=ENRIQUECIMENTO_TIMEOUT_S,
        )
        self.funcao_encerramento = self._criar_funcao(
            "Encerramento",
            "encerramento",
            descricao="Registra o encerramento da Jornada a partir da fila (Req 17.12)",
            memoria_mb=256,
            timeout_s=ENCERRAMENTO_TIMEOUT_S,
        )
        self.funcao_varredura = self._criar_funcao(
            "Varredura",
            "varredura",
            descricao="Marca Jornadas abandonadas (30 min sem interação, sem Chamado)",
            memoria_mb=256,
            timeout_s=VARREDURA_TIMEOUT_S,
        )
        self._configurar_api()
        self._configurar_enriquecimento()
        self._configurar_encerramento()
        self._configurar_varredura()
        self._configurar_agente()

        # --- HTTP API ------------------------------------------------------------------------
        self.funcao_autorizador = self._criar_autorizador()
        self.api_http = self._criar_api_http(rotas)
        # Domínio sem esquema, para ser a origem do CloudFront.
        self.dominio_api = f"{self.api_http.api_id}.execute-api.{Aws.REGION}.{Aws.URL_SUFFIX}"

        CfnOutput(self, "ApiHttpId", value=self.api_http.api_id)
        CfnOutput(self, "SegredoOrigemNome", value=self.nome_segredo_origem)

    # ------------------------------------------------------------------------------------------
    # Funções e papéis
    # ------------------------------------------------------------------------------------------
    def _criar_funcao(
        self,
        id_: str,
        nome: str,
        *,
        descricao: str,
        memoria_mb: int,
        timeout_s: int,
    ) -> lambda_.Function:
        """Lambda com papel próprio (sem política gerenciada) e só o acesso da matriz."""
        papel = iam.Role(
            self,
            f"Role{id_}",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description=f"Papel da Lambda {nome} (privilégio mínimo)",
        )
        logs_grupo = logs.LogGroup(
            self,
            f"Logs{id_}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,  # só logs, sem PII (Req 18)
        )
        logs_grupo.grant_write(papel)

        funcao = lambda_.Function(
            self,
            f"Funcao{id_}",
            description=descricao,
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=self._arquitetura,
            handler=self._handlers[nome],
            code=self._codigo,
            role=papel,
            log_group=logs_grupo,
            memory_size=memoria_mb,
            timeout=Duration.seconds(timeout_s),
            environment={"TRES_PREFIXO": self._prefixo},
        )

        # Tabelas: ações agrupadas por conjunto de permissões (menos instruções por papel).
        grupos: dict[frozenset[str], list[str]] = {}
        for tabela, niveis in ACESSO_TABELAS[nome].items():
            alvo = self._dados.tabelas[tabela]
            grupos.setdefault(niveis, []).extend([alvo.table_arn, f"{alvo.table_arn}/index/*"])
            funcao.add_environment(f"TRES_TABELA_{tabela.upper()}", alvo.table_name)
        for niveis, recursos in grupos.items():
            acoes = [a for nivel in sorted(niveis) for a in ACOES_DYNAMODB[nivel]]
            papel.add_to_policy(iam.PolicyStatement(actions=acoes, resources=recursos))

        self._permitir_chave(papel)
        return funcao

    def _permitir_chave(self, papel: iam.IRole) -> None:
        """Uso da chave do cliente (tabelas, fila, segredos e fotos; Req 18.2, 20.1).

        Instrução no próprio papel, sem ``chave.grant_*``: o grant do L2 também grava na política
        da chave (stack de dados), o que cria um ciclo entre stacks. A política da chave já
        delega o acesso à conta, então a permissão do papel basta.
        """
        papel.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "kms:Decrypt",
                    "kms:Encrypt",
                    "kms:ReEncrypt*",
                    "kms:GenerateDataKey*",
                    "kms:DescribeKey",
                ],
                resources=[self._dados.chave.key_arn],
            )
        )

    @staticmethod
    def _ler_segredo(papel: iam.IRole, segredo: secretsmanager.ISecret) -> None:
        papel.add_to_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"],
                resources=[segredo.secret_arn],
            )
        )

    def _configurar_api(self) -> None:
        arm = self._armazenamento
        funcao = self.funcao_api
        # Fotos por URL pré-assinada: a Lambda assina com o próprio papel (Req 12.7).
        papel = funcao.role
        papel.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
                resources=[arm.bucket_fotos.arn_for_objects("*")],
            )
        )
        papel.add_to_policy(
            iam.PolicyStatement(
                actions=["sqs:SendMessage", "sqs:GetQueueAttributes"],
                resources=[arm.fila_encerramentos.queue_arn],
            )
        )
        # A falha de registro de encerramento aparece ao Gestor pela contagem da DLQ (Req 17.12).
        papel.add_to_policy(
            iam.PolicyStatement(
                actions=["sqs:GetQueueAttributes"],
                resources=[arm.dlq_encerramentos.queue_arn],
            )
        )
        self._ler_segredo(papel, arm.segredo_app)
        arm.parametro_modelo_llm.grant_read(papel)
        arm.parametro_prefixo_manuais.grant_read(papel)
        funcao.add_environment("TRES_FILA_ENCERRAMENTOS_URL", arm.fila_encerramentos.queue_url)
        funcao.add_environment("TRES_DLQ_ENCERRAMENTOS_URL", arm.dlq_encerramentos.queue_url)
        funcao.add_environment("TRES_BUCKET_FOTOS", arm.bucket_fotos.bucket_name)
        funcao.add_environment("TRES_SEGREDO_APP_ARN", arm.segredo_app.secret_arn)
        funcao.add_environment("TRES_PARAM_MODELO_LLM", arm.parametro_modelo_llm.parameter_name)
        funcao.add_environment(
            "TRES_PARAM_PREFIXO_MANUAIS", arm.parametro_prefixo_manuais.parameter_name
        )

        # Rotas de Dados_Pessoais rodam na função separada, que não tem o papel acima.
        pessoais = self.funcao_dados_pessoais
        self._ler_segredo(pessoais.role, arm.segredo_app)
        pessoais.add_environment("TRES_SEGREDO_APP_ARN", arm.segredo_app.secret_arn)

    def _configurar_enriquecimento(self) -> None:
        # A API dispara a função de forma assíncrona; o Pacote já nasce com valores provisórios
        # (Req 10.2), então não há por que repetir a invocação em caso de erro.
        lambda_.EventInvokeConfig(
            self,
            "EnriquecimentoAssincrono",
            function=self.funcao_enriquecimento,
            retry_attempts=0,
            max_event_age=Duration.seconds(60),
        )
        self.funcao_enriquecimento.grant_invoke(self.funcao_api.role)
        self.funcao_api.add_environment(
            "TRES_FUNCAO_ENRIQUECIMENTO", self.funcao_enriquecimento.function_name
        )

    def _configurar_encerramento(self) -> None:
        # Uma mensagem por execução e retorno parcial: só a que falhar volta para a fila,
        # e depois da 3ª tentativa vai para a DLQ (Req 17.12).
        # Mapeamento criado direto (sem ``SqsEventSource``), como em ``_permitir_chave``: o
        # grant do L2 sobre a fila criptografada mexeria na política da chave.
        fila = self._armazenamento.fila_encerramentos
        self.funcao_encerramento.role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "sqs:ReceiveMessage",
                    "sqs:DeleteMessage",
                    "sqs:GetQueueAttributes",
                    "sqs:ChangeMessageVisibility",
                ],
                resources=[fila.queue_arn],
            )
        )
        self.mapeamento_encerramento = lambda_.EventSourceMapping(
            self,
            "MapeamentoEncerramento",
            target=self.funcao_encerramento,
            event_source_arn=fila.queue_arn,
            batch_size=1,
            max_concurrency=5,
            report_batch_item_failures=True,
        )
        self.mapeamento_encerramento.node.add_dependency(self.funcao_encerramento.role)

    def _configurar_varredura(self) -> None:
        papel_agenda = iam.Role(
            self,
            "RoleAgendaVarredura",
            assumed_by=iam.ServicePrincipal(
                "scheduler.amazonaws.com",
                conditions={"StringEquals": {"aws:SourceAccount": Aws.ACCOUNT_ID}},
            ),
            description="Permite ao EventBridge Scheduler invocar só a varredura de abandono",
        )
        self.funcao_varredura.grant_invoke(papel_agenda)
        self.agenda_varredura = scheduler.CfnSchedule(
            self,
            "AgendaVarredura",
            name=f"{self._prefixo}-varredura-abandono",
            description="Varredura de Jornadas abandonadas a cada 5 minutos (Req 17.2)",
            schedule_expression="rate(5 minutes)",
            flexible_time_window=scheduler.CfnSchedule.FlexibleTimeWindowProperty(mode="OFF"),
            state="ENABLED",
            target=scheduler.CfnSchedule.TargetProperty(
                arn=self.funcao_varredura.function_arn,
                role_arn=papel_agenda.role_arn,
                input='{"origem": "scheduler"}',
                retry_policy=scheduler.CfnSchedule.RetryPolicyProperty(
                    maximum_retry_attempts=1,
                    maximum_event_age_in_seconds=300,
                ),
            ),
        )

    def _configurar_agente(self) -> None:
        """Permissão de invocar o AgentCore Runtime, restrita ao ARN informado (Q13).

        O runtime só existe na tarefa 17.4. Sem ARN, nenhuma permissão é concedida (nunca ``*``).
        """
        if not self._runtime_arn:
            return
        recursos = [self._runtime_arn, f"{self._runtime_arn}/runtime-endpoint/*"]
        for funcao in (self.funcao_api, self.funcao_enriquecimento):
            funcao.role.add_to_policy(
                iam.PolicyStatement(actions=[ACAO_IAM_INVOCAR_RUNTIME], resources=recursos)
            )
            funcao.add_environment("TRES_AGENTE_RUNTIME_ARN", self._runtime_arn)

    # ------------------------------------------------------------------------------------------
    # API Gateway
    # ------------------------------------------------------------------------------------------
    def _criar_autorizador(self) -> lambda_.Function:
        papel = iam.Role(
            self,
            "RoleAutorizador",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            description="Papel do autorizador de origem: lê só o segredo de origem",
        )
        logs_grupo = logs.LogGroup(
            self,
            "LogsAutorizador",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )
        logs_grupo.grant_write(papel)
        funcao = lambda_.Function(
            self,
            "FuncaoAutorizador",
            description="Só deixa passar requisições com o cabeçalho de origem do CloudFront",
            runtime=lambda_.Runtime.PYTHON_3_12,
            architecture=self._arquitetura,
            handler="index.handler",
            code=lambda_.Code.from_asset(str(CODIGO_AUTORIZADOR)),
            role=papel,
            log_group=logs_grupo,
            memory_size=128,
            timeout=Duration.seconds(AUTORIZADOR_TIMEOUT_S),
            environment={"TRES_SEGREDO_ORIGEM_ARN": self.segredo_origem.secret_arn},
        )
        self._ler_segredo(papel, self.segredo_origem)
        self._permitir_chave(papel)  # o segredo usa a chave do cliente
        return funcao

    def _criar_api_http(self, rotas: tuple[Rota, ...]) -> apigw.HttpApi:
        autorizador = authorizers.HttpLambdaAuthorizer(
            "AutorizadorOrigem",
            self.funcao_autorizador,
            response_types=[authorizers.HttpLambdaResponseType.SIMPLE],
            identity_source=[f"$request.header.{CABECALHO_ORIGEM}"],
            results_cache_ttl=Duration.minutes(5),
        )
        api = apigw.HttpApi(
            self,
            "ApiHttp",
            api_name=f"{self._prefixo}-api",
            description="API do TRES Autoatendimento (acessível só pelo CloudFront)",
            default_authorizer=autorizador,
        )

        destinos = {
            "api": integrations.HttpLambdaIntegration("IntegracaoApi", self.funcao_api),
            "dados_pessoais": integrations.HttpLambdaIntegration(
                "IntegracaoDadosPessoais", self.funcao_dados_pessoais
            ),
        }
        for rota in rotas:
            api.add_routes(
                path=rota.caminho,
                methods=[apigw.HttpMethod(rota.metodo)],
                integration=destinos[rota.destino],
            )

        # Q18: integração abaixo do teto de 30 s do serviço (fixo para HTTP API).
        for filho in api.node.find_all():
            if isinstance(filho, apigw.CfnIntegration):
                filho.add_property_override("TimeoutInMillis", INTEGRACAO_TIMEOUT_MS)

        # Throttling por rota (e um padrão para qualquer rota que venha a existir).
        estagio = api.default_stage.node.default_child
        estagio.default_route_settings = apigw.CfnStage.RouteSettingsProperty(
            throttling_rate_limit=LIMITE_PADRAO.taxa,
            throttling_burst_limit=LIMITE_PADRAO.rajada,
        )
        estagio.route_settings = {
            rota.chave: {
                "ThrottlingRateLimit": rota.limite.taxa,
                "ThrottlingBurstLimit": rota.limite.rajada,
            }
            for rota in rotas
        }
        return api
