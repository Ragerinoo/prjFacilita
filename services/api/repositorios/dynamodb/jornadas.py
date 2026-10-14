"""Adaptador DynamoDB de `JornadasRepo` (tabela `jornadas`).

Atributos de índice esparso:
  * `ativa_pk = "ATIVA"` só enquanto a Jornada está `ativa` e sem Chamado (`gsi_ativas`,
    chave de ordenação `ultima_interacao`); removido na escalada e no encerramento.
  * `encerrada_pk = "ENC"` e `encerrada_em` (espelho de `encerramento.em`) só depois do
    encerramento (`gsi_encerradas`).

Contadores e fatos mudam só por `UpdateItem` atômico com condição (design, "jornadas").
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Final

from dominio import (
    Camada,
    JornadaEncerrada,
    Nivel,
    ResultadoEncerramento,
    aplicar_encerramento,
    marcar_abandono,
)
from dominio.encerramento import ATIVA_PK, ENCERRADA_PK
from repositorios.dynamodb._base import (
    TENTATIVAS_OTIMISTAS,
    Tabela,
    dt_str,
    sem_nulos,
    str_dt,
)
from repositorios.erros import ErroRepositorio
from repositorios.modelos import (
    DecisaoRegistrada,
    EscaladaJornada,
    GatilhoRegistrado,
    Jornada,
    OrigemRisco,
    ResultadoCondicional,
    RiscoMarcado,
)

_QUATRO_CASAS: Final = Decimal("0.0001")
_ZERO: Final = Decimal("0")

NOME_TABELA: Final = "jornadas"
GSI_ATIVAS: Final = "gsi_ativas"
GSI_ENCERRADAS: Final = "gsi_encerradas"

# ----------------------------------------------------------------------------- conversão


def decisao_para_item(d: DecisaoRegistrada) -> dict[str, Any]:
    return {
        "prioridade": d.prioridade,
        "classificacao": d.classificacao,
        "canal": d.canal,
        "criterio": d.criterio,
        "em": dt_str(d.em),
    }


def decisao_de_item(it: dict[str, Any]) -> DecisaoRegistrada:
    return DecisaoRegistrada(
        prioridade=it["prioridade"],
        classificacao=it["classificacao"],
        canal=it["canal"],
        criterio=int(it["criterio"]),  # type: ignore[arg-type]
        em=str_dt(it["em"]),
    )


def gatilho_para_item(g: GatilhoRegistrado) -> dict[str, Any]:
    return {"tipo": g.tipo, "em": dt_str(g.em), "registrado": g.registrado}


def escalada_para_item(e: EscaladaJornada) -> dict[str, Any]:
    return {
        "chamado_numero": e.chamado_numero,
        "em": dt_str(e.em),
        "gatilhos": [gatilho_para_item(g) for g in e.gatilhos],
        "decisao": decisao_para_item(e.decisao),
    }


def _escalada_de_item(it: dict[str, Any]) -> EscaladaJornada:
    return EscaladaJornada(
        chamado_numero=it["chamado_numero"],
        em=str_dt(it["em"]),
        gatilhos=tuple(
            GatilhoRegistrado(g["tipo"], str_dt(g["em"]), bool(g.get("registrado", True)))
            for g in it["gatilhos"]
        ),
        decisao=decisao_de_item(it["decisao"]),
    )


def _encerramento_para_item(e: JornadaEncerrada) -> dict[str, Any]:
    return sem_nulos(
        {
            "camada": e.camada,
            "em": dt_str(e.encerrada_em),
            "tempo_s": e.tempo_s,
            "custo_brl": e.custo_brl,
            "problema_id": e.problema_id,
            "desfecho": e.desfecho,
        }
    )


def _encerramento_de_item(jornada_id: str, it: dict[str, Any]) -> JornadaEncerrada:
    return JornadaEncerrada(
        jornada_id=jornada_id,
        camada=it["camada"],
        encerrada_em=str_dt(it["em"]),
        tempo_s=int(it["tempo_s"]),
        custo_brl=Decimal(it["custo_brl"]),
        problema_id=None if it.get("problema_id") is None else int(it["problema_id"]),
        desfecho=it.get("desfecho"),
    )


def jornada_para_item(j: Jornada) -> dict[str, Any]:
    """Item completo da Jornada, com os atributos de índice esparso coerentes com o estado."""
    return sem_nulos(
        {
            "jornada_id": j.jornada_id,
            "criada_em": dt_str(j.criada_em),
            "ultima_interacao": dt_str(j.ultima_interacao),
            "estado": j.estado,
            "origem": j.origem,
            "origem_inicial": j.origem_inicial,
            "modelo_id": j.modelo_id,
            "numero_serie": j.numero_serie,
            "problema_id": j.problema_id,
            "problemas_selecionados": list(j.problemas_selecionados),
            "seletor": (
                None
                if j.seletor_area is None and j.seletor_estado is None
                else sem_nulos({"area": j.seletor_area, "estado": j.seletor_estado})
            ),
            "risco": (
                None
                if j.risco is None
                else {"marcado": True, "origem": j.risco.origem, "em": dt_str(j.risco.em)}
            ),
            "fatos": {"guia_respondeu_nao": j.guia_respondeu_nao},
            "contadores": {
                "msgs_modelo": j.msgs_modelo,
                "ia_nao": j.ia_nao,
                "frustracao_alta_seq": j.frustracao_alta_seq,
            },
            "custo_ia_brl": j.custo_ia_brl,
            "escalada": None if j.escalada is None else escalada_para_item(j.escalada),
            "encerramento": (
                None if j.encerramento is None else _encerramento_para_item(j.encerramento)
            ),
            "ativa_pk": j.ativa_pk,
            "encerrada_pk": j.encerrada_pk,
            "encerrada_em": None if j.encerrada_em is None else dt_str(j.encerrada_em),
        }
    )


def jornada_de_item(it: dict[str, Any]) -> Jornada:
    seletor = it.get("seletor") or {}
    risco = it.get("risco")
    contadores = it.get("contadores") or {}
    return Jornada(
        jornada_id=it["jornada_id"],
        criada_em=str_dt(it["criada_em"]),
        ultima_interacao=str_dt(it["ultima_interacao"]),
        origem=it["origem"],
        origem_inicial=it["origem_inicial"],
        estado=it["estado"],
        modelo_id=it.get("modelo_id"),
        numero_serie=it.get("numero_serie"),
        problema_id=None if it.get("problema_id") is None else int(it["problema_id"]),
        problemas_selecionados=tuple(int(p) for p in it.get("problemas_selecionados", [])),
        seletor_area=seletor.get("area"),
        seletor_estado=seletor.get("estado"),
        risco=None if not risco else RiscoMarcado(risco["origem"], str_dt(risco["em"])),
        guia_respondeu_nao=bool((it.get("fatos") or {}).get("guia_respondeu_nao", False)),
        msgs_modelo=int(contadores.get("msgs_modelo", 0)),
        ia_nao=int(contadores.get("ia_nao", 0)),
        frustracao_alta_seq=int(contadores.get("frustracao_alta_seq", 0)),
        custo_ia_brl=Decimal(it.get("custo_ia_brl", _ZERO)),
        escalada=None if not it.get("escalada") else _escalada_de_item(it["escalada"]),
        encerramento=(
            None
            if not it.get("encerramento")
            else _encerramento_de_item(it["jornada_id"], it["encerramento"])
        ),
    )


# ----------------------------------------------------------------------------- repositório


class JornadasDynamoDB:
    def __init__(self, recurso: Any, prefixo: str = "tres") -> None:
        self._t = Tabela(recurso, f"{prefixo}-{NOME_TABELA}", NOME_TABELA, pk="jornada_id")

    # -- auxiliares ---------------------------------------------------------------------

    def ler(self, jornada_id: str) -> Jornada | None:
        """Leitura fortemente consistente (também usada pelo adaptador de Chamados)."""
        item = self._t.obter(self._t.chave(jornada_id))
        return None if item is None else jornada_de_item(item)

    def _exigir(self, jornada_id: str) -> Jornada:
        j = self.ler(jornada_id)
        if j is None:
            raise self._t.nao_encontrado(self._t.chave(jornada_id))
        return j

    def _mutar(
        self,
        jornada_id: str,
        expressao: str,
        nomes: dict[str, str] | None = None,
        valores: dict[str, Any] | None = None,
        condicao: str | None = None,
    ) -> tuple[bool, Jornada]:
        aplicado, item = self._t.atualizar(
            self._t.chave(jornada_id), expressao, nomes, valores, condicao
        )
        return aplicado, jornada_de_item(item)

    # -- interface ----------------------------------------------------------------------

    def criar(self, jornada: Jornada) -> ResultadoCondicional[Jornada]:
        if self._t.gravar(
            jornada_para_item(jornada),
            condicao="attribute_not_exists(#pk)",
            nomes={"#pk": "jornada_id"},
        ):
            return ResultadoCondicional(True, jornada)
        existente = self.ler(jornada.jornada_id)
        if existente is None:  # removida entre o Put e a leitura: caso de infraestrutura
            raise ErroRepositorio("jornadas: registro sumiu durante a criação")
        return ResultadoCondicional(False, existente)

    def obter(self, jornada_id: str) -> Jornada | None:
        return self.ler(jornada_id)

    def associar_modelo(
        self, jornada_id: str, modelo_id: str, numero_serie: str | None = None
    ) -> Jornada:
        partes = ["#modelo = :modelo", "#origem = :busca"]
        nomes = {"#modelo": "modelo_id", "#origem": "origem"}
        valores: dict[str, Any] = {":modelo": modelo_id, ":busca": "busca"}
        if numero_serie is not None:
            partes.append("#serie = :serie")
            nomes["#serie"] = "numero_serie"
            valores[":serie"] = numero_serie
        return self._mutar(jornada_id, "SET " + ", ".join(partes), nomes, valores)[1]

    def registrar_seletor(self, jornada_id: str, area: str, estado: str) -> Jornada:
        return self._mutar(
            jornada_id,
            "SET #seletor = :seletor",
            {"#seletor": "seletor"},
            {":seletor": {"area": area, "estado": estado}},
        )[1]

    def registrar_interacao(self, jornada_id: str, em: datetime) -> Jornada:
        # Jornada encerrada nunca muda e a última interação nunca retrocede (Req 17.2).
        return self._mutar(
            jornada_id,
            "SET #ui = :em",
            {"#ui": "ultima_interacao", "#estado": "estado"},
            {":em": dt_str(em), ":enc": "encerrada"},
            condicao="#estado <> :enc AND #ui < :em",
        )[1]

    def registrar_problema_selecionado(self, jornada_id: str, problema_id: int) -> bool:
        nomes = {"#p": "problema_id", "#sel": "problemas_selecionados"}
        primeira, _ = self._mutar(
            jornada_id,
            "SET #p = :p, #sel = list_append(if_not_exists(#sel, :vazio), :novo)",
            nomes,
            {":p": problema_id, ":vazio": [], ":novo": [problema_id]},
            condicao="attribute_not_exists(#sel) OR NOT contains(#sel, :p)",
        )
        if not primeira:  # já selecionado antes: só atualiza o problema atual
            self._mutar(jornada_id, "SET #p = :p", {"#p": "problema_id"}, {":p": problema_id})
        return primeira

    def marcar_guia_respondeu_nao(self, jornada_id: str) -> Jornada:
        return self._mutar(
            jornada_id,
            "SET #fatos.#g = :verdadeiro",
            {"#fatos": "fatos", "#g": "guia_respondeu_nao"},
            {":verdadeiro": True},
        )[1]

    def marcar_risco(
        self, jornada_id: str, origem: OrigemRisco, em: datetime
    ) -> ResultadoCondicional[Jornada]:
        aplicado, j = self._mutar(
            jornada_id,
            "SET #risco = :risco",
            {"#risco": "risco"},
            {":risco": {"marcado": True, "origem": origem, "em": dt_str(em)}},
            condicao="attribute_not_exists(#risco)",
        )
        return ResultadoCondicional(aplicado, j)

    def incrementar_msgs_modelo(
        self, jornada_id: str, limite: int
    ) -> ResultadoCondicional[Jornada]:
        aplicado, j = self._mutar(
            jornada_id,
            "SET #c.#m = if_not_exists(#c.#m, :zero) + :um",
            {"#c": "contadores", "#m": "msgs_modelo"},
            {":zero": 0, ":um": 1, ":limite": limite},
            condicao="attribute_not_exists(#c.#m) OR #c.#m < :limite",
        )
        return ResultadoCondicional(aplicado, j)

    def incrementar_ia_nao(self, jornada_id: str) -> Jornada:
        return self._mutar(
            jornada_id,
            "SET #c.#n = if_not_exists(#c.#n, :zero) + :um",
            {"#c": "contadores", "#n": "ia_nao"},
            {":zero": 0, ":um": 1},
        )[1]

    def atualizar_frustracao(self, jornada_id: str, nivel: Nivel) -> Jornada:
        nomes = {"#c": "contadores", "#f": "frustracao_alta_seq"}
        if nivel == "alta":
            return self._mutar(
                jornada_id,
                "SET #c.#f = if_not_exists(#c.#f, :zero) + :um",
                nomes,
                {":zero": 0, ":um": 1},
            )[1]
        return self._mutar(jornada_id, "SET #c.#f = :zero", nomes, {":zero": 0})[1]

    def somar_custo_ia(self, jornada_id: str, custo_brl: Decimal) -> Jornada:
        if custo_brl < 0:
            raise ValueError("custo_brl não pode ser negativo")
        # Soma atômica no servidor: cada parcela é arredondada a 4 casas antes de somar.
        parcela = custo_brl.quantize(_QUATRO_CASAS, rounding=ROUND_HALF_UP)
        return self._mutar(
            jornada_id,
            "SET #custo = if_not_exists(#custo, :zero) + :parcela",
            {"#custo": "custo_ia_brl"},
            {":zero": _ZERO, ":parcela": parcela},
        )[1]

    def registrar_gatilho_adicional(
        self, jornada_id: str, gatilho: GatilhoRegistrado
    ) -> ResultadoCondicional[Jornada]:
        aplicado, j = self._mutar(
            jornada_id,
            "SET #e.#g = list_append(#e.#g, :novo)",
            {"#e": "escalada", "#g": "gatilhos"},
            {":novo": [gatilho_para_item(gatilho)]},
            condicao="attribute_exists(#e)",
        )
        return ResultadoCondicional(aplicado, j)

    # -- encerramento -------------------------------------------------------------------

    def _gravar_encerramento(
        self,
        novo: Jornada,
        condicao: str,
        nomes_extra: dict[str, str] | None = None,
        valores_extra: dict[str, Any] | None = None,
    ) -> bool:
        """Update condicional que fecha a Jornada e mantém os índices esparsos coerentes:
        grava `encerrada_pk`/`encerrada_em` e remove `ativa_pk`. A condição pode usar
        `#estado` e `:enc`; o que mais ela usar vem em `nomes_extra`/`valores_extra`."""
        assert novo.encerramento is not None
        aplicado, _ = self._t.atualizar(
            self._t.chave(novo.jornada_id),
            "SET #estado = :enc, #encerramento = :e, #epk = :epk, #eem = :eem REMOVE #apk",
            {
                "#estado": "estado",
                "#encerramento": "encerramento",
                "#epk": "encerrada_pk",
                "#eem": "encerrada_em",
                "#apk": "ativa_pk",
                **(nomes_extra or {}),
            },
            {
                ":enc": "encerrada",
                ":e": _encerramento_para_item(novo.encerramento),
                ":epk": ENCERRADA_PK,
                ":eem": dt_str(novo.encerramento.encerrada_em),
                **(valores_extra or {}),
            },
            condicao,
        )
        return aplicado

    def encerrar(
        self,
        jornada_id: str,
        camada: Camada,
        em: datetime,
        custo_brl: Decimal = Decimal("0"),
        problema_id: int | None = None,
        desfecho: str | None = None,
    ) -> ResultadoEncerramento:
        # A regra é do domínio; a gravação é condicional (`estado <> encerrada`, Req 17.1).
        # Se outra escrita fechar a Jornada entre a leitura e a gravação, relê e o domínio
        # devolve "não aplicado" com a camada vencedora.
        for _ in range(TENTATIVAS_OTIMISTAS):
            j = self._exigir(jornada_id)
            r = aplicar_encerramento(
                j.estado_dominio(), camada, em, custo_brl, problema_id, desfecho
            )
            if not r.aplicado:
                return r
            if self._gravar_encerramento(j.com_estado_dominio(r.jornada), "#estado <> :enc"):
                return r
        raise ErroRepositorio("jornadas: conflito ao encerrar a Jornada")

    def marcar_abandono(
        self, jornada_id: str, agora: datetime, custo_brl: Decimal = Decimal("0")
    ) -> ResultadoEncerramento:
        # Só abandona Jornada ainda ativa, sem Chamado e sem interação desde a leitura
        # (uma interação concorrente cancela o abandono, Req 17.2).
        for _ in range(TENTATIVAS_OTIMISTAS):
            j = self._exigir(jornada_id)
            r = marcar_abandono(j.estado_dominio(), agora, custo_brl, j.problema_id)
            if not r.aplicado:
                return r
            gravou = self._gravar_encerramento(
                j.com_estado_dominio(r.jornada),
                "#estado = :ativa AND attribute_not_exists(#escalada) AND #ui = :ui_lida",
                {"#escalada": "escalada", "#ui": "ultima_interacao"},
                {":ativa": "ativa", ":ui_lida": dt_str(j.ultima_interacao)},
            )
            if gravou:
                return r
        raise ErroRepositorio("jornadas: conflito ao marcar o abandono da Jornada")

    # -- consultas por índice -----------------------------------------------------------

    def listar_ativas_sem_interacao_ate(self, limite: datetime) -> list[Jornada]:
        itens = self._t.consultar(
            "#pk = :pk AND #sk <= :limite",
            {"#pk": "ativa_pk", "#sk": "ultima_interacao"},
            {":pk": ATIVA_PK, ":limite": dt_str(limite)},
            indice=GSI_ATIVAS,
        )
        jornadas = [jornada_de_item(i) for i in itens]
        return sorted(jornadas, key=lambda j: (j.ultima_interacao, j.jornada_id))

    def listar_encerradas(self, inicio: datetime, fim: datetime) -> list[Jornada]:
        itens = self._t.consultar(
            "#pk = :pk AND #sk BETWEEN :ini AND :fim",
            {"#pk": "encerrada_pk", "#sk": "encerrada_em"},
            {":pk": ENCERRADA_PK, ":ini": dt_str(inicio), ":fim": dt_str(fim)},
            indice=GSI_ENCERRADAS,
        )
        jornadas = [jornada_de_item(i) for i in itens]
        return sorted(
            jornadas,
            key=lambda j: (j.encerrada_em, j.jornada_id),  # type: ignore[arg-type,return-value]
        )
