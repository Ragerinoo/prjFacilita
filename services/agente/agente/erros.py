"""Erros do agente e o mapeamento para a resposta de erro do contrato."""

from __future__ import annotations

from typing import Any, Final

REQUISICAO_INVALIDA: Final = "requisicao_invalida"
MODO_DESCONHECIDO: Final = "modo_desconhecido"
MASCARAMENTO: Final = "mascaramento"
RECUPERACAO_INDISPONIVEL: Final = "recuperacao_indisponivel"
MODELO_INDISPONIVEL: Final = "modelo_indisponivel"
SAIDA_INVALIDA: Final = "saida_invalida"
TEMPO_ESGOTADO: Final = "tempo_esgotado"
INTERNO: Final = "interno"

CODIGOS: Final = (
    REQUISICAO_INVALIDA,
    MODO_DESCONHECIDO,
    MASCARAMENTO,
    RECUPERACAO_INDISPONIVEL,
    MODELO_INDISPONIVEL,
    SAIDA_INVALIDA,
    TEMPO_ESGOTADO,
    INTERNO,
)


class ErroAgente(Exception):
    """Falha prevista do agente; vira `{"erro": {"codigo", "mensagem", "detalhes"?}}`.

    A mensagem é fixa e não contém texto do Consumidor nem detalhes de infraestrutura.
    `detalhes` só é usado por `requisicao_invalida` (lista de `{campo, motivo}`).
    """

    def __init__(self, codigo: str, mensagem: str, detalhes: list[dict[str, str]] | None = None):
        super().__init__(f"{codigo}: {mensagem}")
        self.codigo = codigo
        self.mensagem = mensagem
        self.detalhes = detalhes

    def para_resposta(self) -> dict[str, Any]:
        erro: dict[str, Any] = {"codigo": self.codigo, "mensagem": self.mensagem}
        if self.detalhes:
            erro["detalhes"] = self.detalhes
        return {"erro": erro}
