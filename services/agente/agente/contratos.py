"""Contratos do agente: requisição, resposta e saída do modelo, todos com JSON Schema.

Fonte: design.md, seção 3.5 ("Contrato de invocação"). Validação com a biblioteca `jsonschema`
(sem validador próprio). Três camadas, todas validadas:

  1. REQUISIÇÃO que a API envia (`validar_requisicao`).
  2. SAÍDA DO MODELO (texto JSON), tratada como dado não confiável (`SAIDA_MODELO_*`).
  3. RESPOSTA que o agente devolve, auto-verificada antes de sair (`validar_resposta`).

Resposta de erro (qualquer modo): `{"erro": {"codigo", "mensagem", "detalhes"?}}`, ver `erros.py`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

from jsonschema import Draft202012Validator

from dominio.custo import Precos

from . import erros
from .erros import ErroAgente

MODO_RESPONDER: Final = "responder"
MODO_RESUMO: Final = "resumo_repasse"
MODO_SUGESTAO: Final = "sugestao_atendente"
MODOS: Final = (MODO_RESPONDER, MODO_RESUMO, MODO_SUGESTAO)

# Limites do contrato (Req 6.11: mensagem de até 1000 caracteres; Req 10.3 e 15.3).
MENSAGEM_MAX: Final = 1000
SUGESTAO_MAX: Final = 2000

NIVEIS: Final = ("baixa", "média", "alta")
SENTIMENTOS_PACOTE: Final = ("neutro", "frustração moderada", "frustração alta")
RESULTADOS: Final = ("solucao", "sem_embasamento", "problema_catalogado", "risco")

_DECIMAL = r"^[0-9]+(\.[0-9]+)?$"
_CUSTO = r"^[0-9]+\.[0-9]{4}$"

# ---------------------------------------------------------------------------------------------
# 1. Requisição
# ---------------------------------------------------------------------------------------------
REQUISICAO_SCHEMA: Final[dict[str, Any]] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "agente-requisicao/1",
    "type": "object",
    "required": ["modo", "jornada_id", "modelo_id"],
    "properties": {
        "modo": {"enum": list(MODOS)},
        "jornada_id": {"type": "string", "pattern": r"^[A-Za-z0-9]{1,64}$"},
        "modelo_id": {"type": "string", "pattern": r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,79}$"},
        "numero_serie": {"type": ["string", "null"], "maxLength": 40},
        "passos_registrados": {
            "type": "array",
            "maxItems": 100,
            "items": {
                "type": "object",
                "required": ["camada", "passo", "resultado"],
                "properties": {
                    "camada": {"enum": ["guia", "ia"]},
                    "passo": {"type": "string", "minLength": 1, "maxLength": 200},
                    "resultado": {"enum": ["sim", "não", "sem resposta"]},
                },
            },
        },
        "historico": {
            "type": "array",
            "maxItems": 100,
            "items": {
                "type": "object",
                "required": ["papel", "texto"],
                "properties": {
                    "papel": {"enum": ["consumidor", "assistente"]},
                    "texto": {"type": "string", "maxLength": 4000},
                },
            },
        },
        "mensagem": {"type": "string", "maxLength": MENSAGEM_MAX},
        "solucoes_anteriores": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "required": ["id", "resumo"],
                "properties": {
                    "id": {"type": "string", "maxLength": 64},
                    "resumo": {"type": "string", "maxLength": 1000},
                },
            },
        },
        "limiar_relevancia": {"type": "number", "minimum": 0, "maximum": 1},
        "problemas_catalogados": {
            "type": "array",
            "maxItems": 50,
            "items": {
                "type": "object",
                "required": ["id", "titulo"],
                "properties": {
                    "id": {"type": "integer", "minimum": 1},
                    "titulo": {"type": "string", "minLength": 1, "maxLength": 80},
                },
            },
        },
        # Preços vêm da tabela `config` da API (o agente não acessa o banco). Sem eles, o custo
        # em BRL não é calculado (`custo_brl` = null); os tokens são sempre devolvidos.
        "precos": {
            "type": "object",
            "required": ["entrada_por_1m", "saida_por_1m"],
            "properties": {
                "entrada_por_1m": {"type": "string", "pattern": _DECIMAL},
                "saida_por_1m": {"type": "string", "pattern": _DECIMAL},
            },
        },
        "cotacao_usd_brl": {"type": "string", "pattern": _DECIMAL},
        # Pacote_Repasse (modo `sugestao_atendente`); só os campos abaixo são lidos.
        "pacote": {
            "type": "object",
            "required": ["resumo", "categoria"],
            "properties": {
                "resumo": {"type": "string", "maxLength": 300},
                "categoria": {"type": "string", "maxLength": 80},
                "prioridade": {"enum": ["P1", "P2", "P3"]},
                "classificacao": {"enum": ["provável defeito", "provável uso"]},
                "sentimento": {"enum": list(SENTIMENTOS_PACOTE)},
                "proxima_acao": {"type": "string", "maxLength": 200},
                "ja_tentado": {
                    "type": "array",
                    "maxItems": 100,
                    "items": {
                        "type": "object",
                        "required": ["passo", "camada", "resultado"],
                        "properties": {
                            "passo": {"type": "string", "maxLength": 200},
                            "camada": {"enum": ["guia", "ia"]},
                            "resultado": {"enum": ["sim", "não", "sem resposta"]},
                        },
                    },
                },
            },
        },
    },
    "allOf": [
        {
            "if": {"properties": {"modo": {"const": MODO_RESPONDER}}, "required": ["modo"]},
            "then": {
                "required": ["mensagem", "problemas_catalogados"],
                "properties": {"mensagem": {"pattern": r"\S"}},
            },
        },
        {
            "if": {"properties": {"modo": {"const": MODO_SUGESTAO}}, "required": ["modo"]},
            "then": {"required": ["pacote"]},
        },
        # precos e cotação andam juntos
        {"dependentRequired": {"precos": ["cotacao_usd_brl"], "cotacao_usd_brl": ["precos"]}},
    ],
}

# ---------------------------------------------------------------------------------------------
# 2. Saída do modelo (dado não confiável)
# ---------------------------------------------------------------------------------------------
_TRECHOS_USADOS: Final = {
    "type": "array",
    "items": {"type": "integer", "minimum": 1},
    "maxItems": 10,
    "uniqueItems": True,
}

SAIDA_MODELO_RESPONDER_SCHEMA: Final[dict[str, Any]] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["trechos_usados", "texto", "problema_id", "risco_seguranca", "sentimento"],
    "properties": {
        "trechos_usados": _TRECHOS_USADOS,
        "texto": {"type": "string", "maxLength": 2000},
        "problema_id": {"type": ["integer", "null"], "minimum": 1},
        "risco_seguranca": {"type": "boolean"},
        "sentimento": {"enum": [*NIVEIS, None]},
    },
}

SAIDA_MODELO_RESUMO_SCHEMA: Final[dict[str, Any]] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["resumo", "sentimento", "proxima_acao"],
    "properties": {
        "resumo": {"type": "string", "minLength": 1, "maxLength": 300},
        "sentimento": {"enum": list(SENTIMENTOS_PACOTE)},
        "proxima_acao": {"type": "string", "minLength": 1, "maxLength": 200},
    },
}

SAIDA_MODELO_SUGESTAO_SCHEMA: Final[dict[str, Any]] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["trechos_usados", "sugestao"],
    "properties": {
        "trechos_usados": _TRECHOS_USADOS,
        "sugestao": {"type": "string", "minLength": 1, "maxLength": SUGESTAO_MAX},
    },
}

# ---------------------------------------------------------------------------------------------
# 3. Resposta do agente
# ---------------------------------------------------------------------------------------------
_USO: Final = {
    "type": "object",
    "additionalProperties": False,
    "required": ["tokens_entrada", "tokens_saida", "modelo"],
    "properties": {
        "tokens_entrada": {"type": "integer", "minimum": 0},
        "tokens_saida": {"type": "integer", "minimum": 0},
        "modelo": {"type": ["string", "null"]},
    },
}
_FONTE: Final = {
    "type": "object",
    "additionalProperties": False,
    "required": ["manual", "secao", "score"],
    "properties": {
        "manual": {"type": "string", "minLength": 1},
        "secao": {"type": "string", "minLength": 1},
        "score": {"type": "number", "minimum": 0},
    },
}
_CUSTO_BRL: Final = {"type": ["string", "null"], "pattern": _CUSTO}

RESPOSTA_RESPONDER_SCHEMA: Final[dict[str, Any]] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "resultado", "texto", "fontes", "problema_id", "risco_seguranca", "sentimento",
        "uso", "custo_brl", "score_maximo",
    ],  # fmt: skip
    "properties": {
        "resultado": {"enum": list(RESULTADOS)},
        "texto": {"type": "string"},
        "fontes": {"type": "array", "items": _FONTE},
        "problema_id": {"type": ["integer", "null"]},
        "risco_seguranca": {"type": "boolean"},
        "sentimento": {"enum": [*NIVEIS, None]},
        "uso": _USO,
        "custo_brl": _CUSTO_BRL,
        "score_maximo": {"type": "number", "minimum": 0},
        # Presente (true) quando o modelo foi chamado mas a saída foi descartada pelo código.
        "saida_invalida": {"type": "boolean"},
    },
}

RESPOSTA_RESUMO_SCHEMA: Final[dict[str, Any]] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["resumo", "sentimento", "proxima_acao", "uso", "custo_brl"],
    "properties": {
        "resumo": {"type": "string", "minLength": 1, "maxLength": 300},
        "sentimento": {"enum": list(SENTIMENTOS_PACOTE)},
        "proxima_acao": {"type": "string", "minLength": 1, "maxLength": 200},
        "uso": _USO,
        "custo_brl": _CUSTO_BRL,
    },
}

RESPOSTA_SUGESTAO_SCHEMA: Final[dict[str, Any]] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["sugestao", "fontes", "sem_embasamento", "uso", "custo_brl"],
    "properties": {
        "sugestao": {"type": "string", "maxLength": SUGESTAO_MAX},
        "fontes": {"type": "array", "items": _FONTE},
        "sem_embasamento": {"type": "boolean"},
        "uso": _USO,
        "custo_brl": _CUSTO_BRL,
    },
}

_RESPOSTA_POR_MODO: Final[Mapping[str, dict[str, Any]]] = {
    MODO_RESPONDER: RESPOSTA_RESPONDER_SCHEMA,
    MODO_RESUMO: RESPOSTA_RESUMO_SCHEMA,
    MODO_SUGESTAO: RESPOSTA_SUGESTAO_SCHEMA,
}


def _caminho(erro: Any) -> str:
    partes = [str(p) for p in erro.absolute_path]
    return ".".join(partes) if partes else "(raiz)"


def erros_de_esquema(schema: Mapping[str, Any], obj: Any) -> list[dict[str, str]]:
    """Todos os erros do objeto contra o esquema, como `{campo, motivo}` ordenados."""
    validador = Draft202012Validator(schema)
    achados = [
        {"campo": _caminho(e), "motivo": e.message}
        for e in sorted(validador.iter_errors(obj), key=lambda e: (_caminho(e), e.message))
    ]
    return achados


def validar_resposta(modo: str, resposta: Mapping[str, Any]) -> None:
    """Auto-verificação da resposta antes de sair. Falha aqui é bug do agente (`interno`)."""
    achados = erros_de_esquema(_RESPOSTA_POR_MODO[modo], resposta)
    if achados:
        raise ErroAgente(erros.INTERNO, "Resposta do agente fora do contrato.", achados)


# ---------------------------------------------------------------------------------------------
# Requisição tipada
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Requisicao:
    modo: str
    jornada_id: str
    modelo_id: str
    numero_serie: str | None = None
    passos_registrados: tuple[dict[str, str], ...] = ()
    historico: tuple[dict[str, str], ...] = ()
    mensagem: str = ""
    solucoes_anteriores: tuple[dict[str, str], ...] = ()
    limiar_relevancia: float | None = None
    problemas_catalogados: tuple[dict[str, Any], ...] = ()
    precos: Precos | None = None
    cotacao_usd_brl: Decimal | None = None
    pacote: dict[str, Any] | None = field(default=None)


def validar_requisicao(payload: Any) -> Requisicao:
    """Valida o payload contra `REQUISICAO_SCHEMA` e devolve a `Requisicao` tipada.

    Levanta `ErroAgente(modo_desconhecido)` para modo ausente/inválido e
    `ErroAgente(requisicao_invalida)` com a lista completa de `{campo, motivo}` nos demais casos.
    """
    if not isinstance(payload, Mapping):
        raise ErroAgente(erros.REQUISICAO_INVALIDA, "O corpo da requisição deve ser um objeto JSON.")
    modo = payload.get("modo")
    if modo not in MODOS:
        raise ErroAgente(erros.MODO_DESCONHECIDO, "Modo desconhecido ou ausente.")
    achados = erros_de_esquema(REQUISICAO_SCHEMA, payload)
    if achados:
        raise ErroAgente(erros.REQUISICAO_INVALIDA, "Requisição fora do contrato.", achados)
    precos = payload.get("precos")
    return Requisicao(
        modo=modo,
        jornada_id=payload["jornada_id"],
        modelo_id=payload["modelo_id"],
        numero_serie=payload.get("numero_serie"),
        passos_registrados=tuple(dict(p) for p in payload.get("passos_registrados", ())),
        historico=tuple(dict(h) for h in payload.get("historico", ())),
        mensagem=payload.get("mensagem", ""),
        solucoes_anteriores=tuple(dict(s) for s in payload.get("solucoes_anteriores", ())),
        limiar_relevancia=(
            float(payload["limiar_relevancia"]) if "limiar_relevancia" in payload else None
        ),
        problemas_catalogados=tuple(dict(p) for p in payload.get("problemas_catalogados", ())),
        precos=(
            Precos(
                entrada_por_1m=Decimal(precos["entrada_por_1m"]),
                saida_por_1m=Decimal(precos["saida_por_1m"]),
            )
            if precos
            else None
        ),
        cotacao_usd_brl=(
            Decimal(payload["cotacao_usd_brl"]) if "cotacao_usd_brl" in payload else None
        ),
        pacote=_pacote_permitido(payload.get("pacote")),
    )


def _pacote_permitido(pacote: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Só os campos do Pacote que o agente lê (lista de permissão); o resto é descartado."""
    if pacote is None:
        return None
    permitidos = (
        "resumo", "categoria", "prioridade", "classificacao", "sentimento", "proxima_acao",
        "ja_tentado",
    )  # fmt: skip
    return {k: pacote[k] for k in permitidos if k in pacote}


# ---------------------------------------------------------------------------------------------
# Saída do modelo: texto -> objeto
# ---------------------------------------------------------------------------------------------
def extrair_json(texto: str) -> Any:
    """Extrai o objeto JSON do texto do modelo (tolera cercas ```json e texto em volta).

    Levanta `ValueError` se não houver um objeto JSON válido.
    """
    bruto = texto.strip()
    if bruto.startswith("```"):
        bruto = bruto.strip("`").strip()
        if bruto.lower().startswith("json"):
            bruto = bruto[4:].strip()
    inicio, fim = bruto.find("{"), bruto.rfind("}")
    if inicio == -1 or fim <= inicio:
        raise ValueError("sem objeto JSON")
    return json.loads(bruto[inicio : fim + 1])
