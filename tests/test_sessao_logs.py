import logging

from tests.apoio.sessao import COOKIE, com_origem, em_cookie
from tests.apoio.valores import ANA


async def test_logs_sem_cookie_nem_email(cliente, entrar_como, caplog):
    caplog.set_level(logging.DEBUG)
    ana = em_cookie(await entrar_como(ANA))
    await cliente.get("/v1/conta", headers=ana)
    await cliente.delete("/v1/conta", headers=com_origem(ana, None))
    await cliente.delete("/v1/conta", headers=ana)
    for segredo in (ANA, ana["Cookie"], ana["Cookie"].removeprefix(f"{COOKIE}=")):
        assert segredo not in caplog.text
