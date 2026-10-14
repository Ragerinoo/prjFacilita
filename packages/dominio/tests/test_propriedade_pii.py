"""Teste de propriedade do mascaramento de PII (Req 18.3).

Feature: tres-autoatendimento, Property 16: Mascaramento remove toda PII

Para qualquer texto contendo telefone, CPF, e-mail ou CEP, a saída de `mascarar_pii`
não contém nenhuma das substrings originais de PII e contém o marcador do tipo
correspondente.

**Validates: Requirements 18.3**
"""

from __future__ import annotations

import string

from hypothesis import assume, given
from hypothesis import strategies as st

from dominio.pii import (
    MARCADOR_CEP,
    MARCADOR_CPF,
    MARCADOR_EMAIL,
    MARCADOR_TELEFONE,
    _cpf_valido,
    mascarar_pii,
)

# --- Texto ao redor: sem dígitos, sem '@' e sem caracteres que "colam" na PII ---------------
_ALFABETO_TEXTO = string.ascii_letters + "áéíóúãõçÁÉÇ" + " ,;:!?"
_texto_ao_redor = st.text(alphabet=_ALFABETO_TEXTO, max_size=40)


def _embutir(prefixo: str, pii: str, sufixo: str) -> str:
    return f"{prefixo} {pii} {sufixo}"


def _digitos(n: int) -> st.SearchStrategy[str]:
    return st.text(alphabet=string.digits, min_size=n, max_size=n)


# --- Telefones ---------------------------------------------------------------------------
_ddd = st.integers(min_value=11, max_value=99).map(str)
_celular = st.tuples(st.just("9"), _digitos(4), _digitos(4)).map(lambda t: (t[0] + t[1], t[2]))
_fixo = st.tuples(_digitos(4), _digitos(4))
_sep = st.sampled_from(["-", " ", "- ", " - "])
_pais = st.sampled_from(["+55 ", "+55", "+ 55 "])


@st.composite
def _telefones(draw: st.DrawFn) -> str:
    primeira, segunda = draw(st.one_of(_celular, _fixo))
    sep = draw(_sep)
    corpo = f"{primeira}{sep}{segunda}"
    ddd = draw(st.one_of(st.none(), _ddd))
    if ddd is None:
        # Sem DDD e sem país: exige separador (8 dígitos colados seriam um CEP).
        return corpo
    forma_ddd = draw(
        st.sampled_from(["({ddd}) {c}", "({ddd}){c}", "{ddd} {c}", "{ddd}{c}"])
    ).format(ddd=ddd, c=corpo)
    if draw(st.booleans()):
        return draw(_pais) + forma_ddd
    return forma_ddd


@st.composite
def _telefones_so_digitos(draw: st.DrawFn) -> str:
    """Telefones sem nenhuma pontuação, com ou sem +55."""
    ddd = draw(_ddd)
    primeira, segunda = draw(st.one_of(_celular, _fixo))
    numero = f"{ddd}{primeira}{segunda}"
    if draw(st.booleans()):
        return "+55" + numero
    # 11 dígitos puros que fecham como CPF válido são ambíguos por projeto (viram [CPF]).
    assume(len(numero) != 11 or not _cpf_valido(numero))
    return numero


_qualquer_telefone = st.one_of(_telefones(), _telefones_so_digitos())


# --- CPFs (dígitos verificadores válidos) ---------------------------------------------------
def _com_verificadores(base: str) -> str:
    nums = [int(c) for c in base]
    for tamanho in (9, 10):
        soma = sum(n * p for n, p in zip(nums[:tamanho], range(tamanho + 1, 1, -1), strict=True))
        nums.append((soma * 10 % 11) % 10)
    return "".join(map(str, nums))


_cpf_digitos = _digitos(9).map(_com_verificadores).filter(_cpf_valido)


