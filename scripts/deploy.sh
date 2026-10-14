#!/usr/bin/env bash
# Deploy completo: cdk deploy, build do front-end, sync do site no S3, invalidação do CloudFront
# e carga do seed (Req 18.7, 20.1, 20.3, 20.5).
#
# Credenciais: cadeia padrão da AWS (perfil/SSO/variáveis de ambiente). Nada é lido do repositório
# e nenhum segredo é impresso. Variáveis (só nomes): TRES_PREFIXO (padrão "tres"), AWS_REGION,
# AWS_PROFILE, PYTHON (padrão python3), PULAR_CDK, PULAR_CARGA.
#
# Uso: scripts/deploy.sh [--sem-cdk] [--sem-carga]
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIXO="${TRES_PREFIXO:-tres}"
PYTHON="${PYTHON:-python3}"
PULAR_CDK="${PULAR_CDK:-0}"
PULAR_CARGA="${PULAR_CARGA:-0}"
for arg in "$@"; do
  case "$arg" in
    --sem-cdk) PULAR_CDK=1 ;;
    --sem-carga) PULAR_CARGA=1 ;;
    *) echo "Opção desconhecida: $arg" >&2; exit 2 ;;
  esac
done

for cmd in aws npm "$PYTHON"; do
  command -v "$cmd" >/dev/null || { echo "Falta o comando: $cmd" >&2; exit 1; }
done
if [ "$PULAR_CDK" != "1" ]; then
  command -v cdk >/dev/null || { echo "Falta o comando: cdk (npm i -g aws-cdk)" >&2; exit 1; }
fi

saida_stack() { # stack chave
  aws cloudformation describe-stacks --stack-name "$1" \
    --query "Stacks[0].Outputs[?OutputKey=='$2'].OutputValue | [0]" --output text
}

echo "==> 1/5 cdk deploy (prefixo: $PREFIXO)"
if [ "$PULAR_CDK" != "1" ]; then
  (cd "$RAIZ/infra" && cdk deploy --all --require-approval never -c "prefixo=$PREFIXO")
else
  echo "    (pulado)"
fi

BUCKET_SITE="$(saida_stack "$PREFIXO-armazenamento" BucketSiteNome)"
BUCKET_MANUAIS="$(saida_stack "$PREFIXO-armazenamento" BucketManuaisNome)"
DISTRIBUICAO="$(saida_stack "$PREFIXO-borda" DistribuicaoId)"
DOMINIO="$(saida_stack "$PREFIXO-borda" DominioCloudFront)"

echo "==> 2/5 build do front-end"
(cd "$RAIZ/apps/web" && npm ci && npm run build)

echo "==> 3/5 sync do site para s3://$BUCKET_SITE"
aws s3 sync "$RAIZ/apps/web/dist" "s3://$BUCKET_SITE" --delete \
  --exclude "index.html" --cache-control "public,max-age=31536000,immutable"
aws s3 cp "$RAIZ/apps/web/dist/index.html" "s3://$BUCKET_SITE/index.html" \
  --cache-control "no-cache"

echo "==> 4/5 invalidação do CloudFront ($DISTRIBUICAO)"
aws cloudfront create-invalidation --distribution-id "$DISTRIBUICAO" --paths "/*" >/dev/null

echo "==> 5/5 carga do seed"
if [ "$PULAR_CARGA" != "1" ]; then
  TRES_PREFIXO_TABELAS="$PREFIXO" TRES_BUCKET_MANUAIS="$BUCKET_MANUAIS" \
    "$PYTHON" "$RAIZ/scripts/carregar_seed.py" --bucket-manuais "$BUCKET_MANUAIS" --prefixo "$PREFIXO"
else
  echo "    (pulada)"
fi

echo
echo "Pronto: https://$DOMINIO/m/tres-passione?s=DEMO001"
echo "Usuários do Painel_CS: CS_SENHA_INICIAL=<senha> $PYTHON scripts/criar_usuarios_cs.py"
