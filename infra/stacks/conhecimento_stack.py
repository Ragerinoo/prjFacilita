"""Stack da Base_Conhecimento: Bedrock Knowledge Base sobre S3 Vectors (Req 6.2, 6.3, 20.2, 20.3).

O que a stack cria (decisões de ``services/agente/premissas.py``, tarefa 17.1):

* Vector bucket + índice do S3 Vectors: ``float32``, 1024 dimensões, métrica cosseno (Cohere
  Embed Multilingual v3). As chaves ``AMAZON_BEDROCK_TEXT`` e ``AMAZON_BEDROCK_METADATA`` são
  *não filtráveis*: o Bedrock guarda nelas o texto do trecho e a cópia dos metadados, e sem isso
  o limite de metadados filtráveis do vetor estoura. ``modelo_id``, ``manual`` e ``secao``
  continuam filtráveis (o filtro por ``modelo_id`` do Req 6.2 depende disso).
* Knowledge Base (tipo VECTOR) com ``S3_VECTORS`` e o modelo de embeddings.
* Data source S3 lendo SÓ o prefixo das seções (``secoes/``) do bucket de manuais, com chunking
  ``FIXED_SIZE`` (300 tokens, 20 % de sobreposição). Nunca hierárquico (estoura o limite de
  metadados do S3 Vectors) e sem busca híbrida (não existe nesse vector store).
* Papel de serviço do Bedrock com privilégio mínimo: ler o prefixo, ``kms:Decrypt`` na chave do
  cliente (só via S3), invocar o modelo de embeddings e acessar o índice (e só ele).

Por que um prefixo ``secoes/`` separado de ``manuais/``: o seed continua guardando o manual
original inteiro em ``manuais/<modelo_id>/`` (fonte da verdade, Req 20.3). O script de
sincronização divide cada manual em um arquivo por seção e grava em
``secoes/<modelo_id>/<manual>/<slug>.md`` (+ ``.metadata.json``). Só esse prefixo é indexado,
senão o manual inteiro, sem o nome da seção nos metadados, seria indexado em duplicidade (o
data source S3 aceita um único prefixo de inclusão e não tem exclusão).

Notas de projeto:
- Os constructs L1 ``aws_s3vectors`` e ``aws_bedrock.CfnKnowledgeBase/CfnDataSource`` existem no
  ``aws-cdk-lib`` fixado (2.273.0); não foi preciso ``CfnResource`` nem recurso customizado.
- O vector bucket usa SSE-S3 (padrão do serviço). Ele só guarda vetores e trechos de manuais
  oficiais (sem dados pessoais). SSE-KMS exigiria acrescentar ao key policy da ``DadosStack`` o
  principal de serviço de indexação do S3 Vectors, algo que não foi possível confirmar sem uma
  conta AWS (ver ``PENDENTE`` na tarefa 17.2). Os buckets de dados continuam com a chave do
  cliente.
- A confiança do papel usa ``aws:SourceArn`` com curinga de Knowledge Bases da conta: citar a KB
  específica criaria um ciclo (papel -> KB -> papel).
- Esta stack só recebe a chave e o bucket de manuais; nada em ``DadosStack`` ou
  ``ArmazenamentoStack`` depende dela (a política padrão da chave já delega o acesso ao IAM).
"""

from aws_cdk import Aws, CfnOutput, RemovalPolicy, Stack
from aws_cdk import aws_bedrock as bedrock
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3vectors as s3vectors
from aws_cdk import aws_ssm as ssm
from constructs import Construct

# Valores iguais aos de ``services/agente/premissas.py`` (o teste confere cada um).
MODELO_EMBEDDINGS_ID = "cohere.embed-multilingual-v3"
EMBEDDINGS_DIMENSOES = 1024
EMBEDDINGS_TIPO_VETOR = "float32"
EMBEDDINGS_METRICA = "cosine"
CHUNKING_ESTRATEGIA = "FIXED_SIZE"
CHUNKING_MAX_TOKENS = 300
CHUNKING_SOBREPOSICAO_PERCENTUAL = 20

# Prefixo indexado: uma seção por arquivo. Igual a
# ``scripts/preprocessar_manuais.PREFIXO_S3_SECOES`` (o teste confere). O manual inteiro
# continua em ``premissas.PREFIXO_S3_MANUAIS``.
PREFIXO_S3_SECOES = "secoes/"

