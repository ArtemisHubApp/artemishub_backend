import pytest


@pytest.mark.parametrize(
    ("metodo", "url"),
    [("GET", "/v1/conversas/"), ("POST", "/v1/auth/login/"), ("GET", "/health/")],
)
async def test_barra_no_fim_da_404_sem_redirecionar(cliente, metodo, url):
    """O redirecionamento automático montava o `Location` com o `Host` de quem pediu."""
    r = await cliente.request(metodo, url, headers={"Host": "outro.example.org"})
    assert r.status_code == 404
    assert "location" not in r.headers
