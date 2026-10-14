"""Erros da API e o envelope padronizado (design, "API (Lambda) - contrato HTTP").

Formato único de erro, em pt-BR e sem dados pessoais:

    {"erro": {"codigo": "...", "mensagem": "...", "campos": [{"campo": "...", "motivo": "..."}]}}

`campos` só aparece quando há campos inválidos. Códigos HTTP: 400/422 validação, 401 sem
credencial, 403 sem permissão, 404 não encontrado, 409 conflito, 429 limite de taxa e
502/504 dependência indisponível.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final

from dominio import ErroCampo

# --- Códigos estáveis (parte do contrato; o front-end reage a eles) --------------------------
JSON_INVALIDO: Final = "json_invalido"
VALIDACAO: Final = "validacao"
NAO_AUTENTICADO: Final = "nao_autenticado"
SEM_PERMISSAO: Final = "sem_permissao"
NAO_ENCONTRADO: Final = "nao_encontrado"
METODO_NAO_PERMITIDO: Final = "metodo_nao_permitido"
CONFLITO: Final = "conflito"
CORPO_MUITO_GRANDE: Final = "corpo_muito_grande"
LIMITE_TAXA: Final = "limite_taxa"
ERRO_INTERNO: Final = "erro_interno"
DEPENDENCIA_INDISPONIVEL: Final = "dependencia_indisponivel"
TEMPO_ESGOTADO: Final = "tempo_esgotado"


class ErroApi(Exception):
    """Erro de negócio ou de protocolo que vira uma resposta HTTP no envelope padrão.

    A `mensagem` é mostrada ao usuário: escreva em pt-BR, em frase curta, sem dados pessoais.
    """

    def __init__(
        self,
        status: int,
        codigo: str,
        mensagem: str,
        campos: Iterable[ErroCampo] = (),
        cabecalhos: Mapping[str, str] | None = None,
        extras: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(f"{status} {codigo}")  # sem a mensagem: não vai para logs
        self.status = status
        self.codigo = codigo
        self.mensagem = mensagem
        self.campos: tuple[ErroCampo, ...] = tuple(campos)
        self.cabecalhos: dict[str, str] = dict(cabecalhos or {})
        # Campos irmãos de `erro` no corpo (por exemplo o envelope `jornada` do alerta de risco,
        # que o front-end lê também nas respostas de erro). Nunca sobrescrevem `erro`.
        self.extras: dict[str, Any] = dict(extras or {})

    def com_extras(self, **extras: Any) -> ErroApi:
        """Acrescenta campos irmãos de `erro` ao corpo e devolve o próprio erro."""
        self.extras.update(extras)
        return self

    def para_envelope(self) -> dict[str, Any]:
        erro: dict[str, Any] = {"codigo": self.codigo, "mensagem": self.mensagem}
        if self.campos:
            erro["campos"] = [{"campo": c.campo, "motivo": c.motivo} for c in self.campos]
        return {**self.extras, "erro": erro}


class ErroConfiguracao(RuntimeError):
    """Configuração ou segredo ausente/ilegível. Vira 500 genérico (detalhe só no log)."""


def json_invalido(mensagem: str = "O corpo da requisição não é um JSON válido.") -> ErroApi:
    return ErroApi(400, JSON_INVALIDO, mensagem)


def validacao(
    campos: Iterable[ErroCampo], mensagem: str = "Alguns campos estão inválidos."
) -> ErroApi:
    return ErroApi(422, VALIDACAO, mensagem, campos)


def nao_autenticado(mensagem: str = "É preciso entrar para continuar.") -> ErroApi:
    return ErroApi(401, NAO_AUTENTICADO, mensagem)


def sem_permissao(mensagem: str = "Você não tem permissão para esta ação.") -> ErroApi:
    return ErroApi(403, SEM_PERMISSAO, mensagem)


def nao_encontrado(mensagem: str = "Não encontramos o que você procurou.") -> ErroApi:
    return ErroApi(404, NAO_ENCONTRADO, mensagem)


def conflito(mensagem: str) -> ErroApi:
    return ErroApi(409, CONFLITO, mensagem)


def limite_taxa(
    mensagem: str = "Muitas tentativas. Aguarde um instante e tente de novo.",
) -> ErroApi:
    return ErroApi(429, LIMITE_TAXA, mensagem)


def dependencia_indisponivel(
    mensagem: str = "Um serviço de apoio está indisponível. Tente de novo em instantes.",
) -> ErroApi:
    return ErroApi(502, DEPENDENCIA_INDISPONIVEL, mensagem)


def tempo_esgotado(
    mensagem: str = "A operação demorou demais. Tente de novo.",
) -> ErroApi:
    return ErroApi(504, TEMPO_ESGOTADO, mensagem)
