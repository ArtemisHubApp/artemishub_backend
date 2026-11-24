from dataclasses import replace

import httpx

from artemis_backend.main import criar_app
from tests.apoio.sessao import em_cookie, logar
from tests.apoio.valores import ANA


async def test_respostas_v1_nao_ficam_em_cache(app, cliente, entrar_como):
    @app.get("/v1/_teste/quebra")
    async def quebra() -> None:
        raise RuntimeError

    ana = await entrar_como(ANA)
    cookie = {"Cookie": em_cookie(ana)["Cookie"]}
    for metodo, url, cabecalhos, status in [
        ("GET", "/v1/consentimento", {}, 200),
        ("GET", "/v1/conta", ana, 200),
        ("POST", "/v1/auth/sair", {}, 204),
        ("GET", "/v1/conversas/", {}, 307),
        ("GET", "/v1/conta", {}, 401),
        ("DELETE", "/v1/conta", cookie, 403),
        ("GET", "/v1/nao-existe", {}, 404),
        ("GET", "/v1/auth/login", {}, 405),
        ("POST", "/v1/auth/login", {}, 422),
        ("GET", "/v1/_teste/quebra", {}, 500),
    ]:
        r = await cliente.request(metodo, url, headers=cabecalhos)
        assert r.status_code == status, (metodo, url)
        assert r.headers.get_list("cache-control") == ["no-store"], (metodo, url)
    assert "cache-control" not in (await cliente.get("/health")).headers


async def test_503_do_banco_nao_fica_em_cache(config, porta_fechada):
    url = f"postgresql+asyncpg://u:p@127.0.0.1:{porta_fechada}/d"
    app = criar_app(replace(config, database_url=url))
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://teste") as c:
        r = await logar(c)
    await app.state.motor.dispose()
    assert r.status_code == 503
    assert r.headers.get_list("cache-control") == ["no-store"]
