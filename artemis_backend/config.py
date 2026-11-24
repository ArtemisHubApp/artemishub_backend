import os
import re
from dataclasses import dataclass, field

# O segredo vem primeiro: sem ele a API não pode subir nem em teste de configuração.
_VARIAVEIS = (
    "ARTEMIS_JWT_SEGREDO",
    "DATABASE_URL",
    "ARTEMIS_AGENTS_URL",
    "ARTEMIS_AGENTS_TOKEN",
    "ARTEMIS_ORIGEM",
)

_SEGREDO_MINIMO_BYTES = 32

_FORMATO_ORIGEM = re.compile(
    r"(?P<esquema>https?)://(?P<host>[a-z0-9-]+(\.[a-z0-9-]+)*)(:(?P<porta>[1-9][0-9]{0,4}))?"
)
_HOSTS_LOCAIS = {"localhost", "127.0.0.1"}
_PORTA_PADRAO = {"http": 80, "https": 443}
_PORTA_MAXIMA = 65535
_BOOLEANOS = {"true": True, "false": False}


def _validar_origem(origem: str) -> None:
    """A origem é comparada por igualdade, então precisa estar como o navegador a escreve."""
    partes = _FORMATO_ORIGEM.fullmatch(origem)
    if partes is None:
        raise ValueError(
            "ARTEMIS_ORIGEM precisa ser esquema://host[:porta], em minúsculas, "
            "sem caminho nem barra no fim"
        )
    if partes["esquema"] == "http" and partes["host"] not in _HOSTS_LOCAIS:
        raise ValueError("ARTEMIS_ORIGEM precisa ser https fora de localhost e 127.0.0.1")
    porta = int(partes["porta"] or 0)
    if porta > _PORTA_MAXIMA or porta == _PORTA_PADRAO[partes["esquema"]]:
        raise ValueError("ARTEMIS_ORIGEM tem porta inválida ou igual à padrão (que se omite)")


@dataclass(frozen=True)
class Config:
    # repr=False: a URL do banco leva a senha, e o resto são segredos.
    database_url: str = field(repr=False)
    jwt_segredo: str = field(repr=False)
    agents_url: str
    agents_token: str = field(repr=False)
    origem: str
    cookie_seguro: bool = True

    def __post_init__(self) -> None:
        _validar_origem(self.origem)
        # http só passa na validação da origem quando o host é local.
        if not self.cookie_seguro and not self.origem.startswith("http://"):
            raise ValueError(
                "ARTEMIS_COOKIE_SEGURO só pode ser false com ARTEMIS_ORIGEM em http local"
            )

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
        cookie_seguro = os.environ.get("ARTEMIS_COOKIE_SEGURO", "true")
        if cookie_seguro not in _BOOLEANOS:
            raise ValueError("ARTEMIS_COOKIE_SEGURO precisa ser true ou false")
        return cls(
            database_url=valores["DATABASE_URL"],
            jwt_segredo=valores["ARTEMIS_JWT_SEGREDO"],
            agents_url=valores["ARTEMIS_AGENTS_URL"],
            agents_token=valores["ARTEMIS_AGENTS_TOKEN"],
            origem=valores["ARTEMIS_ORIGEM"],
            cookie_seguro=_BOOLEANOS[cookie_seguro],
        )
