#!/usr/bin/env python3
"""Script de carga idempotente do seed (Req 20.3, 20.7, 3.3, 3.4).

Lê ``seed/`` (catálogo, 13 problemas, instruções, mapa do seletor e manuais) e carrega:

* DynamoDB: tabelas ``<prefixo>-modelos``, ``<prefixo>-problemas`` e ``<prefixo>-instrucoes``;
* S3: manuais (um arquivo por seção + ``.metadata.json``) no bucket de manuais.

Fluxo (design, seção 3.10):

1. Fase 1: lê e valida TUDO em memória (limites de texto, 13 problemas, mapa sem sobreposição,
   manuais presentes, tamanho dos grupos). Qualquer falha aborta SEM escrever nada e lista cada
   item com o motivo.
2. Fase 2: grava cada grupo (problemas, catálogo, instruções de cada modelo) em um único
   ``TransactWriteItems``, então um grupo ou entra inteiro ou não entra. Falha: interrompe a
   carga e indica o grupo e o motivo.
3. Manuais: envia ao S3. Em falha, remove os objetos criados NESTA execução e restaura os que
   foram sobrescritos.

Idempotência: as chaves são determinísticas (``modelo_id``, ``problema_id``,
``modelo_id`` + ``problema_id#variante`` e a chave S3 ``manuais/<modelo_id>/<arquivo>``) e a
gravação é um ``Put`` que sobrescreve com o mesmo conteúdo. Duas execuções dão o mesmo conjunto
de registros. Objetos S3 com conteúdo idêntico nem são reenviados.

A lógica recebe clientes boto3 injetados (``carregar``), então é testável com ``moto``. A CLI
fina (``main``) monta os clientes. Configuração por argumentos ou variáveis de ambiente (nunca
segredos; as credenciais AWS vêm da cadeia padrão do boto3):

    python scripts/carregar_seed.py --bucket-manuais <bucket> [--prefixo tres] [--regiao sa-east-1]
    TRES_PREFIXO_TABELAS, TRES_BUCKET_MANUAIS, AWS_REGION

``--validar-apenas`` roda só a fase 1 (não acessa a AWS).

Base de conhecimento (opcional, tarefa 17.2): ``--sincronizar-conhecimento`` (com
``--knowledge-base-id`` ou ``TRES_KNOWLEDGE_BASE_ID``, e opcionalmente ``--data-source-id``)
divide os manuais em uma seção por arquivo, envia ao bucket (prefixo ``secoes/``) e roda a
ingestão da Knowledge Base, esperando terminar. Veja ``sincronizar_conhecimento.py``. Sem a
opção, nada muda.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

_RAIZ = Path(__file__).resolve().parent.parent

# O script roda fora de um pacote instalado: resolve ``dominio`` e ``premissas`` pelo repositório.
for _caminho in (_RAIZ / "packages" / "dominio" / "src", _RAIZ / "services" / "agente"):
    if str(_caminho) not in sys.path:
        sys.path.insert(0, str(_caminho))

from dominio.cache import normalizar_pergunta  # noqa: E402
from dominio.guia import (  # noqa: E402
    VARIANTE_EXTERNO,
    VARIANTE_PADRAO,
    VARIANTES,
    validar_instrucao,
    validar_titulo_problema,
)
from dominio.qr import PADRAO_MODELO_ID, TAMANHO_MAX_MODELO_ID  # noqa: E402
from dominio.seletor import validar_mapa, validar_tamanho_areas  # noqa: E402
from premissas import (  # noqa: E402
    CHAVE_METADADO_MANUAL,
    CHAVE_METADADO_MODELO,
    CHAVE_METADADO_SECAO,
    PREFIXO_S3_MANUAIS,
    REGIAO_PADRAO,
    S3_VECTORS_METADADOS_CUSTOM_MAX_BYTES,
)
from sincronizar_conhecimento import (  # noqa: E402
    TEMPO_LIMITE_INGESTAO_PADRAO_S,
    ErroSincronizacao,
    ResultadoSincronizacao,
    secoes_dos_manuais,
    sincronizar,
)

SEED_PADRAO = _RAIZ / "seed"
PREFIXO_TABELAS_PADRAO = "tres"

# Nomes das tabelas (infra/stacks/dados_stack.py: ``<prefixo>-<nome>``) e atributos de chave.
TABELA_MODELOS = "modelos"  # PK modelo_id
TABELA_PROBLEMAS = "problemas"  # PK problema_id (número)
TABELA_INSTRUCOES = "instrucoes"  # PK modelo_id, SK problema_variante = "<problema_id>#<variante>"

CATALOGO_PK_ATRIBUTO = "catalogo_pk"  # chave do ``gsi_catalogo`` (infra/stacks/dados_stack.py)
CATALOGO_PK_VALOR = "CATALOGO"
TOTAL_PROBLEMAS = 13  # Req 3.1
MAX_ITENS_TRANSACAO = 100  # limite do TransactWriteItems
PROBLEMA_VAZAMENTO = 10  # único com variante ``externo`` (Req 3.11)


# --------------------------------------------------------------------------------------------
# Erros
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Falha:
    """Um item da carga que falhou e o motivo (Req 20.7)."""

    item: str
    motivo: str

    def __str__(self) -> str:
        return f"{self.item}: {self.motivo}"


class ErroCarga(Exception):
    """A carga foi interrompida. ``falhas`` lista cada item com o motivo."""

    def __init__(self, falhas: list[Falha]) -> None:
        self.falhas = list(falhas)
        super().__init__("\n".join(f"- {f}" for f in self.falhas))


# --------------------------------------------------------------------------------------------
# Seed em memória
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ManualLocal:
    """Um manual do seed já lido: arquivo de conteúdo e sidecar de metadados."""

    modelo_id: str
    chave_s3: str
    corpo: bytes
    corpo_sidecar: bytes

    @property
    def chave_sidecar(self) -> str:
        return f"{self.chave_s3}.metadata.json"


@dataclass(frozen=True, slots=True)
class Seed:
    modelos: list[Any]
    problemas: list[Any]
    instrucoes: dict[str, list[Any]] = field(default_factory=dict)  # por modelo_id
    seletores: dict[str, Any] = field(default_factory=dict)  # por modelo_id
    manuais: dict[str, list[ManualLocal]] = field(default_factory=dict)  # por modelo_id


@dataclass(frozen=True, slots=True)
class GrupoDynamo:
    """Itens gravados juntos em um ``TransactWriteItems``."""

    nome: str
    tabela: str
    itens: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class ResultadoCarga:
    grupos: dict[str, int]  # nome do grupo -> itens gravados
    manuais_enviados: tuple[str, ...]  # chaves S3 gravadas nesta execução
    manuais_inalterados: tuple[str, ...]  # chaves S3 que já tinham o mesmo conteúdo
    # Preenchido só quando a sincronização da Knowledge Base foi pedida (tarefa 17.2).
    conhecimento: ResultadoSincronizacao | None = None


def _sem_comentarios(valor: Any) -> Any:
    """Remove, em qualquer nível, as chaves que começam com ``_`` (``_aviso``, ``_nota``)."""
    if isinstance(valor, dict):
        return {k: _sem_comentarios(v) for k, v in valor.items() if not str(k).startswith("_")}
    if isinstance(valor, list):
        return [_sem_comentarios(v) for v in valor]
    return valor


def _ler_json(caminho: Path, item: str, falhas: list[Falha]) -> Any | None:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        falhas.append(Falha(item, "arquivo não encontrado"))
    except (OSError, UnicodeDecodeError) as exc:
        falhas.append(Falha(item, f"não foi possível ler o arquivo: {exc}"))
    except json.JSONDecodeError as exc:
        falhas.append(Falha(item, f"JSON inválido: {exc}"))
    return None


def _lista_de(objeto: Any, chave: str, item: str, falhas: list[Falha]) -> list[Any]:
    lista = objeto.get(chave) if isinstance(objeto, dict) else None
    if not isinstance(lista, list):
        falhas.append(Falha(item, f'esperado um objeto com a lista "{chave}"'))
        return []
    return lista


def _ler_manual(
    seed_dir: Path, modelo_id: str, relativo: Any, falhas: list[Falha]
) -> ManualLocal | None:
    item = f"manuais > {modelo_id} > {relativo}"
    if not isinstance(relativo, str) or not relativo.strip():
        falhas.append(Falha(item, "caminho do manual deve ser um texto não vazio"))
        return None
    raiz = seed_dir.resolve()
    caminho = (seed_dir / relativo).resolve()
    if not caminho.is_relative_to(raiz):
        falhas.append(Falha(item, "o caminho do manual sai do diretório do seed"))
        return None
    sidecar = caminho.with_name(caminho.name + ".metadata.json")
    try:
        corpo = caminho.read_bytes()
    except OSError:
        falhas.append(Falha(item, "arquivo do manual não encontrado"))
        return None
    if not corpo.strip():
        falhas.append(Falha(item, "arquivo do manual está vazio"))
        return None
    try:
        corpo_sidecar = sidecar.read_bytes()
    except OSError:
        falhas.append(Falha(item, f"metadados ausentes ({sidecar.name})"))
        return None

    try:
        meta = json.loads(corpo_sidecar)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        falhas.append(Falha(f"{item} > {sidecar.name}", f"JSON inválido: {exc}"))
        return None
    atributos = meta.get("metadataAttributes") if isinstance(meta, dict) else None
    if not isinstance(atributos, dict):
        falhas.append(Falha(f"{item} > {sidecar.name}", 'esperado o objeto "metadataAttributes"'))
        return None
    erros: list[str] = []
    if atributos.get(CHAVE_METADADO_MODELO) != modelo_id:
        erros.append(f'"{CHAVE_METADADO_MODELO}" deve ser "{modelo_id}"')
    for chave in (CHAVE_METADADO_MANUAL, CHAVE_METADADO_SECAO):
        valor = atributos.get(chave)
        # ``secao`` é opcional enquanto o manual não é dividido por seção (tarefa 17.2).
        if chave == CHAVE_METADADO_SECAO and valor is None:
            continue
        if not isinstance(valor, str) or not valor.strip():
            erros.append(f'"{chave}" deve ser um texto não vazio')
    if len(corpo_sidecar) > S3_VECTORS_METADADOS_CUSTOM_MAX_BYTES:
        erros.append(f"metadados com mais de {S3_VECTORS_METADADOS_CUSTOM_MAX_BYTES} bytes")
    if erros:
        falhas.extend(Falha(f"{item} > {sidecar.name}", e) for e in erros)
        return None

    return ManualLocal(
        modelo_id=modelo_id,
        chave_s3=f"{PREFIXO_S3_MANUAIS}{modelo_id}/{caminho.name}",
        corpo=corpo,
        corpo_sidecar=corpo_sidecar,
    )


def ler_seed(seed_dir: Path) -> tuple[Seed, list[Falha]]:
    """Lê o seed para a memória. Devolve o que foi lido e as falhas de leitura."""
    seed_dir = Path(seed_dir)
    falhas: list[Falha] = []

    catalogo = _ler_json(seed_dir / "catalogo.json", "catalogo.json", falhas)
    modelos = _lista_de(catalogo, "modelos", "catalogo.json", falhas) if catalogo else []
    problemas_raw = _ler_json(seed_dir / "problemas.json", "problemas.json", falhas)
    problemas = (
        _lista_de(problemas_raw, "problemas", "problemas.json", falhas) if problemas_raw else []
    )
    modelos = _sem_comentarios(modelos)
    problemas = _sem_comentarios(problemas)

    instrucoes: dict[str, list[Any]] = {}
    for caminho in sorted((seed_dir / "instrucoes").glob("*.json")):
        item = f"instrucoes/{caminho.name}"
        dados = _ler_json(caminho, item, falhas)
        if dados is not None:
            instrucoes[caminho.stem] = _sem_comentarios(
                _lista_de(dados, "instrucoes", item, falhas)
            )

    seletores: dict[str, Any] = {}
    for caminho in sorted((seed_dir / "seletor").glob("*.json")):
        dados = _ler_json(caminho, f"seletor/{caminho.name}", falhas)
        if dados is not None:
            seletores[caminho.stem] = _sem_comentarios(dados)

    manuais: dict[str, list[ManualLocal]] = {}
    for modelo in modelos:
        modelo_id = modelo.get("modelo_id") if isinstance(modelo, dict) else None
        lista = modelo.get("manuais", []) if isinstance(modelo, dict) else []
        if not isinstance(modelo_id, str) or not isinstance(lista, list):
            continue  # o erro estrutural sai em ``validar_seed``
        for relativo in lista:
            manual = _ler_manual(seed_dir, modelo_id, relativo, falhas)
            if manual is not None:
                manuais.setdefault(modelo_id, []).append(manual)

    return Seed(modelos, problemas, instrucoes, seletores, manuais), falhas


# --------------------------------------------------------------------------------------------
# Fase 1: validação em memória
# --------------------------------------------------------------------------------------------


def _texto(valor: Any) -> bool:
    return isinstance(valor, str) and bool(valor.strip())


def _validar_problemas(problemas: list[Any], falhas: list[Falha]) -> dict[int, str]:
    """Valida os 13 Problemas_Catalogados. Devolve ``problema_id -> título`` dos válidos."""
    titulos: dict[int, str] = {}
    if len(problemas) != TOTAL_PROBLEMAS:
        falhas.append(
            Falha(
                "problemas.json",
                f"devem existir exatamente {TOTAL_PROBLEMAS} problemas (há {len(problemas)})",
            )
        )
    slugs: set[str] = set()
    for i, p in enumerate(problemas):
        rotulo = f"problemas.json > problema #{i + 1}"
        if not isinstance(p, dict):
            falhas.append(Falha(rotulo, "deve ser um objeto"))
            continue
        pid = p.get("problema_id")
        if isinstance(pid, bool) or not isinstance(pid, int) or not 1 <= pid <= TOTAL_PROBLEMAS:
            falhas.append(Falha(rotulo, f"problema_id deve ser inteiro de 1 a {TOTAL_PROBLEMAS}"))
            continue
        rotulo = f"problemas.json > problema {pid}"
        if pid in titulos:
            falhas.append(Falha(rotulo, "problema_id repetido"))
            continue
        ordem = p.get("ordem")
        # ``ordem == problema_id`` e ``problema_id`` único já garantem ordens sem repetição.
        if isinstance(ordem, bool) or not isinstance(ordem, int) or ordem != pid:
            falhas.append(Falha(rotulo, "ordem deve ser igual ao problema_id (ordem do Req 3.1)"))
        for erro in validar_titulo_problema(p.get("titulo")):
            falhas.append(Falha(f"{rotulo} > {erro.campo}", erro.motivo))
        for campo in ("slug", "icone", "icone_alt"):
            if not _texto(p.get(campo)):
                falhas.append(Falha(f"{rotulo} > {campo}", "obrigatório e não vazio"))
        slug = p.get("slug")
        if isinstance(slug, str):
            if slug in slugs:
                falhas.append(Falha(f"{rotulo} > slug", f"slug repetido: {slug}"))
            slugs.add(slug)
        titulos[pid] = p.get("titulo") if isinstance(p.get("titulo"), str) else ""
    faltando = sorted(set(range(1, TOTAL_PROBLEMAS + 1)) - set(titulos))
    if faltando and len(problemas) == TOTAL_PROBLEMAS:
        falhas.append(Falha("problemas.json", f"problema_id ausente: {faltando}"))
    return titulos


def _validar_modelos(seed: Seed, falhas: list[Falha]) -> set[str]:
    ids: set[str] = set()
    for i, m in enumerate(seed.modelos):
        rotulo = f"catalogo.json > modelo #{i + 1}"
        if not isinstance(m, dict):
            falhas.append(Falha(rotulo, "deve ser um objeto"))
            continue
        mid = m.get("modelo_id")
        if (
            not isinstance(mid, str)
            or len(mid) > TAMANHO_MAX_MODELO_ID
            or PADRAO_MODELO_ID.fullmatch(mid) is None
        ):
            falhas.append(Falha(rotulo, "modelo_id deve ser um slug (a-z, 0-9 e hífens)"))
            continue
        rotulo = f"catalogo.json > modelo {mid}"
        if mid in ids:
            falhas.append(Falha(rotulo, "modelo_id repetido"))
            continue
        ids.add(mid)
        for campo in ("nome", "nome_normalizado", "foto_url"):
            if not _texto(m.get(campo)):
                falhas.append(Falha(f"{rotulo} > {campo}", "obrigatório e não vazio"))
        if _texto(m.get("nome")) and _texto(m.get("nome_normalizado")):
            esperado = normalizar_pergunta(m["nome"])
            if m["nome_normalizado"] != esperado:
                falhas.append(
                    Falha(
                        f"{rotulo} > nome_normalizado",
                        f'deve ser "{esperado}" (sem acento, caixa e pontuação; usado na busca)',
                    )
                )
        volts = m.get("voltagens")
        if not isinstance(volts, list) or not volts or not all(_texto(v) for v in volts):
            falhas.append(Falha(f"{rotulo} > voltagens", "lista não vazia de textos"))
        if not isinstance(m.get("ativo"), bool):
            falhas.append(Falha(f"{rotulo} > ativo", "deve ser verdadeiro ou falso"))
        manuais = m.get("manuais")
        if not isinstance(manuais, list):
            falhas.append(Falha(f"{rotulo} > manuais", "deve ser uma lista"))
        else:
            chaves = [mn.chave_s3 for mn in seed.manuais.get(mid, [])]
            if len(chaves) != len(set(chaves)):
                falhas.append(
                    Falha(f"{rotulo} > manuais", "dois manuais com o mesmo nome de arquivo")
                )
    return ids


def _validar_instrucoes(
    seed: Seed, modelos: set[str], titulos: dict[int, str], falhas: list[Falha]
) -> None:
    com_instrucoes_completas = 0
    for mid, lista in seed.instrucoes.items():
        arquivo = f"instrucoes/{mid}.json"
        if mid not in modelos:
            falhas.append(Falha(arquivo, f"modelo {mid} não existe no catálogo"))
            continue
        vistos: set[tuple[int, str]] = set()
        for i, ins in enumerate(lista):
            rotulo = f"{arquivo} > instrução #{i + 1}"
            if not isinstance(ins, dict):
                falhas.append(Falha(rotulo, "deve ser um objeto"))
                continue
            pid, variante = ins.get("problema_id"), ins.get("variante")
            if isinstance(pid, bool) or not isinstance(pid, int) or pid not in range(1, 14):
                falhas.append(
                    Falha(rotulo, f"problema_id deve ser inteiro de 1 a {TOTAL_PROBLEMAS}")
                )
                continue
            rotulo = f"{arquivo} > problema {pid} ({variante})"
            if ins.get("modelo_id") != mid:
                falhas.append(Falha(rotulo, f'modelo_id deve ser "{mid}" (nome do arquivo)'))
            if variante not in VARIANTES:
                falhas.append(Falha(rotulo, f"variante deve ser uma de {', '.join(VARIANTES)}"))
                continue
            if variante == VARIANTE_EXTERNO and pid != PROBLEMA_VAZAMENTO:
                falhas.append(Falha(rotulo, "variante externo só existe para Vazamento (Req 3.11)"))
            if (pid, variante) in vistos:
                falhas.append(Falha(rotulo, "instrução repetida"))
            vistos.add((pid, variante))
            for erro in validar_instrucao(ins, titulos.get(pid)):
                falhas.append(Falha(f"{rotulo} > {erro.campo}", erro.motivo))
        ausentes = [p for p in range(1, 14) if (p, VARIANTE_PADRAO) not in vistos]
        if ausentes:
            falhas.append(
                Falha(arquivo, f"faltam instruções padrao para os problemas {ausentes} (Req 3.1)")
            )
        else:
            com_instrucoes_completas += 1
    if com_instrucoes_completas == 0:
        falhas.append(
            Falha("instrucoes/", "ao menos um modelo precisa das instruções dos 13 problemas")
        )


def _validar_seletores(
    seed: Seed, modelos: set[str], titulos: dict[int, str], falhas: list[Falha]
) -> None:
    for mid, mapa in seed.seletores.items():
        arquivo = f"seletor/{mid}.json"
        if mid not in modelos:
            falhas.append(Falha(arquivo, f"modelo {mid} não existe no catálogo"))
            continue
        for erro in validar_mapa(mapa) + validar_tamanho_areas(mapa):
            falhas.append(Falha(f"{arquivo} > {erro.campo}", erro.motivo))
        regras = mapa.get("regras") if isinstance(mapa, dict) else None
        for i, regra in enumerate(regras if isinstance(regras, list) else []):
            ids = regra.get("problemas") if isinstance(regra, dict) else None
            for pid in ids if isinstance(ids, list) else []:
                if pid not in titulos:
                    falhas.append(
                        Falha(f"{arquivo} > regras[{i}].problemas", f"problema {pid} não existe")
                    )


def validar_seed(seed: Seed) -> list[Falha]:
    """Valida o seed já lido. Lista vazia significa que a carga pode começar."""
    falhas: list[Falha] = []
    titulos = _validar_problemas(seed.problemas, falhas)
    modelos = _validar_modelos(seed, falhas)
    if not modelos:
        falhas.append(Falha("catalogo.json", "o catálogo precisa de ao menos um modelo"))
    _validar_instrucoes(seed, modelos, titulos, falhas)
    _validar_seletores(seed, modelos, titulos, falhas)
    if not any(seed.manuais.get(m) for m in modelos):
        falhas.append(Falha("manuais", "ao menos um modelo precisa de manual (Req 20.3)"))
    return falhas


# --------------------------------------------------------------------------------------------
# Plano de gravação
# --------------------------------------------------------------------------------------------


def montar_grupos(seed: Seed, prefixo: str) -> list[GrupoDynamo]:
    """Monta os grupos (ordem fixa) com chaves determinísticas. Não acessa a AWS."""
    problemas = tuple(dict(p) for p in sorted(seed.problemas, key=lambda p: p["problema_id"]))
    modelos: list[dict[str, Any]] = []
    for m in sorted(seed.modelos, key=lambda m: m["modelo_id"]):
        item = {k: v for k, v in m.items() if k != "manuais"}
        # Partição única do índice ``gsi_catalogo``: a API lista o catálogo sem ``Scan``.
        item[CATALOGO_PK_ATRIBUTO] = CATALOGO_PK_VALOR
        item["manuais"] = [mn.chave_s3 for mn in seed.manuais.get(m["modelo_id"], [])]
        if m["modelo_id"] in seed.seletores:
            item["seletor"] = seed.seletores[m["modelo_id"]]
        modelos.append(item)

    grupos = [
        GrupoDynamo("problemas", f"{prefixo}-{TABELA_PROBLEMAS}", problemas),
        GrupoDynamo("catalogo", f"{prefixo}-{TABELA_MODELOS}", tuple(modelos)),
    ]
    for mid in sorted(seed.instrucoes):
        itens = []
        for ins in sorted(seed.instrucoes[mid], key=lambda i: (i["problema_id"], i["variante"])):
            item = dict(ins)
            item["problema_variante"] = f"{ins['problema_id']}#{ins['variante']}"
            itens.append(item)
        grupos.append(
            GrupoDynamo(f"instrucoes:{mid}", f"{prefixo}-{TABELA_INSTRUCOES}", tuple(itens))
        )
    return grupos


def _validar_grupos(grupos: list[GrupoDynamo]) -> list[Falha]:
    return [
        Falha(
            f"grupo {g.nome}",
            f"{len(g.itens)} itens excedem o limite de {MAX_ITENS_TRANSACAO} da transação",
        )
        for g in grupos
        if len(g.itens) > MAX_ITENS_TRANSACAO
    ]


def _preparar_secoes(seed: Seed) -> tuple[list[Any], list[Falha]]:
    """Divide os manuais em seções (puro, sem AWS). Falhas no formato de ``Falha``."""
    try:
        return secoes_dos_manuais(seed.manuais), []
    except ErroSincronizacao as erro:
        return [], [Falha(f.item, f.motivo) for f in erro.falhas]


def validar(seed_dir: Path, *, conhecimento: bool = False) -> Seed:
    """Fase 1 completa (leitura e validação). Levanta ``ErroCarga`` com todas as falhas.

    Com ``conhecimento=True``, confere também que todos os manuais se dividem em seções.
    """
    seed, falhas = ler_seed(seed_dir)
    falhas = falhas + validar_seed(seed)
    if not falhas:
        falhas = _validar_grupos(montar_grupos(seed, PREFIXO_TABELAS_PADRAO))
    if not falhas and conhecimento:
        falhas = _preparar_secoes(seed)[1]
    if falhas:
        raise ErroCarga(falhas)
    return seed


# --------------------------------------------------------------------------------------------
# Fase 2: gravação
# --------------------------------------------------------------------------------------------


def _para_dynamo(valor: Any) -> Any:
    """Prepara o valor para o serializador do DynamoDB (que não aceita ``float``)."""
    if isinstance(valor, float):
        return Decimal(str(valor))
    if isinstance(valor, dict):
        return {k: _para_dynamo(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_para_dynamo(v) for v in valor]
    return valor


def _descrever_erro(exc: Exception) -> str:
    resposta = getattr(exc, "response", None)
    if not isinstance(resposta, Mapping):
        return f"{type(exc).__name__}: {exc}"
    erro = resposta.get("Error", {})
    texto = f"{erro.get('Code', type(exc).__name__)}: {erro.get('Message', exc)}"
    razoes = [r for r in resposta.get("CancellationReasons", []) if r.get("Code") != "None"]
    if razoes:
        texto += " (" + "; ".join(f"{r.get('Code')}: {r.get('Message', '')}" for r in razoes) + ")"
    return texto


def _gravar_grupo(dynamodb: Any, grupo: GrupoDynamo) -> None:
    from boto3.dynamodb.types import TypeSerializer

    serializador = TypeSerializer()
    itens = [
        {
            "Put": {
                "TableName": grupo.tabela,
                "Item": {k: serializador.serialize(_para_dynamo(v)) for k, v in item.items()},
            }
        }
        for item in grupo.itens
    ]
    try:
        dynamodb.transact_write_items(TransactItems=itens)
    except Exception as exc:
        raise ErroCarga(
            [Falha(f"grupo {grupo.nome} (tabela {grupo.tabela})", _descrever_erro(exc))]
        ) from exc


def _ler_objeto(s3: Any, bucket: str, chave: str) -> tuple[bytes, str] | None:
    """Conteúdo e tipo do objeto existente, ou ``None`` se não existe."""
    try:
        resposta = s3.get_object(Bucket=bucket, Key=chave)
    except Exception as exc:
        codigo = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if codigo in ("NoSuchKey", "404", "NotFound"):
            return None
        raise
    return resposta["Body"].read(), resposta.get("ContentType", "application/octet-stream")


def _enviar_manuais(
    s3: Any, bucket: str, manuais: list[ManualLocal]
) -> tuple[list[str], list[str]]:
    """Envia os manuais. Em falha, desfaz esta execução e levanta ``ErroCarga``.

    Devolve ``(enviados, inalterados)``. Desfazer = apagar o que foi criado agora e restaurar o
    que foi sobrescrito, para não deixar manual parcial nem perder a versão anterior.
    """
    objetos = []
    for mn in manuais:
        objetos.append((mn.chave_s3, mn.corpo, "text/markdown; charset=utf-8"))
        objetos.append((mn.chave_sidecar, mn.corpo_sidecar, "application/json"))

    criados: list[str] = []
    sobrescritos: dict[str, tuple[bytes, str]] = {}
    inalterados: list[str] = []
    atual = "manuais"
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
        problemas_ao_desfazer: list[str] = []
        for chave in criados:
            try:
                s3.delete_object(Bucket=bucket, Key=chave)
            except Exception as exc_rm:
                problemas_ao_desfazer.append(f"{chave}: {_descrever_erro(exc_rm)}")
        for chave, (corpo, tipo) in sobrescritos.items():
            try:
                s3.put_object(Bucket=bucket, Key=chave, Body=corpo, ContentType=tipo)
            except Exception as exc_rs:
                problemas_ao_desfazer.append(f"{chave}: {_descrever_erro(exc_rs)}")
        falhas = [Falha(f"manual {atual}", motivo)]
        if problemas_ao_desfazer:
            falhas.extend(
                Falha("desfazer envio de manual", f"objeto pode ter ficado inconsistente: {p}")
                for p in problemas_ao_desfazer
            )
        raise ErroCarga(falhas) from exc
    return criados, inalterados


def carregar(
    seed_dir: Path,
    *,
    dynamodb: Any,
    s3: Any,
    bucket_manuais: str | None,
    prefixo: str = PREFIXO_TABELAS_PADRAO,
    log: Callable[[str], None] = lambda _msg: None,
    bedrock_agent: Any = None,
    knowledge_base_id: str | None = None,
    data_source_id: str | None = None,
    tempo_limite_ingestao_s: float = TEMPO_LIMITE_INGESTAO_PADRAO_S,
    dormir: Callable[[float], None] | None = None,
) -> ResultadoCarga:
    """Carrega o seed. ``dynamodb`` e ``s3`` são clientes boto3 (``boto3.client(...)``).

    Levanta ``ErroCarga`` (com cada item e motivo) se a validação ou qualquer gravação falhar.
    Falha na validação não escreve nada.

    Passo opcional (tarefa 17.2): com ``knowledge_base_id`` e ``bedrock_agent`` (cliente
    ``bedrock-agent``), depois dos manuais divide cada um em seções, envia ao bucket e roda a
    ingestão da Knowledge Base (``sincronizar_conhecimento``). A divisão em seções é validada na
    fase 1, antes de qualquer gravação. Sem ``knowledge_base_id``, o comportamento é o de sempre.
    Se o envio das seções ou a ingestão falhar, a carga é interrompida com o item e o motivo; o
    que já foi gravado fica (a carga é idempotente, basta rodar de novo).
    """
    seed, falhas = ler_seed(seed_dir)
    falhas += validar_seed(seed)
    grupos = montar_grupos(seed, prefixo) if not falhas else []
    falhas += _validar_grupos(grupos)
    if not falhas and not bucket_manuais:
        falhas.append(Falha("configuração", "bucket de manuais não informado"))
    secoes: list[Any] = []
    if not falhas and knowledge_base_id:
        if bedrock_agent is None:
            falhas.append(Falha("configuração", "cliente bedrock-agent não informado"))
        secoes, falhas_secoes = _preparar_secoes(seed)
        falhas += falhas_secoes
    if falhas:
        raise ErroCarga(falhas)
    log(f"Seed validado: {sum(len(g.itens) for g in grupos)} registros em {len(grupos)} grupos.")

    resultado: dict[str, int] = {}
    for grupo in grupos:
        _gravar_grupo(dynamodb, grupo)
        resultado[grupo.nome] = len(grupo.itens)
        log(f"Grupo {grupo.nome}: {len(grupo.itens)} registros gravados em {grupo.tabela}.")

    manuais = [mn for m in sorted(seed.manuais) for mn in seed.manuais[m]]
    enviados, inalterados = _enviar_manuais(s3, bucket_manuais, manuais)
    log(f"Manuais: {len(enviados)} objetos enviados, {len(inalterados)} já estavam iguais.")

    conhecimento = None
    if knowledge_base_id:
        opcoes = {"dormir": dormir} if dormir is not None else {}
        try:
            conhecimento = sincronizar(
                secoes,
                s3=s3,
                bedrock_agent=bedrock_agent,
                bucket_manuais=bucket_manuais,
                knowledge_base_id=knowledge_base_id,
                data_source_id=data_source_id,
                tempo_limite_s=tempo_limite_ingestao_s,
                log=log,
                **opcoes,
            )
        except ErroSincronizacao as erro:
            raise ErroCarga([Falha(f.item, f.motivo) for f in erro.falhas]) from erro
    return ResultadoCarga(resultado, tuple(enviados), tuple(inalterados), conhecimento)


# --------------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------------


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Carrega o seed no DynamoDB e os manuais no S3.")
    p.add_argument("--seed-dir", type=Path, default=SEED_PADRAO, help="diretório do seed")
    p.add_argument(
        "--prefixo",
        default=os.environ.get("TRES_PREFIXO_TABELAS", PREFIXO_TABELAS_PADRAO),
        help="prefixo das tabelas (env TRES_PREFIXO_TABELAS; padrão: tres)",
    )
    p.add_argument(
        "--bucket-manuais",
        default=os.environ.get("TRES_BUCKET_MANUAIS"),
        help="bucket S3 dos manuais (env TRES_BUCKET_MANUAIS)",
    )
    p.add_argument(
        "--regiao",
        default=os.environ.get("AWS_REGION") or REGIAO_PADRAO,
        help=f"região AWS (env AWS_REGION; padrão: {REGIAO_PADRAO})",
    )
    p.add_argument(
        "--validar-apenas", action="store_true", help="só valida o seed, sem acessar a AWS"
    )
    p.add_argument(
        "--sincronizar-conhecimento",
        action="store_true",
        help="depois dos manuais, envia as seções e roda a ingestão da Knowledge Base",
    )
    p.add_argument(
        "--knowledge-base-id",
        default=os.environ.get("TRES_KNOWLEDGE_BASE_ID"),
        help="id da Knowledge Base (env TRES_KNOWLEDGE_BASE_ID; saída KnowledgeBaseId da stack)",
    )
    p.add_argument(
        "--data-source-id",
        default=os.environ.get("TRES_DATA_SOURCE_ID"),
        help="id do data source (env TRES_DATA_SOURCE_ID; padrão: o único da Knowledge Base)",
    )
    p.add_argument(
        "--tempo-limite-ingestao",
        type=float,
        default=TEMPO_LIMITE_INGESTAO_PADRAO_S,
        help="segundos de espera pela ingestão (padrão: %(default)s)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(argv)
    try:
        if args.validar_apenas:
            seed = validar(args.seed_dir, conhecimento=args.sincronizar_conhecimento)
            print(f"Seed válido: {len(seed.modelos)} modelos, {len(seed.problemas)} problemas.")
            return 0
        if not args.bucket_manuais:
            raise ErroCarga(
                [Falha("configuração", "informe --bucket-manuais ou TRES_BUCKET_MANUAIS")]
            )
        if args.sincronizar_conhecimento and not args.knowledge_base_id:
            raise ErroCarga(
                [
                    Falha(
                        "configuração",
                        "informe --knowledge-base-id ou TRES_KNOWLEDGE_BASE_ID para sincronizar",
                    )
                ]
            )

        import boto3
        from botocore.config import Config

        config = Config(
            connect_timeout=5, read_timeout=10, retries={"max_attempts": 3, "mode": "standard"}
        )
        dynamodb = boto3.client("dynamodb", region_name=args.regiao, config=config)
        s3 = boto3.client("s3", region_name=args.regiao, config=config)
        extra: dict[str, Any] = {}
        if args.sincronizar_conhecimento:
            extra = {
                "bedrock_agent": boto3.client(
                    "bedrock-agent", region_name=args.regiao, config=config
                ),
                "knowledge_base_id": args.knowledge_base_id,
                "data_source_id": args.data_source_id,
                "tempo_limite_ingestao_s": args.tempo_limite_ingestao,
            }
        carregar(
            args.seed_dir,
            dynamodb=dynamodb,
            s3=s3,
            bucket_manuais=args.bucket_manuais,
            prefixo=args.prefixo,
            log=print,
            **extra,
        )
    except ErroCarga as erro:
        print("Carga interrompida. Itens com falha:", file=sys.stderr)
        print(erro, file=sys.stderr)
        return 1
    print("Carga concluída.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
