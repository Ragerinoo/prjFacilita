"""Validadores de entrada do Consumidor e do Atendente (Req 5, 6, 12, 15, 16).

Funções puras: sem I/O e sem relógio global. O instante "agora" entra por parâmetro
(`validar_agendamento`). Cada validador devolve um `ResultadoValidacao` com a lista
completa de `{campo, motivo}` (mesmo formato de `ErroCampo` do Pacote_Repasse), para que
a camada de API monte o envelope de erro do design sem reinterpretar regras.

`validar_telefone` e `validar_cep` seguem o contrato do design e devolvem `bool`.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Collection
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dominio.pacote import ErroCampo
from dominio.tipos import Prioridade

# --- Limites (Req 5.2, 6.11, 12.6, 12.7, 15.3, 15.6, 16.1, 16.2) -----------------------------

TELEFONE_DIGITOS: Final = (10, 11)
CEP_DIGITOS: Final = 8
CARACTERES_ACEITOS_CONTATO: Final = frozenset("0123456789 ()-")

MIMES_FOTO: Final = frozenset({"image/jpeg", "image/png"})
FOTO_MAX_BYTES: Final = 5 * 1024 * 1024  # 5 MB
FOTOS_MAX_POR_CHAMADO: Final = 3

MENSAGEM_CONSUMIDOR_MAX: Final = 1000
MENSAGEM_ATENDENTE_MAX: Final = 2000
NOTA_MIN: Final = 1
NOTA_MAX: Final = 5
COMENTARIO_MAX: Final = 500
AGENDAMENTO_MAX_DIAS: Final = 30
SOLUCAO_MAX: Final = 500
PERGUNTA_CACHE_MAX: Final = 300
RESPOSTA_CACHE_MAX: Final = 1000

DESFECHOS: Final = ("falso defeito", "defeito real")
TIPOS_SOLUCAO: Final = ("instrução do manual", "outra")

DadoPessoal = str  # "telefone" | "cep"
TELEFONE: Final = "telefone"
CEP: Final = "cep"
_DADOS_POR_PRIORIDADE: Final[dict[str, tuple[str, ...]]] = {
    "P1": (TELEFONE,),
    "P2": (TELEFONE, CEP),
    "P3": (),
}


def _carregar_fuso_brasilia() -> tzinfo:
    """America/Sao_Paulo; sem `tzdata` no sistema, usa UTC-3 fixo (sem horário de verão)."""
    try:
        return ZoneInfo("America/Sao_Paulo")
    except (ZoneInfoNotFoundError, ValueError, OSError):  # pragma: no cover - depende do SO
        return timezone(timedelta(hours=-3), "BRT")


FUSO_BRASILIA: Final[tzinfo] = _carregar_fuso_brasilia()


# --- Resultado -------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ResultadoValidacao:
    """Resultado de um validador: aceito quando `erros` está vazio."""

    erros: tuple[ErroCampo, ...] = ()

    @property
    def aceita(self) -> bool:
        return not self.erros

    @property
    def motivo(self) -> str | None:
        """Motivo do primeiro erro (útil quando o validador tem um único campo)."""
        return self.erros[0].motivo if self.erros else None

    def __bool__(self) -> bool:
        return self.aceita


ResultadoFoto = ResultadoValidacao  # nome usado no design (Req 12.10)


def _ok() -> ResultadoValidacao:
    return ResultadoValidacao()


def _erro(campo: str, motivo: str) -> ResultadoValidacao:
    return ResultadoValidacao((ErroCampo(campo, motivo),))


def _juntar(*resultados: ResultadoValidacao) -> ResultadoValidacao:
    return ResultadoValidacao(tuple(e for r in resultados for e in r.erros))


def _texto_1_a_n(campo: str, texto: object, maximo: int, rotulo: str) -> ResultadoValidacao:
    """Aceita `str` com 1 a `maximo` caracteres (comprimento literal, sem `strip`)."""
    if not isinstance(texto, str) or len(texto) == 0:
        return _erro(campo, f"{rotulo} não pode ficar vazio.")
    if len(texto) > maximo:
        return _erro(campo, f"{rotulo} deve ter no máximo {maximo} caracteres.")
    return _ok()


# --- Telefone e CEP (Req 12.6) ---------------------------------------------------------------


def _digitos_se_formato_valido(s: object) -> str | None:
    """Dígitos de `s` se só tem dígitos ASCII, espaços, parênteses e hífen; senão `None`."""
    if not isinstance(s, str) or not all(c in CARACTERES_ACEITOS_CONTATO for c in s):
        return None
    return "".join(c for c in s if c.isdigit())


def validar_telefone(s: str) -> bool:
    """Só dígitos, espaços, parênteses e hífen, com 10 ou 11 dígitos (DDD incluído)."""
    digitos = _digitos_se_formato_valido(s)
    return digitos is not None and len(digitos) in TELEFONE_DIGITOS


def validar_cep(s: str) -> bool:
    """Só dígitos, espaços, parênteses e hífen, com exatamente 8 dígitos."""
    digitos = _digitos_se_formato_valido(s)
    return digitos is not None and len(digitos) == CEP_DIGITOS


# --- Nome e e-mail do Consumidor (handoff do chatbot, Req 18) ----------------------------------

NOME_MIN: Final = 2
NOME_MAX: Final = 100
EMAIL_MAX: Final = 254
_EMAIL: Final = re.compile(r"[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+")


def validar_nome(s: str) -> bool:
    """De 2 a 100 caracteres após `strip`, sem caracteres de controle."""
    if not isinstance(s, str):
        return False
    texto = s.strip()
    if not NOME_MIN <= len(texto) <= NOME_MAX:
        return False
    return not any(unicodedata.category(c) == "Cc" for c in texto)


def validar_email(s: str) -> bool:
    """Até 254 caracteres, no formato simples `local@dominio.tld`, sem espaços."""
    if not isinstance(s, str) or len(s) > EMAIL_MAX:
        return False
    return _EMAIL.fullmatch(s) is not None


# --- Foto (Req 12.7, 12.10) ------------------------------------------------------------------


def validar_foto(mime: str, bytes_: int, ja_anexadas: int) -> ResultadoFoto:
    """Aceita JPEG/PNG de até 5 MB quando há menos de 3 fotos já anexadas.

    Função pura: rejeitar uma foto não altera as já anexadas (Req 12.10). O motivo
    segue a ordem formato, tamanho, limite de fotos.
    """
    if not isinstance(mime, str) or mime.strip().lower() not in MIMES_FOTO:
        return _erro("foto", "Formato não aceito. Envie uma foto JPEG ou PNG.")
    if bytes_ > FOTO_MAX_BYTES:
        return _erro("foto", "A foto tem mais de 5 MB. Envie uma foto menor.")
    if ja_anexadas >= FOTOS_MAX_POR_CHAMADO:
        return _erro("foto", "Limite de 3 fotos por chamado atingido.")
    return _ok()


# --- Mensagem do Consumidor (Req 6.11) -------------------------------------------------------


def validar_mensagem_consumidor(texto: str) -> ResultadoValidacao:
    """De 1 a 1000 caracteres e não composta só de espaços em branco."""
    if not isinstance(texto, str) or not texto.strip():
        return _erro("mensagem", "Digite uma mensagem antes de enviar.")
    if len(texto) > MENSAGEM_CONSUMIDOR_MAX:
        return _erro(
            "mensagem", f"A mensagem deve ter no máximo {MENSAGEM_CONSUMIDOR_MAX} caracteres."
        )
    return _ok()


# --- Dados pessoais solicitados (Req 12.2, 12.3, 12.4) ---------------------------------------


def dados_pessoais_solicitados(
    prioridade: Prioridade, ja_informados: Collection[DadoPessoal] = ()
) -> tuple[DadoPessoal, ...]:
    """Dados exigidos pela prioridade (P1: telefone; P2: telefone e CEP; P3: nenhum) que
    ainda não foram informados. Nunca pede de novo um dado já informado."""
    try:
        exigidos = _DADOS_POR_PRIORIDADE[prioridade]
    except KeyError:
        raise ValueError(f"Prioridade desconhecida: {prioridade!r}") from None
    return tuple(d for d in exigidos if d not in ja_informados)


# --- Avaliação (Req 5.2, 5.5) ----------------------------------------------------------------


def validar_nota(nota: int) -> ResultadoValidacao:
    """Inteiro de 1 a 5 (booleanos não contam como inteiros)."""
    if isinstance(nota, bool) or not isinstance(nota, int) or not NOTA_MIN <= nota <= NOTA_MAX:
        return _erro("nota", f"A nota deve ser um número inteiro de {NOTA_MIN} a {NOTA_MAX}.")
    return _ok()


def validar_comentario(comentario: str | None) -> ResultadoValidacao:
    """Opcional: ausente ou de até 500 caracteres."""
    if comentario is None:
        return _ok()
    if not isinstance(comentario, str) or len(comentario) > COMENTARIO_MAX:
        return _erro("comentario", f"O comentário deve ter no máximo {COMENTARIO_MAX} caracteres.")
    return _ok()


def validar_avaliacao(
    nota: int, comentario: str | None = None, ja_avaliada: bool = False
) -> ResultadoValidacao:
    """Nota de 1 a 5 e comentário opcional de até 500; no máximo 1 avaliação por Jornada."""
    if ja_avaliada:
        return _erro("avaliacao", "Esta jornada já foi avaliada.")
    return _juntar(validar_nota(nota), validar_comentario(comentario))


# --- Mensagem do Atendente (Req 15.3, 15.8) --------------------------------------------------


def validar_mensagem_atendente(texto: str, confirmada: bool = True) -> ResultadoValidacao:
    """Texto final de 1 a 2000 caracteres, enviado só após confirmação explícita."""
    texto_ok = _texto_1_a_n("mensagem", texto, MENSAGEM_ATENDENTE_MAX, "A mensagem")
    if confirmada:
        return texto_ok
    return _juntar(texto_ok, _erro("confirmacao", "Confirme o envio antes de enviar a mensagem."))


# --- Agendamento de ligação (Req 15.6, 15.9) -------------------------------------------------


def _para_brasilia(momento: datetime) -> datetime:
    """Datetime sem fuso é lido como horário de Brasília."""
    if momento.tzinfo is None or momento.utcoffset() is None:
        return momento.replace(tzinfo=FUSO_BRASILIA)
    return momento.astimezone(FUSO_BRASILIA)


def validar_agendamento(
    data: date | None, hora: time | None, agora: datetime
) -> ResultadoValidacao:
    """Data e hora completas, futuras e em até 30 dias a partir de `agora` (fuso de Brasília).

    `data` e `hora` são lidas como horário de Brasília. `agora` sem fuso também. A
    comparação é feita em UTC (instantes absolutos), sem aritmética de relógio local.
    """
    erros: list[ErroCampo] = []
    if data is None:
        erros.append(ErroCampo("data", "Informe a data da ligação."))
    if hora is None:
        erros.append(ErroCampo("hora", "Informe o horário da ligação."))
    if data is None or hora is None:
        return ResultadoValidacao(tuple(erros))

    alvo = datetime.combine(data, hora.replace(tzinfo=None), tzinfo=FUSO_BRASILIA)
    alvo_utc = alvo.astimezone(UTC)
    inicio_utc = _para_brasilia(agora).astimezone(UTC)
    if alvo_utc <= inicio_utc:
        return _erro("data", "A data e o horário devem estar no futuro.")
    if alvo_utc > inicio_utc + timedelta(days=AGENDAMENTO_MAX_DIAS):
        return _erro("data", f"O agendamento deve ser em até {AGENDAMENTO_MAX_DIAS} dias.")
    return _ok()


# --- Encerramento do Chamado (Req 16.1, 16.6) ------------------------------------------------


def validar_encerramento(
    desfecho: str | None, tipo_solucao: str | None, descricao_solucao: str | None
) -> ResultadoValidacao:
    """Exige Desfecho e solução (tipo e descrição de 1 a 500 caracteres)."""
    erros: list[ResultadoValidacao] = []
    if desfecho not in DESFECHOS:
        erros.append(_erro("desfecho", "Informe o desfecho: falso defeito ou defeito real."))
    if tipo_solucao not in TIPOS_SOLUCAO:
        erros.append(
            _erro("tipo_solucao", "Informe o tipo da solução: instrução do manual ou outra.")
        )
    erros.append(_texto_1_a_n("descricao_solucao", descricao_solucao, SOLUCAO_MAX, "A solução"))
    return _juntar(*erros)


# --- Limites do Cache_Respostas (Req 16.2, 16.7) ---------------------------------------------


def validar_pergunta_cache(pergunta: str) -> ResultadoValidacao:
    """Pergunta do cache: 1 a 300 caracteres."""
    return _texto_1_a_n("pergunta", pergunta, PERGUNTA_CACHE_MAX, "A pergunta")


def validar_resposta_cache(resposta: str) -> ResultadoValidacao:
    """Resposta do cache: 1 a 1000 caracteres."""
    return _texto_1_a_n("resposta", resposta, RESPOSTA_CACHE_MAX, "A resposta")


def validar_entrada_cache(pergunta: str, resposta: str) -> ResultadoValidacao:
    """Valida pergunta e resposta juntas, devolvendo todos os campos inválidos."""
    return _juntar(validar_pergunta_cache(pergunta), validar_resposta_cache(resposta))
