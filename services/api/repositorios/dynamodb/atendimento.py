"""Adaptadores DynamoDB de eventos, mensagens, dados pessoais, acessos à PII e Ordem_Servico."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from dominio import ItemJaTentado
from repositorios.dynamodb._base import Tabela, de_dynamo, dt_str, para_dynamo, sem_nulos, str_dt
from repositorios.erros import ErroRepositorio
from repositorios.ids import novo_ulid
from repositorios.modelos import (
    AcessoPII,
    AutorMensagem,
    Consentimento,
    DadosPessoaisRegistro,
    Evento,
    MensagemChamado,
    OrdemServico,
    ResultadoCondicional,
    os_id_de,
)

# ----------------------------------------------------------------------------- Eventos


class EventosDynamoDB:
    """Tabela `eventos` (PK `jornada_id`, SK `ts_ulid` = `evento_id`)."""

    def __init__(self, recurso: Any, prefixo: str = "tres") -> None:
        self._t = Tabela(recurso, f"{prefixo}-eventos", "eventos", pk="jornada_id", sk="ts_ulid")

    def registrar(self, evento: Evento) -> bool:
        # `Put` condicional na chave: o reenvio do mesmo `evento_id` não duplica (Req 3.12).
        return self._t.gravar(
            {
                "jornada_id": evento.jornada_id,
                "ts_ulid": evento.ts_ulid,
                "tipo": evento.tipo,
                "em": dt_str(evento.em),
                "dados": para_dynamo(evento.dados),
            },
            condicao="attribute_not_exists(#pk)",
            nomes={"#pk": "jornada_id"},
        )

    def listar(self, jornada_id: str) -> list[Evento]:
        itens = self._t.consultar("#pk = :pk", {"#pk": "jornada_id"}, {":pk": jornada_id})
        return [
            Evento(
                jornada_id=i["jornada_id"],
                evento_id=i["ts_ulid"],
                tipo=i["tipo"],
                em=str_dt(i["em"]),
                dados=de_dynamo(i.get("dados", {})),
            )
            for i in sorted(itens, key=lambda i: i["ts_ulid"])
        ]


# ----------------------------------------------------------------------------- Mensagens


def _mensagem_de_item(i: dict[str, Any]) -> MensagemChamado:
    return MensagemChamado(
        numero=i["numero"],
        ts_ulid=i["ts_ulid"],
        autor=i["autor"],
        texto=i["texto"],
        em=str_dt(i["em"]),
        lida=bool(i.get("lida", False)),
    )


class MensagensChamadoDynamoDB:
    """Tabela `mensagens_chamado` (PK `numero`, SK `ts_ulid`)."""

    def __init__(self, recurso: Any, prefixo: str = "tres") -> None:
        self._t = Tabela(
            recurso,
            f"{prefixo}-mensagens_chamado",
            "mensagens_chamado",
            pk="numero",
            sk="ts_ulid",
        )

    def adicionar(
        self, numero: str, autor: AutorMensagem, texto: str, em: datetime
    ) -> MensagemChamado:
        msg = MensagemChamado(numero, novo_ulid(em), autor, texto, em)
        gravou = self._t.gravar(
            {
                "numero": numero,
                "ts_ulid": msg.ts_ulid,
                "autor": autor,
                "texto": texto,
                "em": dt_str(em),
                "lida": False,
            },
            condicao="attribute_not_exists(#pk)",
            nomes={"#pk": "numero"},
        )
        if not gravou:  # colisão de ULID (praticamente impossível): não sobrescreve
            raise ErroRepositorio("mensagens_chamado: chave de mensagem já existe")
        return msg

    def listar(self, numero: str) -> list[MensagemChamado]:
        itens = self._t.consultar("#pk = :pk", {"#pk": "numero"}, {":pk": numero})
        return [_mensagem_de_item(i) for i in sorted(itens, key=lambda i: i["ts_ulid"])]

    def marcar_lidas(self, numero: str, autor: AutorMensagem) -> int:
        pendentes = self._t.consultar(
            "#pk = :pk",
            {"#pk": "numero", "#autor": "autor", "#lida": "lida"},
            {":pk": numero, ":autor": autor, ":falso": False},
            filtro="#autor = :autor AND #lida = :falso",
        )
        mudadas = 0
        for item in pendentes:
            # Condicional: se outra requisição já marcou, não conta duas vezes.
            aplicado, _ = self._t.atualizar(
                self._t.chave(numero, item["ts_ulid"]),
                "SET #lida = :verdadeiro",
                {"#lida": "lida"},
                {":verdadeiro": True, ":falso": False},
                condicao="#lida = :falso",
            )
            mudadas += int(aplicado)
        return mudadas


# ----------------------------------------------------------------------------- PII


def _dados_pessoais_de_item(i: dict[str, Any]) -> DadosPessoaisRegistro:
    c = i["consentimento"]
    return DadosPessoaisRegistro(
        numero=i["numero"],
        consentimento=Consentimento(str_dt(c["em"]), c["versao_finalidade"]),
        telefone=i.get("telefone"),
        cep=i.get("cep"),
        nome=i.get("nome"),
        email=i.get("email"),
    )


class DadosPessoaisDynamoDB:
    """Tabela `dados_pessoais` (PK `numero`): único lugar com telefone, CEP, nome e e-mail
    (Req 18)."""

    def __init__(self, recurso: Any, prefixo: str = "tres") -> None:
        self._t = Tabela(recurso, f"{prefixo}-dados_pessoais", "dados_pessoais", pk="numero")

    def salvar(
        self,
        numero: str,
        consentimento: Consentimento,
        telefone: str | None = None,
        cep: str | None = None,
        nome: str | None = None,
        email: str | None = None,
    ) -> DadosPessoaisRegistro:
        # Upsert (de propósito): só os campos informados substituem os atuais (Req 12.4).
        partes = ["#consentimento = :consentimento"]
        nomes = {"#consentimento": "consentimento"}
        valores: dict[str, Any] = {
            ":consentimento": {
                "em": dt_str(consentimento.em),
                "versao_finalidade": consentimento.versao_finalidade,
            }
        }
        for atributo, valor in (
            ("telefone", telefone),
            ("cep", cep),
            ("nome", nome),
            ("email", email),
        ):
            if valor is not None:
                partes.append(f"#{atributo} = :{atributo}")
                nomes[f"#{atributo}"] = atributo
                valores[f":{atributo}"] = valor
        _, item = self._t.atualizar(
            self._t.chave(numero),
            "SET " + ", ".join(partes),
            nomes,
            valores,
            criar_se_ausente=True,
        )
        return _dados_pessoais_de_item(item)

    def obter(self, numero: str) -> DadosPessoaisRegistro | None:
        item = self._t.obter(self._t.chave(numero))
        return None if item is None else _dados_pessoais_de_item(item)


class AcessosPIIDynamoDB:
    """Tabela `acessos_pii` (PK `numero`, SK `ts_ulid`): trilha de acesso (Req 18.6)."""

    def __init__(self, recurso: Any, prefixo: str = "tres") -> None:
        self._t = Tabela(
            recurso, f"{prefixo}-acessos_pii", "acessos_pii", pk="numero", sk="ts_ulid"
        )

    def registrar(self, numero: str, atendente_id: str, em: datetime) -> AcessoPII:
        # Se a gravação falhar, `ErroRepositorio` sobe e os dados não são devolvidos (Req 18.9).
        acesso = AcessoPII(numero, novo_ulid(em), atendente_id, em.replace(microsecond=0))
        gravou = self._t.gravar(
            {
                "numero": numero,
                "ts_ulid": acesso.ts_ulid,
                "atendente_id": atendente_id,
                "em": dt_str(acesso.em),
            },
            condicao="attribute_not_exists(#pk)",
            nomes={"#pk": "numero"},
        )
        if not gravou:
            raise ErroRepositorio("acessos_pii: chave de acesso já existe")
        return acesso

    def listar(self, numero: str) -> list[AcessoPII]:
        itens = self._t.consultar("#pk = :pk", {"#pk": "numero"}, {":pk": numero})
        return [
            AcessoPII(i["numero"], i["ts_ulid"], i["atendente_id"], str_dt(i["em"]))
            for i in sorted(itens, key=lambda i: i["ts_ulid"])
        ]


# ----------------------------------------------------------------------------- OS


def _ordem_de_item(i: dict[str, Any]) -> OrdemServico:
    return OrdemServico(
        numero=i["numero"],
        modelo=i["modelo"],
        numero_serie=i["numero_serie"],
        categoria=i["categoria"],
        ja_tentado=tuple(
            ItemJaTentado(t["passo"], t["camada"], t["resultado"]) for t in i.get("ja_tentado", [])
        ),
        status=i["status"],
    )


class OrdensServicoDynamoDB:
    """Tabela `ordens_servico` (PK `os_id` = `OS#<numero>`)."""

    def __init__(self, recurso: Any, prefixo: str = "tres") -> None:
        self._t = Tabela(recurso, f"{prefixo}-ordens_servico", "ordens_servico", pk="os_id")

    def criar_rascunho(self, ordem: OrdemServico) -> ResultadoCondicional[OrdemServico]:
        # Chave determinística + `Put` condicional: no máximo uma OS por Chamado (Req 11.8).
        item = sem_nulos(
            {
                "os_id": ordem.os_id,
                "numero": ordem.numero,
                "modelo": ordem.modelo,
                "numero_serie": ordem.numero_serie,
                "categoria": ordem.categoria,
                "ja_tentado": [
                    {"passo": t.passo, "camada": t.camada, "resultado": t.resultado}
                    for t in ordem.ja_tentado
                ],
                "status": ordem.status,
            }
        )
        if self._t.gravar(item, "attribute_not_exists(#pk)", {"#pk": "os_id"}):
            return ResultadoCondicional(True, ordem)
        existente = self.obter(ordem.numero)
        if existente is None:
            raise ErroRepositorio("ordens_servico: registro sumiu durante a criação")
        return ResultadoCondicional(False, existente)

    def obter(self, numero: str) -> OrdemServico | None:
        item = self._t.obter(self._t.chave(os_id_de(numero)))
        return None if item is None else _ordem_de_item(item)

    def confirmar(self, numero: str) -> ResultadoCondicional[OrdemServico]:
        aplicado, item = self._t.atualizar(
            self._t.chave(os_id_de(numero)),
            "SET #status = :aberta",
            {"#status": "status"},
            {":aberta": "aberta"},
            condicao="#status <> :aberta",
        )
        return ResultadoCondicional(aplicado, _ordem_de_item(item))
