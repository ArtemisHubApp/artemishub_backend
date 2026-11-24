import json
import socket

import httpx
import pytest

from ferramentas.agentes_simulados.pedido import pedido_valido
from tests.apoio.contrato import validador
from tests.apoio.conversas import LEMBRANCA
from tests.apoio.simulador import AUTORIZADA, TOKEN, pedido, simulador_no_ar

ROTA = "/v1/responder"
TROCA = {"pergunta": "p", "resposta": "r"}
VALIDOS = [
    pedido(),
    pedido("á" * 1000),
    pedido(" "),
    pedido(historico=[TROCA] * 3),
    pedido(historico=[{"pergunta": "", "resposta": ""}]),
    pedido(lembranca=LEMBRANCA),
    pedido(lembranca={**LEMBRANCA, "uf": None, "cbo_familia": "1" * 20}),
]
INVALIDOS = [
    *({k: v for k, v in pedido().items() if k != campo} for campo in pedido()),
    pedido(extra=1),
    pedido(""),
    pedido("a" * 1001),
    pedido("a\x00b"),
    pedido("a\ud800b"),
    pedido(1),
    pedido(None),
    pedido(sessao=""),
    pedido(sessao=None),
    pedido(sessao="\x00"),
    pedido(historico=None),
    pedido(historico=[TROCA] * 4),
    pedido(historico=["a"]),
    pedido(historico=[{"pergunta": "p"}]),
    pedido(historico=[{**TROCA, "extra": "x"}]),
    pedido(historico=[{**TROCA, "resposta": 1}]),
    pedido(historico=[{**TROCA, "resposta": "\udfff"}]),
    pedido(lembranca=[]),
    pedido(lembranca={}),
    pedido(lembranca={**LEMBRANCA, "extra": 1}),
    pedido(lembranca={**LEMBRANCA, "salario": 1}),
    pedido(lembranca={**LEMBRANCA, "direitos": None}),
    pedido(lembranca={**LEMBRANCA, "uf": "SPX"}),
    pedido(lembranca={**LEMBRANCA, "cbo_familia": "1" * 21}),
    pedido(lembranca={**LEMBRANCA, "ocupacao": "o" * 201}),
    pedido(lembranca={**LEMBRANCA, "cbo_familia_nome": "\x00"}),
    pedido(lembranca={**LEMBRANCA, "uf": float("nan")}),
    [],
    None,
    "texto",
]


@pytest.fixture
def url():
    with simulador_no_ar() as base:
        yield base


def enviar(url: str, conteudo: bytes, **cabecalhos) -> httpx.Response:
    return httpx.post(
        url + ROTA, content=conteudo, headers={**AUTORIZADA, **cabecalhos}, trust_env=False
    )


def cru(url: str, cabecalhos: bytes) -> bytes:
    """Manda só os cabeçalhos, como estão, e lê a primeira linha da resposta."""
    host, porta = url.removeprefix("http://").split(":")
    with socket.create_connection((host, int(porta)), timeout=10) as conexao:
        conexao.sendall(cabecalhos)
        return conexao.makefile("rb").readline()


@pytest.mark.parametrize("corpo", VALIDOS, ids=range(len(VALIDOS)))
def test_pedido_valido_no_simulador_e_no_contrato(corpo):
    assert validador("pedido").is_valid(corpo)
    assert pedido_valido(corpo)


@pytest.mark.parametrize("corpo", INVALIDOS, ids=range(len(INVALIDOS)))
def test_pedido_invalido_no_simulador_e_no_contrato(corpo):
    assert not validador("pedido").is_valid(corpo)
    assert not pedido_valido(corpo)


@pytest.mark.parametrize(
    "autorizacao", [None, "", "Bearer", "Bearer outro", TOKEN, f"bearer {TOKEN}", "Bearer \xe9"]
)
def test_sem_token_certo_da_401(url, autorizacao):
    cabecalhos = {} if autorizacao is None else {b"Authorization": autorizacao.encode("latin-1")}
    r = httpx.post(url + ROTA, json=pedido(), headers=cabecalhos, trust_env=False)
    assert r.status_code == 401
    assert "SIMULADO" not in r.text


def test_authorization_repetido_da_401(url):
    cabecalhos = [*AUTORIZADA.items(), *AUTORIZADA.items()]
    r = httpx.post(url + ROTA, json=pedido(), headers=cabecalhos, trust_env=False)
    assert r.status_code == 401


@pytest.mark.parametrize(
    "conteudo",
    [b"", b"{", b"\xff\xfe", b"[" * 100_000, b"1" * 10_000, json.dumps(pedido("")).encode()],
    ids=["vazio", "cortado", "nao-utf8", "aninhado", "numero-enorme", "fora-do-contrato"],
)
def test_corpo_invalido_da_422_sem_eco(url, conteudo):
    r = enviar(url, conteudo)
    assert r.status_code == 422
    assert r.json() == {"detail": "Pedido fora do contrato"}


@pytest.mark.parametrize(
    ("tamanho", "status"),
    [
        (b"Content-Length: 524289\r\n", b"413"),
        (b"Content-Length: " + b"9" * 5000 + b"\r\n", b"413"),
        (b"Content-Length: -1\r\n", b"411"),
        (b"Content-Length: 1x\r\n", b"411"),
        (b"Content-Length: \xb2\r\n", b"411"),
        (b"Content-Length: 1\r\nContent-Length: 2\r\n", b"411"),
        (b"Transfer-Encoding: chunked\r\n", b"411"),
        (b"Content-Length: 1\r\nTransfer-Encoding: chunked\r\n", b"411"),
        (b"", b"411"),
    ],
)
def test_tamanho_do_corpo(url, tamanho, status):
    linhas = b"POST /v1/responder HTTP/1.1\r\nHost: 127.0.0.1\r\n"
    autorizacao = f"Authorization: Bearer {TOKEN}\r\n".encode()
    assert status in cru(url, linhas + autorizacao + tamanho + b"\r\n")


@pytest.mark.parametrize("host", ["outro.example.org", "127.0.0.1.example.org", "0.0.0.0", ""])
def test_outro_host_da_403(url, host):
    r = enviar(url, json.dumps(pedido()).encode(), Host=host)
    assert r.status_code == 403


@pytest.mark.parametrize("host", ["127.0.0.1:8001", "localhost:8001", "localhost"])
def test_host_local_passa(url, host):
    assert enviar(url, json.dumps(pedido()).encode(), Host=host).status_code == 200


def test_outra_rota_da_404(url):
    r = httpx.post(url + "/v1/outra", json=pedido(), headers=AUTORIZADA, trust_env=False)
    assert r.status_code == 404


def test_outro_metodo_e_recusado(url):
    assert httpx.get(url + ROTA, headers=AUTORIZADA, trust_env=False).status_code == 501


def test_nao_registra_corpo_nem_token(url, capfd):
    enviar(url, json.dumps(pedido("zqx-pergunta")).encode())
    enviar(url, b"zqx{")
    httpx.post(url + ROTA + "?zqx", headers={"Authorization": "Bearer zqx"}, trust_env=False)
    cru(url, b"zqx linha quebrada\r\n\r\n")
    saida = "".join(capfd.readouterr())
    assert "zqx" not in saida and TOKEN not in saida
