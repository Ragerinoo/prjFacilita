"""Teste de propriedade da rejeição de Pacote_Repasse fora do esquema (Req 10.7).

Feature: tres-autoatendimento, Property 9: Pacote fora do esquema é rejeitado com a lista dos
campos inválidos

Para qualquer Pacote_Repasse válido ao qual se aplica um conjunto de mutações que o torna
inválido (campo obrigatório removido, tipo errado, tamanho fora do intervalo, valor fora do
domínio, propriedade extra, versão de esquema desconhecida, mais de 3 anexos), `validar_pacote`
devolve um erro com motivo para **cada** campo afetado e nenhum campo a mais, e
`pacote_de_json` levanta `ErroPacoteInvalido` com essa mesma lista.

O trecho "o fluxo de recebimento não cria nem altera Chamado" é do Painel/API (fora do pacote
`dominio`); aqui se verifica que a rejeição é uma exceção/lista de erros sem efeitos
colaterais (a entrada não é alterada).

**Validates: Requirements 10.7**
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from dominio.pacote import (
    ErroPacoteInvalido,
    pacote_de_json,
    pacote_para_dict,
    validar_pacote,
)
from test_propriedade_pacote_ida_volta import pacotes_validos

Mutador = Callable[[Any, dict[str, Any]], list[str]]

_CAMPOS = (
    "schema_version",
    "numero_chamado",
    "modelo",
    "numero_serie",
    "origem",
    "categoria",
    "resumo",
    "ja_tentado",
    "classificacao",
    "prioridade",
    "canal_recomendado",
    "sentimento",
    "anexos",
    "proxima_acao",
)

# Domínios do esquema v1 (cópia independente do JSON Schema, para o teste não depender dele).
_ENUMS: dict[str, tuple[str, ...]] = {
    "origem": ("qr", "busca"),
    "categoria": (
        "nao_liga",
        "luz_vermelha_fixa",
        "alerta_vermelho_piscando",
        "teclas_e_sensor_vermelho_piscando",
        "luz_amarela",
        "nao_extrai",
        "bebida_aguada",
        "bebida_fria",
        "alavanca_travada",
        "vazamento",
        "nao_puxa_agua",
        "bico_entupido",
        "alavanca_nao_fecha_com_capsula",
        "outro",
    ),
    "classificacao": ("provável defeito", "provável uso"),
    "prioridade": ("P1", "P2", "P3"),
    "canal_recomendado": (
        "ligação imediata",
        "chat ou ligação, à escolha do Consumidor",
        "chat assíncrono",
    ),
    "sentimento": ("neutro", "frustração moderada", "frustração alta"),
}
_LIMITES_TEXTO = {"modelo": 80, "resumo": 300, "proxima_acao": 200}
_ENUM_ITEM = {
    "camada": ("guia", "ia"),
    "resultado": ("sim", "não", "sem resposta"),
    "mime": ("image/jpeg", "image/png"),
}

# --- Geradores de valores de mutação ----------------------------------------------------------
_json_finito = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.lists(st.integers(), max_size=3),
    st.dictionaries(st.text(max_size=5), st.integers(), max_size=3),
)
_nao_texto = _json_finito
_nao_lista = st.one_of(
    st.text(max_size=10),
    st.none(),
    st.booleans(),
    st.integers(),
    st.dictionaries(st.text(max_size=5), st.integers(), max_size=3),
)
_nao_objeto = st.one_of(st.text(max_size=10), st.none(), st.booleans(), st.integers())
_extra_valor = st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=10))


def _fora_do_dominio(dominio: tuple[str, ...]) -> st.SearchStrategy[str]:
    variantes = [v.upper() for v in dominio] + [v + " " for v in dominio] + ["", "P4", "x"]
    return st.one_of(st.text(max_size=20), st.sampled_from(variantes)).filter(
        lambda s: s not in dominio
    )


_versao_errada = st.one_of(
    st.integers().filter(lambda n: n != 1),
    st.text(max_size=5),
    st.none(),
    st.floats(allow_nan=False, allow_infinity=False).filter(lambda f: f != 1),
)

# `[0-9A-HJKMNP-TV-Z]{10}` com prefixo `TRES-`; qualquer outra coisa é inválida.
_RE_CHAMADO = re.compile(r"TRES-[0-9A-HJKMNP-TV-Z]{10}")
_RE_SERIE = re.compile(r"[A-Za-z0-9]{1,30}|não informado")


def _fora_do_padrao(regex: re.Pattern[str]) -> st.SearchStrategy[str]:
    # Inclui valores válidos com quebra de linha final: `$` do `re.search` aceitaria "…\n".
    com_quebra = st.sampled_from(["TRES-0123456789\n", "ABC123\n", "não informado\n", "A\n"])
    return st.one_of(st.text(max_size=45), com_quebra).filter(lambda s: regex.fullmatch(s) is None)


def _longo(draw: Any, limite: int) -> str:
    extra = draw(st.integers(min_value=1, max_value=30))
    return draw(st.sampled_from(["a", "ç", "😀"])) * (limite + extra)


# --- Mutadores de um campo de topo: devolvem os caminhos que passam a ser inválidos -----------
def _remover(chave: str) -> Mutador:
    def aplicar(_draw: Any, d: dict[str, Any]) -> list[str]:
        del d[chave]
        return [chave]

    return aplicar


def _trocar(chave: str, valores: st.SearchStrategy[Any]) -> Mutador:
    def aplicar(draw: Any, d: dict[str, Any]) -> list[str]:
        d[chave] = draw(valores)
        return [chave]

    return aplicar


def _texto_longo(chave: str, limite: int) -> Mutador:
    def aplicar(draw: Any, d: dict[str, Any]) -> list[str]:
        d[chave] = _longo(draw, limite)
        return [chave]

    return aplicar


def _vazio(chave: str) -> Mutador:
    def aplicar(_draw: Any, d: dict[str, Any]) -> list[str]:
        d[chave] = ""
        return [chave]

    return aplicar


def _anexos_demais(draw: Any, d: dict[str, Any]) -> list[str]:
    extra = draw(st.integers(min_value=1, max_value=3))
    anexo = {"chave": "uploads/x.png", "mime": "image/png"}
    d["anexos"] = [copy.deepcopy(anexo) for _ in range(3 + extra)]
    return ["anexos"]


def _mutar_item(lista: str, campos: tuple[str, ...]) -> Mutador:
    """Mutação aninhada em `ja_tentado[i]` ou `anexos[i]` (exige lista não vazia)."""

    def aplicar(draw: Any, d: dict[str, Any]) -> list[str]:
        itens = d[lista]
        i = draw(st.integers(min_value=0, max_value=len(itens) - 1))
        campo = draw(st.sampled_from(campos))
        tipo = draw(st.sampled_from(["remover", "tipo", "dominio_ou_tamanho", "extra", "item"]))
        base = f"{lista}[{i}]"
        if tipo == "remover":
            del itens[i][campo]
            return [f"{base}.{campo}"]
        if tipo == "tipo":
            itens[i][campo] = draw(_nao_texto)
            return [f"{base}.{campo}"]
        if tipo == "extra":
            nome = draw(st.text(min_size=1, max_size=8).filter(lambda n: n not in campos))
            itens[i][nome] = draw(_extra_valor)
            return [f"{base}.{nome}"]
        if tipo == "item":
            itens[i] = draw(_nao_objeto)
            return [base]
        if campo in _ENUM_ITEM:
            itens[i][campo] = draw(_fora_do_dominio(_ENUM_ITEM[campo]))
        elif campo == "passo":
            itens[i][campo] = draw(st.sampled_from(["", _longo(draw, 200)]))
        else:  # chave: só tem minLength
            itens[i][campo] = ""
        return [f"{base}.{campo}"]

    return aplicar


def _para_campo_de_topo(chave: str) -> list[Mutador]:
    mutadores: list[Mutador] = [_remover(chave)]
    if chave == "schema_version":
        mutadores.append(_trocar(chave, _versao_errada))
        return mutadores
    if chave in _ENUMS:
        mutadores += [_trocar(chave, _fora_do_dominio(_ENUMS[chave])), _trocar(chave, _nao_texto)]
        return mutadores
    if chave == "numero_chamado":
        mutadores += [_trocar(chave, _fora_do_padrao(_RE_CHAMADO)), _trocar(chave, _nao_texto)]
    elif chave == "numero_serie":
        mutadores += [_trocar(chave, _fora_do_padrao(_RE_SERIE)), _trocar(chave, _nao_texto)]
    elif chave in _LIMITES_TEXTO:
        mutadores += [
            _vazio(chave),
            _texto_longo(chave, _LIMITES_TEXTO[chave]),
            _trocar(chave, _nao_texto),
        ]
    elif chave == "ja_tentado":
        mutadores += [
            _trocar(chave, _nao_lista),
            _mutar_item("ja_tentado", ("passo", "camada", "resultado")),
        ]
    elif chave == "anexos":
        mutadores += [
            _trocar(chave, _nao_lista),
            _anexos_demais,
            _mutar_item("anexos", ("chave", "mime")),
        ]
    return mutadores


@st.composite
def pacote_mutado(draw: Any) -> tuple[dict[str, Any], set[str]]:
    """Pacote válido + mutações em campos de topo distintos e propriedades extras.

    Devolve o dict mutado e o conjunto exato de caminhos que devem ser reportados.
    """
    d = pacote_para_dict(draw(pacotes_validos))
    escolhidos = draw(st.lists(st.sampled_from(_CAMPOS), unique=True, max_size=len(_CAMPOS)))
    extras = draw(
        st.lists(
            st.text(min_size=1, max_size=10).filter(lambda n: n not in _CAMPOS),
            unique=True,
            max_size=3,
        )
    )
    if not escolhidos and not extras:  # ao menos uma mutação
        escolhidos = [draw(st.sampled_from(_CAMPOS))]

    esperados: set[str] = set()
    for chave in escolhidos:
        candidatos = _para_campo_de_topo(chave)
        # Mutação aninhada exige lista não vazia; sem itens, usa as demais.
        if chave in ("ja_tentado", "anexos") and not d[chave]:
            candidatos = [m for m in candidatos if m.__qualname__.split(".")[0] != "_mutar_item"]
        mutador = draw(st.sampled_from(candidatos))
        esperados.update(mutador(draw, d))
    for nome in extras:
        d[nome] = draw(_extra_valor)
        esperados.add(nome)
    return d, esperados


@given(caso=pacote_mutado())
def test_pacote_fora_do_esquema_e_rejeitado_com_os_campos_invalidos(
    caso: tuple[dict[str, Any], set[str]],
) -> None:
    # Feature: tres-autoatendimento, Property 9: Pacote fora do esquema é rejeitado com a lista
    # dos campos inválidos
    mutado, esperados = caso
    antes = copy.deepcopy(mutado)

    erros = validar_pacote(mutado)

    # Cada campo inválido é listado, com motivo, e nenhum campo válido é acusado (Req 10.7).
    assert {e.campo for e in erros} == esperados
    assert all(isinstance(e.motivo, str) and e.motivo.strip() for e in erros)
    # Determinístico e sem efeito colateral sobre a entrada.
    assert validar_pacote(mutado) == erros
    assert mutado == antes

    # A desserialização rejeita com a mesma lista de erros (a API responde 422 com ela).
    with pytest.raises(ErroPacoteInvalido) as info:
        pacote_de_json(json.dumps(mutado))
    assert info.value.erros == erros
