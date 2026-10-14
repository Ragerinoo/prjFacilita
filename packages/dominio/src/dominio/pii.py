"""Mascaramento de dados pessoais (PII) em texto livre (Req 18.3, 18.8).

`mascarar_pii` troca cada telefone, CPF, e-mail e CEP por um marcador do tipo
correspondente (`[TELEFONE]`, `[CPF]`, `[EMAIL]`, `[CEP]`). Função pura: sem I/O.

Decisões de projeto:
  * Os marcadores não contêm dígitos nem `@`; portanto nenhum padrão os reconhece
    e a função é idempotente: ``mascarar_pii(mascarar_pii(x)) == mascarar_pii(x)``.
  * Padrões ordenados por prioridade numa única expressão: o casamento mais à
    esquerda vence e, na mesma posição, vale a ordem e-mail, telefone com +55,
    CPF, CEP, telefone.
  * Na dúvida, mascara-se (errar para o lado da privacidade). Um número de 11
    dígitos sem pontuação é ambíguo entre CPF e celular com DDD: é tratado como
    CPF quando os dígitos verificadores fecham; caso contrário, como telefone se
    tiver a forma DDD (11 a 99) + 9 + 8 dígitos; senão, como CPF. Um número de 8
    dígitos sem hífen é tratado como CEP.
  * Qualquer falha interna levanta `ErroMascaramento`; o chamador não deve enviar
    nem gravar o texto original.
"""

from __future__ import annotations

import re
from typing import Final

from dominio.erros import ErroMascaramento

MARCADOR_EMAIL: Final = "[EMAIL]"
MARCADOR_TELEFONE: Final = "[TELEFONE]"
MARCADOR_CPF: Final = "[CPF]"
MARCADOR_CEP: Final = "[CEP]"

# Separadores toleráveis dentro de um número (espaço, espaço sem quebra, ponto, hífen).
_SEP = r"[ \t\u00a0.\-]"

_PADRAO = re.compile(
    rf"""
    (?P<email>
        [\w.+%\-]+@[\w\-]+(?:\.[\w\-]+)+
    )
    |
    (?P<tel_pais>                                   # +55 (11) 98765-4321, +55 11 3333-4444
        (?<!\d)\+{_SEP}*55{_SEP}*
        (?:\(?\d{{2}}\)?{_SEP}{{0,3}})?
        (?:9\d{{4}}|\d{{4}}){_SEP}{{0,3}}\d{{4}}(?!\d)
    )
    |
    (?P<cpf>                                        # 123.456.789-09, 12345678909
        (?<!\d)\d{{3}}\.?\d{{3}}\.?\d{{3}}-?\d{{2}}(?!\d)
    )
    |
    (?P<cep>                                        # 01310-100, 01310100
        (?<!\d)(?:\d{{5}}-\d{{3}}|\d{{8}})(?!\d)
    )
    |
    (?P<tel>                                        # (11) 98765-4321, 11 3333-4444, 98765-4321
        (?<!\d)
        (?:\(\d{{2}}\){_SEP}{{0,3}}|\d{{2}}{_SEP}{{0,3}})?
        (?:9\d{{4}}|\d{{4}})(?:{_SEP}{{1,3}})?\d{{4}}(?!\d)
        |
        (?<!\d)(?:(?:\d{{2}})?9\d{{8}}|\d{{10}})(?!\d)   # 11987654321, 987654321, 1133334444
    )
    """,
    re.VERBOSE,
)


def _cpf_valido(digitos: str) -> bool:
    """Confere os dois dígitos verificadores de um CPF de 11 dígitos."""
    nums = [int(c) for c in digitos]
    if len(nums) != 11 or len(set(nums)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(n * p for n, p in zip(nums[:tamanho], range(tamanho + 1, 1, -1), strict=True))
        if (soma * 10 % 11) % 10 != nums[tamanho]:
            return False
    return True


def _cpf_ou_telefone(trecho: str) -> str:
    """Resolve a ambiguidade de 11 dígitos sem pontuação (CPF x celular com DDD)."""
    if any(not c.isdigit() for c in trecho):
        return MARCADOR_CPF  # há pontuação de CPF
    if _cpf_valido(trecho):
        return MARCADOR_CPF
    ddd = int(trecho[:2])
    if 11 <= ddd <= 99 and trecho[2] == "9":
        return MARCADOR_TELEFONE
    return MARCADOR_CPF


def _substituir(m: re.Match[str]) -> str:
    tipo = m.lastgroup
    if tipo == "email":
        return MARCADOR_EMAIL
    if tipo in ("tel_pais", "tel"):
        return MARCADOR_TELEFONE
    if tipo == "cpf":
        return _cpf_ou_telefone(m.group(0))
    if tipo == "cep":
        return MARCADOR_CEP
    raise ErroMascaramento(f"tipo de PII desconhecido: {tipo!r}")


def mascarar_pii(texto: str) -> str:
    """Substitui telefone, CPF, e-mail e CEP de `texto` por marcadores do tipo.

    Levanta `ErroMascaramento` se `texto` não for `str` ou em qualquer falha
    interna (Req 18.8): nesse caso nada pode ser enviado ao modelo nem gravado.
    """
    if not isinstance(texto, str):
        raise ErroMascaramento("o texto a mascarar deve ser str")
    try:
        return _PADRAO.sub(_substituir, texto)
    except ErroMascaramento:
        raise
    except Exception as exc:  # noqa: BLE001 - qualquer falha interna vira ErroMascaramento
        raise ErroMascaramento("falha interna ao mascarar dados pessoais") from exc
