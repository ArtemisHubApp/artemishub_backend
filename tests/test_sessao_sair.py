import pytest

from tests.apoio.sessao import (
    APAGADO,
    COOKIE,
    ORIGEM_NEGADA,
    atributos_do_cookie,
    com_origem,
    em_cookie,
)
from tests.apoio.valores import ANA, ORIGEM_DE_TESTE


async def test_sair_e_excluir_conta_apagam_o_cookie(cliente, entrar_como):
    ana = em_cookie(await entrar_como(ANA))
    for metodo, url in [("POST", "/v1/auth/sair"), ("DELETE", "/v1/conta")]:
        r = await cliente.request(metodo, url, headers=ana)
        assert (r.status_code, r.content) == (204, b"")
        assert atributos_do_cookie(r) == APAGADO


async def test_sair_com_cookie_invalido_ou_repetido_apaga(cliente):
    for cookie in (f"{COOKIE}=lixo", f"{COOKIE}=a; {COOKIE}=b", f"{COOKIE}="):
        r = await cliente.post(
            "/v1/auth/sair", headers={"Cookie": cookie, "Origin": ORIGEM_DE_TESTE}
        )
        assert r.status_code == 204
        assert atributos_do_cookie(r) == APAGADO


async def test_sair_com_cookie_exige_origin_mesmo_com_authorization(cliente, entrar_como):
    """Sair age sobre o próprio cookie, então o cabeçalho não dispensa a origem."""
    ana = await entrar_como(ANA)
    cabecalhos = {**ana, **com_origem(em_cookie(ana), None)}
    r = await cliente.post("/v1/auth/sair", headers=cabecalhos)
    assert (r.status_code, r.json()) == (403, ORIGEM_NEGADA)
    assert "set-cookie" not in r.headers


@pytest.mark.parametrize("cabecalhos", [{}, {"Origin": "https://outro.example.org"}])
async def test_sair_sem_sessao_nao_mexe_no_cookie(cliente, cabecalhos):
    """Um formulário de outro site chega sem o cookie (SameSite); a resposta não pode apagá-lo."""
    r = await cliente.post("/v1/auth/sair", headers=cabecalhos)
    assert r.status_code == 204
    assert "set-cookie" not in r.headers
