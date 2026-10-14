"""Teste de propriedade da ida e volta do Pacote_Repasse (Req 10.1, 10.5, 10.6, 10.9).

Feature: tres-autoatendimento, Property 8: Ida e volta do Pacote_Repasse

Para qualquer Pacote_Repasse válido (incluindo número de série "não informado", lista de
anexos vazia, lista "já tentado" vazia ou longa e textos com acentos e emojis),
`pacote_de_json(pacote_para_json(p))` é igual a `p` em todos os campos, com os itens de
"já tentado" na mesma ordem, e `pacote_para_json(p)` é UTF-8 válido, aceito por
`validar_pacote` e contém a versão do esquema.

**Validates: Requirements 10.1, 10.5, 10.6, 10.9**
"""

from __future__ import annotations

import json
import string

from hypothesis import given
from hypothesis import strategies as st

from dominio.pacote import (
    NAO_INFORMADO,
    SCHEMA_VERSION,
    Anexo,
    ItemJaTentado,
    PacoteRepasse,
    pacote_de_json,
    pacote_para_json,
    validar_pacote,
)

# --- Geradores de texto: acentos, emojis e unicode, sem surrogates isolados -------------------
# (surrogates isolados não são UTF-8 válido, logo não são texto de Pacote válido)
_EMOJIS = st.sampled_from(["😀", "🔥", "☕", "🚫", "👍🏽", "🇧🇷", "⚠️", "💧"])
_ACENTUADOS = st.sampled_from(list("áéíóúâêôãõçÁÉÍÓÚÂÊÔÃÕÇüñ") + ["e\u0301", "a\u0303", "ç"])
_unicode_livre = st.characters(blacklist_categories=("Cs",))
_fragmento = st.one_of(_unicode_livre.map(str), _EMOJIS, _ACENTUADOS)


def _texto(min_size: int, max_size: int) -> st.SearchStrategy[str]:
    """Texto com 1+ fragmentos unicode; o tamanho em code points respeita [min, max]."""
    return (
        st.lists(_fragmento, min_size=min_size, max_size=max_size)
        .map("".join)
        .filter(lambda s: min_size <= len(s) <= max_size)
    )


# --- Campos do esquema ----------------------------------------------------------------------
_ALFABETO_ULID = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford: sem I, L, O, U
_numero_chamado = st.text(alphabet=_ALFABETO_ULID, min_size=10, max_size=10).map(
    lambda s: f"TRES-{s}"
)
_numero_serie = st.one_of(
    st.just(NAO_INFORMADO),
    st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=30),
)
_item_ja_tentado = st.builds(
    ItemJaTentado,
    passo=_texto(1, 200),
    camada=st.sampled_from(["guia", "ia"]),
    resultado=st.sampled_from(["sim", "não", "sem resposta"]),
)
_anexo = st.builds(
    Anexo,
    chave=_texto(1, 120),
    mime=st.sampled_from(["image/jpeg", "image/png"]),
)

_CATEGORIAS = [
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
]
_CANAIS = [
    "ligação imediata",
    "chat ou ligação, à escolha do Consumidor",
    "chat assíncrono",
]

pacotes_validos = st.builds(
    PacoteRepasse,
    numero_chamado=_numero_chamado,
    modelo=_texto(1, 80),
    numero_serie=_numero_serie,
    origem=st.sampled_from(["qr", "busca"]),
    categoria=st.sampled_from(_CATEGORIAS),
    resumo=_texto(1, 300),
    ja_tentado=st.lists(_item_ja_tentado, max_size=25).map(tuple),
    classificacao=st.sampled_from(["provável defeito", "provável uso"]),
    prioridade=st.sampled_from(["P1", "P2", "P3"]),
    canal_recomendado=st.sampled_from(_CANAIS),
    sentimento=st.sampled_from(["neutro", "frustração moderada", "frustração alta"]),
    anexos=st.lists(_anexo, max_size=3).map(tuple),
    proxima_acao=_texto(1, 200),
)


@given(p=pacotes_validos)
def test_ida_e_volta_do_pacote_repasse(p: PacoteRepasse) -> None:
    # Feature: tres-autoatendimento, Property 8: Ida e volta do Pacote_Repasse
    texto = pacote_para_json(p)

    # UTF-8 válido: codifica e decodifica sem perdas (Req 10.5, 10.6).
    assert texto.encode("utf-8").decode("utf-8") == texto

    # Aceito pelo esquema e contém a versão do esquema (Req 10.1).
    assert validar_pacote(json.loads(texto)) == []
    assert json.loads(texto)["schema_version"] == SCHEMA_VERSION

    # Ida e volta: igual em todos os campos, "já tentado" na mesma ordem (Req 10.1, 10.9).
    volta = pacote_de_json(texto)
    assert volta == p
    assert [i.passo for i in volta.ja_tentado] == [i.passo for i in p.ja_tentado]
    assert volta.numero_serie == p.numero_serie
