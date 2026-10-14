"""Stack de dados: chave KMS do cliente e tabelas DynamoDB (Req 18.2, 20.1, 14.1, 17.1).

Todas as tabelas usam cobrança sob demanda e SSE-KMS com a chave gerenciada pelo cliente.
Os índices ``gsi_ativas``, ``gsi_encerradas`` e ``gsi_fila`` são esparsos: só os itens que
possuem os atributos de chave do índice aparecem nele (a aplicação grava e remove esses
atributos conforme o ciclo de vida da Jornada e do Chamado).
"""

from dataclasses import dataclass, field

from aws_cdk import CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_kms as kms
from constructs import Construct

S = dynamodb.AttributeType.STRING
N = dynamodb.AttributeType.NUMBER


@dataclass(frozen=True)
class IndiceSpec:
    """Índice secundário global esparso."""

    nome: str
    pk: str
    sk: str


@dataclass(frozen=True)
class TabelaSpec:
    nome: str
    pk: str
    sk: str | None = None
    pk_tipo: dynamodb.AttributeType = S
    ttl: str | None = None
    indices: tuple[IndiceSpec, ...] = field(default_factory=tuple)


# Fonte única das tabelas (design.md, "Data Models").
TABELAS: tuple[TabelaSpec, ...] = (
    TabelaSpec(
        "modelos",
        pk="modelo_id",
        # Listagem do catálogo sem ``Scan`` (nenhum papel o tem): partição constante
        # ``catalogo_pk = "CATALOGO"`` (gravada pelo seed) e ordem alfabética por nome.
        indices=(IndiceSpec("gsi_catalogo", pk="catalogo_pk", sk="nome_normalizado"),),
    ),
    TabelaSpec("problemas", pk="problema_id", pk_tipo=N),  # 1 a 13
    TabelaSpec("instrucoes", pk="modelo_id", sk="problema_variante"),
    TabelaSpec(
        "jornadas",
        pk="jornada_id",
        indices=(
            # Jornadas ativas e sem Chamado (varredura de abandono, Req 17.2).
            IndiceSpec("gsi_ativas", pk="ativa_pk", sk="ultima_interacao"),
            # Jornadas encerradas, consulta por intervalo de datas (Req 17.1).
            # A chave de ordenação precisa ser um atributo de topo: ``encerrada_em``
            # espelha ``encerramento.em``.
            IndiceSpec("gsi_encerradas", pk="encerrada_pk", sk="encerrada_em"),
        ),
    ),
    TabelaSpec("eventos", pk="jornada_id", sk="ts_ulid"),
    TabelaSpec(
        "chamados",
        pk="numero",
        # Fila do Painel_CS: ordem por prioridade, horário e número (Req 14.1).
        indices=(IndiceSpec("gsi_fila", pk="fila_pk", sk="fila_sk"),),
    ),
    TabelaSpec("mensagens_chamado", pk="numero", sk="ts_ulid"),
    TabelaSpec("dados_pessoais", pk="numero"),
    TabelaSpec("acessos_pii", pk="numero", sk="ts_ulid"),
    TabelaSpec("ordens_servico", pk="os_id"),
    TabelaSpec("cache_respostas", pk="chave"),
    TabelaSpec("avaliacoes", pk="jornada_id"),
    TabelaSpec("agregados_dia", pk="dia", sk="metrica"),
    TabelaSpec("usuarios_cs", pk="usuario"),
    TabelaSpec("sessoes_cs", pk="token_hash", ttl="ttl"),
    TabelaSpec("config", pk="chave"),
)


class DadosStack(Stack):
    """Chave KMS do cliente e todas as tabelas DynamoDB do design."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        prefixo: str = "tres",
        destruir_ao_remover: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Dados de clientes: por padrão os recursos sobrevivem à remoção da stack.
        remocao = RemovalPolicy.DESTROY if destruir_ao_remover else RemovalPolicy.RETAIN

        self.chave = kms.Key(
            self,
            "ChaveDados",
            alias=f"alias/{prefixo}-dados",
            description="Chave do cliente para tabelas, buckets e filas do TRES Autoatendimento",
            enable_key_rotation=True,
            removal_policy=remocao,
        )

        self.tabelas: dict[str, dynamodb.Table] = {}
        for spec in TABELAS:
            self.tabelas[spec.nome] = self._criar_tabela(spec, prefixo, remocao)

        CfnOutput(self, "ChaveDadosArn", value=self.chave.key_arn)

    def _criar_tabela(
        self, spec: TabelaSpec, prefixo: str, remocao: RemovalPolicy
    ) -> dynamodb.Table:
        tabela = dynamodb.Table(
            self,
            f"Tabela-{spec.nome}",
            table_name=f"{prefixo}-{spec.nome}",
            partition_key=dynamodb.Attribute(name=spec.pk, type=spec.pk_tipo),
            sort_key=dynamodb.Attribute(name=spec.sk, type=S) if spec.sk else None,
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.CUSTOMER_MANAGED,
            encryption_key=self.chave,
            time_to_live_attribute=spec.ttl,
            removal_policy=remocao,
        )
        for indice in spec.indices:
            tabela.add_global_secondary_index(
                index_name=indice.nome,
                partition_key=dynamodb.Attribute(name=indice.pk, type=S),
                sort_key=dynamodb.Attribute(name=indice.sk, type=S),
                projection_type=dynamodb.ProjectionType.ALL,
            )
        return tabela
