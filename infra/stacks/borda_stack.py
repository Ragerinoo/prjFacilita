"""Stack de borda: distribuição CloudFront com o site e ``/api/*`` na mesma origem.

Cobre os Req 18.7 (HTTP redireciona para HTTPS antes de qualquer processamento do corpo, mais
HSTS), 18.2 e 20.1 (o site é lido do bucket com SSE-KMS por OAC) e 20.5 (o valor do cabeçalho de
origem vem do Secrets Manager por referência dinâmica; não aparece no template).

Comportamentos:
- padrão: bucket do site (OAC), cache otimizado, reescrita de rotas do SPA para ``/index.html``.
- ``/api/pub/modelos*``: catálogo com cache de borda curto (Req 1.7), só GET/HEAD, sem cookies.
- ``/api/*``: API Gateway HTTP API, sem cache, repassa cookies, cabeçalhos e query (menos o
  ``Host``), com tempo de espera da origem de 30 s (Q18: >= o teto de 30 s do HTTP API).

Notas de projeto (sem ciclos entre stacks):
- O bucket do site entra como importado (só o nome). Assim o OAC não grava política no bucket
  da stack de armazenamento (isso criaria um ciclo). A leitura pelo CloudFront é liberada lá,
  na política do bucket e na da chave KMS, por condição ``aws:SourceArn`` com curinga de
  distribuições da conta.
- O CORS do bucket de fotos (POST pré-assinado do navegador direto ao S3) precisaria do domínio
  desta distribuição, que só existe depois do deploy; referenciá-lo na stack de armazenamento
  criaria um ciclo. Por isso o ``app.py`` usa ``https://*.cloudfront.net`` por padrão. Para
  restringir ao domínio exato depois do primeiro deploy (saída ``DominioCloudFront``):
  ``cdk deploy -c origens_cors_fotos=https://<id>.cloudfront.net``.
- Sem domínio próprio nem certificado ACM: usa o domínio ``*.cloudfront.net`` e o certificado
  padrão do CloudFront, que não permite escolher a versão mínima de TLS (com domínio próprio,
  definir ``minimum_protocol_version=TLS_V1_2_2021``). Log de acesso e WAF ficam fora do
  MVP (Q12).
"""

from __future__ import annotations

from aws_cdk import CfnOutput, Duration, SecretValue, Stack
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_s3 as s3
from constructs import Construct

# Q18: o HTTP API responde em até 30 s; a espera da origem não pode ser menor.
ORIGEM_TIMEOUT_S = 30
CABECALHO_ORIGEM = "x-origem-cloudfront"
CAMPO_SEGREDO_ORIGEM = "valor"

HSTS_SEGUNDOS = 63_072_000  # 2 anos

# Reescreve rotas do SPA (sem extensão) para o index.html. Fica só no comportamento do site,
# para não trocar respostas 403/404 da API (um tratamento global de erro faria isso).
FUNCAO_SPA_JS = """\
function handler(event) {
  var request = event.request;
  var uri = request.uri;
  if (uri.lastIndexOf('.') <= uri.lastIndexOf('/')) {
    request.uri = '/index.html';
  }
  return request;
}
"""


def montar_csp(host_fotos: str) -> str:
    """CSP restritiva: tudo na própria origem, mais o bucket de fotos para envio e exibição.

    ``host_fotos`` é o domínio regional do bucket de fotos (URL pré-assinada, Req 12.7). Estilos
    inline ficam permitidos porque o React aplica ``style`` por atributo; scripts não.
    """
    fotos = f"https://{host_fotos}"
    diretivas = [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self' 'unsafe-inline'",
        f"img-src 'self' data: {fotos}",
        "media-src 'self'",
        "font-src 'self'",
        f"connect-src 'self' {fotos}",
        "object-src 'none'",
        "base-uri 'self'",
        f"form-action 'self' {fotos}",
        "frame-ancestors 'none'",
        "upgrade-insecure-requests",
    ]
    return "; ".join(diretivas)


