import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime

SENHA_MINIMA = 8
SENHA_MAXIMA = 128
NOME_MAXIMO = 80
_EMAIL_MAXIMO = 254
_FORMATO_EMAIL = re.compile(r"[^\s@\x00]+@[^\s@\x00]+\.[^\s@\x00]+")

# A equipe revisa o texto no ADR de LGPD.
CONSENTIMENTO = (
    "Guardamos suas conversas para você consultar depois. O texto das perguntas é enviado "
    "ao Google Gemini, para gerar a resposta, e ao Langfuse, para acompanhar a qualidade. "
    "No plano gratuito do Gemini, o Google pode usar esse texto para melhorar os produtos "
    "dele. Você pode apagar conversas e a conta quando quiser; os registros no Langfuse "
    "permanecem."
)


class EmailInvalido(ValueError):
    pass


class NomeInvalido(ValueError):
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
    nome: str
    email: str
    senha_hash: str
    consentiu_em: datetime


def normalizar_email(email: str) -> str:
    """Tira espaços das pontas e põe em minúsculas; recusa o que não parece e-mail."""
    normalizado = email.strip().lower()
    if len(normalizado) > _EMAIL_MAXIMO or not _FORMATO_EMAIL.fullmatch(normalizado):
        raise EmailInvalido("E-mail inválido")
    try:
        normalizado.encode("utf-8")
    except UnicodeEncodeError:
        # Surrogate solto: não vira UTF-8, então o banco nem o log conseguiriam tratá-lo.
        raise EmailInvalido("E-mail inválido") from None
    return normalizado


def normalizar_nome(nome: str) -> str:
    """Tira espaços das pontas, reduz os repetidos a um; recusa vazio, longo ou com controle."""
    # Categorias Cc (controle, inclusive NUL) e Cs (surrogate, que não vira UTF-8).
    if any(unicodedata.category(letra) in ("Cc", "Cs") for letra in nome):
        raise NomeInvalido("Nome inválido")
    normalizado = " ".join(nome.split())
    if not 1 <= len(normalizado) <= NOME_MAXIMO:
        raise NomeInvalido("Nome inválido")
    return normalizado


def validar_senha(senha: str) -> None:
    if not SENHA_MINIMA <= len(senha) <= SENHA_MAXIMA:
        raise SenhaInvalida(f"A senha deve ter de {SENHA_MINIMA} a {SENHA_MAXIMA} caracteres")
