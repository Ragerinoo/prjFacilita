"""Métricas simples de Chamados para o Gestor (função pura, sem I/O).

Só conta e rotula. Nunca copia telefone, CEP, texto de mensagens nem resumo do Pacote.
O conjunto de chaves de primeiro nível é fechado: `totais`, `por_problema`, `por_modelo`,
`por_prioridade` e `por_desfecho`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable, Mapping
from typing import Any, Final

from repositorios.modelos import Chamado, Jornada

ROTULO_NAO_INFORMADO: Final = "nao_informado"
PRIORIDADES: Final = ("P1", "P2", "P3")
DESFECHOS: Final = ("falso_defeito", "defeito_real")


def _linha(chave: str, rotulo: str, quantidade: int) -> dict[str, Any]:
    return {"chave": chave, "rotulo": rotulo, "quantidade": quantidade}


def _ordenar(linhas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Quantidade decrescente, depois rótulo crescente."""
    return sorted(linhas, key=lambda x: (-x["quantidade"], x["rotulo"]))


def calcular_metricas(
    chamados: Iterable[Chamado],
    obter_jornada: Callable[[str], Jornada | None],
    titulos_problemas: Mapping[int, str],
) -> dict[str, Any]:
    """Contagens de Chamados por status, problema, modelo, prioridade e desfecho."""
    abertos = 0
    encerrados = 0
    problemas: Counter[int | None] = Counter()
    modelos: Counter[str | None] = Counter()
    prioridades: Counter[str] = Counter()
    desfechos: Counter[str] = Counter()

    for chamado in chamados:
        if chamado.status == "encerrado":
            encerrados += 1
            desfechos[
                chamado.encerramento.desfecho if chamado.encerramento else ROTULO_NAO_INFORMADO
            ] += 1
        else:
            abertos += 1
        prioridades[chamado.prioridade] += 1
        jornada = obter_jornada(chamado.jornada_id)
        problemas[jornada.problema_id if jornada else None] += 1
        modelos[jornada.modelo_id if jornada else None] += 1

    por_problema = []
    for problema_id, qtd in problemas.items():
        if problema_id is None:
            por_problema.append(_linha(ROTULO_NAO_INFORMADO, ROTULO_NAO_INFORMADO, qtd))
        else:
            titulo = titulos_problemas.get(problema_id) or f"Problema {problema_id}"
            por_problema.append(_linha(str(problema_id), titulo, qtd))

    por_modelo = [
        _linha(
            ROTULO_NAO_INFORMADO if m is None else m,
            ROTULO_NAO_INFORMADO if m is None else m,
            qtd,
        )
        for m, qtd in modelos.items()
    ]

    por_prioridade = [_linha(p, p, prioridades[p]) for p in PRIORIDADES]
    por_desfecho = [_linha(d, d, desfechos[d]) for d in DESFECHOS]
    if desfechos[ROTULO_NAO_INFORMADO] > 0:
        por_desfecho.append(
            _linha(ROTULO_NAO_INFORMADO, ROTULO_NAO_INFORMADO, desfechos[ROTULO_NAO_INFORMADO])
        )

    return {
        "totais": {"abertos": abertos, "encerrados": encerrados},
        "por_problema": _ordenar(por_problema),
        "por_modelo": _ordenar(por_modelo),
        "por_prioridade": por_prioridade,
        "por_desfecho": por_desfecho,
    }
