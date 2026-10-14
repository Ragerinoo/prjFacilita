"""Hash de senha do Painel_CS (Req 13, 20.5; Q14): Argon2id principal e scrypt de reserva."""

from __future__ import annotations

import pytest

from servicos import senhas

SENHA = "uma-senha-longa-e-boa-123"


def test_argon2id_e_o_algoritmo_preferido_com_parametros_da_decisao_q14():
    assert senhas.argon2_disponivel()
    assert senhas.algoritmo_preferido() == "argon2id"
    armazenado = senhas.gerar_hash(SENHA)
    assert armazenado.startswith("$argon2id$")
    assert "m=19456,t=2,p=1" in armazenado
    assert SENHA not in armazenado


def test_argon2id_confere_senha_certa_e_recusa_errada():
    armazenado = senhas.gerar_hash(SENHA)
    assert senhas.verificar(SENHA, armazenado)
    assert not senhas.verificar(SENHA + "x", armazenado)
    assert not senhas.verificar("", armazenado)


def test_hashes_da_mesma_senha_usam_sal_diferente():
    assert senhas.gerar_hash(SENHA) != senhas.gerar_hash(SENHA)


def test_scrypt_guarda_algoritmo_e_parametros_e_verifica():
    armazenado = senhas.gerar_hash(SENHA, algoritmo="scrypt")
    partes = armazenado.split("$")
    assert partes[:4] == ["scrypt", str(2**17), "8", "1"]
    assert senhas.verificar(SENHA, armazenado)
    assert not senhas.verificar("outra", armazenado)


@pytest.mark.parametrize(
    "lixo",
    [
        "",
        "texto-qualquer",
        "$argon2id$lixo",
        "scrypt$",
        "scrypt$131072$8$1$@@@$@@@",
        "scrypt$3$8$1$c2Fs$aGFzaA",  # N não é potência de dois
        "scrypt$4294967296$8$1$c2Fs$aGFzaA",  # N enorme: não pode pedir memória
        "scrypt$131072$8$1$c2Fs",  # faltou o hash
    ],
)
def test_hash_ilegivel_nunca_levanta_e_nunca_confere(lixo):
    assert senhas.verificar(SENHA, lixo) is False
    assert senhas.precisa_rehash(lixo) is True


def test_precisa_rehash_por_algoritmo_e_por_parametros():
    atual = senhas.gerar_hash(SENHA)
    assert senhas.precisa_rehash(atual) is False
    # scrypt é aceito para verificar, mas migra para o algoritmo principal.
    assert senhas.precisa_rehash(senhas.gerar_hash(SENHA, algoritmo="scrypt")) is True
    # Argon2id com custo menor que o atual também migra.
    from argon2 import PasswordHasher

    fraco = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(SENHA)
    assert senhas.verificar(SENHA, fraco)
    assert senhas.precisa_rehash(fraco) is True


def test_algoritmo_desconhecido_e_recusado():
    with pytest.raises(ValueError):
        senhas.gerar_hash(SENHA, algoritmo="md5")


def test_hash_ficticio_e_estavel_e_nao_confere_com_nada_razoavel():
    assert senhas.hash_ficticio() == senhas.hash_ficticio()
    assert senhas.hash_ficticio().startswith("$argon2id$")
    assert not senhas.verificar(SENHA, senhas.hash_ficticio())


def test_sem_argon2_o_scrypt_assume(monkeypatch):
    monkeypatch.setattr(senhas, "_ARGON2", None)
    assert senhas.algoritmo_preferido() == "scrypt"
    armazenado = senhas.gerar_hash(SENHA)
    assert armazenado.startswith("scrypt$")
    assert senhas.verificar(SENHA, armazenado)
    assert senhas.precisa_rehash(armazenado) is False
    # Sem Argon2id no runtime, um hash Argon2id não pode ser verificado (e não explode).
    assert senhas.verificar(SENHA, "$argon2id$v=19$m=19456,t=2,p=1$c2Fs$aGFzaA") is False
