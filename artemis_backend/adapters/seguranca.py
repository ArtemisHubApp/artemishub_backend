import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from artemis_backend.domain.usuaria import TokenInvalido

DURACAO_DO_TOKEN = timedelta(minutes=60)


class RelogioDoSistema:
    def agora(self) -> datetime:
        return datetime.now(UTC)


class HasherArgon2:
    def __init__(self) -> None:
        self._argon2 = PasswordHasher()

    def hash(self, senha: str) -> str:
        return self._argon2.hash(senha)

    def confere(self, senha: str, senha_hash: str) -> bool:
        try:
            return self._argon2.verify(senha_hash, senha)
        except (VerificationError, InvalidHashError):
            return False


class EmissorJwt:
    def __init__(self, segredo: str, relogio: RelogioDoSistema) -> None:
        self._segredo = segredo
        self._relogio = relogio

    def emitir(self, usuaria_id: uuid.UUID) -> str:
        agora = self._relogio.agora()
        carga = {"sub": str(usuaria_id), "iat": agora, "exp": agora + DURACAO_DO_TOKEN}
        return jwt.encode(carga, self._segredo, algorithm="HS256")

    def ler(self, token: str) -> uuid.UUID:
        try:
            carga = jwt.decode(
                token,
                self._segredo,
                algorithms=["HS256"],
                options={"require": ["exp", "sub"]},
            )
            return uuid.UUID(carga["sub"])
        except (jwt.PyJWTError, ValueError, TypeError, KeyError) as erro:
            raise TokenInvalido from erro
