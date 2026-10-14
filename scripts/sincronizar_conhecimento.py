#!/usr/bin/env python3
"""Sincroniza os manuais com a Knowledge Base (Req 6.2, 6.3, 20.2, 20.3).

Fluxo (``sincronizar``):

1. Divide cada manual em uma seção por arquivo (``preprocessar_manuais``).
2. Envia as seções e os sidecars ``.metadata.json`` ao bucket de manuais, no prefixo indexado
   (``secoes/<modelo_id>/<manual>/<slug>.md``). Idempotente: objeto com o mesmo conteúdo nem é
   reenviado. Se o envio falhar, remove o que foi criado NESTA execução e restaura o que foi
   sobrescrito (mesma regra da carga dos manuais, Req 20.7).
3. Remove as seções obsoletas dos modelos sincronizados (arquivos que existiam e já não vêm do
   manual). O bucket é versionado, então a remoção só põe um marcador de exclusão. Sem isso, a
   Knowledge Base manteria respostas de seções que o manual já não tem.
4. Chama ``bedrock-agent start_ingestion_job`` e consulta ``get_ingestion_job`` até o fim, com
   limite de tempo. Falha se o job terminar em ``FAILED``/``STOPPED``, se algum documento falhar
   ou se o tempo acabar.

Os clientes boto3 (``s3``, ``bedrock_agent``) são injetados; ``dormir`` e ``relogio`` também,
para os testes não esperarem de verdade. Erros viram ``ErroSincronizacao`` com a lista de itens
e motivos (pt-BR).

Uso isolado (a carga completa usa ``carregar_seed.py --sincronizar-conhecimento``):

    python scripts/sincronizar_conhecimento.py --bucket-manuais <bucket> \
        --knowledge-base-id <id> [--data-source-id <id>] [--seed-dir seed]
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_RAIZ = Path(__file__).resolve().parent.parent
for _caminho in (_RAIZ / "packages" / "dominio" / "src", _RAIZ / "services" / "agente"):
    if str(_caminho) not in sys.path:
        sys.path.insert(0, str(_caminho))

from preprocessar_manuais import (  # noqa: E402
    PREFIXO_S3_SECOES,
    ErroPreprocessamento,
    SecaoManual,
    preprocessar_manual_local,
    validar_conjunto,
)

TEMPO_LIMITE_INGESTAO_PADRAO_S = 600.0
INTERVALO_CONSULTA_PADRAO_S = 5.0
STATUS_EM_ANDAMENTO = frozenset({"STARTING", "IN_PROGRESS"})
STATUS_SUCESSO = "COMPLETE"
STATUS_FALHA = frozenset({"FAILED", "STOPPING", "STOPPED"})
TIPO_MARKDOWN = "text/markdown; charset=utf-8"
TIPO_JSON = "application/json"


# --------------------------------------------------------------------------------------------
# Erros e resultado
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FalhaSincronizacao:
    item: str
    motivo: str

    def __str__(self) -> str:
        return f"{self.item}: {self.motivo}"


class ErroSincronizacao(Exception):
    """A sincronização foi interrompida. ``falhas`` lista cada item com o motivo."""

    def __init__(self, falhas: Sequence[FalhaSincronizacao]) -> None:
        self.falhas = list(falhas)
        super().__init__("\n".join(f"- {f}" for f in self.falhas))


@dataclass(frozen=True, slots=True)
class ResultadoSincronizacao:
    secoes: int  # seções (arquivos de conteúdo) do conjunto
    enviados: tuple[str, ...]  # chaves S3 gravadas nesta execução (conteúdo e sidecars)
    inalterados: tuple[str, ...]  # chaves S3 que já tinham o mesmo conteúdo
    removidos: tuple[str, ...]  # chaves S3 obsoletas removidas
    ingestion_job_id: str | None = None
    status: str | None = None
    estatisticas: Mapping[str, int] = field(default_factory=dict)


def _descrever_erro(exc: Exception) -> str:
    resposta = getattr(exc, "response", None)
    if not isinstance(resposta, Mapping):
        return f"{type(exc).__name__}: {exc}"
    erro = resposta.get("Error", {})
    return f"{erro.get('Code', type(exc).__name__)}: {erro.get('Message', exc)}"


def _codigo_erro(exc: Exception) -> str | None:
    resposta = getattr(exc, "response", None)
    return resposta.get("Error", {}).get("Code") if isinstance(resposta, Mapping) else None


# --------------------------------------------------------------------------------------------
# Seções do seed
# --------------------------------------------------------------------------------------------


def secoes_dos_manuais(manuais: Mapping[str, Sequence[Any]]) -> list[SecaoManual]:
    """Divide os manuais do seed (``modelo_id -> [ManualLocal]``) em seções, em ordem estável.

    Cada manual precisa de ``chave_s3``, ``corpo`` e ``corpo_sidecar`` (como ``ManualLocal`` de
    ``carregar_seed``). Levanta ``ErroSincronizacao`` com todos os manuais que não puderam ser
    divididos e com qualquer conflito de chaves.
    """
    secoes: list[SecaoManual] = []
    falhas: list[FalhaSincronizacao] = []
    for modelo_id in sorted(manuais):
        for manual in manuais[modelo_id]:
            item = f"conhecimento > {modelo_id} > {manual.chave_s3}"
            try:
                secoes.extend(
                    preprocessar_manual_local(
                        modelo_id=modelo_id,
                        nome_arquivo=manual.chave_s3.rsplit("/", 1)[-1],
                        corpo=manual.corpo,
                        corpo_sidecar=manual.corpo_sidecar,
                    )
                )
            except ErroPreprocessamento as exc:
                falhas.append(FalhaSincronizacao(item, str(exc)))
    falhas.extend(FalhaSincronizacao("conhecimento", e) for e in validar_conjunto(secoes))
    if falhas:
        raise ErroSincronizacao(falhas)
    return secoes


# --------------------------------------------------------------------------------------------
# S3
# --------------------------------------------------------------------------------------------


def _ler_objeto(s3: Any, bucket: str, chave: str) -> tuple[bytes, str] | None:
    try:
        resposta = s3.get_object(Bucket=bucket, Key=chave)
    except Exception as exc:
        if _codigo_erro(exc) in ("NoSuchKey", "404", "NotFound"):
            return None
        raise
    return resposta["Body"].read(), resposta.get("ContentType", "application/octet-stream")


def _listar_chaves(s3: Any, bucket: str, prefixo: str) -> list[str]:
    chaves: list[str] = []
    token: str | None = None
    while True:
        args: dict[str, Any] = {"Bucket": bucket, "Prefix": prefixo}
        if token:
            args["ContinuationToken"] = token
        resposta = s3.list_objects_v2(**args)
        chaves.extend(o["Key"] for o in resposta.get("Contents", []))
        if not resposta.get("IsTruncated"):
            return chaves
        token = resposta.get("NextContinuationToken")


def enviar_secoes(
    s3: Any, bucket: str, secoes: Sequence[SecaoManual]
) -> tuple[list[str], list[str], list[str]]:
    """Envia as seções e remove as obsoletas. Devolve ``(enviados, inalterados, removidos)``.

    Em falha no envio, desfaz esta execução e levanta ``ErroSincronizacao``.
    """
    objetos: list[tuple[str, bytes, str]] = []
    for s in secoes:
        objetos.append((s.chave_s3, s.corpo, TIPO_MARKDOWN))
        objetos.append((s.chave_sidecar, s.corpo_sidecar, TIPO_JSON))

    criados: list[str] = []
    sobrescritos: dict[str, tuple[bytes, str]] = {}
    inalterados: list[str] = []
    atual = PREFIXO_S3_SECOES
    try:
        for chave, corpo, tipo in objetos:
            atual = chave
            anterior = _ler_objeto(s3, bucket, chave)
            if anterior is not None and anterior[0] == corpo:
                inalterados.append(chave)
                continue
            # Registra antes do envio: um envio que falha no meio pode ter gravado o objeto.
            if anterior is None:
                criados.append(chave)
            else:
                sobrescritos[chave] = anterior
            s3.put_object(Bucket=bucket, Key=chave, Body=corpo, ContentType=tipo)
    except Exception as exc:
        motivo = _descrever_erro(exc)
        problemas: list[str] = []
        for chave in criados:
            try:
                s3.delete_object(Bucket=bucket, Key=chave)
            except Exception as exc_rm:
                problemas.append(f"{chave}: {_descrever_erro(exc_rm)}")
        for chave, (corpo, tipo) in sobrescritos.items():
            try:
                s3.put_object(Bucket=bucket, Key=chave, Body=corpo, ContentType=tipo)
            except Exception as exc_rs:
                problemas.append(f"{chave}: {_descrever_erro(exc_rs)}")
        falhas = [FalhaSincronizacao(f"seção {atual}", motivo)]
        falhas.extend(
            FalhaSincronizacao(
                "desfazer envio de seção", f"objeto pode ter ficado inconsistente: {p}"
            )
            for p in problemas
        )
        raise ErroSincronizacao(falhas) from exc

    desejadas = {chave for chave, _, _ in objetos}
    removidos: list[str] = []
    try:
        for modelo_id in sorted({s.modelo_id for s in secoes}):
            for chave in _listar_chaves(s3, bucket, f"{PREFIXO_S3_SECOES}{modelo_id}/"):
                if chave not in desejadas:
                    s3.delete_object(Bucket=bucket, Key=chave)
                    removidos.append(chave)
    except Exception as exc:
        raise ErroSincronizacao(
            [FalhaSincronizacao("remoção de seções obsoletas", _descrever_erro(exc))]
        ) from exc
    return criados, inalterados, removidos


# --------------------------------------------------------------------------------------------
# Ingestão
# --------------------------------------------------------------------------------------------


def resolver_data_source(bedrock_agent: Any, knowledge_base_id: str) -> str:
    """Id do único data source da Knowledge Base."""
    try:
        resposta = bedrock_agent.list_data_sources(knowledgeBaseId=knowledge_base_id)
    except Exception as exc:
        raise ErroSincronizacao(
            [FalhaSincronizacao("data source", f"não foi possível listar: {_descrever_erro(exc)}")]
        ) from exc
    fontes = resposta.get("dataSourceSummaries", [])
    if len(fontes) != 1:
        raise ErroSincronizacao(
            [
                FalhaSincronizacao(
                    "data source",
                    f"a Knowledge Base {knowledge_base_id} tem {len(fontes)} data sources; "
                    "informe --data-source-id",
                )
            ]
        )
    return fontes[0]["dataSourceId"]


def iniciar_e_aguardar_ingestao(
    bedrock_agent: Any,
    knowledge_base_id: str,
    data_source_id: str,
    *,
    tempo_limite_s: float = TEMPO_LIMITE_INGESTAO_PADRAO_S,
    intervalo_s: float = INTERVALO_CONSULTA_PADRAO_S,
    dormir: Callable[[float], None] = time.sleep,
    relogio: Callable[[], float] = time.monotonic,
    log: Callable[[str], None] = lambda _msg: None,
) -> tuple[str, str, Mapping[str, int]]:
    """Inicia a ingestão e espera terminar. Devolve ``(job_id, status, estatísticas)``."""
    item = f"ingestão da Knowledge Base {knowledge_base_id}"
    try:
        resposta = bedrock_agent.start_ingestion_job(
            knowledgeBaseId=knowledge_base_id,
            dataSourceId=data_source_id,
            description="Sincronização dos manuais (scripts/sincronizar_conhecimento.py)",
        )
    except Exception as exc:
        dica = (
            " (já existe uma ingestão em andamento; aguarde terminar e rode de novo)"
            if _codigo_erro(exc) == "ConflictException"
            else ""
        )
        raise ErroSincronizacao(
            [FalhaSincronizacao(item, f"não foi possível iniciar: {_descrever_erro(exc)}{dica}")]
        ) from exc

    job = resposta["ingestionJob"]
    job_id = job["ingestionJobId"]
    log(f"Ingestão {job_id} iniciada ({job.get('status', 'STARTING')}).")
    inicio = relogio()
    while True:
        status = job.get("status")
        if status == STATUS_SUCESSO:
            break
        if status in STATUS_FALHA:
            raise ErroSincronizacao(
                [
                    FalhaSincronizacao(
                        f"{item} (job {job_id})",
                        f"terminou com status {status}" + _motivos(job),
                    )
                ]
            )
        if status not in STATUS_EM_ANDAMENTO:
            raise ErroSincronizacao(
                [FalhaSincronizacao(f"{item} (job {job_id})", f"status inesperado: {status}")]
            )
        if relogio() - inicio >= tempo_limite_s:
            raise ErroSincronizacao(
                [
                    FalhaSincronizacao(
                        f"{item} (job {job_id})",
                        f"tempo esgotado após {tempo_limite_s:.0f} s sem terminar (status "
                        f"{status}); o job segue no Bedrock, confira o console e rode de novo",
                    )
                ]
            )
        dormir(intervalo_s)
        try:
            job = bedrock_agent.get_ingestion_job(
                knowledgeBaseId=knowledge_base_id,
                dataSourceId=data_source_id,
                ingestionJobId=job_id,
            )["ingestionJob"]
        except Exception as exc:
            raise ErroSincronizacao(
                [
                    FalhaSincronizacao(
                        f"{item} (job {job_id})",
                        f"não foi possível consultar o andamento: {_descrever_erro(exc)}",
                    )
                ]
            ) from exc

    estatisticas = {k: int(v) for k, v in (job.get("statistics") or {}).items()}
    if estatisticas.get("numberOfDocumentsFailed", 0) > 0:
        raise ErroSincronizacao(
            [
                FalhaSincronizacao(
                    f"{item} (job {job_id})",
                    f"{estatisticas['numberOfDocumentsFailed']} documento(s) falharam"
                    + _motivos(job),
                )
            ]
        )
    return job_id, STATUS_SUCESSO, estatisticas


def _motivos(job: Mapping[str, Any]) -> str:
    motivos = [str(m) for m in job.get("failureReasons") or []]
    return f": {'; '.join(motivos)}" if motivos else ""


# --------------------------------------------------------------------------------------------
# Orquestração
# --------------------------------------------------------------------------------------------


def sincronizar(
    secoes: Sequence[SecaoManual],
    *,
    s3: Any,
    bedrock_agent: Any,
    bucket_manuais: str,
    knowledge_base_id: str,
    data_source_id: str | None = None,
    tempo_limite_s: float = TEMPO_LIMITE_INGESTAO_PADRAO_S,
    intervalo_s: float = INTERVALO_CONSULTA_PADRAO_S,
    dormir: Callable[[float], None] = time.sleep,
    relogio: Callable[[], float] = time.monotonic,
    log: Callable[[str], None] = lambda _msg: None,
) -> ResultadoSincronizacao:
    """Envia as seções e roda a ingestão. Levanta ``ErroSincronizacao`` se algo falhar."""
    falhas = [
        FalhaSincronizacao("configuração", f"{nome} não informado")
        for nome, valor in (
            ("bucket de manuais", bucket_manuais),
            ("knowledge base", knowledge_base_id),
        )
        if not valor
    ]
    if not secoes:
        falhas.append(FalhaSincronizacao("conhecimento", "nenhuma seção para sincronizar"))
    if falhas:
        raise ErroSincronizacao(falhas)

    enviados, inalterados, removidos = enviar_secoes(s3, bucket_manuais, secoes)
    log(
        f"Seções: {len(secoes)} arquivos, {len(enviados)} objetos enviados, "
        f"{len(inalterados)} já estavam iguais, {len(removidos)} obsoletos removidos."
    )
    fonte = data_source_id or resolver_data_source(bedrock_agent, knowledge_base_id)
    job_id, status, estatisticas = iniciar_e_aguardar_ingestao(
        bedrock_agent,
        knowledge_base_id,
        fonte,
        tempo_limite_s=tempo_limite_s,
        intervalo_s=intervalo_s,
        dormir=dormir,
        relogio=relogio,
        log=log,
    )
    log(f"Ingestão {job_id} concluída ({status}): {dict(estatisticas)}.")
    return ResultadoSincronizacao(
        secoes=len(secoes),
        enviados=tuple(enviados),
        inalterados=tuple(inalterados),
        removidos=tuple(removidos),
        ingestion_job_id=job_id,
        status=status,
        estatisticas=estatisticas,
    )


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    from premissas import REGIAO_PADRAO

    p = argparse.ArgumentParser(
        description="Divide os manuais do seed e sincroniza a Knowledge Base."
    )
    p.add_argument("--seed-dir", type=Path, default=_RAIZ / "seed")
    p.add_argument("--bucket-manuais", default=os.environ.get("TRES_BUCKET_MANUAIS"))
    p.add_argument("--knowledge-base-id", default=os.environ.get("TRES_KNOWLEDGE_BASE_ID"))
    p.add_argument("--data-source-id", default=os.environ.get("TRES_DATA_SOURCE_ID"))
    p.add_argument("--regiao", default=os.environ.get("AWS_REGION") or REGIAO_PADRAO)
    p.add_argument("--tempo-limite", type=float, default=TEMPO_LIMITE_INGESTAO_PADRAO_S)
    args = p.parse_args(argv)

    import carregar_seed  # lê e valida o seed (mesma fase 1 da carga)

    try:
        seed = carregar_seed.validar(args.seed_dir)
        secoes = secoes_dos_manuais(seed.manuais)

        import boto3
        from botocore.config import Config

        config = Config(
            connect_timeout=5, read_timeout=30, retries={"max_attempts": 3, "mode": "standard"}
        )
        sincronizar(
            secoes,
            s3=boto3.client("s3", region_name=args.regiao, config=config),
            bedrock_agent=boto3.client("bedrock-agent", region_name=args.regiao, config=config),
            bucket_manuais=args.bucket_manuais,
            knowledge_base_id=args.knowledge_base_id,
            data_source_id=args.data_source_id,
            tempo_limite_s=args.tempo_limite,
            log=print,
        )
    except carregar_seed.ErroCarga as erro:
        print("Seed inválido. Itens com falha:", file=sys.stderr)
        print(erro, file=sys.stderr)
        return 1
    except ErroSincronizacao as erro:
        print("Sincronização interrompida. Itens com falha:", file=sys.stderr)
        print(erro, file=sys.stderr)
        return 1
    print("Sincronização concluída.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