@st.composite
def _cpfs(draw: st.DrawFn) -> str:
    d = draw(_cpf_digitos)
    formato = draw(st.sampled_from(["pontuado", "so_digitos", "so_hifen", "so_pontos"]))
    if formato == "pontuado":
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if formato == "so_hifen":
        return f"{d[:9]}-{d[9:]}"
    if formato == "so_pontos":
        return f"{d[:3]}.{d[3:6]}.{d[6:]}"
    return d


# --- CEPs --------------------------------------------------------------------------------
@st.composite
def _ceps(draw: st.DrawFn) -> str:
    d = draw(_digitos(8))
    return f"{d[:5]}-{d[5:]}" if draw(st.booleans()) else d


# --- E-mails -----------------------------------------------------------------------------
_local = st.text(alphabet=string.ascii_letters + string.digits + "._+-", min_size=1, max_size=15)
_rotulo = st.text(alphabet=string.ascii_lowercase + string.digits + "-", min_size=1, max_size=10)
_tld = st.text(alphabet=string.ascii_lowercase, min_size=2, max_size=6)


@st.composite
def _emails(draw: st.DrawFn) -> str:
    # Domínio de e-mail real tem ao menos um ponto (ex.: exemplo.com).
    rotulos = draw(st.lists(_rotulo, min_size=1, max_size=2))
    dominio = ".".join([*rotulos, draw(_tld)])
    return f"{draw(_local)}@{dominio}"


# --- Propriedades ------------------------------------------------------------------------
def _verifica(entrada: str, pii: str, marcador: str) -> None:
    saida = mascarar_pii(entrada)
    assert pii not in saida, f"PII sobreviveu: {pii!r} em {saida!r}"
    assert marcador in saida, f"marcador {marcador} ausente em {saida!r}"
    # O texto ao redor não tem dígitos nem '@': qualquer um que sobre é resto da PII.
    assert not any(c.isdigit() for c in saida), f"dígito sobrou em {saida!r}"
    assert "@" not in saida, f"'@' sobrou em {saida!r}"


@given(_texto_ao_redor, _qualquer_telefone, _texto_ao_redor)
def test_propriedade_16_telefone_e_mascarado(prefixo: str, telefone: str, sufixo: str) -> None:
    _verifica(_embutir(prefixo, telefone, sufixo), telefone, MARCADOR_TELEFONE)


@given(_texto_ao_redor, _cpfs(), _texto_ao_redor)
def test_propriedade_16_cpf_e_mascarado(prefixo: str, cpf: str, sufixo: str) -> None:
    _verifica(_embutir(prefixo, cpf, sufixo), cpf, MARCADOR_CPF)


@given(_texto_ao_redor, _emails(), _texto_ao_redor)
def test_propriedade_16_email_e_mascarado(prefixo: str, email: str, sufixo: str) -> None:
    _verifica(_embutir(prefixo, email, sufixo), email, MARCADOR_EMAIL)


@given(_texto_ao_redor, _ceps(), _texto_ao_redor)
def test_propriedade_16_cep_e_mascarado(prefixo: str, cep: str, sufixo: str) -> None:
    _verifica(_embutir(prefixo, cep, sufixo), cep, MARCADOR_CEP)


@given(_texto_ao_redor, _qualquer_telefone, _cpfs(), _emails(), _ceps(), _texto_ao_redor)
def test_propriedade_16_todos_os_tipos_juntos(
    prefixo: str, telefone: str, cpf: str, email: str, cep: str, sufixo: str
) -> None:
    entrada = _embutir(prefixo, f"{telefone} ; {cpf} ; {email} ; {cep}", sufixo)
    saida = mascarar_pii(entrada)
    for pii in (telefone, cpf, email, cep):
        assert pii not in saida
    for marcador in (MARCADOR_TELEFONE, MARCADOR_CPF, MARCADOR_EMAIL, MARCADOR_CEP):
        assert marcador in saida
    assert not any(c.isdigit() for c in saida)
    assert "@" not in saida
