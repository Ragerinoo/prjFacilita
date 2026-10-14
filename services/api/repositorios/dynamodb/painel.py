"""Adaptadores DynamoDB do Painel_CS: usuários e sessões."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any

from repositorios.dynamodb._base import TENTATIVAS_OTIMISTAS, Tabela, dt_opt, dt_str, str_dt
from repositorios.erros import ErroNaoEncontrado, ErroRepositorio
from repositorios.modelos import PerfilCS, ResultadoCondicional, SessaoCS, UsuarioCS

# ----------------------------------------------------------------------------- Usuários


def _usuario_de_item(i: dict[str, Any]) -> UsuarioCS:
    return UsuarioCS(
        usuario=i["usuario"],
        hash_senha=i["hash_senha"],
        perfil=i["perfil"],
        falhas=tuple(str_dt(f) for f in i.get("falhas", [])),
        bloqueado_ate=dt_opt(i.get("bloqueado_ate")),
        deve_trocar_senha=bool(i.get("deve_trocar_senha", True)),
    )


class UsuariosCSDynamoDB:
    """Tabela `usuarios_cs` (PK `usuario`). Nunca guarda senha em texto puro."""

    def __init__(self, recurso: Any, prefixo: str = "tres") -> None:
        self._t = Tabela(recurso, f"{prefixo}-usuarios_cs", "usuarios_cs", pk="usuario")

    def criar(self, usuario: UsuarioCS) -> ResultadoCondicional[UsuarioCS]:
        item: dict[str, Any] = {
            "usuario": usuario.usuario,
            "hash_senha": usuario.hash_senha,
            "perfil": usuario.perfil,
            "falhas": [dt_str(f) for f in usuario.falhas],
            "deve_trocar_senha": usuario.deve_trocar_senha,
        }
        if usuario.bloqueado_ate is not None:
            item["bloqueado_ate"] = dt_str(usuario.bloqueado_ate)
        if self._t.gravar(item, "attribute_not_exists(#pk)", {"#pk": "usuario"}):
            return ResultadoCondicional(True, usuario)
        existente = self.obter(usuario.usuario)
        if existente is None:
            raise ErroRepositorio("usuarios_cs: registro sumiu durante a criação")
        return ResultadoCondicional(False, existente)

    def obter(self, usuario: str) -> UsuarioCS | None:
        item = self._t.obter(self._t.chave(usuario))
        return None if item is None else _usuario_de_item(item)

    def _definir(
        self, usuario: str, expressao: str, nomes: dict[str, str], valores: dict
    ) -> UsuarioCS:
        return _usuario_de_item(
            self._t.atualizar(self._t.chave(usuario), expressao, nomes, valores)[1]
        )

    def registrar_falha(self, usuario: str, em: datetime, janela: timedelta) -> UsuarioCS:
        # Lê, descarta as falhas fora da janela e grava com condição na lista lida: duas
        # falhas simultâneas não se perdem (a perdedora relê e tenta de novo).
        for _ in range(TENTATIVAS_OTIMISTAS):
            item = self._t.obter(self._t.chave(usuario))
            if item is None:
                raise self._t.nao_encontrado(self._t.chave(usuario))
            lidas = list(item.get("falhas", []))
            recentes = [dt_str(f) for f in (str_dt(x) for x in lidas) if f > em - janela]
            aplicado, novo = self._t.atualizar(
                self._t.chave(usuario),
                "SET #falhas = :novas",
                {"#falhas": "falhas"},
                {":novas": [*recentes, dt_str(em)], ":lidas": lidas},
                condicao="#falhas = :lidas",
            )
            if aplicado:
                return _usuario_de_item(novo)
        raise ErroRepositorio("usuarios_cs: conflito ao registrar a falha de login")

    def limpar_falhas(self, usuario: str) -> UsuarioCS:
        return self._definir(usuario, "SET #falhas = :vazio", {"#falhas": "falhas"}, {":vazio": []})

    def bloquear(self, usuario: str, ate: datetime) -> UsuarioCS:
        return self._definir(
            usuario, "SET #ate = :ate", {"#ate": "bloqueado_ate"}, {":ate": dt_str(ate)}
        )

    def definir_senha(
        self, usuario: str, hash_senha: str, deve_trocar_senha: bool = False
    ) -> UsuarioCS:
        return self._definir(
            usuario,
            "SET #hash = :hash, #trocar = :trocar",
            {"#hash": "hash_senha", "#trocar": "deve_trocar_senha"},
            {":hash": hash_senha, ":trocar": deve_trocar_senha},
        )

    def perfil_de(self, usuario: str) -> PerfilCS | None:
        item = self._t.obter(
            self._t.chave(usuario), projecao="#perfil", nomes={"#perfil": "perfil"}
        )
        return None if item is None else item["perfil"]


# ----------------------------------------------------------------------------- Sessões


def _sessao_de_item(i: dict[str, Any]) -> SessaoCS:
    return SessaoCS(
        token_hash=i["token_hash"],
        usuario=i["usuario"],
        perfil=i["perfil"],
        ultima_atividade=str_dt(i["ultima_atividade"]),
        ttl=int(i["ttl"]),
    )


class SessoesCSDynamoDB:
    """Tabela `sessoes_cs` (PK `token_hash`, TTL no atributo `ttl`)."""

    def __init__(self, recurso: Any, prefixo: str = "tres") -> None:
        self._t = Tabela(recurso, f"{prefixo}-sessoes_cs", "sessoes_cs", pk="token_hash")

    def criar(self, sessao: SessaoCS) -> None:
        self._t.gravar(
            {
                "token_hash": sessao.token_hash,
                "usuario": sessao.usuario,
                "perfil": sessao.perfil,
                "ultima_atividade": dt_str(sessao.ultima_atividade),
                "ttl": sessao.ttl,
            }
        )

    def obter(self, token_hash: str) -> SessaoCS | None:
        item = self._t.obter(self._t.chave(token_hash))
        return None if item is None else _sessao_de_item(item)

    def renovar(self, token_hash: str, agora: datetime, inatividade: timedelta) -> SessaoCS | None:
        # A expiração vem da comparação com `ultima_atividade`, não do TTL do DynamoDB
        # (que apaga com atraso). Gravação condicional na atividade lida evita que uma
        # renovação concorrente seja desfeita ou que uma sessão renovada seja removida.
        chave = self._t.chave(token_hash)
        for _ in range(TENTATIVAS_OTIMISTAS):
            item = self._t.obter(chave)
            if item is None:
                return None
            sessao = _sessao_de_item(item)
            lida = item["ultima_atividade"]
            if sessao.ultima_atividade < agora - inatividade:
                if self._t.remover(
                    chave, "#ua = :lida", {"#ua": "ultima_atividade"}, {":lida": lida}
                ):
                    return None
                continue
            nova = replace(
                sessao,
                ultima_atividade=max(sessao.ultima_atividade, agora),
                ttl=int((agora + inatividade).timestamp()),
            )
            try:
                aplicado, _ = self._t.atualizar(
                    chave,
                    "SET #ua = :nova, #ttl = :ttl",
                    {"#ua": "ultima_atividade", "#ttl": "ttl"},
                    {":nova": dt_str(nova.ultima_atividade), ":ttl": nova.ttl, ":lida": lida},
                    condicao="#ua = :lida",
                )
            except ErroNaoEncontrado:  # removida (TTL ou logout) entre a leitura e a gravação
                return None
            if aplicado:
                return nova
        raise ErroRepositorio("sessoes_cs: conflito ao renovar a sessão")

    def encerrar(self, token_hash: str) -> bool:
        return self._t.remover(self._t.chave(token_hash))
