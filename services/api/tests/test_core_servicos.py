"""Testes de idempotência, logs sem PII e carregamento de config/segredos."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from core.config import CarregadorConfig
from core.erros import ErroApi, ErroConfiguracao
from core.http import Requisicao
from core.idempotencia import Idempotencia, chave_da_requisicao, ulid_da_chave
from core.logs import OMITIDO, Log, higienizar
from repositorios import criar_repositorios_memoria
from repositorios.ids import eh_ulid

AGORA = datetime(2025, 1, 2, 3, 4, 5, tzinfo=UTC)


# --------------------------------------------------------------------------- idempotência
@given(st.text(min_size=1, max_size=128))
def test_ulid_da_chave_e_valido_e_deterministico(chave):
    assert eh_ulid(ulid_da_chave(chave))
    assert ulid_da_chave(chave) == ulid_da_chave(chave)


def test_chave_do_cabecalho_ou_do_evento_id():
    req = Requisicao("POST", "/x", cabecalhos={"idempotency-key": " abc "})
    assert chave_da_requisicao(req) == "abc"
    assert chave_da_requisicao(Requisicao("POST", "/x"), {"evento_id": "01ABC"}) == "01ABC"
    assert chave_da_requisicao(Requisicao("POST", "/x"), {}) is None
    # cabeçalho tem precedência sobre o corpo
    assert chave_da_requisicao(req, {"evento_id": "outro"}) == "abc"


@pytest.mark.parametrize("ruim", ["", "   ", "x" * 129, 5])
def test_chave_invalida_vira_422(ruim):
    with pytest.raises(ErroApi) as info:
        chave_da_requisicao(Requisicao("POST", "/x"), {"evento_id": ruim})
    assert info.value.status == 422 and info.value.campos[0].campo == "evento_id"


def test_primeira_vez_so_uma_vez_por_escopo_e_chave():
    repos = criar_repositorios_memoria()
    idem = Idempotencia(repos.eventos, lambda: AGORA)
    assert idem.primeira_vez("jornada-1", "k1") is True
    assert idem.primeira_vez("jornada-1", "k1") is False
    assert idem.primeira_vez("jornada-1", "k2") is True
    assert idem.primeira_vez("jornada-2", "k1") is True
    assert idem.primeira_vez("jornada-1", None) is True  # sem chave: nada a deduplicar
    assert idem.primeira_vez("jornada-1", None) is True
    # não polui a linha do tempo da Jornada
    assert repos.eventos.listar("jornada-1") == []


# --------------------------------------------------------------------------- logs
def test_log_omite_campos_sensiveis_e_mascara_pii():
    log = Log(agora=lambda: AGORA)
    linha = json.loads(
        log.linha(
            "info",
            "teste",
            mensagem="oi meu telefone é 11 98765-4321",
            telefone="11987654321",
            Authorization="Bearer abc",
            token_sessao="t",
            detalhe="ligue (11) 98765-4321 ou a@b.com",
            jornada_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
            dados={"cpf": "123"},
            n=3,
        )
    )
    assert linha["mensagem"] == linha["telefone"] == linha["Authorization"] == OMITIDO
    assert linha["token_sessao"] == OMITIDO
    assert "98765" not in linha["detalhe"] and "a@b.com" not in linha["detalhe"]
    assert linha["jornada_id"] == "01ARZ3NDEKTSV4RRFFQ69G5FAV"  # id opaco não é mascarado
    assert linha["dados"] == "<dict>" and linha["n"] == 3
    assert linha["evento"] == "teste" and linha["ts"].startswith("2025-01-02T03:04:05")


def test_log_emite_json_pelo_logger(caplog):
    with caplog.at_level(logging.INFO, logger="tres"):
        Log(agora=lambda: AGORA).com(request_id="r-1").info("ola", status=200)
    registro = json.loads(caplog.records[0].getMessage())
    assert registro["request_id"] == "r-1" and registro["status"] == 200


@given(st.text(max_size=300))
def test_higienizar_nunca_devolve_telefone_nem_email(texto):
    saida = higienizar("detalhe", f"{texto} 11987654321 a@b.com")
    assert "11987654321" not in saida and "a@b.com" not in saida


# --------------------------------------------------------------------------- config
class SsmFake:
    def __init__(self, valores=None, falha=False):
        self.valores = valores or {}
        self.falha = falha
        self.chamadas = []

    def get_parameter(self, Name, WithDecryption):
        self.chamadas.append(Name)
        if self.falha or Name not in self.valores:
            raise RuntimeError("ParameterNotFound")
        return {"Parameter": {"Value": self.valores[Name]}}


class SecretsFake:
    def __init__(self, conteudo):
        self.conteudo = conteudo
        self.chamadas = []

    def get_secret_value(self, SecretId):
        self.chamadas.append(SecretId)
        return {"SecretString": self.conteudo}


def test_config_prefere_ssm_depois_tabela_depois_padrao():
    repos = criar_repositorios_memoria()
    repos.config.definir("limiar_relevancia", 0.5)
    repos.config.definir("modelo_llm_id", "da-tabela")
    ssm = SsmFake({"/tres/config/modelo-llm-id": "do-ssm"})
    cfg = CarregadorConfig(ssm=ssm, repo=repos.config)
    assert cfg.obter("modelo_llm_id") == "do-ssm"
    assert cfg.obter("limiar_relevancia") == 0.5  # SSM não tem: usa a tabela
    assert cfg.obter("inexistente", 7) == 7


def test_config_cai_na_tabela_quando_ssm_falha_e_usa_cache():
    repos = criar_repositorios_memoria()
    repos.config.definir("limite_msgs_modelo", 10)
    ssm = SsmFake(falha=True)
    tempo = [0.0]
    cfg = CarregadorConfig(ssm=ssm, repo=repos.config, relogio=lambda: tempo[0])
    assert cfg.obter("limite_msgs_modelo") == 10
    cfg.obter("limite_msgs_modelo")
    assert len(ssm.chamadas) == 1  # cache dentro do TTL
    repos.config.definir("limite_msgs_modelo", 12)
    tempo[0] = 61.0
    assert cfg.obter("limite_msgs_modelo") == 12


def test_config_local_nao_toca_na_aws():
    repos = criar_repositorios_memoria()
    repos.config.definir("a", 1)
    cfg = CarregadorConfig(repo=repos.config, usar_aws=False)
    assert cfg.obter("a") == 1
    with pytest.raises(ErroConfiguracao):
        cfg.segredo_app()


def test_segredo_app_le_do_secrets_manager_com_cache():
    secrets = SecretsFake(json.dumps({"hmac_chave": "s3gr3d0"}))
    cfg = CarregadorConfig(secrets=secrets, arn_segredo_app="arn:aws:secretsmanager:x")
    assert cfg.hmac_chave() == b"s3gr3d0"
    cfg.segredo("hmac_chave")
    assert secrets.chamadas == ["arn:aws:secretsmanager:x"]
    with pytest.raises(ErroConfiguracao, match="ausente"):
        cfg.segredo("outro")


def test_segredo_nome_padrao_e_falha_sem_vazar_valor(caplog):
    secrets = SecretsFake("não é json s3gr3d0")
    cfg = CarregadorConfig(secrets=secrets, prefixo="/demo/")
    with caplog.at_level(logging.DEBUG, logger="tres"), pytest.raises(ErroConfiguracao) as info:
        cfg.segredo_app()
    assert secrets.chamadas == ["demo/segredo-app"]
    assert "s3gr3d0" not in str(info.value)
    assert "s3gr3d0" not in " ".join(r.getMessage() for r in caplog.records)
