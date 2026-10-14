"""Cache_Respostas puro (Req 7.1, 7.2, 7.6, 7.7, 16.3, 16.8).

Funções sem I/O: normalização da pergunta, chave de cache e decisão de inserção.
A leitura e a escrita no armazenamento ficam no serviço, que usa estas regras.
"""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import replace

from dominio.tipos import EntradaCache, ResultadoInsercao, StatusInsercao


def _normalizar_uma_vez(texto: str) -> str:
    # NFKD separa letras e acentos; descartamos as marcas combinantes (Mn).
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acentos = "".join(c for c in decomposto if unicodedata.category(c) != "Mn")
    # casefold unifica a caixa (inclusive casos como "ß"/"SS").
    minusculas = sem_acentos.casefold()
    # Remove pontuação (P*) e símbolos (S*), como "$", "+" e "|".
    sem_pontuacao = "".join(
        c for c in minusculas if unicodedata.category(c)[0] not in ("P", "S")
    )
    # split() sem argumento colapsa qualquer sequência de espaços e apara as pontas.
    return " ".join(sem_pontuacao.split())


def normalizar_pergunta(pergunta: str) -> str:
    """Normaliza a pergunta: minúsculas, sem acentos, sem pontuação, espaços únicos
    e sem espaços nas extremidades (Req 7.1).

    Idempotente: aplica a transformação até estabilizar, o que cobre caracteres
    Unicode cuja decomposição ou mudança de caixa gera novos caracteres.
    """
    atual = pergunta
    while True:
        proximo = _normalizar_uma_vez(atual)
        if proximo == atual:
            return atual
        atual = proximo


def chave_cache(modelo_id: str, pergunta: str) -> str:
    """Chave do cache: `modelo_id#sha256(pergunta normalizada)` (Req 7.1, 7.2)."""
    digest = hashlib.sha256(normalizar_pergunta(pergunta).encode("utf-8")).hexdigest()
    return f"{modelo_id}#{digest}"


def aceitar_insercao_cache(
    entrada: EntradaCache,
    aprovador_id: str | None,
    existente: EntradaCache | None,
) -> ResultadoInsercao:
    """Decide se `entrada` entra no Cache_Respostas.

    - Sem aprovador (ausente ou em branco): rejeita e mantém `existente` (Req 7.6, 7.7).
    - Com aprovador e entrada existente para a mesma chave: duplicada; mantém a
      existente sem alterações (Req 16.8).
    - Com aprovador e sem existente: aceita, gravando o aprovador na entrada (Req 16.3).
    """
    if aprovador_id is None or not aprovador_id.strip():
        return ResultadoInsercao(StatusInsercao.REJEITADA_SEM_APROVADOR, existente)
    if existente is not None:
        return ResultadoInsercao(StatusInsercao.DUPLICADA, existente)
    return ResultadoInsercao(StatusInsercao.ACEITA, replace(entrada, aprovador_id=aprovador_id))