class BordaStack(Stack):
    """Distribuição CloudFront única para o site e a API."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        bucket_site: s3.IBucket,
        bucket_fotos: s3.IBucket,
        dominio_api: str,
        nome_segredo_origem: str,
        prefixo: str = "tres",
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Importa só pelo nome para o OAC não alterar a política do bucket (ver nota acima).
        site = s3.Bucket.from_bucket_name(self, "SiteImportado", bucket_site.bucket_name)

        # Referência dinâmica ao Secrets Manager: o valor é resolvido pelo CloudFormation no
        # deploy e nunca aparece no template nem no código (Req 20.5).
        valor_origem = SecretValue.secrets_manager(
            nome_segredo_origem, json_field=CAMPO_SEGREDO_ORIGEM
        ).unsafe_unwrap()

        cabecalhos = cloudfront.ResponseHeadersPolicy(
            self,
            "PoliticaCabecalhos",
            comment="Cabeçalhos de segurança: HSTS, CSP, nosniff, Referrer-Policy (Req 18.7)",
            security_headers_behavior=cloudfront.ResponseSecurityHeadersBehavior(
                strict_transport_security=cloudfront.ResponseHeadersStrictTransportSecurity(
                    access_control_max_age=Duration.seconds(HSTS_SEGUNDOS),
                    include_subdomains=True,
                    preload=False,
                    override=True,
                ),
                content_security_policy=cloudfront.ResponseHeadersContentSecurityPolicy(
                    content_security_policy=montar_csp(bucket_fotos.bucket_regional_domain_name),
                    override=True,
                ),
                content_type_options=cloudfront.ResponseHeadersContentTypeOptions(override=True),
                referrer_policy=cloudfront.ResponseHeadersReferrerPolicy(
                    referrer_policy=cloudfront.HeadersReferrerPolicy.NO_REFERRER,
                    override=True,
                ),
                frame_options=cloudfront.ResponseHeadersFrameOptions(
                    frame_option=cloudfront.HeadersFrameOption.DENY,
                    override=True,
                ),
            ),
        )

        origem_api = origins.HttpOrigin(
            dominio_api,
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTPS_ONLY,
            read_timeout=Duration.seconds(ORIGEM_TIMEOUT_S),
            custom_headers={CABECALHO_ORIGEM: valor_origem},
        )

        funcao_spa = cloudfront.Function(
            self,
            "FuncaoSpa",
            comment="Rotas do SPA sem extensão voltam para /index.html",
            code=cloudfront.FunctionCode.from_inline(FUNCAO_SPA_JS),
            runtime=cloudfront.FunctionRuntime.JS_2_0,
        )

        # Catálogo: cache curto na borda, sem cookies e sem cabeçalhos na chave (Req 1.7).
        cache_catalogo = cloudfront.CachePolicy(
            self,
            "CacheCatalogo",
            comment="Catálogo de modelos: cache curto de borda",
            default_ttl=Duration.seconds(30),
            min_ttl=Duration.seconds(0),
            max_ttl=Duration.seconds(60),
            cookie_behavior=cloudfront.CacheCookieBehavior.none(),
            header_behavior=cloudfront.CacheHeaderBehavior.none(),
            query_string_behavior=cloudfront.CacheQueryStringBehavior.all(),
            enable_accept_encoding_gzip=True,
            enable_accept_encoding_brotli=True,
        )

        comportamento_api = {
            "origin": origem_api,
            "viewer_protocol_policy": cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
            "response_headers_policy": cabecalhos,
        }
        self.distribuicao = cloudfront.Distribution(
            self,
            "Distribuicao",
            comment=f"{prefixo}: site e API na mesma origem",
            default_root_object="index.html",
            http_version=cloudfront.HttpVersion.HTTP2_AND_3,
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(site),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                response_headers_policy=cabecalhos,
                compress=True,
                function_associations=[
                    cloudfront.FunctionAssociation(
                        function=funcao_spa,
                        event_type=cloudfront.FunctionEventType.VIEWER_REQUEST,
                    )
                ],
            ),
            # A ordem importa: o padrão mais específico vem primeiro.
            additional_behaviors={
                "/api/pub/modelos*": cloudfront.BehaviorOptions(
                    **comportamento_api,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD,
                    cached_methods=cloudfront.CachedMethods.CACHE_GET_HEAD,
                    cache_policy=cache_catalogo,
                    compress=True,
                ),
                "/api/*": cloudfront.BehaviorOptions(
                    **comportamento_api,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    # Repassa cookie de sessão, cabeçalhos e query; o Host fica de fora
                    # (o API Gateway precisa do próprio Host).
                    origin_request_policy=(
                        cloudfront.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER
                    ),
                ),
            },
        )

        CfnOutput(self, "DominioCloudFront", value=self.distribuicao.distribution_domain_name)
        CfnOutput(self, "DistribuicaoId", value=self.distribuicao.distribution_id)
