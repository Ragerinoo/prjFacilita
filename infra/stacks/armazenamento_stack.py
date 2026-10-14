"""Stack de armazenamento: buckets, fila de encerramentos, segredo e parâmetros.

Cobre os Req 18.2 e 20.1 (SSE-KMS com a chave do cliente criada em ``DadosStack``), 12.7
(fotos por URL pré-assinada), 17.12 (fila de encerramentos com DLQ) e 20.5 (nenhum segredo
no código ou no template).

Notas de projeto:
- Esta stack só recebe a chave (``chave``) da ``DadosStack``; nada da chave depende desta stack,
  então não há ciclo entre stacks. A única alteração na política da chave é o acesso de leitura
  do CloudFront (OAC) ao bucket do site, limitada por conta e por ``aws:SourceArn`` com
  curinga: referenciar a distribuição específica criaria um ciclo com a stack de borda (8.3).
- Os nomes dos buckets são gerados pelo CloudFormation (nomes de bucket são globais).
  Consumidores recebem nome/ARN pelos atributos da stack, não por nome fixo.
- Nenhum valor sensível fica no código. O segredo é gerado pelo Secrets Manager no deploy; os
  parâmetros SSM guardam só configuração não sensível.
"""

from aws_cdk import Aws, CfnOutput, Duration, RemovalPolicy, Stack
from aws_cdk import aws_iam as iam
from aws_cdk import aws_kms as kms
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_sqs as sqs
from aws_cdk import aws_ssm as ssm
from constructs import Construct

# Convenção do bucket de manuais: ``manuais/<modelo_id>/<slug-da-secao>.md`` mais o sidecar
# ``.metadata.json`` (igual a ``services/agente/premissas.PREFIXO_S3_MANUAIS``; o teste confere).
PREFIXO_S3_MANUAIS = "manuais/"

# Req 17.12: até 3 tentativas, cerca de 10 s entre elas (tempo de visibilidade da fila, Q8).
ENCERRAMENTO_MAX_TENTATIVAS = 3
ENCERRAMENTO_VISIBILIDADE = Duration.seconds(10)

# Valor inicial do parâmetro; o ID real do perfil de inferência é conferido na conta (Q3).
# Igual a ``premissas.MODELO_LLM_ID_PADRAO`` (o teste confere).
MODELO_LLM_ID_PADRAO = "global.anthropic.claude-haiku-4-5-20251001-v1:0"


