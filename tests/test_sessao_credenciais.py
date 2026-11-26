import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.apoio.sessao import COOKIE, com_origem, em_cookie, token
from tests.apoio.valores import ANA, BIA, ORIGEM_DE_TESTE, TOKEN_INVALIDO


async def test_authorization_tem_prioridade_e_dispensa_origin(cliente, entrar_como):
    ana, bia = await entrar_como(ANA), await entrar_como(BIA)
    cookie_da_bia = com_origem(em_cookie(bia), None)
    ambos = {**ana, **cookie_da_bia}
    assert (await cliente.get("/v1/conta", headers=ambos)).json()["email"] == ANA
    assert (await cliente.post("/v1/conversas", headers=ambos)).status_code == 201
    assert (await cliente.get("/v1/conversas", headers=bia)).json()["itens"] == []
    assert (await cliente.delete("/v1/conta", headers=ambos)).status_code == 204
    assert (await cliente.get("/v1/conta", headers=bia)).json()["email"] == BIA


@pytest.mark.parametrize(
    "autorizacao", ["", "Bearer", "Bearer ", "Bearer lixo", "Basic YTpi", "lixo"]
)
async def test_authorization_invalida_da_401_mesmo_com_cookie_bom(
    cliente, entrar_como, autorizacao
):
    ana = em_cookie(await entrar_como(ANA))
    cabecalhos = {**ana, "Authorization": autorizacao}
    for metodo, url in [("GET", "/v1/conta"), ("DELETE", "/v1/conta")]:
        r = await cliente.request(metodo, url, headers=cabecalhos)
        assert (r.status_code, r.json()) == (401, TOKEN_INVALIDO)
    assert (await cliente.get("/v1/conta", headers=ana)).status_code == 200


async def test_authorization_repetida_e_recusada(cliente, entrar_como):
    bom = (await entrar_como(ANA))["Authorization"]
    for outra in (bom, "Bearer lixo", ""):
        for par in ((bom, outra), (outra, bom)):
            cabecalhos = [("Authorization", valor) for valor in par]
            r = await cliente.get("/v1/conta", headers=cabecalhos)
            assert (r.status_code, r.json()) == (401, TOKEN_INVALIDO)


async def test_cookie_de_sessao_repetido_e_recusado(cliente, entrar_como):
    bom = em_cookie(await entrar_como(ANA))["Cookie"]
    for outro in (bom, f"{COOKIE}=lixo", f"{COOKIE}="):
        for a, b in ((bom, outro), (outro, bom)):
            for cabecalhos in ([("Cookie", f"{a}; {b}")], [("Cookie", a), ("Cookie", b)]):
                r = await cliente.get("/v1/conta", headers=cabecalhos)
                assert (r.status_code, r.json()) == (401, TOKEN_INVALIDO)


async def test_outros_cookies_nao_atrapalham(cliente, entrar_como):
    bom = em_cookie(await entrar_como(ANA))["Cookie"]
    cookie = f"tema=claro; x{COOKIE}=lixo; ; solto;{bom}; {COOKIE.upper()}=lixo"
    r = await cliente.get("/v1/conta", headers={"Cookie": cookie})
    assert r.status_code == 200


async def test_nome_de_cookie_com_espaco_exotico_nao_e_a_sessao(cliente, entrar_como):
    """O navegador trata `\\xa0artemis_sessao` como outro nome; um strip comum os igualaria."""
    bom = em_cookie(await entrar_como(ANA))["Cookie"].encode()
    r = await cliente.get("/v1/conta", headers={b"Cookie": b"\xa0" + bom})
    assert r.status_code == 401


async def test_cookie_vencido_ou_adulterado(cliente, entrar_como):
    id_ = (await cliente.get("/v1/conta", headers=await entrar_como(ANA))).json()["id"]
    invalidos = [
        token(id_, exp=datetime.now(UTC) - timedelta(minutes=1)),
        token(id_, segredo="outro-segredo-falso-com-mais-de-32-bytes!!"),
        token(str(uuid.uuid4())),
        f'"{token(id_)}"',
        "",
        "lixo",
        "a.b.\xe9",
    ]
    for valor in invalidos:
        cabecalhos = {"Cookie": f"{COOKIE}={valor}".encode("latin-1"), "Origin": ORIGEM_DE_TESTE}
        for metodo, url in [("GET", "/v1/conta"), ("DELETE", "/v1/conta")]:
            r = await cliente.request(metodo, url, headers=cabecalhos)
            assert (r.status_code, r.json()) == (401, TOKEN_INVALIDO)
            assert r.headers["WWW-Authenticate"] == "Bearer"
            assert "set-cookie" not in r.headers
