"""Testes das premissas verificadas (Tarefa 17.1): orçamento de tempo e contratos."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

import premissas


def test_orcamento_de_tempo_cabe_no_limite_do_api_gateway() -> None:
    orcamento = premissas.orcamento_resposta_ia()
    assert orcamento.total_s <= premissas.LAMBDA_API_TIMEOUT_S
    assert premissas.LAMBDA_API_TIMEOUT_S < premissas.API_GATEWAY_HTTP_TIMEOUT_MAX_S
    assert premissas.API_GATEWAY_INTEGRACAO_TIMEOUT_MS < (
        premissas.API_GATEWAY_HTTP_TIMEOUT_MAX_S * 1000
    )


def test_aviso_de_falha_chega_antes_de_30_segundos() -> None:
    # Req 6.12 e 7.9: o aviso de falha aparece em até 30 s após o envio.
    assert premissas.orcamento_resposta_ia().total_s < 30


def test_timeouts_menores_ficam_dentro_do_da_lambda() -> None:
    assert premissas.ENRIQUECIMENTO_TIMEOUT_S < premissas.LAMBDA_ENRIQUECIMENTO_TIMEOUT_S
    assert premissas.CACHE_TIMEOUT_S == 2  # Req 7.8
    assert premissas.SUGESTAO_ATENDENTE_TIMEOUT_S == 10  # Req 15.7


def test_alvo_p90_cabe_no_teto_duro_do_agente() -> None:
    assert premissas.ALVO_P90_RESPOSTA_S == 10  # Req 6.8
    assert premissas.ALVO_P90_RESPOSTA_S < premissas.AGENTE_RESPONDER_TIMEOUT_S


def test_runtime_session_id_exemplo_ulid() -> None:
    sessao = premissas.runtime_session_id("01J8Z3K4M5N6P7Q8R9S0T1V2W3")
    assert sessao == "tres-jornada-01J8Z3K4M5N6P7Q8R9S0T1V2W3"
    assert len(sessao) == 39


@pytest.mark.parametrize("invalido", ["", "com espaco", "a-b", "!"])
def test_runtime_session_id_rejeita_jornada_invalida(invalido: str) -> None:
    with pytest.raises(ValueError):
        premissas.runtime_session_id(invalido)


@given(st.text(alphabet="0123456789ABCDEFGHJKMNPQRSTVWXYZ", min_size=20, max_size=64))
def test_runtime_session_id_sempre_dentro_do_intervalo_da_api(jornada_id: str) -> None:
    sessao = premissas.runtime_session_id(jornada_id)
    assert premissas.RUNTIME_SESSION_ID_MIN <= len(sessao) <= premissas.RUNTIME_SESSION_ID_MAX
    assert sessao.endswith(jornada_id)


def test_sidecar_e_filtro_usam_as_mesmas_chaves() -> None:
    sidecar = premissas.sidecar_metadados("tres-modelo-x", "Manual Modelo X", "4.2 Limpeza")
    atributos = sidecar["metadataAttributes"]
    assert set(atributos) == set(premissas.METADADOS_OBRIGATORIOS)
    filtro = premissas.filtro_retrieve_por_modelo("tres-modelo-x")
    assert filtro == {"equals": {"key": "modelo_id", "value": "tres-modelo-x"}}


def test_metadados_do_sidecar_cabem_no_limite_do_s3_vectors() -> None:
    import json

    sidecar = premissas.sidecar_metadados("m" * 80, "Manual " + "x" * 100, "Secao " + "y" * 150)
    tamanho = len(json.dumps(sidecar["metadataAttributes"], ensure_ascii=False).encode())
    assert tamanho < premissas.S3_VECTORS_METADADOS_CUSTOM_MAX_BYTES
    assert len(premissas.METADADOS_OBRIGATORIOS) <= premissas.S3_VECTORS_METADADOS_CHAVES_MAX


def test_decisoes_cobrem_as_questoes_da_tarefa() -> None:
    assert {d.questao for d in premissas.DECISOES} == {"Q1", "Q2", "Q3", "Q13", "Q14", "Q18"}
    assert all(d.estado in {"verificado", "parcial", "pendente"} for d in premissas.DECISOES)


def test_hash_de_senha_segue_o_minimo_da_owasp() -> None:
    argon2 = premissas.HASH_SENHA_ARGON2
    assert argon2["memory_cost_kib"] >= 19456
    assert argon2["time_cost"] >= 2
    assert argon2["parallelism"] >= 1
    scrypt = premissas.HASH_SENHA_SCRYPT
    assert scrypt["n"] >= 2**17 and scrypt["r"] >= 8
    # O scrypt de 128 MiB precisa caber no limite de memória pedido ao OpenSSL e na Lambda.
    memoria_necessaria = 128 * scrypt["n"] * scrypt["r"]  # bytes, fórmula do scrypt
    assert scrypt["maxmem_bytes"] > memoria_necessaria
    assert premissas.LAMBDA_API_MEMORIA_MB * 1024 * 1024 > scrypt["maxmem_bytes"]