# Chaves que o Bedrock grava no vetor e que não podem ser filtráveis.
CHAVES_NAO_FILTRAVEIS = ("AMAZON_BEDROCK_TEXT", "AMAZON_BEDROCK_METADATA")


class ConhecimentoStack(Stack):
    """Knowledge Base (S3 Vectors) alimentada pelas seções dos manuais."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        chave: kms.IKey,
        bucket_manuais: s3.IBucket,
        prefixo: str = "tres",
        destruir_ao_remover: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        remocao = RemovalPolicy.DESTROY if destruir_ao_remover else RemovalPolicy.RETAIN
        nome_indice = f"{prefixo}-manuais"

        # --- Vector store (S3 Vectors) -------------------------------------------------------
        self.vector_bucket = s3vectors.CfnVectorBucket(self, "VectorBucketManuais")
        self.vector_bucket.apply_removal_policy(remocao)

        self.indice = s3vectors.CfnIndex(
            self,
            "IndiceManuais",
            index_name=nome_indice,
            vector_bucket_arn=self.vector_bucket.attr_vector_bucket_arn,
            data_type=EMBEDDINGS_TIPO_VETOR,
            dimension=EMBEDDINGS_DIMENSOES,
            distance_metric=EMBEDDINGS_METRICA,
            metadata_configuration=s3vectors.CfnIndex.MetadataConfigurationProperty(
                non_filterable_metadata_keys=list(CHAVES_NAO_FILTRAVEIS)
            ),
        )
        self.indice.apply_removal_policy(remocao)

        # --- Papel de serviço do Bedrock (privilégio mínimo) ---------------------------------
        self.papel = iam.Role(
            self,
            "PapelBaseConhecimento",
            description="Papel do Bedrock Knowledge Base dos manuais TRES",
            assumed_by=iam.ServicePrincipal(
                "bedrock.amazonaws.com",
                conditions={
                    "StringEquals": {"aws:SourceAccount": Aws.ACCOUNT_ID},
                    "ArnLike": {
                        "aws:SourceArn": (
                            f"arn:{Aws.PARTITION}:bedrock:{Aws.REGION}:{Aws.ACCOUNT_ID}"
                            ":knowledge-base/*"
                        )
                    },
                },
            ),
        )
        politica = iam.Policy(
            self,
            "PoliticaBaseConhecimento",
            roles=[self.papel],
            statements=[
                # Dados de origem: listar o bucket e ler só o prefixo das seções.
                iam.PolicyStatement(
                    sid="ListarBucketDeManuais",
                    actions=["s3:ListBucket"],
                    resources=[bucket_manuais.bucket_arn],
                    conditions={"StringEquals": {"aws:ResourceAccount": Aws.ACCOUNT_ID}},
                ),
                iam.PolicyStatement(
                    sid="LerSecoesDosManuais",
                    actions=["s3:GetObject"],
                    resources=[bucket_manuais.arn_for_objects(f"{PREFIXO_S3_SECOES}*")],
                    conditions={"StringEquals": {"aws:ResourceAccount": Aws.ACCOUNT_ID}},
                ),
                # O bucket usa SSE-KMS com a chave do cliente: decifrar, só por intermédio do S3.
                iam.PolicyStatement(
                    sid="DecifrarManuais",
                    actions=["kms:Decrypt"],
                    resources=[chave.key_arn],
                    conditions={
                        "StringEquals": {"kms:ViaService": f"s3.{Aws.REGION}.amazonaws.com"}
                    },
                ),
                # Só o modelo de embeddings escolhido.
                iam.PolicyStatement(
                    sid="InvocarModeloDeEmbeddings",
                    actions=["bedrock:InvokeModel"],
                    resources=[
                        f"arn:{Aws.PARTITION}:bedrock:{Aws.REGION}::foundation-model/"
                        f"{MODELO_EMBEDDINGS_ID}"
                    ],
                ),
                # Só o índice desta Knowledge Base.
                iam.PolicyStatement(
                    sid="AcessarIndiceDeVetores",
                    actions=[
                        "s3vectors:PutVectors",
                        "s3vectors:GetVectors",
                        "s3vectors:DeleteVectors",
                        "s3vectors:QueryVectors",
                        "s3vectors:GetIndex",
                    ],
                    resources=[self.indice.attr_index_arn],
                ),
            ],
        )

        # --- Knowledge Base ------------------------------------------------------------------
        self.knowledge_base = bedrock.CfnKnowledgeBase(
            self,
            "BaseConhecimento",
            name=f"{prefixo}-manuais",
            description="Seções dos manuais oficiais TRES (um arquivo por seção, filtro modelo_id)",
            role_arn=self.papel.role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=(
                        f"arn:{Aws.PARTITION}:bedrock:{Aws.REGION}::foundation-model/"
                        f"{MODELO_EMBEDDINGS_ID}"
                    ),
                    embedding_model_configuration=bedrock.CfnKnowledgeBase.EmbeddingModelConfigurationProperty(
                        bedrock_embedding_model_configuration=bedrock.CfnKnowledgeBase.BedrockEmbeddingModelConfigurationProperty(
                            # Cohere v3 tem 1024 dimensões fixas: ``dimensions`` só vale para
                            # modelos que aceitam escolher (Titan v2), então fica de fora.
                            embedding_data_type=EMBEDDINGS_TIPO_VETOR.upper()
                        )
                    ),
                ),
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="S3_VECTORS",
                s3_vectors_configuration=bedrock.CfnKnowledgeBase.S3VectorsConfigurationProperty(
                    index_arn=self.indice.attr_index_arn,
                    vector_bucket_arn=self.vector_bucket.attr_vector_bucket_arn,
                ),
            ),
        )
        # O Bedrock valida o acesso ao criar a KB: as permissões precisam existir antes.
        self.knowledge_base.node.add_dependency(politica)
        self.knowledge_base.apply_removal_policy(remocao)

        # --- Data source: seções dos manuais, chunking FIXED_SIZE ----------------------------
        self.data_source = bedrock.CfnDataSource(
            self,
            "FonteManuais",
            name=f"{prefixo}-manuais-secoes",
            description="Arquivos por seção em secoes/<modelo_id>/ com sidecar .metadata.json",
            knowledge_base_id=self.knowledge_base.attr_knowledge_base_id,
            data_deletion_policy="DELETE" if destruir_ao_remover else "RETAIN",
            data_source_configuration=bedrock.CfnDataSource.DataSourceConfigurationProperty(
                type="S3",
                s3_configuration=bedrock.CfnDataSource.S3DataSourceConfigurationProperty(
                    bucket_arn=bucket_manuais.bucket_arn,
                    inclusion_prefixes=[PREFIXO_S3_SECOES],
                    bucket_owner_account_id=Aws.ACCOUNT_ID,
                ),
            ),
            vector_ingestion_configuration=bedrock.CfnDataSource.VectorIngestionConfigurationProperty(
                chunking_configuration=bedrock.CfnDataSource.ChunkingConfigurationProperty(
                    chunking_strategy=CHUNKING_ESTRATEGIA,
                    fixed_size_chunking_configuration=bedrock.CfnDataSource.FixedSizeChunkingConfigurationProperty(
                        max_tokens=CHUNKING_MAX_TOKENS,
                        overlap_percentage=CHUNKING_SOBREPOSICAO_PERCENTUAL,
                    ),
                )
            ),
        )
        self.data_source.apply_removal_policy(remocao)

        self.knowledge_base_id = self.knowledge_base.attr_knowledge_base_id
        self.knowledge_base_arn = self.knowledge_base.attr_knowledge_base_arn
        self.data_source_id = self.data_source.attr_data_source_id

        # --- Configuração para o agente (17.3/17.4) e para o script de sincronização ---------
        ssm.StringParameter(
            self,
            "ParametroKnowledgeBaseId",
            parameter_name=f"/{prefixo}/config/knowledge-base-id",
            description="ID da Knowledge Base dos manuais (Retrieve do agente; ingestão)",
            string_value=self.knowledge_base_id,
        )
        ssm.StringParameter(
            self,
            "ParametroDataSourceId",
            parameter_name=f"/{prefixo}/config/knowledge-base-data-source-id",
            description="ID do data source da Knowledge Base (start_ingestion_job)",
            string_value=self.data_source_id,
        )
        ssm.StringParameter(
            self,
            "ParametroPrefixoSecoes",
            parameter_name=f"/{prefixo}/config/secoes-prefixo",
            description="Prefixo das seções de manuais indexadas pela Knowledge Base",
            string_value=PREFIXO_S3_SECOES,
        )

        CfnOutput(self, "KnowledgeBaseId", value=self.knowledge_base_id)
        CfnOutput(self, "KnowledgeBaseArn", value=self.knowledge_base_arn)
        CfnOutput(self, "KnowledgeBaseDataSourceId", value=self.data_source_id)
        CfnOutput(self, "IndiceVetoresArn", value=self.indice.attr_index_arn)
