import pytest

CORPOS = [b"\xff\xfe{}", b"9" * 5000, b"[" * 100_000, b'{"zqx": "a\xe9"}']


@pytest.fixture
def rotas(ana, conversa) -> list[tuple[str, dict]]:
    return [
        ("/v1/auth/cadastro", {}),
        ("/v1/auth/login", {}),
        (f"/v1/conversas/{conversa}/mensagens", ana),
    ]


@pytest.mark.parametrize("corpo", CORPOS, ids=["nao-utf8", "numero-enorme", "aninhado", "latin1"])
async def test_corpo_ilegivel_da_422_documentado(cliente, rotas, corpo):
    for rota, cabecalhos in rotas:
        r = await cliente.post(
            rota, content=corpo, headers={**cabecalhos, "Content-Type": "application/json"}
        )
        assert r.status_code == 422, rota
        [erro] = r.json()["detail"]
        assert set(erro) == {"loc", "msg", "type"} and erro["loc"][0] == "body"
        assert erro["type"] == "json_invalid" and "zqx" not in r.text


@pytest.mark.parametrize("corpo", CORPOS[1:], ids=["numero-enorme", "aninhado", "latin1"])
async def test_corpo_que_dava_400_diz_o_motivo_em_portugues(cliente, corpo):
    r = await cliente.post(
        "/v1/auth/login", content=corpo, headers={"Content-Type": "application/json"}
    )
    assert r.json() == {
        "detail": [{"loc": ["body"], "msg": "Corpo não é um JSON válido", "type": "json_invalid"}]
    }
