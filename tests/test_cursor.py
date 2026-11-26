import base64
import struct
import uuid
import zlib
from datetime import UTC, datetime, timedelta, timezone

import pytest

from artemis_backend.adapters.cursor import CursorInvalido, escrever_cursor, ler_cursor
from artemis_backend.domain.conversa import PosicaoNaLista
from tests.apoio.conversas import nova_conversa
from tests.apoio.valores import ANA

ROTA = "/v1/conversas"
POSICAO = PosicaoNaLista(
    atualizada_em=datetime(2026, 11, 24, 12, 0, 0, 123457, tzinfo=UTC),
    criada_em=datetime(2026, 11, 24, 11, 59, 59, 999999, tzinfo=UTC),
    id=uuid.UUID("0b0a7f1e-2f60-4d3f-9a1c-6f8f5f1f0e01"),
)
CURSOR = escrever_cursor(POSICAO)


def forjado(atualizada: int, criada: int = 0) -> str:
    """Cursor com a soma de verificação certa, para chegar à conversão das datas."""
    corpo = struct.pack(">qq16s", atualizada, criada, b"\x00" * 16)
    return base64.urlsafe_b64encode(corpo + struct.pack(">I", zlib.crc32(corpo))).decode()


ILEGIVEIS = [
    "",
    " ",
    "null",
    "NaN",
    "a" * 47,
    "a" * 48,
    "a" * 49,
    "a" * 200,
    CURSOR[:-1],
    CURSOR + "A",
    CURSOR + "=",
    CURSOR + "\n",
    " " + CURSOR,
    CURSOR[:10] + "+" + CURSOR[11:],
    CURSOR[:10] + "é" + CURSOR[11:],
    CURSOR[:10] + "\x00" + CURSOR[11:],
    "١" * 48,
    str(uuid.uuid4()),
    base64.urlsafe_b64encode(b'{"atualizada_em": NaN}').decode(),
    forjado(2**63 - 1),
    forjado(-(2**63)),
    forjado(0, 2**62),
]


@pytest.mark.parametrize("fuso", [UTC, timezone(timedelta(hours=-3))])
def test_ida_e_volta_preserva_os_microssegundos(fuso):
    local = PosicaoNaLista(
        POSICAO.atualizada_em.astimezone(fuso), POSICAO.criada_em.astimezone(fuso), POSICAO.id
    )
    assert ler_cursor(escrever_cursor(local)) == POSICAO
    assert escrever_cursor(local) == CURSOR
    assert len(CURSOR) <= 200


@pytest.mark.parametrize("ano", [1, 1969, 9999])
def test_datas_extremas_vao_e_voltam(ano):
    data = datetime(ano, 12, 31, 23, 59, 59, 999999, tzinfo=UTC)
    posicao = PosicaoNaLista(data, data, uuid.UUID(int=2**128 - 1))
    assert ler_cursor(escrever_cursor(posicao)) == posicao


@pytest.mark.parametrize("posicao", range(len(CURSOR)))
def test_qualquer_caractere_trocado_e_recusado(posicao):
    outro = "A" if CURSOR[posicao] != "A" else "B"
    with pytest.raises(CursorInvalido):
        ler_cursor(CURSOR[:posicao] + outro + CURSOR[posicao + 1 :])


@pytest.mark.parametrize("cursor", ILEGIVEIS)
async def test_cursor_ilegivel_da_422_sem_eco(cliente, ana, cursor):
    r = await cliente.get(ROTA, headers=ana, params={"cursor": cursor})
    assert r.status_code == 422
    [erro] = r.json()["detail"]
    assert set(erro) == {"loc", "msg", "type"}
    assert erro["loc"] == ["query", "cursor"]
    assert len(cursor) < 5 or cursor not in r.text


async def test_cursor_longo_da_422_sem_eco(cliente, ana):
    r = await cliente.get(ROTA, headers=ana, params={"cursor": "z" * 201})
    assert r.status_code == 422
    assert "zzz" not in r.text


async def test_cursor_com_bytes_que_nao_sao_utf8(cliente, ana):
    r = await cliente.get(f"{ROTA}?cursor=%ff%fe%ed%a0%80", headers=ana)
    assert r.status_code == 422


@pytest.mark.parametrize("data", [datetime.min, datetime.max])
async def test_cursor_com_data_extrema_nao_da_500(cliente, ana, data):
    em_utc = data.replace(tzinfo=UTC)
    cursor = escrever_cursor(PosicaoNaLista(em_utc, em_utc, uuid.uuid4()))
    r = await cliente.get(ROTA, headers=ana, params={"cursor": cursor})
    assert r.status_code == 200


@pytest.mark.parametrize("limite", ["0", "101", "-1", "", "abc", "NaN", "inf", "1.5", "9" * 5000])
async def test_limite_invalido_da_422_sem_eco(cliente, ana, limite):
    r = await cliente.get(ROTA, headers=ana, params={"limite": limite})
    assert r.status_code == 422
    assert all(set(e) == {"loc", "msg", "type"} for e in r.json()["detail"])
    assert "999" not in r.text and "abc" not in r.text


async def test_cursor_nao_leva_dado_da_usuaria(cliente, ana):
    for _ in range(2):
        await nova_conversa(cliente, ana)
    usuaria = (await cliente.get("/v1/conta", headers=ana)).json()["id"]
    cursor = (await cliente.get(ROTA, headers=ana, params={"limite": 1})).json()["proximo"]
    cru = base64.urlsafe_b64decode(cursor)
    assert uuid.UUID(usuaria).bytes not in cru
    assert ANA.encode() not in cru
