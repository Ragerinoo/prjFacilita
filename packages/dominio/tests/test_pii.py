"""Testes de unidade do mascaramento de PII (Req 18.3, 18.8)."""

from __future__ import annotations

import pytest

import dominio.pii as pii
from dominio.erros import ErroMascaramento
from dominio.pii import mascarar_pii


@pytest.mark.parametrize(
    "telefone",
    [
        "(11) 98765-4321",
        "(11)98765-4321",
        "11 98765-4321",
        "11987654321",
        "98765-4321",
        "+55 11 98765-4321",
        "+55 (11) 98765-4321",
        "+5511987654321",
        "(11) 3333-4444",
        "1133334444",
        "11 3333 4444",
    ],
)
def test_telefone_vira_marcador(telefone: str) -> None:
    assert mascarar_pii(f"me liga no {telefone} por favor") == "me liga no [TELEFONE] por favor"


@pytest.mark.parametrize(
    "cpf", ["123.456.789-09", "12345678909", "123456789-09", "123.456.78909"]
)
def test_cpf_vira_marcador(cpf: str) -> None:
    assert mascarar_pii(f"meu cpf é {cpf}.") == "meu cpf é [CPF]."


def test_cpf_sem_pontos_que_parece_celular_e_invalido_como_cpf_vira_telefone() -> None:
    assert mascarar_pii("11987654321") == "[TELEFONE]"


@pytest.mark.parametrize("cep", ["01310-100", "01310100"])
def test_cep_vira_marcador(cep: str) -> None:
    assert mascarar_pii(f"moro no CEP {cep}") == "moro no CEP [CEP]"


def test_email_vira_marcador() -> None:
    assert mascarar_pii("escreva para ana.silva+tres@exemplo.com.br.") == "escreva para [EMAIL]."


def test_email_com_digitos_nao_vira_telefone() -> None:
    assert mascarar_pii("11987654321@exemplo.com") == "[EMAIL]"


def test_varios_tipos_na_mesma_mensagem() -> None:
    texto = "Ana, cpf 123.456.789-09, tel +55 (21) 91234-5678, a@b.com, CEP 20040-020"
    assert mascarar_pii(texto) == "Ana, cpf [CPF], tel [TELEFONE], [EMAIL], CEP [CEP]"


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "a máquina vaza água na base",
        "usei 200 ml de água e 3 cápsulas",
        "são 10:30 de 12/03/2024",
        "preço R$ 1.234,56",
    ],
)
def test_texto_sem_pii_e_preservado(texto: str) -> None:
    assert mascarar_pii(texto) == texto


def test_e_idempotente() -> None:
    texto = "tel (11) 98765-4321, cpf 123.456.789-09, a@b.com, cep 01310-100"
    uma_vez = mascarar_pii(texto)
    assert mascarar_pii(uma_vez) == uma_vez


def test_entrada_que_nao_e_texto_levanta_erro_de_mascaramento() -> None:
    with pytest.raises(ErroMascaramento):
        mascarar_pii(None)  # type: ignore[arg-type]


def test_falha_interna_levanta_erro_de_mascaramento(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(_m: object) -> str:
        raise RuntimeError("falha")

    monkeypatch.setattr(pii, "_substituir", explode)
    with pytest.raises(ErroMascaramento):
        mascarar_pii("cep 01310-100")
