"""Adaptadores DynamoDB de cache de respostas, avaliações, agregados do dia e configuração."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from typing import Any

from dominio import (
    EntradaCache,
    ResultadoInsercao,
    StatusInsercao,
    aceitar_insercao_cache,
    chave_cache,
    normalizar_pergunta,
)
from repositorios.dynamodb._base import (
    Tabela,
    de_dynamo,
    dt_opt,
    dt_str,
    para_dynamo,
    sem_nulos,
    str_dt,
)
from repositorios.erros import ErroRepositorio
from repositorios.modelos import AgregadoDia, Avaliacao, RegistroCache, ResultadoCondicional

# ----------------------------------------------------------------------------- Cache


def _registro_cache_de_item(i: dict[str, Any]) -> RegistroCache:
    return RegistroCache(
        chave=i["chave"],
        modelo_id=i["modelo_id"],
        pergunta_normalizada=i["pergunta_normalizada"],
        pergunta=i["pergunta"],
        resposta=i["resposta"],
        aprovador_id=i["aprovador_id"],
        aprovado_em=dt_opt(i.get("aprovado_em")),
        fontes=tuple(de_dynamo(f) for f in i.get("fontes", [])),
        hits=int(i.get("hits", 0)),
    )


def _entrada_de(r: RegistroCache) -> EntradaCache:
    return EntradaCache(r.modelo_id, r.pergunta, r.resposta, r.aprovador_id, r.aprovado_em)


class CacheRespostasDynamoDB:
    """Tabela `cache_respostas` (PK `chave` = `modelo_id#hash`).

    `recurso_leitura` (opcional) atende só `obter`, com timeout de 2 s (Req 7.8): quem chama
    trata `ErroRepositorio` como "miss".
    """

    def __init__(
        self, recurso: Any, prefixo: str = "tres", recurso_leitura: Any | None = None
    ) -> None:
        nome = f"{prefixo}-cache_respostas"
        self._t = Tabela(recurso, nome, "cache_respostas", pk="chave")
        self._leitura = (
            self._t
            if recurso_leitura is None
            else Tabela(recurso_leitura, nome, "cache_respostas", pk="chave")
        )

    def obter(self, chave: str) -> RegistroCache | None:
        item = self._leitura.obter(self._leitura.chave(chave))
        return None if item is None else _registro_cache_de_item(item)

    def inserir(
        self, entrada: EntradaCache, fontes: Sequence[Mapping[str, Any]] = ()
    ) -> ResultadoInsercao:
        chave = chave_cache(entrada.modelo_id, entrada.pergunta)
        atual = self.obter_consistente(chave)
        existente = None if atual is None else _entrada_de(atual)
        resultado = aceitar_insercao_cache(entrada, entrada.aprovador_id, existente)
        if not resultado.aceita:
            return resultado

        aceita = resultado.entrada
        assert aceita is not None and aceita.aprovador_id is not None
        item = sem_nulos(
            {
                "chave": chave,
                "modelo_id": aceita.modelo_id,
                "pergunta_normalizada": normalizar_pergunta(aceita.pergunta),
                "pergunta": aceita.pergunta,
                "resposta": aceita.resposta,
                "aprovador_id": aceita.aprovador_id,
                "aprovado_em": None if aceita.aprovado_em is None else dt_str(aceita.aprovado_em),
                "fontes": [para_dynamo(dict(f)) for f in fontes],
                "hits": 0,
            }
        )
        # `Put` condicional (Req 16.8): se alguém inseriu a mesma chave nesse meio-tempo,
        # a entrada existente fica como está e o resultado é "duplicada".
        if self._t.gravar(item, "attribute_not_exists(#pk)", {"#pk": "chave"}):
            return resultado
        vencedora = self.obter_consistente(chave)
        if vencedora is None:
            raise ErroRepositorio("cache_respostas: registro sumiu durante a inserção")
        return ResultadoInsercao(StatusInsercao.DUPLICADA, _entrada_de(vencedora))

    def obter_consistente(self, chave: str) -> RegistroCache | None:
        """Leitura fortemente consistente pelo cliente de escrita (usada na inserção)."""
        item = self._t.obter(self._t.chave(chave))
        return None if item is None else _registro_cache_de_item(item)

    def registrar_hit(self, chave: str) -> int:
        _, item = self._t.atualizar(
            self._t.chave(chave),
            "SET #hits = if_not_exists(#hits, :zero) + :um",
            {"#hits": "hits"},
            {":zero": 0, ":um": 1},
        )
        return int(item["hits"])


# ----------------------------------------------------------------------------- Avaliações


def _avaliacao_de_item(i: dict[str, Any]) -> Avaliacao:
    return Avaliacao(
        jornada_id=i["jornada_id"],
        nota=int(i["nota"]),
        camada=i["camada"],
        em=str_dt(i["em"]),
        comentario=i.get("comentario", ""),
    )


class AvaliacoesDynamoDB:
    """Tabela `avaliacoes` (PK `jornada_id`)."""

    def __init__(self, recurso: Any, prefixo: str = "tres") -> None:
        self._t = Tabela(recurso, f"{prefixo}-avaliacoes", "avaliacoes", pk="jornada_id")

    def registrar(self, avaliacao: Avaliacao) -> ResultadoCondicional[Avaliacao]:
        # `Put` condicional: uma avaliação por Jornada (Req 5.5).
        gravou = self._t.gravar(
            {
                "jornada_id": avaliacao.jornada_id,
                "nota": avaliacao.nota,
                "camada": avaliacao.camada,
                "em": dt_str(avaliacao.em),
                "comentario": avaliacao.comentario,
            },
            "attribute_not_exists(#pk)",
            {"#pk": "jornada_id"},
        )
        if gravou:
            return ResultadoCondicional(True, avaliacao)
        existente = self.obter(avaliacao.jornada_id)
        if existente is None:
            raise ErroRepositorio("avaliacoes: registro sumiu durante a gravação")
        return ResultadoCondicional(False, existente)

    def obter(self, jornada_id: str) -> Avaliacao | None:
        item = self._t.obter(self._t.chave(jornada_id))
        return None if item is None else _avaliacao_de_item(item)

    def listar_periodo(self, inicio: datetime, fim: datetime) -> list[Avaliacao]:
        # A tabela não tem índice por data: varredura filtrada. Aceitável no volume do MVP
        # (consulta de métricas, não do fluxo do Consumidor); vira GSI por dia se crescer.
        itens = self._t.varrer(
            "#em BETWEEN :ini AND :fim",
            {"#em": "em"},
            {":ini": dt_str(inicio), ":fim": dt_str(fim)},
        )
        avaliacoes = [_avaliacao_de_item(i) for i in itens]
        return sorted(avaliacoes, key=lambda a: (a.em, a.jornada_id))


# ----------------------------------------------------------------------------- Agregados


class AgregadosDiaDynamoDB:
    """Tabela `agregados_dia` (PK `dia` ISO, SK `metrica`): contadores atômicos."""

    def __init__(self, recurso: Any, prefixo: str = "tres") -> None:
        self._t = Tabela(
            recurso, f"{prefixo}-agregados_dia", "agregados_dia", pk="dia", sk="metrica"
        )

    def incrementar(self, dia: date, metrica: str, delta: int = 1) -> int:
        if delta <= 0:
            raise ValueError("delta deve ser positivo")
        _, item = self._t.atualizar(
            self._t.chave(dia.isoformat(), metrica),
            "SET #valor = if_not_exists(#valor, :zero) + :delta",
            {"#valor": "valor"},
            {":zero": 0, ":delta": delta},
            criar_se_ausente=True,  # o contador nasce no primeiro incremento
        )
        return int(item["valor"])

    def obter(self, dia: date, metrica: str) -> int:
        item = self._t.obter(self._t.chave(dia.isoformat(), metrica))
        return 0 if item is None else int(item["valor"])

    def listar(self, inicio: date, fim: date) -> list[AgregadoDia]:
        # `dia` é a chave de partição: uma consulta por dia do intervalo (máx. 90 dias).
        agregados: list[AgregadoDia] = []
        dia = inicio
        while dia <= fim:
            itens = self._t.consultar("#pk = :pk", {"#pk": "dia"}, {":pk": dia.isoformat()})
            agregados.extend(AgregadoDia(i["dia"], i["metrica"], int(i["valor"])) for i in itens)
            dia += timedelta(days=1)
        return sorted(agregados, key=lambda a: (a.dia, a.metrica))


# ----------------------------------------------------------------------------- Config


class ConfigDynamoDB:
    """Tabela `config` (PK `chave`, atributo `valor`).

    Números inteiros voltam como `int`; fracionários continuam `Decimal` (valores
    monetários e limiares não passam por `float`).
    """

    def __init__(self, recurso: Any, prefixo: str = "tres") -> None:
        self._t = Tabela(recurso, f"{prefixo}-config", "config", pk="chave")

    @staticmethod
    def _valor(item: dict[str, Any]) -> Any:
        return de_dynamo(item.get("valor"), fracionario_como_float=False)

    def obter(self, chave: str) -> Any | None:
        item = self._t.obter(self._t.chave(chave))
        return None if item is None else self._valor(item)

    def definir(self, chave: str, valor: Any) -> None:
        self._t.gravar({"chave": chave, "valor": para_dynamo(valor)})

    def listar(self) -> dict[str, Any]:
        return {i["chave"]: self._valor(i) for i in self._t.varrer()}
