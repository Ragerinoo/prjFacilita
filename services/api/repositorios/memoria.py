"""Fakes em memória dos repositórios, com as mesmas garantias condicionais do DynamoDB.

Servem aos testes das camadas de cima (escalada, rotas, encerramento) sem I/O. Todos os
repositórios de uma instância compartilham uma única trava reentrante, o que torna cada
método atômico (equivalente a um `UpdateItem` condicional) e a transação
"Chamado + Jornada" de `criar_com_escalada` tudo-ou-nada (equivalente ao `TransactWriteItems`).

Os registros são imutáveis; o que é mutável (`Evento.dados`, `Config`, fontes do cache) é
copiado na entrada e na saída para o chamador nunca alterar o estado interno.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from threading import RLock
from typing import Any

from dominio import (
    Anexo,
    Camada,
    EntradaCache,
    Nivel,
    PacoteRepasse,
    ResultadoEncerramento,
    ResultadoInsercao,
    aceitar_insercao_cache,
    aplicar_encerramento,
    chave_cache,
    marcar_abandono,
    normalizar_pergunta,
    proximo_estado_frustracao,
    registrar_interacao,
    validar_pacote,
)
from dominio.pacote import pacote_para_dict
from repositorios.catalogo import CatalogoMemoria
from repositorios.erros import ErroNaoEncontrado, ErroRepositorio
from repositorios.ids import novo_ulid
from repositorios.interfaces import Repositorios
from repositorios.modelos import (
    RANKING_PRIORIDADE,
    AcessoPII,
    AgregadoDia,
    AnexoChamado,
    AutorMensagem,
    Avaliacao,
    Chamado,
    Consentimento,
    DadosPessoaisRegistro,
    DecisaoRegistrada,
    EncerramentoChamado,
    EscaladaJornada,
    Evento,
    GatilhoRegistrado,
    Jornada,
    MensagemChamado,
    OrdemServico,
    OrigemRisco,
    PerfilCS,
    RegistroCache,
    Responsavel,
    ResultadoCondicional,
    ResultadoEscalada,
    RiscoMarcado,
    SessaoCS,
    StatusOS,
    StatusPacoteIA,
    UsuarioCS,
    os_id_de,
)

_QUATRO_CASAS = Decimal("0.0001")


def _nova_trava(trava: RLock | None) -> RLock:
    return trava if trava is not None else RLock()


def _exigir_pacote_valido(pacote: PacoteRepasse) -> None:
    """Como o adaptador DynamoDB: o Pacote só é gravado se for válido no esquema v1."""
    erros = validar_pacote(pacote_para_dict(pacote))
    if erros:
        raise ErroRepositorio(
            "Pacote inválido: " + "; ".join(f"{e.campo}: {e.motivo}" for e in erros)
        )


# ----------------------------------------------------------------------------- Jornadas


class JornadasMemoria:
    def __init__(self, trava: RLock | None = None) -> None:
        self._trava = _nova_trava(trava)
        self._itens: dict[str, Jornada] = {}

    # -- auxiliares (chamar com a trava) ------------------------------------------------

    def _exigir(self, jornada_id: str) -> Jornada:
        j = self._itens.get(jornada_id)
        if j is None:
            raise ErroNaoEncontrado("jornadas", jornada_id)
        return j

    def _salvar(self, j: Jornada) -> Jornada:
        self._itens[j.jornada_id] = j
        return j

    # -- interface ----------------------------------------------------------------------

    def criar(self, jornada: Jornada) -> ResultadoCondicional[Jornada]:
        with self._trava:
            existente = self._itens.get(jornada.jornada_id)
            if existente is not None:
                return ResultadoCondicional(False, existente)
            return ResultadoCondicional(True, self._salvar(jornada))

    def obter(self, jornada_id: str) -> Jornada | None:
        with self._trava:
            return self._itens.get(jornada_id)

    def associar_modelo(
        self, jornada_id: str, modelo_id: str, numero_serie: str | None = None
    ) -> Jornada:
        with self._trava:
            j = self._exigir(jornada_id)
            serie = numero_serie if numero_serie is not None else j.numero_serie
            return self._salvar(replace(j, modelo_id=modelo_id, numero_serie=serie, origem="busca"))

    def registrar_seletor(self, jornada_id: str, area: str, estado: str) -> Jornada:
        with self._trava:
            j = self._exigir(jornada_id)
            return self._salvar(replace(j, seletor_area=area, seletor_estado=estado))

    def registrar_interacao(self, jornada_id: str, em: datetime) -> Jornada:
        with self._trava:
            j = self._exigir(jornada_id)
            return self._salvar(j.com_estado_dominio(registrar_interacao(j.estado_dominio(), em)))

    def registrar_problema_selecionado(self, jornada_id: str, problema_id: int) -> bool:
        with self._trava:
            j = self._exigir(jornada_id)
            primeira = problema_id not in j.problemas_selecionados
            selecionados = j.problemas_selecionados + ((problema_id,) if primeira else ())
            self._salvar(replace(j, problema_id=problema_id, problemas_selecionados=selecionados))
            return primeira

    def marcar_guia_respondeu_nao(self, jornada_id: str) -> Jornada:
        with self._trava:
            return self._salvar(replace(self._exigir(jornada_id), guia_respondeu_nao=True))

    def marcar_risco(
        self, jornada_id: str, origem: OrigemRisco, em: datetime
    ) -> ResultadoCondicional[Jornada]:
        with self._trava:
            j = self._exigir(jornada_id)
            if j.risco is not None:
                return ResultadoCondicional(False, j)
            return ResultadoCondicional(
                True, self._salvar(replace(j, risco=RiscoMarcado(origem, em)))
            )

    def incrementar_msgs_modelo(
        self, jornada_id: str, limite: int
    ) -> ResultadoCondicional[Jornada]:
        with self._trava:
            j = self._exigir(jornada_id)
            if not j.msgs_modelo < limite:
                return ResultadoCondicional(False, j)
            return ResultadoCondicional(
                True, self._salvar(replace(j, msgs_modelo=j.msgs_modelo + 1))
            )

    def incrementar_ia_nao(self, jornada_id: str) -> Jornada:
        with self._trava:
            j = self._exigir(jornada_id)
            return self._salvar(replace(j, ia_nao=j.ia_nao + 1))

    def atualizar_frustracao(self, jornada_id: str, nivel: Nivel) -> Jornada:
        with self._trava:
            j = self._exigir(jornada_id)
            seq = proximo_estado_frustracao(j.frustracao_alta_seq, nivel)
            return self._salvar(replace(j, frustracao_alta_seq=seq))

    def somar_custo_ia(self, jornada_id: str, custo_brl: Decimal) -> Jornada:
        if custo_brl < 0:
            raise ValueError("custo_brl não pode ser negativo")
        with self._trava:
            j = self._exigir(jornada_id)
            total = (j.custo_ia_brl + custo_brl).quantize(_QUATRO_CASAS, rounding=ROUND_HALF_UP)
            return self._salvar(replace(j, custo_ia_brl=total))

    def registrar_gatilho_adicional(
        self, jornada_id: str, gatilho: GatilhoRegistrado
    ) -> ResultadoCondicional[Jornada]:
        with self._trava:
            j = self._exigir(jornada_id)
            if j.escalada is None:
                return ResultadoCondicional(False, j)
            escalada = replace(j.escalada, gatilhos=j.escalada.gatilhos + (gatilho,))
            return ResultadoCondicional(True, self._salvar(replace(j, escalada=escalada)))

    def encerrar(
        self,
        jornada_id: str,
        camada: Camada,
        em: datetime,
        custo_brl: Decimal = Decimal("0"),
        problema_id: int | None = None,
        desfecho: str | None = None,
    ) -> ResultadoEncerramento:
        with self._trava:
            j = self._exigir(jornada_id)
            r = aplicar_encerramento(
                j.estado_dominio(), camada, em, custo_brl, problema_id, desfecho
            )
            if r.aplicado:
                self._salvar(j.com_estado_dominio(r.jornada))
            return r

    def marcar_abandono(
        self, jornada_id: str, agora: datetime, custo_brl: Decimal = Decimal("0")
    ) -> ResultadoEncerramento:
        with self._trava:
            j = self._exigir(jornada_id)
            r = marcar_abandono(j.estado_dominio(), agora, custo_brl, j.problema_id)
            if r.aplicado:
                self._salvar(j.com_estado_dominio(r.jornada))
            return r

    def listar_ativas_sem_interacao_ate(self, limite: datetime) -> list[Jornada]:
        with self._trava:
            ativas = [
                j for j in self._itens.values() if j.ativa_pk and j.ultima_interacao <= limite
            ]
        return sorted(ativas, key=lambda j: (j.ultima_interacao, j.jornada_id))

    def listar_encerradas(self, inicio: datetime, fim: datetime) -> list[Jornada]:
        with self._trava:
            itens = [
                j
                for j in self._itens.values()
                if j.encerrada_em is not None and inicio <= j.encerrada_em <= fim
            ]
        return sorted(itens, key=lambda j: (j.encerrada_em, j.jornada_id))  # type: ignore[arg-type,return-value]

    # -- usado só pela transação do ChamadosMemoria -------------------------------------

    def _escalar(self, jornada_id: str, escalada: EscaladaJornada) -> None:
        j = self._itens[jornada_id]
        estado = "escalada" if j.estado == "ativa" else j.estado
        self._itens[jornada_id] = replace(j, escalada=escalada, estado=estado)

    def _atualizar_decisao(self, jornada_id: str, decisao: DecisaoRegistrada) -> None:
        j = self._itens.get(jornada_id)
        if j is not None and j.escalada is not None:
            self._itens[jornada_id] = replace(j, escalada=replace(j.escalada, decisao=decisao))


# ----------------------------------------------------------------------------- Eventos


class EventosMemoria:
    def __init__(self, trava: RLock | None = None) -> None:
        self._trava = _nova_trava(trava)
        self._itens: dict[tuple[str, str], Evento] = {}

    def registrar(self, evento: Evento) -> bool:
        chave = (evento.jornada_id, evento.ts_ulid)
        with self._trava:
            if chave in self._itens:
                return False
            self._itens[chave] = copy.deepcopy(evento)
            return True

    def listar(self, jornada_id: str) -> list[Evento]:
        with self._trava:
            itens = [e for (jid, _), e in self._itens.items() if jid == jornada_id]
        return [copy.deepcopy(e) for e in sorted(itens, key=lambda e: e.ts_ulid)]


# ----------------------------------------------------------------------------- Chamados


class ChamadosMemoria:
    def __init__(self, jornadas: JornadasMemoria, trava: RLock | None = None) -> None:
        self._trava = _nova_trava(trava)
        self._jornadas = jornadas
        self._itens: dict[str, Chamado] = {}

    def _exigir(self, numero: str) -> Chamado:
        c = self._itens.get(numero)
        if c is None:
            raise ErroNaoEncontrado("chamados", numero)
        return c

    def _salvar(self, c: Chamado) -> Chamado:
        self._itens[c.numero] = c
        return c

    def criar_com_escalada(
        self,
        chamado: Chamado,
        gatilho: GatilhoRegistrado,
        decisao: DecisaoRegistrada,
    ) -> ResultadoEscalada:
        if chamado.status != "aberto":
            raise ErroRepositorio("um Chamado novo deve ter status 'aberto'")
        _exigir_pacote_valido(chamado.pacote)
        with self._trava:
            # Todas as condições são checadas antes de qualquer escrita (tudo ou nada).
            jornada = self._jornadas._itens.get(chamado.jornada_id)
            if jornada is None:
                return ResultadoEscalada(False, "jornada_inexistente")
            if jornada.escalada is not None:
                return ResultadoEscalada(
                    False, "jornada_ja_escalada", jornada.escalada.chamado_numero
                )
            if chamado.numero in self._itens:
                return ResultadoEscalada(False, "numero_em_uso")
            self._salvar(chamado)
            self._jornadas._escalar(
                chamado.jornada_id,
                EscaladaJornada(
                    chamado_numero=chamado.numero,
                    em=chamado.criado_em,
                    gatilhos=(gatilho,),
                    decisao=decisao,
                ),
            )
            return ResultadoEscalada(True, "criado")

    def obter(self, numero: str) -> Chamado | None:
        with self._trava:
            return self._itens.get(numero)

    def listar_fila(self) -> list[Chamado]:
        with self._trava:
            fila = [c for c in self._itens.values() if c.fila_sk is not None]
        return sorted(fila, key=lambda c: c.fila_sk or "")

    def listar_todos(self) -> list[Chamado]:
        with self._trava:
            todos = list(self._itens.values())
        return sorted(todos, key=lambda c: (c.criado_em, c.numero))

    def assumir(
        self, numero: str, usuario: str, nome: str, em: datetime
    ) -> ResultadoCondicional[Chamado]:
        with self._trava:
            c = self._exigir(numero)
            if c.status == "encerrado" or c.responsavel is not None:
                return ResultadoCondicional(False, c)
            novo = replace(c, responsavel=Responsavel(usuario, nome, em), status="em_atendimento")
            return ResultadoCondicional(True, self._salvar(novo))

    def reavaliar(
        self, numero: str, decisao: DecisaoRegistrada, pacote: PacoteRepasse
    ) -> ResultadoCondicional[Chamado]:
        if pacote.numero_chamado != numero or pacote.prioridade != decisao.prioridade:
            raise ErroRepositorio("o Pacote deve ser do mesmo Chamado e refletir a nova decisão")
        _exigir_pacote_valido(pacote)
        with self._trava:
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
            self._salvar(novo)
            self._jornadas._atualizar_decisao(c.jornada_id, decisao)
            return ResultadoCondicional(True, novo)

    def atualizar_campos_ia(
        self,
        numero: str,
        resumo: str,
        sentimento: str,
        proxima_acao: str,
        status: StatusPacoteIA,
    ) -> Chamado:
        with self._trava:
            c = self._exigir(numero)
            pacote = replace(
                c.pacote, resumo=resumo, sentimento=sentimento, proxima_acao=proxima_acao
            )  # type: ignore[arg-type]
            _exigir_pacote_valido(pacote)
            return self._salvar(replace(c, pacote=pacote, pacote_ia_status=status))

    def marcar_alerta_p1_visto(self, numero: str) -> Chamado:
        with self._trava:
            return self._salvar(replace(self._exigir(numero), alerta_p1_visto=True))

    def definir_resposta_nao_lida(self, numero: str, valor: bool) -> Chamado:
        with self._trava:
            return self._salvar(replace(self._exigir(numero), resposta_nao_lida=valor))

    def definir_os_status(self, numero: str, status: StatusOS) -> Chamado:
        with self._trava:
            return self._salvar(replace(self._exigir(numero), os_status=status))

    def definir_agendamento(self, numero: str, data_hora: datetime) -> Chamado:
        with self._trava:
            return self._salvar(replace(self._exigir(numero), agendamento=data_hora))

    def adicionar_anexo(
        self, numero: str, anexo: AnexoChamado, maximo: int = 3
    ) -> ResultadoCondicional[Chamado]:
        with self._trava:
            c = self._exigir(numero)
            if not len(c.anexos) < maximo:
                return ResultadoCondicional(False, c)
            pacote = replace(c.pacote, anexos=c.pacote.anexos + (Anexo(anexo.chave, anexo.mime),))
            novo = replace(c, anexos=c.anexos + (anexo,), pacote=pacote)
            return ResultadoCondicional(True, self._salvar(novo))

    def encerrar(
        self, numero: str, encerramento: EncerramentoChamado
    ) -> ResultadoCondicional[Chamado]:
        with self._trava:
            c = self._exigir(numero)
            if c.status == "encerrado":
                return ResultadoCondicional(False, c)
            novo = replace(c, status="encerrado", encerramento=encerramento)
            return ResultadoCondicional(True, self._salvar(novo))


# ----------------------------------------------------------------------------- Mensagens


class MensagensChamadoMemoria:
    def __init__(self, trava: RLock | None = None) -> None:
        self._trava = _nova_trava(trava)
        self._itens: dict[str, list[MensagemChamado]] = {}

    def adicionar(
        self, numero: str, autor: AutorMensagem, texto: str, em: datetime
    ) -> MensagemChamado:
        msg = MensagemChamado(numero, novo_ulid(em), autor, texto, em)
        with self._trava:
            self._itens.setdefault(numero, []).append(msg)
        return msg

    def listar(self, numero: str) -> list[MensagemChamado]:
        with self._trava:
            return sorted(self._itens.get(numero, []), key=lambda m: m.ts_ulid)

    def marcar_lidas(self, numero: str, autor: AutorMensagem) -> int:
        with self._trava:
            msgs = self._itens.get(numero, [])
            mudadas = 0
            for i, m in enumerate(msgs):
                if m.autor == autor and not m.lida:
                    msgs[i] = replace(m, lida=True)
                    mudadas += 1
            return mudadas


# ----------------------------------------------------------------------------- PII


class DadosPessoaisMemoria:
    def __init__(self, trava: RLock | None = None) -> None:
        self._trava = _nova_trava(trava)
        self._itens: dict[str, DadosPessoaisRegistro] = {}

    def salvar(
        self,
        numero: str,
        consentimento: Consentimento,
        telefone: str | None = None,
        cep: str | None = None,
        nome: str | None = None,
        email: str | None = None,
    ) -> DadosPessoaisRegistro:
        with self._trava:
            atual = self._itens.get(numero)
            novo = DadosPessoaisRegistro(
                numero=numero,
                consentimento=consentimento,
                telefone=telefone if telefone is not None else (atual.telefone if atual else None),
                cep=cep if cep is not None else (atual.cep if atual else None),
                nome=nome if nome is not None else (atual.nome if atual else None),
                email=email if email is not None else (atual.email if atual else None),
            )
            self._itens[numero] = novo
            return novo

    def obter(self, numero: str) -> DadosPessoaisRegistro | None:
        with self._trava:
            return self._itens.get(numero)


class AcessosPIIMemoria:
    def __init__(self, trava: RLock | None = None) -> None:
        self._trava = _nova_trava(trava)
        self._itens: dict[str, list[AcessoPII]] = {}

    def registrar(self, numero: str, atendente_id: str, em: datetime) -> AcessoPII:
        em_segundos = em.replace(microsecond=0)
        acesso = AcessoPII(numero, novo_ulid(em), atendente_id, em_segundos)
        with self._trava:
            self._itens.setdefault(numero, []).append(acesso)
        return acesso

    def listar(self, numero: str) -> list[AcessoPII]:
        with self._trava:
            return sorted(self._itens.get(numero, []), key=lambda a: a.ts_ulid)


# ----------------------------------------------------------------------------- OS


class OrdensServicoMemoria:
    def __init__(self, trava: RLock | None = None) -> None:
        self._trava = _nova_trava(trava)
        self._itens: dict[str, OrdemServico] = {}

    def criar_rascunho(self, ordem: OrdemServico) -> ResultadoCondicional[OrdemServico]:
        chave = os_id_de(ordem.numero)
        with self._trava:
            existente = self._itens.get(chave)
            if existente is not None:
                return ResultadoCondicional(False, existente)
            self._itens[chave] = ordem
            return ResultadoCondicional(True, ordem)

    def obter(self, numero: str) -> OrdemServico | None:
        with self._trava:
            return self._itens.get(os_id_de(numero))

    def confirmar(self, numero: str) -> ResultadoCondicional[OrdemServico]:
        chave = os_id_de(numero)
        with self._trava:
            ordem = self._itens.get(chave)
            if ordem is None:
                raise ErroNaoEncontrado("ordens_servico", chave)
            if ordem.status == "aberta":
                return ResultadoCondicional(False, ordem)
            nova = replace(ordem, status="aberta")
            self._itens[chave] = nova
            return ResultadoCondicional(True, nova)


# ----------------------------------------------------------------------------- Cache


class CacheRespostasMemoria:
    def __init__(self, trava: RLock | None = None) -> None:
        self._trava = _nova_trava(trava)
        self._itens: dict[str, RegistroCache] = {}

    def obter(self, chave: str) -> RegistroCache | None:
        with self._trava:
            registro = self._itens.get(chave)
        return copy.deepcopy(registro) if registro else None

    def inserir(
        self, entrada: EntradaCache, fontes: Sequence[Mapping[str, Any]] = ()
    ) -> ResultadoInsercao:
        chave = chave_cache(entrada.modelo_id, entrada.pergunta)
        with self._trava:
            atual = self._itens.get(chave)
            existente = (
                EntradaCache(
                    atual.modelo_id,
                    atual.pergunta,
                    atual.resposta,
                    atual.aprovador_id,
                    atual.aprovado_em,
                )
                if atual
                else None
            )
            resultado = aceitar_insercao_cache(entrada, entrada.aprovador_id, existente)
            if resultado.aceita:
                aceita = resultado.entrada
                assert aceita is not None and aceita.aprovador_id is not None
                self._itens[chave] = RegistroCache(
                    chave=chave,
                    modelo_id=aceita.modelo_id,
                    pergunta_normalizada=normalizar_pergunta(aceita.pergunta),
                    pergunta=aceita.pergunta,
                    resposta=aceita.resposta,
                    aprovador_id=aceita.aprovador_id,
                    aprovado_em=aceita.aprovado_em,
                    fontes=tuple(copy.deepcopy(dict(f)) for f in fontes),
                )
            return resultado

    def registrar_hit(self, chave: str) -> int:
        with self._trava:
            registro = self._itens.get(chave)
            if registro is None:
                raise ErroNaoEncontrado("cache_respostas", chave)
            self._itens[chave] = replace(registro, hits=registro.hits + 1)
            return registro.hits + 1


# ----------------------------------------------------------------------------- Avaliações


class AvaliacoesMemoria:
    def __init__(self, trava: RLock | None = None) -> None:
        self._trava = _nova_trava(trava)
        self._itens: dict[str, Avaliacao] = {}

    def registrar(self, avaliacao: Avaliacao) -> ResultadoCondicional[Avaliacao]:
        with self._trava:
            existente = self._itens.get(avaliacao.jornada_id)
            if existente is not None:
                return ResultadoCondicional(False, existente)
            self._itens[avaliacao.jornada_id] = avaliacao
            return ResultadoCondicional(True, avaliacao)

    def obter(self, jornada_id: str) -> Avaliacao | None:
        with self._trava:
            return self._itens.get(jornada_id)

    def listar_periodo(self, inicio: datetime, fim: datetime) -> list[Avaliacao]:
        with self._trava:
            itens = [a for a in self._itens.values() if inicio <= a.em <= fim]
        return sorted(itens, key=lambda a: (a.em, a.jornada_id))


# ----------------------------------------------------------------------------- Agregados


class AgregadosDiaMemoria:
    def __init__(self, trava: RLock | None = None) -> None:
        self._trava = _nova_trava(trava)
        self._itens: dict[tuple[str, str], int] = {}

    def incrementar(self, dia: date, metrica: str, delta: int = 1) -> int:
        if delta <= 0:
            raise ValueError("delta deve ser positivo")
        chave = (dia.isoformat(), metrica)
        with self._trava:
            self._itens[chave] = self._itens.get(chave, 0) + delta
            return self._itens[chave]

    def obter(self, dia: date, metrica: str) -> int:
        with self._trava:
            return self._itens.get((dia.isoformat(), metrica), 0)

    def listar(self, inicio: date, fim: date) -> list[AgregadoDia]:
        ini, f = inicio.isoformat(), fim.isoformat()
        with self._trava:
            itens = [
                AgregadoDia(dia, metrica, valor)
                for (dia, metrica), valor in self._itens.items()
                if ini <= dia <= f
            ]
        return sorted(itens, key=lambda a: (a.dia, a.metrica))


# ----------------------------------------------------------------------------- Painel_CS


class UsuariosCSMemoria:
    def __init__(self, trava: RLock | None = None) -> None:
        self._trava = _nova_trava(trava)
        self._itens: dict[str, UsuarioCS] = {}

    def _exigir(self, usuario: str) -> UsuarioCS:
        u = self._itens.get(usuario)
        if u is None:
            raise ErroNaoEncontrado("usuarios_cs", usuario)
        return u

    def criar(self, usuario: UsuarioCS) -> ResultadoCondicional[UsuarioCS]:
        with self._trava:
            existente = self._itens.get(usuario.usuario)
            if existente is not None:
                return ResultadoCondicional(False, existente)
            self._itens[usuario.usuario] = usuario
            return ResultadoCondicional(True, usuario)

    def obter(self, usuario: str) -> UsuarioCS | None:
        with self._trava:
            return self._itens.get(usuario)

    def _salvar(self, u: UsuarioCS) -> UsuarioCS:
        self._itens[u.usuario] = u
        return u

    def registrar_falha(self, usuario: str, em: datetime, janela: timedelta) -> UsuarioCS:
        with self._trava:
            u = self._exigir(usuario)
            recentes = tuple(f for f in u.falhas if f > em - janela)
            return self._salvar(replace(u, falhas=recentes + (em,)))

    def limpar_falhas(self, usuario: str) -> UsuarioCS:
        with self._trava:
            return self._salvar(replace(self._exigir(usuario), falhas=()))

    def bloquear(self, usuario: str, ate: datetime) -> UsuarioCS:
        with self._trava:
            return self._salvar(replace(self._exigir(usuario), bloqueado_ate=ate))

    def definir_senha(
        self, usuario: str, hash_senha: str, deve_trocar_senha: bool = False
    ) -> UsuarioCS:
        with self._trava:
            u = self._exigir(usuario)
            return self._salvar(
                replace(u, hash_senha=hash_senha, deve_trocar_senha=deve_trocar_senha)
            )

    def perfil_de(self, usuario: str) -> PerfilCS | None:
        with self._trava:
            u = self._itens.get(usuario)
            return u.perfil if u else None


class SessoesCSMemoria:
    def __init__(self, trava: RLock | None = None) -> None:
        self._trava = _nova_trava(trava)
        self._itens: dict[str, SessaoCS] = {}

    def criar(self, sessao: SessaoCS) -> None:
        with self._trava:
            self._itens[sessao.token_hash] = sessao

    def obter(self, token_hash: str) -> SessaoCS | None:
        with self._trava:
            return self._itens.get(token_hash)

    def renovar(self, token_hash: str, agora: datetime, inatividade: timedelta) -> SessaoCS | None:
        with self._trava:
            sessao = self._itens.get(token_hash)
            if sessao is None:
                return None
            if sessao.ultima_atividade < agora - inatividade:
                del self._itens[token_hash]
                return None
            nova = replace(
                sessao,
                ultima_atividade=max(sessao.ultima_atividade, agora),
                ttl=int((agora + inatividade).timestamp()),
            )
            self._itens[token_hash] = nova
            return nova

    def encerrar(self, token_hash: str) -> bool:
        with self._trava:
            return self._itens.pop(token_hash, None) is not None


class ConfigMemoria:
    def __init__(self, trava: RLock | None = None) -> None:
        self._trava = _nova_trava(trava)
        self._itens: dict[str, Any] = {}

    def obter(self, chave: str) -> Any | None:
        with self._trava:
            return copy.deepcopy(self._itens.get(chave))

    def definir(self, chave: str, valor: Any) -> None:
        with self._trava:
            self._itens[chave] = copy.deepcopy(valor)

    def listar(self) -> dict[str, Any]:
        with self._trava:
            return copy.deepcopy(self._itens)


# ----------------------------------------------------------------------------- composição


def criar_repositorios_memoria() -> Repositorios:
    """Conjunto completo de fakes que compartilham a mesma trava (transações coerentes)."""
    trava = RLock()
    jornadas = JornadasMemoria(trava)
    return Repositorios(
        jornadas=jornadas,
        eventos=EventosMemoria(trava),
        chamados=ChamadosMemoria(jornadas, trava),
        mensagens=MensagensChamadoMemoria(trava),
        dados_pessoais=DadosPessoaisMemoria(trava),
        acessos_pii=AcessosPIIMemoria(trava),
        ordens_servico=OrdensServicoMemoria(trava),
        cache=CacheRespostasMemoria(trava),
        avaliacoes=AvaliacoesMemoria(trava),
        agregados=AgregadosDiaMemoria(trava),
        usuarios_cs=UsuariosCSMemoria(trava),
        sessoes=SessoesCSMemoria(trava),
        config=ConfigMemoria(trava),
        catalogo=CatalogoMemoria(),
    )
