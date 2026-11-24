import asyncio
import uuid
from datetime import datetime
from typing import Protocol

from artemis_backend.domain.usuaria import (
    SENHA_MAXIMA,
    ConsentimentoAusente,
    CredenciaisInvalidas,
    TokenInvalido,
    Usuaria,
    normalizar_email,
    validar_senha,
)


class RepositorioContas(Protocol):
    async def criar(self, usuaria: Usuaria) -> None:
        """Grava a usuária; levanta EmailJaCadastrado se o e-mail já existe."""

    async def por_email(self, email: str) -> Usuaria | None: ...

    async def por_id(self, id: uuid.UUID) -> Usuaria | None: ...


class HasherSenha(Protocol):
    def hash(self, senha: str) -> str: ...

    def confere(self, senha: str, senha_hash: str) -> bool: ...


class EmissorToken(Protocol):
    def emitir(self, usuaria_id: uuid.UUID) -> str: ...

    def ler(self, token: str) -> uuid.UUID:
        """Devolve o id da usuária; levanta TokenInvalido se não valer."""


class Relogio(Protocol):
    def agora(self) -> datetime: ...


class ServicoContas:
    def __init__(
        self,
        repositorio: RepositorioContas,
        hasher: HasherSenha,
        emissor: EmissorToken,
        relogio: Relogio,
    ) -> None:
        self._repositorio = repositorio
        self._hasher = hasher
        self._emissor = emissor
        self._relogio = relogio
        # Hash de uma senha qualquer, para o login de e-mail inexistente gastar o mesmo tempo.
        self._hash_ficticio = hasher.hash("senha-ficticia-so-para-gastar-tempo")

    async def cadastrar(self, email: str, senha: str, consentimento: bool) -> uuid.UUID:
        if consentimento is not True:
            raise ConsentimentoAusente("O consentimento é obrigatório")
        email = normalizar_email(email)
        validar_senha(senha)
        usuaria = Usuaria(
            id=uuid.uuid4(),
            email=email,
            senha_hash=await asyncio.to_thread(self._hasher.hash, senha),
            consentiu_em=self._relogio.agora(),
        )
        await self._repositorio.criar(usuaria)
        return usuaria.id

    async def entrar(self, email: str, senha: str) -> str:
        email = normalizar_email(email)
        if len(senha) > SENHA_MAXIMA:
            raise CredenciaisInvalidas
        usuaria = await self._repositorio.por_email(email)
        alvo = usuaria.senha_hash if usuaria else self._hash_ficticio
        confere = await asyncio.to_thread(self._hasher.confere, senha, alvo)
        if usuaria is None or not confere:
            raise CredenciaisInvalidas
        return self._emissor.emitir(usuaria.id)

    async def usuaria_do_token(self, token: str) -> uuid.UUID:
        usuaria_id = self._emissor.ler(token)
        if await self._repositorio.por_id(usuaria_id) is None:
            raise TokenInvalido
        return usuaria_id
