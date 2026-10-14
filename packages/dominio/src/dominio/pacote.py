"""Pacote_Repasse: esquema versão 1, validação, serialização e montagem (Req 10).

Funções puras. A única leitura externa é o arquivo do JSON Schema empacotado junto com o
código (acesso local somente leitura, via `importlib.resources`). A validação usa a
biblioteca `jsonschema`; não existe validador próprio (design, seção 3.7).
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from typing import Any, Final, Literal, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from dominio.erros import ErroDominio
from dominio.tipos import Classificacao, Prioridade

SCHEMA_VERSION: Final = 1
NAO_INFORMADO: Final = "não informado"

# Valores de fallback do Req 10.4 (texto exato exigido pelo requisito).
RESUMO_FALLBACK: Final = "Resumo indisponível — ver histórico da Jornada"
SENTIMENTO_FALLBACK: Final = "neutro"
PROXIMA_ACAO_FALLBACK: Final = "Revisar o histórico da Jornada"

RESUMO_MAX: Final = 300
PROXIMA_ACAO_MAX: Final = 200

Origem = Literal["qr", "busca"]
CamadaPasso = Literal["guia", "ia"]
ResultadoPasso = Literal["sim", "não", "sem resposta"]
Sentimento = Literal["neutro", "frustração moderada", "frustração alta"]
MimeAnexo = Literal["image/jpeg", "image/png"]

SENTIMENTOS: Final[tuple[str, ...]] = ("neutro", "frustração moderada", "frustração alta")


@dataclass(frozen=True, slots=True)
class ErroCampo:
    """Um campo inválido e o motivo da invalidade (Req 10.7)."""

    campo: str
    motivo: str


class ErroPacoteInvalido(ErroDominio):
    """JSON que não é um Pacote_Repasse válido. `erros` lista cada campo inválido."""

    def __init__(self, erros: list[ErroCampo]) -> None:
        self.erros = erros
        super().__init__("; ".join(f"{e.campo}: {e.motivo}" for e in erros))


@dataclass(frozen=True, slots=True)
class ItemJaTentado:
    """Passo já tentado pelo Consumidor, em ordem cronológica na lista."""

    passo: str
    camada: CamadaPasso
    resultado: ResultadoPasso


@dataclass(frozen=True, slots=True)
class Anexo:
    chave: str
    mime: MimeAnexo


@dataclass(frozen=True, slots=True)
class PacoteRepasse:
    """Pacote_Repasse versão 1 (Req 10.1). Imutável; listas viram tuplas."""

    numero_chamado: str
    modelo: str
    numero_serie: str
    origem: Origem
    categoria: str
    resumo: str
    ja_tentado: tuple[ItemJaTentado, ...]
    classificacao: Classificacao
    prioridade: Prioridade
    canal_recomendado: str
    sentimento: Sentimento
    anexos: tuple[Anexo, ...]
    proxima_acao: str
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True, slots=True)
class CamposDeterministicos:
    """Campos do Req 10.2, vindos da Jornada e do Motor_Escalada (sem modelo de linguagem).

    `numero_serie` ausente (`None` ou vazio) vira "não informado" (Req 10.9).
    """

    numero_chamado: str
    modelo: str
    origem: Origem
    categoria: str
    classificacao: Classificacao
    prioridade: Prioridade
    canal_recomendado: str
    numero_serie: str | None = None
    ja_tentado: tuple[ItemJaTentado, ...] = ()
    anexos: tuple[Anexo, ...] = ()


@dataclass(frozen=True, slots=True)
class SaidaAssistente:
    """Resposta do Assistente_IA no modo `resumo_repasse` (Req 10.3).

    `erro` e `tempo_esgotado` (mais de 10 s, Req 10.4) são decididos por quem chama o agente.
    """

    resumo: str | None = None
    sentimento: str | None = None
    proxima_acao: str | None = None
    erro: bool = False
    tempo_esgotado: bool = False


# --------------------------------------------------------------------------- esquema


@lru_cache(maxsize=1)
def _validador() -> Draft202012Validator:
    texto = (
        resources.files("dominio")
        .joinpath("schemas", "pacote_repasse_v1.json")
        .read_text(encoding="utf-8")
    )
    esquema = json.loads(texto)
    Draft202012Validator.check_schema(esquema)
    return Draft202012Validator(esquema)


def esquema_pacote() -> dict[str, Any]:
    """Cópia do JSON Schema versão 1 do Pacote_Repasse."""
    return json.loads(json.dumps(_validador().schema))


_TIPOS_JSON = {
    "string": "texto",
    "object": "objeto",
    "array": "lista",
    "integer": "inteiro",
    "number": "número",
    "boolean": "booleano",
    "null": "nulo",
}


def _caminho(partes: Any) -> str:
    saida = ""
    for parte in partes:
        if isinstance(parte, int):
            saida += f"[{parte}]"
        else:
            saida += f".{parte}" if saida else str(parte)
    return saida


def _juntar(base: str, nome: str) -> str:
    return f"{base}.{nome}" if base else nome


def _motivo(erro: ValidationError, campo: str) -> str:
    validador = erro.validator
    esperado = erro.validator_value
    if validador == "required":
        return "campo obrigatório ausente"
    if validador == "additionalProperties":
        return "campo não previsto no esquema"
    if validador == "const":
        if campo == "schema_version":
            return f"versão de esquema não suportada (suportada: {esperado})"
        return f"valor deve ser {esperado!r}"
    if validador == "enum":
        permitidos = ", ".join(repr(v) for v in esperado)
        return f"valor fora do domínio (permitidos: {permitidos})"
    if validador == "type":
        tipos = esperado if isinstance(esperado, list) else [esperado]
        nomes = " ou ".join(_TIPOS_JSON.get(t, str(t)) for t in tipos)
        return f"tipo inválido (esperado: {nomes})"
    if validador == "pattern":
        return "formato inválido"
    if validador == "minLength":
        return f"texto curto demais (mínimo {esperado} caractere(s))"
    if validador == "maxLength":
        return f"texto longo demais (máximo {esperado} caracteres)"
    if validador == "maxItems":
        return f"itens demais (máximo {esperado})"
    return str(erro.message)


def _campos_e_motivos(erro: ValidationError) -> list[ErroCampo]:
    base = _caminho(erro.absolute_path)
    instancia = erro.instance
    if erro.validator == "required" and isinstance(instancia, dict):
        faltando = [n for n in erro.validator_value if n not in instancia]
        return [ErroCampo(_juntar(base, n), _motivo(erro, n)) for n in faltando]
    if erro.validator == "additionalProperties" and isinstance(instancia, dict):
        previstas = erro.schema.get("properties", {})
        extras = [k for k in instancia if k not in previstas]
        return [ErroCampo(_juntar(base, str(k)), _motivo(erro, str(k))) for k in extras]
    campo = base or "$"
    return [ErroCampo(campo, _motivo(erro, campo))]


def validar_pacote(obj: Mapping[str, Any]) -> list[ErroCampo]:
    """Valida `obj` contra o esquema v1 e devolve **todos** os erros (Req 10.7).

    Lista vazia significa válido. A raiz é indicada por "$". Ordem determinística.
    """
    alvo: Any = dict(obj) if isinstance(obj, Mapping) else obj
    erros: set[ErroCampo] = set()
    for erro in _validador().iter_errors(alvo):
        erros.update(_campos_e_motivos(erro))
    return sorted(erros, key=lambda e: (e.campo, e.motivo))


# --------------------------------------------------------------------- serialização


def pacote_para_dict(p: PacoteRepasse) -> dict[str, Any]:
    """Representação JSON-compatível do Pacote, na ordem dos campos do esquema."""
    return {
        "schema_version": p.schema_version,
        "numero_chamado": p.numero_chamado,
        "modelo": p.modelo,
        "numero_serie": p.numero_serie,
        "origem": p.origem,
        "categoria": p.categoria,
        "resumo": p.resumo,
        "ja_tentado": [
            {"passo": i.passo, "camada": i.camada, "resultado": i.resultado} for i in p.ja_tentado
        ],
        "classificacao": p.classificacao,
        "prioridade": p.prioridade,
        "canal_recomendado": p.canal_recomendado,
        "sentimento": p.sentimento,
        "anexos": [{"chave": a.chave, "mime": a.mime} for a in p.anexos],
        "proxima_acao": p.proxima_acao,
    }


def pacote_para_json(p: PacoteRepasse) -> str:
    """JSON do Pacote com acentos preservados (`ensure_ascii=False`, Req 10.5, 10.6).

    O texto devolvido deve ser gravado/transmitido em UTF-8.
    """
    return json.dumps(pacote_para_dict(p), ensure_ascii=False, allow_nan=False)


def _de_dict_valido(d: Mapping[str, Any]) -> PacoteRepasse:
    return PacoteRepasse(
        schema_version=d["schema_version"],
        numero_chamado=d["numero_chamado"],
        modelo=d["modelo"],
        numero_serie=d["numero_serie"],
        origem=d["origem"],
        categoria=d["categoria"],
        resumo=d["resumo"],
        ja_tentado=tuple(
            ItemJaTentado(passo=i["passo"], camada=i["camada"], resultado=i["resultado"])
            for i in d["ja_tentado"]
        ),
        classificacao=d["classificacao"],
        prioridade=d["prioridade"],
        canal_recomendado=d["canal_recomendado"],
        sentimento=d["sentimento"],
        anexos=tuple(Anexo(chave=a["chave"], mime=a["mime"]) for a in d["anexos"]),
        proxima_acao=d["proxima_acao"],
    )


def pacote_de_json(s: str) -> PacoteRepasse:
    """Desserializa e valida. Levanta `ErroPacoteInvalido` com todos os campos inválidos."""
    try:
        obj = json.loads(s)
    except (ValueError, RecursionError) as exc:
        raise ErroPacoteInvalido([ErroCampo("$", f"JSON inválido: {exc}")]) from exc
    erros = validar_pacote(obj) if isinstance(obj, dict) else [ErroCampo("$", "esperado objeto")]
    if erros:
        raise ErroPacoteInvalido(erros)
    return _de_dict_valido(obj)


# ----------------------------------------------------------------------- montagem


def _montar(
    det: CamposDeterministicos, resumo: str, sentimento: Sentimento, proxima_acao: str
) -> PacoteRepasse:
    return PacoteRepasse(
        numero_chamado=det.numero_chamado,
        modelo=det.modelo,
        numero_serie=det.numero_serie or NAO_INFORMADO,
        origem=det.origem,
        categoria=det.categoria,
        resumo=resumo,
        ja_tentado=tuple(det.ja_tentado),
        classificacao=det.classificacao,
        prioridade=det.prioridade,
        canal_recomendado=det.canal_recomendado,
        sentimento=sentimento,
        anexos=tuple(det.anexos),
        proxima_acao=proxima_acao,
    )


def pacote_fallback(det: CamposDeterministicos) -> PacoteRepasse:
    """Pacote com os campos determinísticos e os três campos de IA em fallback (Req 10.4)."""
    return _montar(det, RESUMO_FALLBACK, SENTIMENTO_FALLBACK, PROXIMA_ACAO_FALLBACK)


def saida_assistente_valida(saida: SaidaAssistente | None) -> bool:
    """Verdadeiro se a saída pode preencher resumo, sentimento e próxima ação (Req 10.3, 10.4).

    Inválida: ausente, com erro, tempo esgotado, resumo vazio (ou só espaços) ou com mais
    de 300 caracteres, sentimento fora do domínio, ou próxima ação vazia ou com mais de 200.
    """
    if saida is None or saida.erro or saida.tempo_esgotado:
        return False
    resumo, sentimento, acao = saida.resumo, saida.sentimento, saida.proxima_acao
    if not isinstance(resumo, str) or not resumo.strip() or len(resumo) > RESUMO_MAX:
        return False
    if sentimento not in SENTIMENTOS:
        return False
    return isinstance(acao, str) and bool(acao.strip()) and len(acao) <= PROXIMA_ACAO_MAX


def montar_pacote(det: CamposDeterministicos, saida: SaidaAssistente | None) -> PacoteRepasse:
    """Monta o Pacote: determinísticos + saída do assistente, ou fallback se inválida.

    O fallback é aplicado se, e somente se, a saída do assistente é inválida
    (`saida_assistente_valida`). Nesse caso os três campos de IA são substituídos juntos.
    """
    if not saida_assistente_valida(saida):
        return pacote_fallback(det)
    assert saida is not None  # garantido por saida_assistente_valida
    return _montar(
        det,
        str(saida.resumo),
        cast(Sentimento, saida.sentimento),
        str(saida.proxima_acao),
    )
