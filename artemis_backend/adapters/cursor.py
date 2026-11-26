"""Cursor da lista de conversas: a última posição lida, em base64url e sem dado da usuária."""

import base64
import re
import struct
import uuid
import zlib
from datetime import UTC, datetime, timedelta

from artemis_backend.domain.conversa import PosicaoNaLista

CURSOR_MAXIMO = 200
# Microssegundos de atualizada_em e de criada_em desde 1970, e o id.
_POSICAO = struct.Struct(">qq16s")
# Só denuncia cursor estragado; quem protege os dados é o filtro por usuaria_id na consulta.
_SOMA = struct.Struct(">I")
_INICIO = datetime(1970, 1, 1, tzinfo=UTC)
_MICROSSEGUNDO = timedelta(microseconds=1)
_FORMATO = re.compile(r"[A-Za-z0-9_-]{48}")


class CursorInvalido(ValueError):
    pass


def escrever_cursor(posicao: PosicaoNaLista) -> str:
    corpo = _POSICAO.pack(
        (posicao.atualizada_em - _INICIO) // _MICROSSEGUNDO,
        (posicao.criada_em - _INICIO) // _MICROSSEGUNDO,
        posicao.id.bytes,
    )
    return base64.urlsafe_b64encode(corpo + _SOMA.pack(zlib.crc32(corpo))).decode("ascii")


def ler_cursor(cursor: str) -> PosicaoNaLista:
    if not _FORMATO.fullmatch(cursor):
        raise CursorInvalido
    dados = base64.urlsafe_b64decode(cursor)
    corpo, soma = dados[: _POSICAO.size], dados[_POSICAO.size :]
    if _SOMA.pack(zlib.crc32(corpo)) != soma:
        raise CursorInvalido
    atualizada_em, criada_em, id_ = _POSICAO.unpack(corpo)
    try:
        return PosicaoNaLista(
            _INICIO + atualizada_em * _MICROSSEGUNDO,
            _INICIO + criada_em * _MICROSSEGUNDO,
            uuid.UUID(bytes=id_),
        )
    except OverflowError:
        raise CursorInvalido from None
