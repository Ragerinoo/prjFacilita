"""Criação das tabelas DynamoDB dos testes (espelha `infra/stacks/dados_stack.py`).

Usado pelos testes de contrato dos repositórios (tarefa 9.3). A lista abaixo repete as
chaves e os índices esparsos da stack; o teste `test_tabelas_espelham_a_stack_cdk` (em
`test_repositorios_contrato.py`) acusa qualquer divergência quando o `aws_cdk` está instalado.
"""

from __future__ import annotations

from typing import Any, Final

PREFIXO: Final = "tres"

# (nome, pk, tipo_pk, sk, ttl, [(indice, pk, sk)])
TABELAS: Final[list[tuple[str, str, str, str | None, str | None, list[tuple[str, str, str]]]]] = [
    (
        "modelos",
        "modelo_id",
        "S",
        None,
        None,
        [("gsi_catalogo", "catalogo_pk", "nome_normalizado")],
    ),
    ("problemas", "problema_id", "N", None, None, []),
    ("instrucoes", "modelo_id", "S", "problema_variante", None, []),
    (
        "jornadas",
        "jornada_id",
        "S",
        None,
        None,
        [
            ("gsi_ativas", "ativa_pk", "ultima_interacao"),
            ("gsi_encerradas", "encerrada_pk", "encerrada_em"),
        ],
    ),
    ("eventos", "jornada_id", "S", "ts_ulid", None, []),
    ("chamados", "numero", "S", None, None, [("gsi_fila", "fila_pk", "fila_sk")]),
    ("mensagens_chamado", "numero", "S", "ts_ulid", None, []),
    ("dados_pessoais", "numero", "S", None, None, []),
    ("acessos_pii", "numero", "S", "ts_ulid", None, []),
    ("ordens_servico", "os_id", "S", None, None, []),
    ("cache_respostas", "chave", "S", None, None, []),
    ("avaliacoes", "jornada_id", "S", None, None, []),
    ("agregados_dia", "dia", "S", "metrica", None, []),
    ("usuarios_cs", "usuario", "S", None, None, []),
    ("sessoes_cs", "token_hash", "S", None, "ttl", []),
    ("config", "chave", "S", None, None, []),
]


def criar_tabelas(recurso: Any, prefixo: str = PREFIXO) -> None:
    """Cria todas as tabelas (e índices) `<prefixo>-<nome>` no recurso dado."""
    for nome, pk, tipo_pk, sk, _ttl, indices in TABELAS:
        tipos = {pk: tipo_pk}
        if sk:
            tipos[sk] = "S"
        for _, ipk, isk in indices:
            tipos[ipk] = "S"
            tipos[isk] = "S"
        args: dict[str, Any] = {
            "TableName": f"{prefixo}-{nome}",
            "KeySchema": [{"AttributeName": pk, "KeyType": "HASH"}]
            + ([{"AttributeName": sk, "KeyType": "RANGE"}] if sk else []),
            "AttributeDefinitions": [
                {"AttributeName": a, "AttributeType": t} for a, t in sorted(tipos.items())
            ],
            "BillingMode": "PAY_PER_REQUEST",
        }
        if indices:
            args["GlobalSecondaryIndexes"] = [
                {
                    "IndexName": i,
                    "KeySchema": [
                        {"AttributeName": ipk, "KeyType": "HASH"},
                        {"AttributeName": isk, "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
                for i, ipk, isk in indices
            ]
        recurso.create_table(**args)
