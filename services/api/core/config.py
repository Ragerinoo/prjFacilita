"""Configuração e segredos (Req 20.5: nada de segredo no código ou no repositório).

Ordem de busca de um valor de configuração (`CarregadorConfig.obter`):
  1. parâmetro SSM ``/<prefixo>/config/<chave com hífens>`` (ex.: ``/tres/config/modelo-llm-id``);
  2. tabela ``config`` via `ConfigRepo` (chave com sublinhados, ex.: ``limiar_relevancia``);
  3. o `padrao` informado.
Os dois primeiros são lidos com cache curto (TTL) para refletir edições do Gestor sem reiniciar
a Lambda. Falha de uma fonte (permissão, rede, parâmetro ausente) passa para a seguinte e é
registrada só com o nome da chave, nunca com o valor.

Segredos (Secrets Manager, ``<prefixo>/segredo-app``) vêm só de lá: não existe fallback para a
tabela ``config`` (segredo não pode morar em tabela editável). O valor nunca é logado.

Os clientes `ssm` e `secretsmanager` são injetados (testes e uso local). Sem injeção, são
criados sob demanda com `boto3` e timeouts curtos (Req 20.6). Com `usar_aws=False` (modo local)
as fontes AWS são ignoradas.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping
from typing import Any, Final

from core.erros import ErroConfiguracao
from core.logs import Log
from repositorios.interfaces import ConfigRepo

TTL_CONFIG_S: Final = 60.0
TTL_SEGREDO_S: Final = 300.0
_AUSENTE: Final = object()


def _cliente_boto3(servico: str) -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(
        servico,
        config=Config(
            connect_timeout=2,
            read_timeout=3,
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )


class CarregadorConfig:
    def __init__(
        self,
        *,
        prefixo: str = "tres",
        ssm: Any | None = None,
        secrets: Any | None = None,
        repo: ConfigRepo | None = None,
        usar_aws: bool = True,
        arn_segredo_app: str | None = None,
        relogio: Callable[[], float] = time.monotonic,
        log: Log | None = None,
    ) -> None:
        self._prefixo = prefixo.strip("/") or "tres"
        self._ssm = ssm
        self._secrets = secrets
        self._repo = repo
        self._usar_aws = usar_aws
        self._id_segredo_app = arn_segredo_app or f"{self._prefixo}/segredo-app"
        self._relogio = relogio
        self._log = log or Log()
        self._cache: dict[str, tuple[float, Any]] = {}
        self._cache_segredo: tuple[float, Mapping[str, Any]] | None = None

    # -- configuração -----------------------------------------------------------------------
    def nome_parametro(self, chave: str) -> str:
        return f"/{self._prefixo}/config/{chave.replace('_', '-')}"

    def obter(self, chave: str, padrao: Any = None) -> Any:
        agora = self._relogio()
        em_cache = self._cache.get(chave)
        if em_cache and em_cache[0] > agora:
            valor = em_cache[1]
        else:
            valor = self._buscar(chave)
            # Ausência também entra no cache (evita uma ida ao SSM por requisição).
            self._cache[chave] = (agora + TTL_CONFIG_S, valor)
        return padrao if valor is _AUSENTE else valor

    def invalidar(self, chave: str | None = None) -> None:
        """Esquece o cache (por exemplo depois de `PUT /cs/config`)."""
        if chave is None:
            self._cache.clear()
        else:
            self._cache.pop(chave, None)

    def _buscar(self, chave: str) -> Any:
        if self._usar_aws:
            try:
                resposta = self._cliente_ssm().get_parameter(
                    Name=self.nome_parametro(chave), WithDecryption=True
                )
                return resposta["Parameter"]["Value"]
            except Exception as exc:  # noqa: BLE001 - qualquer falha cai para a tabela
                self._log.aviso("config_ssm_indisponivel", chave_config=chave, erro=exc)
        if self._repo is not None:
            try:
                valor = self._repo.obter(chave)
            except Exception as exc:  # noqa: BLE001
                self._log.aviso("config_tabela_indisponivel", chave_config=chave, erro=exc)
                return _AUSENTE
            if valor is not None:
                return valor
        return _AUSENTE

    # -- segredos ---------------------------------------------------------------------------
    def segredo_app(self) -> Mapping[str, Any]:
        """Conteúdo JSON do segredo da aplicação (ex.: ``hmac_chave``). Nunca logar."""
        agora = self._relogio()
        if self._cache_segredo and self._cache_segredo[0] > agora:
            return self._cache_segredo[1]
        if not self._usar_aws:
            raise ErroConfiguracao("Segredo da aplicação indisponível: modo local sem segredo.")
        try:
            resposta = self._cliente_secrets().get_secret_value(SecretId=self._id_segredo_app)
            conteudo = json.loads(resposta["SecretString"])
        except Exception as exc:
            self._log.erro("segredo_app_indisponivel", erro=exc)
            raise ErroConfiguracao("Não foi possível ler o segredo da aplicação.") from None
        if not isinstance(conteudo, dict):
            raise ErroConfiguracao("O segredo da aplicação não é um objeto JSON.")
        self._cache_segredo = (agora + TTL_SEGREDO_S, conteudo)
        return conteudo

    def segredo(self, campo: str) -> str:
        valor = self.segredo_app().get(campo)
        if not isinstance(valor, str) or not valor:
            raise ErroConfiguracao(f"Campo ausente no segredo da aplicação: {campo}")
        return valor

    def hmac_chave(self) -> bytes:
        return self.segredo("hmac_chave").encode("utf-8")

    # -- clientes ---------------------------------------------------------------------------
    def _cliente_ssm(self) -> Any:
        if self._ssm is None:
            self._ssm = _cliente_boto3("ssm")
        return self._ssm

    def _cliente_secrets(self) -> Any:
        if self._secrets is None:
            self._secrets = _cliente_boto3("secretsmanager")
        return self._secrets
