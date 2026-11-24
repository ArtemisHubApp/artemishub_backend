import re
import uuid
from dataclasses import dataclass
from datetime import datetime

SENHA_MINIMA = 8
SENHA_MAXIMA = 128
_EMAIL_MAXIMO = 254
_FORMATO_EMAIL = re.compile(r"[^\s@\x00]+@[^\s@\x00]+\.[^\s@\x00]+")


class EmailInvalido(ValueError):
    pass


class SenhaInvalida(ValueError):
    pass


class ConsentimentoAusente(ValueError):
    pass


class EmailJaCadastrado(Exception):
    pass


class CredenciaisInvalidas(Exception):
    pass


class TokenInvalido(Exception):
    pass


@dataclass(frozen=True)
class Usuaria:
    id: uuid.UUID
    email: str
    senha_hash: str
    consentiu_em: datetime


def normalizar_email(email: str) -> str:
    """Tira espaços das pontas e põe em minúsculas; recusa o que não parece e-mail."""
    normalizado = email.strip().lower()
    if len(normalizado) > _EMAIL_MAXIMO or not _FORMATO_EMAIL.fullmatch(normalizado):
        raise EmailInvalido("E-mail inválido")
    return normalizado


def validar_senha(senha: str) -> None:
    if not SENHA_MINIMA <= len(senha) <= SENHA_MAXIMA:
        raise SenhaInvalida(f"A senha deve ter de {SENHA_MINIMA} a {SENHA_MAXIMA} caracteres")
