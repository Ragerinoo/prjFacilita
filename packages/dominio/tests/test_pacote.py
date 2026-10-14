"""Testes unitários do Pacote_Repasse (Req 10.1 a 10.7, 10.9)."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from dominio.pacote import (
    NAO_INFORMADO,
    PROXIMA_ACAO_FALLBACK,
    RESUMO_FALLBACK,
    SENTIMENTO_FALLBACK,
    Anexo,
    CamposDeterministicos,
    ErroCampo,
    ErroPacoteInvalido,
    ItemJaTentado,
    SaidaAssistente,
    esquema_pacote,
    montar_pacote,
    pacote_de_json,
    pacote_fallback,
    pacote_para_dict,
    pacote_para_json,
    validar_pacote,
)


def _det(**kw: Any) -> CamposDeterministicos:
    base: dict[str, Any] = {
        "numero_chamado": "TRES-0123456789",
        "modelo": "Mini Me",
        "origem": "qr",
        "categoria": "nao_extrai",
        "classificacao": "provável defeito",
        "prioridade": "P2",
        "canal_recomendado": "chat ou ligação, à escolha do Consumidor",
        "numero_serie": "SN123",
        "ja_tentado": (
            ItemJaTentado("Verificar o reservatório", "guia", "não"),
            ItemJaTentado("Descalcificar", "ia", "sem resposta"),
        ),
        "anexos": (Anexo("fotos/a.jpg", "image/jpeg"),),
    }
    base.update(kw)
    return CamposDeterministicos(**base)


def _saida_ok() -> SaidaAssistente:
    return SaidaAssistente("Máquina não extrai café.", "frustração moderada", "Ligar hoje ☎️")


def _dict_valido() -> dict[str, Any]:
    return pacote_para_dict(montar_pacote(_det(), _saida_ok()))


def test_esquema_v1_tem_versao_e_14_campos_obrigatorios() -> None:
    esquema = esquema_pacote()
    assert esquema["$id"] == "pacote-repasse/1"
    assert len(esquema["required"]) == 14
    assert len(esquema["properties"]["categoria"]["enum"]) == 14  # 13 problemas + "outro"


def test_pacote_montado_e_valido_e_preenche_campos_deterministicos() -> None:
    p = montar_pacote(_det(), _saida_ok())
    assert validar_pacote(pacote_para_dict(p)) == []
    assert (p.numero_chamado, p.modelo, p.prioridade) == ("TRES-0123456789", "Mini Me", "P2")
    assert p.resumo == "Máquina não extrai café."
    assert [i.passo for i in p.ja_tentado] == ["Verificar o reservatório", "Descalcificar"]


@pytest.mark.parametrize(
    "saida",
    [
        None,
        SaidaAssistente(erro=True),
        SaidaAssistente("ok", "neutro", "agir", tempo_esgotado=True),
        SaidaAssistente("", "neutro", "agir"),
        SaidaAssistente("   ", "neutro", "agir"),
        SaidaAssistente("x" * 301, "neutro", "agir"),
        SaidaAssistente("ok", "irritado", "agir"),
        SaidaAssistente("ok", "neutro", ""),
        SaidaAssistente("ok", "neutro", "y" * 201),
    ],
)
def test_saida_invalida_aplica_fallback_e_continua_valido(saida: SaidaAssistente | None) -> None:
    p = montar_pacote(_det(), saida)
    assert p == pacote_fallback(_det())
    assert (p.resumo, p.sentimento, p.proxima_acao) == (
        RESUMO_FALLBACK,
        SENTIMENTO_FALLBACK,
        PROXIMA_ACAO_FALLBACK,
    )
    assert RESUMO_FALLBACK == "Resumo indisponível — ver histórico da Jornada"
    assert validar_pacote(pacote_para_dict(p)) == []


def test_resumo_com_300_caracteres_e_aceito() -> None:
    p = montar_pacote(_det(), SaidaAssistente("x" * 300, "neutro", "agir"))
    assert p.resumo == "x" * 300


def test_serie_ausente_vira_nao_informado_e_anexos_vazios_sao_validos() -> None:
    for serie in (None, ""):
        p = montar_pacote(_det(numero_serie=serie, anexos=()), _saida_ok())
        assert p.numero_serie == NAO_INFORMADO
        assert p.anexos == ()
        assert validar_pacote(pacote_para_dict(p)) == []


def test_json_preserva_acentos_e_ida_e_volta() -> None:
    p = montar_pacote(_det(), _saida_ok())
    s = pacote_para_json(p)
    assert "provável defeito" in s and "\\u" not in s
    s.encode("utf-8")
    assert json.loads(s)["schema_version"] == 1
    assert pacote_de_json(s) == p


def test_de_json_rejeita_json_malformado_e_nao_objeto() -> None:
    for entrada in ("{", "[]", "null"):
        with pytest.raises(ErroPacoteInvalido) as exc:
            pacote_de_json(entrada)
        assert exc.value.erros[0].campo == "$"


def test_validar_devolve_todos_os_erros_com_campo_e_motivo() -> None:
    d = _dict_valido()
    del d["modelo"]
    d["resumo"] = "x" * 301
    d["schema_version"] = 2
    d["prioridade"] = "P9"
    d["anexos"] = [{"chave": "a", "mime": "image/png"}] * 4
    d["ja_tentado"][0]["camada"] = "humano"
    d["extra"] = 1
    erros = validar_pacote(d)
    campos = {e.campo for e in erros}
    assert campos == {
        "modelo",
        "resumo",
        "schema_version",
        "prioridade",
        "anexos",
        "ja_tentado[0].camada",
        "extra",
    }
    assert all(isinstance(e, ErroCampo) and e.motivo for e in erros)
    assert "versão" in next(e for e in erros if e.campo == "schema_version").motivo


def test_validar_nao_altera_a_entrada_e_rejeita_raiz_nao_objeto() -> None:
    d = _dict_valido()
    antes = copy.deepcopy(d)
    validar_pacote(d)
    assert d == antes
    assert validar_pacote([]) == [ErroCampo("$", "tipo inválido (esperado: objeto)")]  # type: ignore[arg-type]


def test_de_json_rejeita_pacote_fora_do_esquema_com_lista_de_campos() -> None:
    d = _dict_valido()
    d["numero_chamado"] = "TRES-123"
    d["resumo"] = ""
    with pytest.raises(ErroPacoteInvalido) as exc:
        pacote_de_json(json.dumps(d))
    assert {e.campo for e in exc.value.erros} == {"numero_chamado", "resumo"}
