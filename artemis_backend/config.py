import os
from dataclasses import dataclass, field

# O segredo vem primeiro: sem ele a API não pode subir nem em teste de configuração.
_VARIAVEIS = (
    "ARTEMIS_JWT_SEGREDO",
    "DATABASE_URL",
    "ARTEMIS_AGENTS_URL",
    "ARTEMIS_AGENTS_TOKEN",
)

_SEGREDO_MINIMO_BYTES = 32


@dataclass(frozen=True)
class Config:
    # repr=False: a URL do banco leva a senha, e o resto são segredos.
    database_url: str = field(repr=False)
    jwt_segredo: str = field(repr=False)
    agents_url: str
    agents_token: str = field(repr=False)

    @classmethod
    def de_ambiente(cls) -> "Config":
        valores = {nome: os.environ.get(nome, "").strip() for nome in _VARIAVEIS}
        for nome, valor in valores.items():
            if not valor:
                raise ValueError(f"Variável de ambiente obrigatória ausente: {nome}")
        if len(valores["ARTEMIS_JWT_SEGREDO"].encode()) < _SEGREDO_MINIMO_BYTES:
            raise ValueError(
                f"ARTEMIS_JWT_SEGREDO precisa ter pelo menos {_SEGREDO_MINIMO_BYTES} bytes"
            )
        return cls(
            database_url=valores["DATABASE_URL"],
            jwt_segredo=valores["ARTEMIS_JWT_SEGREDO"],
            agents_url=valores["ARTEMIS_AGENTS_URL"],
            agents_token=valores["ARTEMIS_AGENTS_TOKEN"],
        )
