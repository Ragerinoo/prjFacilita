"""Adaptador DynamoDB de `ChamadosRepo` (tabela `chamados`, índice esparso `gsi_fila`).

Garantias (design, "Garantias por escrita condicional"):
  * Um Chamado por Jornada (Req 9.9): `TransactWriteItems` com `Put` do Chamado
    (`attribute_not_exists(numero)`) e `Update` da Jornada (`escalada` ausente).
  * Um responsável por Chamado (Req 14.6): `Update` com `attribute_not_exists(responsavel)`.
  * Uma só camada de encerramento: `Update` com `status <> encerrado`; o Chamado sai da fila
    (remove `fila_pk` e `fila_sk`).
  * A prioridade nunca diminui (Req 8.5): reavaliação só se a nova prioridade for mais alta.

Pendência (camada AWS): `listar_todos` está declarado só para satisfazer o Protocol
`ChamadosRepo` e levanta `ErroIndisponivelForaDoModoLocal`. A consulta real, que também lista
os Chamados encerrados, só existe no Modo_Local (repositório em memória) e fica para quando a
camada AWS entrar em escopo. Não há `Query`, `Scan` nem índice novo para ela.
"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from datetime import datetime
from typing import Any, Final

from dominio import (
    FILA_PK,
    ErroPacoteInvalido,
    PacoteRepasse,
    montar_fila_sk,
    pacote_de_json,
    validar_pacote,
)
from dominio.pacote import pacote_para_dict
from repositorios.dynamodb import jornadas as jornadas_ddb
from repositorios.dynamodb._base import (
    ORCAMENTO_GRAVACAO_S,
    TENTATIVAS_OTIMISTAS,
    Tabela,
    de_dynamo,
    dt_str,
    executar_transacao,
    put_transacao,
    sem_nulos,
    str_dt,
    update_transacao,
)
from repositorios.erros import ErroIndisponivelForaDoModoLocal, ErroRepositorio
from repositorios.modelos import (
    RANKING_PRIORIDADE,
    AnexoChamado,
    Chamado,
    DecisaoRegistrada,
    EncerramentoChamado,
    EscaladaJornada,
    GatilhoRegistrado,
    Responsavel,
    ResultadoCondicional,
    ResultadoEscalada,
    StatusOS,
    StatusPacoteIA,
)

NOME_TABELA: Final = "chamados"
GSI_FILA: Final = "gsi_fila"

# ----------------------------------------------------------------------------- conversão


def _validar(pacote: PacoteRepasse) -> dict[str, Any]:
    """Dicionário do Pacote, só se ele é válido no esquema v1 (Req 10.7)."""
    d = pacote_para_dict(pacote)
    erros = validar_pacote(d)
    if erros:
        raise ErroRepositorio(
            "Pacote inválido: " + "; ".join(f"{e.campo}: {e.motivo}" for e in erros)
        )
    return d


def _pacote_de_item(d: dict[str, Any]) -> PacoteRepasse:
    try:
        return pacote_de_json(json.dumps(de_dynamo(d), ensure_ascii=False))
    except ErroPacoteInvalido as exc:
        raise ErroRepositorio(f"chamados: Pacote gravado é inválido ({exc})") from exc


def chamado_para_item(c: Chamado, pacote: dict[str, Any] | None = None) -> dict[str, Any]:
    return sem_nulos(
        {
            "numero": c.numero,
            "jornada_id": c.jornada_id,
            "criado_em": dt_str(c.criado_em),
            "prioridade": c.prioridade,
            "classificacao": c.classificacao,
            "canal": c.canal,
            "decisao_criterio": c.decisao_criterio,
            "pacote": pacote if pacote is not None else pacote_para_dict(c.pacote),
            "status": c.status,
            "pacote_ia_status": c.pacote_ia_status,
            "gatilho_nao_registrado": c.gatilho_nao_registrado,
            "responsavel": (
                None
                if c.responsavel is None
                else {
                    "usuario": c.responsavel.usuario,
                    "nome": c.responsavel.nome,
                    "inicio": dt_str(c.responsavel.inicio),
                }
            ),
            "alerta_p1_visto": c.alerta_p1_visto,
            "resposta_nao_lida": c.resposta_nao_lida,
            "os_status": c.os_status,
            # O agendamento guarda o deslocamento original (ex.: -03:00, fuso de Brasília).
            "agendamento": (
                None if c.agendamento is None else {"data_hora": _com_fuso(c.agendamento)}
            ),
            "anexos": [_anexo_para_item(a) for a in c.anexos],
            "encerramento": (
                None if c.encerramento is None else _encerramento_para_item(c.encerramento)
            ),
            # Índice esparso: só enquanto o Chamado não está encerrado.
            "fila_pk": c.fila_pk,
            "fila_sk": c.fila_sk,
        }
    )


def _com_fuso(valor: datetime) -> str:
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValueError("datetime deve ter fuso horário (datetime ciente de fuso)")
    return valor.isoformat()


def _anexo_para_item(a: AnexoChamado) -> dict[str, Any]:
    return {"chave": a.chave, "mime": a.mime, "bytes": a.bytes}


def _encerramento_para_item(e: EncerramentoChamado) -> dict[str, Any]:
    return {
        "desfecho": e.desfecho,
        "solucao_tipo": e.solucao_tipo,
        "solucao": e.solucao,
        "em": dt_str(e.em),
        "por": e.por,
    }


def chamado_de_item(it: dict[str, Any]) -> Chamado:
    resp = it.get("responsavel")
    enc = it.get("encerramento")
    agendamento = it.get("agendamento")
    return Chamado(
        numero=it["numero"],
        jornada_id=it["jornada_id"],
        criado_em=str_dt(it["criado_em"]),
        prioridade=it["prioridade"],
        classificacao=it["classificacao"],
        canal=it["canal"],
        decisao_criterio=int(it["decisao_criterio"]),  # type: ignore[arg-type]
        pacote=_pacote_de_item(it["pacote"]),
        status=it["status"],
        pacote_ia_status=it.get("pacote_ia_status", "pendente"),
        gatilho_nao_registrado=bool(it.get("gatilho_nao_registrado", False)),
        responsavel=(
            None if not resp else Responsavel(resp["usuario"], resp["nome"], str_dt(resp["inicio"]))
        ),
        alerta_p1_visto=bool(it.get("alerta_p1_visto", False)),
        resposta_nao_lida=bool(it.get("resposta_nao_lida", False)),
        os_status=it.get("os_status", "nao_aplicavel"),
        agendamento=None if not agendamento else str_dt(agendamento["data_hora"]),
        anexos=tuple(
            AnexoChamado(a["chave"], a["mime"], int(a["bytes"])) for a in it.get("anexos", [])
        ),
        encerramento=(
            None
            if not enc
            else EncerramentoChamado(
                desfecho=enc["desfecho"],
                solucao_tipo=enc["solucao_tipo"],
                solucao=enc["solucao"],
                em=str_dt(enc["em"]),
                por=enc["por"],
            )
        ),
    )


# ----------------------------------------------------------------------------- repositório


class ChamadosDynamoDB:
    def __init__(self, recurso: Any, prefixo: str = "tres") -> None:
        self._t = Tabela(recurso, f"{prefixo}-{NOME_TABELA}", NOME_TABELA, pk="numero")
        self._jornadas = jornadas_ddb.JornadasDynamoDB(recurso, prefixo)
        # O Chamado e a Jornada ficam em tabelas diferentes; a transação usa o cliente comum.
        self._tj = self._jornadas._t

    # -- auxiliares ---------------------------------------------------------------------

    def _mutar(
        self,
        numero: str,
        expressao: str,
        nomes: dict[str, str] | None = None,
        valores: dict[str, Any] | None = None,
        condicao: str | None = None,
    ) -> tuple[bool, Chamado]:
        aplicado, item = self._t.atualizar(
            self._t.chave(numero), expressao, nomes, valores, condicao
        )
        return aplicado, chamado_de_item(item)

    def _exigir(self, numero: str) -> Chamado:
        c = self.obter(numero)
        if c is None:
            raise self._t.nao_encontrado(self._t.chave(numero))
        return c

    # -- criação (transação) ------------------------------------------------------------

    def criar_com_escalada(
        self,
        chamado: Chamado,
        gatilho: GatilhoRegistrado,
        decisao: DecisaoRegistrada,
    ) -> ResultadoEscalada:
        if chamado.status != "aberto":
            raise ErroRepositorio("um Chamado novo deve ter status 'aberto'")
        item_chamado = chamado_para_item(chamado, _validar(chamado.pacote))
        escalada = EscaladaJornada(
            chamado_numero=chamado.numero,
            em=chamado.criado_em,
            gatilhos=(gatilho,),
            decisao=decisao,
        )
        escalada_item = jornadas_ddb.escalada_para_item(escalada)
        inicio = time.monotonic()

        for _ in range(TENTATIVAS_OTIMISTAS):
            jornada = self._jornadas.ler(chamado.jornada_id)
            if jornada is None:
                return ResultadoEscalada(False, "jornada_inexistente")
            if jornada.escalada is not None:
                return ResultadoEscalada(
                    False, "jornada_ja_escalada", jornada.escalada.chamado_numero
                )

            # Ativa -> escalada (sai do `gsi_ativas`); encerrada fica como está, só ganha
            # o Chamado (Req 17.2). A condição `estado = <lido>` detecta mudança concorrente.
            nomes = {
                "#escalada": "escalada",
                "#estado": "estado",
                "#_pk": "jornada_id",
            }
            valores: dict[str, Any] = {":e": escalada_item, ":estado_lido": jornada.estado}
            expressao = "SET #escalada = :e"
            if jornada.estado == "ativa":
                expressao += ", #estado = :escalada REMOVE #apk"
                nomes["#apk"] = "ativa_pk"
                valores[":escalada"] = "escalada"
            falhas = executar_transacao(
                self._t,
                [
                    update_transacao(
                        self._tj,
                        self._tj.chave(chamado.jornada_id),
                        expressao,
                        "attribute_exists(#_pk) AND attribute_not_exists(#escalada) "
                        "AND #estado = :estado_lido",
                        nomes,
                        valores,
                    ),
                    put_transacao(
                        self._t,
                        item_chamado,
                        "attribute_not_exists(#numero)",
                        {"#numero": "numero"},
                    ),
                ],
                "criar_com_escalada",
            )
            if falhas is None:
                return ResultadoEscalada(True, "criado")

            # Cancelada por condição: descobre qual (mesma ordem de precedência do fake).
            atual = self._jornadas.ler(chamado.jornada_id)
            if atual is None:
                return ResultadoEscalada(False, "jornada_inexistente")
            if atual.escalada is not None:
                return ResultadoEscalada(
                    False, "jornada_ja_escalada", atual.escalada.chamado_numero
                )
            if self.obter(chamado.numero) is not None:
                return ResultadoEscalada(False, "numero_em_uso")
            # Nenhum dos dois: o estado da Jornada mudou entre a leitura e a transação.
            if time.monotonic() - inicio > ORCAMENTO_GRAVACAO_S / 2:
                break
        raise ErroRepositorio("chamados: conflito ao criar o Chamado com escalada")

    # -- leitura ------------------------------------------------------------------------

    def obter(self, numero: str) -> Chamado | None:
        item = self._t.obter(self._t.chave(numero))
        return None if item is None else chamado_de_item(item)

    def listar_fila(self) -> list[Chamado]:
        itens = self._t.consultar(
            "#pk = :pk",
            {"#pk": "fila_pk"},
            {":pk": FILA_PK},
            indice=GSI_FILA,
        )
        chamados = [chamado_de_item(i) for i in itens]
        return sorted(chamados, key=lambda c: c.fila_sk or "")

    def listar_todos(self) -> list[Chamado]:
        """Declarado só para satisfazer o Protocol `ChamadosRepo`.

        PENDÊNCIA (camada AWS): a implementação real, que lista também os Chamados
        encerrados, fica para quando a camada AWS entrar em escopo. Hoje a consulta
        só existe no Modo_Local (repositório em memória). Não usa a tabela, nem
        `Query`, nem `Scan`.
        """
        raise ErroIndisponivelForaDoModoLocal("ChamadosDynamoDB.listar_todos")

    # -- atualizações -------------------------------------------------------------------

    def assumir(
        self, numero: str, usuario: str, nome: str, em: datetime
    ) -> ResultadoCondicional[Chamado]:
        aplicado, c = self._mutar(
            numero,
            "SET #resp = :resp, #status = :em_atendimento",
            {"#resp": "responsavel", "#status": "status"},
            {
                ":resp": {"usuario": usuario, "nome": nome, "inicio": dt_str(em)},
                ":em_atendimento": "em_atendimento",
                ":encerrado": "encerrado",
            },
            condicao="attribute_not_exists(#resp) AND #status <> :encerrado",
        )
        return ResultadoCondicional(aplicado, c)

    def reavaliar(
        self, numero: str, decisao: DecisaoRegistrada, pacote: PacoteRepasse
    ) -> ResultadoCondicional[Chamado]:
        if pacote.numero_chamado != numero or pacote.prioridade != decisao.prioridade:
            raise ErroRepositorio("o Pacote deve ser do mesmo Chamado e refletir a nova decisão")
        pacote_item = _validar(pacote)

        for _ in range(TENTATIVAS_OTIMISTAS):
            c = self._exigir(numero)
            eleva = RANKING_PRIORIDADE[decisao.prioridade] < RANKING_PRIORIDADE[c.prioridade]
            if c.status == "encerrado" or not eleva:
                return ResultadoCondicional(False, c)

            novo = replace(
                c,
                prioridade=decisao.prioridade,
                classificacao=decisao.classificacao,
                canal=decisao.canal,
                decisao_criterio=decisao.criterio,
                pacote=pacote,
            )
            # Chamado e decisão da Jornada mudam juntos; `fila_sk` reposiciona na fila.
            falhas = executar_transacao(
                self._t,
                [
                    update_transacao(
                        self._t,
                        self._t.chave(numero),
                        "SET #prioridade = :prioridade, #classificacao = :classificacao, "
                        "#canal = :canal, #criterio = :criterio, #pacote = :pacote, "
                        "#fila_sk = :fila_sk",
                        "attribute_exists(#numero) AND #status <> :encerrado "
                        "AND #prioridade = :prioridade_lida",
                        {
                            "#numero": "numero",
                            "#status": "status",
                            "#prioridade": "prioridade",
                            "#classificacao": "classificacao",
                            "#canal": "canal",
                            "#criterio": "decisao_criterio",
                            "#pacote": "pacote",
                            "#fila_sk": "fila_sk",
                        },
                        {
                            ":encerrado": "encerrado",
                            ":prioridade_lida": c.prioridade,
                            ":prioridade": decisao.prioridade,
                            ":classificacao": decisao.classificacao,
                            ":canal": decisao.canal,
                            ":criterio": decisao.criterio,
                            ":pacote": pacote_item,
                            ":fila_sk": montar_fila_sk(decisao.prioridade, c.criado_em, numero),
                        },
                    ),
                    update_transacao(
                        self._tj,
                        self._tj.chave(c.jornada_id),
                        "SET #escalada.#decisao = :decisao",
                        "attribute_exists(#escalada)",
                        {"#escalada": "escalada", "#decisao": "decisao"},
                        {":decisao": jornadas_ddb.decisao_para_item(decisao)},
                    ),
                ],
                "reavaliar",
            )
            if falhas is None:
                return ResultadoCondicional(True, novo)
            if len(falhas) > 1 and falhas[1] and not falhas[0]:
                raise ErroRepositorio("chamados: a Jornada do Chamado não tem escalada")
            # Chamado mudou entre a leitura e a transação: relê e decide de novo.
        raise ErroRepositorio("chamados: conflito ao reavaliar o Chamado")

    def atualizar_campos_ia(
        self,
        numero: str,
        resumo: str,
        sentimento: str,
        proxima_acao: str,
        status: StatusPacoteIA,
    ) -> Chamado:
        atual = self._exigir(numero)
        # O Pacote resultante precisa continuar válido; senão nada é gravado.
        _validar(
            replace(atual.pacote, resumo=resumo, sentimento=sentimento, proxima_acao=proxima_acao)  # type: ignore[arg-type]
        )
        # Só os três campos de IA mudam: um enriquecimento tardio não desfaz uma reavaliação.
        return self._mutar(
            numero,
            "SET #pacote.#resumo = :resumo, #pacote.#sentimento = :sentimento, "
            "#pacote.#acao = :acao, #ia = :ia",
            {
                "#pacote": "pacote",
                "#resumo": "resumo",
                "#sentimento": "sentimento",
                "#acao": "proxima_acao",
                "#ia": "pacote_ia_status",
            },
            {":resumo": resumo, ":sentimento": sentimento, ":acao": proxima_acao, ":ia": status},
        )[1]

    def _definir(self, numero: str, atributo: str, valor: Any) -> Chamado:
        return self._mutar(numero, "SET #a = :v", {"#a": atributo}, {":v": valor})[1]

    def marcar_alerta_p1_visto(self, numero: str) -> Chamado:
        return self._definir(numero, "alerta_p1_visto", True)

    def definir_resposta_nao_lida(self, numero: str, valor: bool) -> Chamado:
        return self._definir(numero, "resposta_nao_lida", valor)

    def definir_os_status(self, numero: str, status: StatusOS) -> Chamado:
        return self._definir(numero, "os_status", status)

    def definir_agendamento(self, numero: str, data_hora: datetime) -> Chamado:
        return self._definir(numero, "agendamento", {"data_hora": _com_fuso(data_hora)})

    def adicionar_anexo(
        self, numero: str, anexo: AnexoChamado, maximo: int = 3
    ) -> ResultadoCondicional[Chamado]:
        # A lista do Chamado e a do Pacote crescem juntas, com o limite checado no servidor.
        item_pacote = {"chave": anexo.chave, "mime": anexo.mime}
        aplicado, c = self._mutar(
            numero,
            "SET #anexos = list_append(if_not_exists(#anexos, :vazio), :novo), "
            "#pacote.#anexos = list_append(#pacote.#anexos, :novo_pacote)",
            {"#anexos": "anexos", "#pacote": "pacote"},
            {
                ":vazio": [],
                ":novo": [_anexo_para_item(anexo)],
                ":novo_pacote": [item_pacote],
                ":maximo": maximo,
            },
            condicao="attribute_not_exists(#anexos) OR size(#anexos) < :maximo",
        )
        return ResultadoCondicional(aplicado, c)

    def encerrar(
        self, numero: str, encerramento: EncerramentoChamado
    ) -> ResultadoCondicional[Chamado]:
        aplicado, c = self._mutar(
            numero,
            "SET #status = :encerrado, #enc = :enc REMOVE #fila_pk, #fila_sk",
            {
                "#status": "status",
                "#enc": "encerramento",
                "#fila_pk": "fila_pk",
                "#fila_sk": "fila_sk",
            },
            {":encerrado": "encerrado", ":enc": _encerramento_para_item(encerramento)},
            condicao="#status <> :encerrado",
        )
        return ResultadoCondicional(aplicado, c)