class ArmazenamentoStack(Stack):
    """Buckets (site, fotos, manuais), fila de encerramentos com DLQ, segredo e parâmetros."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        chave: kms.IKey,
        prefixo: str = "tres",
        destruir_ao_remover: bool = False,
        origens_cors_fotos: tuple[str, ...] = (),
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self._chave = chave
        self._destruir = destruir_ao_remover
        # Dados de clientes: por padrão os recursos sobrevivem à remoção da stack.
        self._remocao = RemovalPolicy.DESTROY if destruir_ao_remover else RemovalPolicy.RETAIN

        # --- Buckets ------------------------------------------------------------------------
        self.bucket_site = self._criar_bucket("BucketSite")
        self.bucket_fotos = self._criar_bucket("BucketFotos", origens_cors=origens_cors_fotos)
        self.bucket_manuais = self._criar_bucket("BucketManuais", versionado=True)
        self._permitir_leitura_cloudfront_na_chave()
        self._permitir_leitura_cloudfront_no_bucket_do_site()

        # --- Fila de encerramentos + DLQ (Req 17.12) ----------------------------------------
        self.dlq_encerramentos = sqs.Queue(
            self,
            "DlqEncerramentos",
            queue_name=f"{prefixo}-encerramentos-dlq",
            encryption=sqs.QueueEncryption.KMS,
            encryption_master_key=chave,
            enforce_ssl=True,
            retention_period=Duration.days(14),
            removal_policy=self._remocao,
        )
        self.fila_encerramentos = sqs.Queue(
            self,
            "FilaEncerramentos",
            queue_name=f"{prefixo}-encerramentos",
            encryption=sqs.QueueEncryption.KMS,
            encryption_master_key=chave,
            enforce_ssl=True,
            # A Lambda consumidora (8.3) precisa de timeout <= esta visibilidade.
            visibility_timeout=ENCERRAMENTO_VISIBILIDADE,
            dead_letter_queue=sqs.DeadLetterQueue(
                max_receive_count=ENCERRAMENTO_MAX_TENTATIVAS,
                queue=self.dlq_encerramentos,
            ),
            removal_policy=self._remocao,
        )

        # --- Segredo (gerado no deploy; o valor nunca passa pelo código) (Req 20.5) ---------
        self.segredo_app = secretsmanager.Secret(
            self,
            "SegredoApp",
            secret_name=f"{prefixo}/segredo-app",
            description="Chave HMAC da aplicação (hash de token de sessão e identificadores)",
            encryption_key=chave,
            generate_secret_string=secretsmanager.SecretStringGenerator(
                secret_string_template='{"usuario": "app"}',
                generate_string_key="hmac_chave",
                password_length=64,
                exclude_punctuation=True,
            ),
            removal_policy=self._remocao,
        )

        # --- Parâmetros de configuração não sensíveis (SSM) ---------------------------------
        self.parametro_modelo_llm = ssm.StringParameter(
            self,
            "ParametroModeloLlm",
            parameter_name=f"/{prefixo}/config/modelo-llm-id",
            description="ID do perfil de inferência do modelo de linguagem (TRES_MODELO_LLM_ID)",
            string_value=MODELO_LLM_ID_PADRAO,
        )
        self.parametro_prefixo_manuais = ssm.StringParameter(
            self,
            "ParametroPrefixoManuais",
            parameter_name=f"/{prefixo}/config/manuais-prefixo",
            description="Prefixo das seções de manuais no bucket de manuais",
            string_value=PREFIXO_S3_MANUAIS,
        )

        CfnOutput(self, "BucketSiteNome", value=self.bucket_site.bucket_name)
        CfnOutput(self, "BucketFotosNome", value=self.bucket_fotos.bucket_name)
        CfnOutput(self, "BucketManuaisNome", value=self.bucket_manuais.bucket_name)
        CfnOutput(self, "FilaEncerramentosUrl", value=self.fila_encerramentos.queue_url)
        CfnOutput(self, "DlqEncerramentosNome", value=self.dlq_encerramentos.queue_name)

    def _criar_bucket(
        self,
        id_: str,
        *,
        versionado: bool = False,
        origens_cors: tuple[str, ...] = (),
    ) -> s3.Bucket:
        cors = (
            [
                s3.CorsRule(
                    allowed_methods=[s3.HttpMethods.POST],
                    allowed_origins=list(origens_cors),
                    allowed_headers=["*"],
                    max_age=3000,
                )
            ]
            if origens_cors
            else None
        )
        return s3.Bucket(
            self,
            id_,
            encryption=s3.BucketEncryption.KMS,
            encryption_key=self._chave,
            bucket_key_enabled=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            versioned=versionado,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            lifecycle_rules=[
                s3.LifecycleRule(abort_incomplete_multipart_upload_after=Duration.days(7))
            ],
            cors=cors,
            removal_policy=self._remocao,
            auto_delete_objects=self._destruir,
        )

    def _permitir_leitura_cloudfront_no_bucket_do_site(self) -> None:
        """Deixa o CloudFront (OAC) ler o site, sem acoplar à distribuição (evita ciclo).

        A stack de borda importa o bucket só pelo nome, então a política do bucket mora aqui.
        O ``aws:SourceArn`` com curinga limita a distribuições da conta.
        """
        distribuicoes = f"arn:{Aws.PARTITION}:cloudfront::{Aws.ACCOUNT_ID}:distribution/*"
        self.bucket_site.add_to_resource_policy(
            iam.PolicyStatement(
                sid="PermitirCloudFrontLerSite",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("cloudfront.amazonaws.com")],
                actions=["s3:GetObject"],
                resources=[self.bucket_site.arn_for_objects("*")],
                conditions={"ArnLike": {"aws:SourceArn": distribuicoes}},
            )
        )

    def _permitir_leitura_cloudfront_na_chave(self) -> None:
        """Deixa o CloudFront (OAC) decifrar objetos do site, sem acoplar à distribuição.

        Sem isto, um bucket com SSE-KMS não é servido pelo CloudFront. A condição usa curinga
        de distribuições da conta para não criar ciclo entre a chave e a stack de borda.
        """
        distribuicoes = f"arn:{Aws.PARTITION}:cloudfront::{Aws.ACCOUNT_ID}:distribution/*"
        self._chave.add_to_resource_policy(
            iam.PolicyStatement(
                sid="PermitirCloudFrontDecifrarSite",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("cloudfront.amazonaws.com")],
                actions=["kms:Decrypt"],
                resources=["*"],
                conditions={"ArnLike": {"aws:SourceArn": distribuicoes}},
            )
        )
