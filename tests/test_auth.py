import asyncio
import logging
import socket
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
import jwt
import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from artemis_backend.adapters.rotas_auth import usuaria_atual
from artemis_backend.main import criar_app
from tests.conftest import SEGREDO_DE_TESTE, SENHA_DE_TESTE, config_alembic

EMAIL = "ana@example.com"
MENSAGEM_503 = {"detail": "Serviço indisponível, tente de novo"}


def corpo(email: str = EMAIL, senha: str = SENHA_DE_TESTE, **extra) -> dict:
    return {"email": email, "senha": senha, "consentimento": True, **extra}


async def cadastrar(cliente, **kw):
    return await cliente.post("/v1/auth/cadastro", json=corpo(**kw))


async def logar(cliente, email: str = EMAIL, senha: str = SENHA_DE_TESTE):
    return await cliente.post("/v1/auth/login", json={"email": email, "senha": senha})


async def ler_banco(app, sql: str) -> list:
    motor = create_async_engine(app.state.config.database_url)
    async with motor.connect() as conexao:
        linhas = (await conexao.execute(text(sql))).all()
    await motor.dispose()
    return linhas


async def test_cadastro_e_login(cliente):
    r = await cadastrar(cliente)
    assert r.status_code == 201
    uuid.UUID(r.json()["id"])
    r = await logar(cliente)
    assert r.status_code == 200
    assert set(r.json()) == {"token", "tipo"}
    assert r.json()["tipo"] == "bearer"


async def test_cadastro_grava_consentimento_e_email_normalizado(cliente, app):
    await cadastrar(cliente, email="  Ana@Example.COM ")
    linhas = await ler_banco(app, "SELECT email, consentiu_em FROM usuarias")
    assert [(e, c is not None) for e, c in linhas] == [(EMAIL, True)]


@pytest.mark.parametrize("consentimento", [False, "true", 1, None])
async def test_cadastro_sem_consentimento(cliente, consentimento):
    r = await cadastrar(cliente, consentimento=consentimento)
    assert r.status_code == 422


async def test_cadastro_com_consentimento_ausente(cliente):
    r = await cliente.post("/v1/auth/cadastro", json={"email": EMAIL, "senha": SENHA_DE_TESTE})
    assert r.status_code == 422


async def test_email_repetido_com_maiusculas_e_espacos(cliente):
    assert (await cadastrar(cliente)).status_code == 201
    assert (await cadastrar(cliente, email="  ANA@example.com  ")).status_code == 409


async def test_login_normaliza_o_email(cliente):
    await cadastrar(cliente)
    assert (await logar(cliente, email=" ANA@Example.com ")).status_code == 200


@pytest.mark.parametrize("email", ["", "sem-arroba", "a@b", "a b@example.com", "a@@example.com"])
async def test_email_invalido(cliente, email):
    assert (await cadastrar(cliente, email=email)).status_code == 422
    assert (await logar(cliente, email=email)).status_code == 422


async def test_email_com_byte_nulo_nao_da_500(cliente):
    assert (await cadastrar(cliente, email="a\x00b@example.com")).status_code == 422
    assert (await logar(cliente, email="a\x00b@example.com")).status_code == 422


async def test_cadastros_simultaneos_com_o_mesmo_email(cliente):
    respostas = await asyncio.gather(cadastrar(cliente), cadastrar(cliente))
    assert sorted(r.status_code for r in respostas) == [201, 409]


async def test_senha_curta_e_longa(cliente):
    assert (await cadastrar(cliente, senha="a" * 7)).status_code == 422
    assert (await cadastrar(cliente, senha="a" * 129)).status_code == 422
    assert (await cadastrar(cliente, senha="a" * 8)).status_code == 201
    assert (await cadastrar(cliente, email="b@example.com", senha="a" * 128)).status_code == 201


async def test_senha_enorme_no_login_e_recusada(cliente):
    assert (await logar(cliente, senha="a" * 129)).status_code == 422


async def test_422_nao_repete_senha_nem_email(cliente):
    senha = "curta"
    r = await cliente.post(
        "/v1/auth/cadastro",
        json={"email": "invalido-segredo@", "senha": senha, "consentimento": "talvez"},
    )
    assert r.status_code == 422
    assert "curta" not in r.text and "invalido-segredo" not in r.text and "talvez" not in r.text


async def test_login_errado_e_email_inexistente_tem_a_mesma_resposta(cliente):
    await cadastrar(cliente)
    errada = await logar(cliente, senha="outra-senha-errada")
    inexistente = await logar(cliente, email="ninguem@example.com")
    assert errada.status_code == inexistente.status_code == 401
    assert errada.json() == inexistente.json()


async def test_senha_guardada_com_argon2(cliente, app):
    await cadastrar(cliente)
    [(senha_hash,)] = await ler_banco(app, "SELECT senha_hash FROM usuarias")
    assert senha_hash.startswith("$argon2")
    assert SENHA_DE_TESTE not in senha_hash


def token(sub: str | None = None, *, exp: datetime | None = None, segredo=SEGREDO_DE_TESTE, **kw):
    agora = datetime.now(UTC)
    carga = {"sub": sub, "exp": exp or agora + timedelta(minutes=5), "iat": agora}
    carga = {k: v for k, v in carga.items() if v is not None}
    return jwt.encode(carga, segredo, algorithm="HS256", **kw)


@pytest.fixture
def com_rota_protegida(app):
    """Rota só dos testes, para exercitar `usuaria_atual` antes da Task 3."""
    from fastapi import Depends

    @app.get("/_teste/eu")
    async def eu(usuaria: Annotated[uuid.UUID, Depends(usuaria_atual)]) -> dict[str, str]:
        return {"id": str(usuaria)}

    return app


async def ver(cliente, tk: str | None):
    cabecalho = {"Authorization": f"Bearer {tk}"} if tk else {}
    return await cliente.get("/_teste/eu", headers=cabecalho)


async def test_usuaria_atual_aceita_token_valido(cliente, com_rota_protegida):
    id_ = (await cadastrar(cliente)).json()["id"]
    tk = (await logar(cliente)).json()["token"]
    r = await ver(cliente, tk)
    assert (r.status_code, r.json()) == (200, {"id": id_})


async def test_token_do_login_dura_60_minutos(cliente):
    await cadastrar(cliente)
    carga = jwt.decode((await logar(cliente)).json()["token"], SEGREDO_DE_TESTE, ["HS256"])
    assert carga["exp"] - carga["iat"] == 3600


async def test_token_vencido_adulterado_e_alg_none(cliente, com_rota_protegida):
    id_ = (await cadastrar(cliente)).json()["id"]
    vencido = token(id_, exp=datetime.now(UTC) - timedelta(minutes=1))
    adulterado = token(id_, segredo="outro-segredo-falso-com-mais-de-32-bytes!!")
    sem_alg = jwt.encode({"sub": id_, "exp": datetime.now(UTC) + timedelta(hours=1)}, None, "none")
    for tk in (vencido, adulterado, sem_alg):
        assert (await ver(cliente, tk)).status_code == 401


async def test_token_ausente_malformado_ou_de_usuaria_inexistente(cliente, com_rota_protegida):
    await cadastrar(cliente)
    assert (await ver(cliente, None)).status_code == 401
    assert (await ver(cliente, "lixo")).status_code == 401
    assert (await ver(cliente, token("nao-e-uuid"))).status_code == 401
    assert (await ver(cliente, token(str(uuid.uuid4())))).status_code == 401
    sem_exp = jwt.encode({"sub": str(uuid.uuid4())}, SEGREDO_DE_TESTE, "HS256")
    assert (await ver(cliente, sem_exp)).status_code == 401
    sem_sub = jwt.encode({"exp": datetime.now(UTC) + timedelta(hours=1)}, SEGREDO_DE_TESTE, "HS256")
    assert (await ver(cliente, sem_sub)).status_code == 401


async def test_entrar_como_devolve_cabecalho_que_funciona(cliente, entrar_como, com_rota_protegida):
    r = await cliente.get("/_teste/eu", headers=await entrar_como("bia@example.com"))
    assert r.status_code == 200


async def test_logs_sem_email_senha_nem_token(cliente, caplog):
    caplog.set_level(logging.DEBUG)
    await cadastrar(cliente)
    tk = (await logar(cliente)).json()["token"]
    await logar(cliente, senha="errada-errada")
    await cadastrar(cliente)
    await cadastrar(cliente, email="x", senha="curta")
    for segredo in (EMAIL, SENHA_DE_TESTE, tk, "errada-errada"):
        assert segredo not in caplog.text


def test_migracoes_sem_database_url_dao_mensagem_clara(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="DATABASE_URL"):
        command.upgrade(config_alembic(""), "head")


async def post_bruto(cliente, rota: str, corpo: bytes):
    return await cliente.post(rota, content=corpo, headers={"Content-Type": "application/json"})


@pytest.mark.parametrize("rota", ["/v1/auth/cadastro", "/v1/auth/login"])
@pytest.mark.parametrize(
    "email, senha",
    [
        ("a\\ud800b@example.com", "senhaboa123"),
        ("ana@example.com", "senha\\udfffboa123"),
    ],
)
async def test_surrogate_solto_e_recusado_sem_500_nem_log(cliente, caplog, rota, email, senha):
    caplog.set_level(logging.DEBUG)
    corpo = f'{{"email":"{email}","senha":"{senha}","consentimento":true}}'.encode()
    r = await post_bruto(cliente, rota, corpo)
    assert r.status_code in (401, 422)
    assert "ud800" not in r.text and "senhaboa" not in r.text
    assert "senhaboa" not in caplog.text and "Traceback" not in caplog.text


async def test_banco_inalcancavel_da_503_json_e_log_so_com_o_tipo(config, caplog):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    app = criar_app(replace(config, database_url=f"postgresql+asyncpg://u:p@127.0.0.1:{porta}/d"))
    transporte = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://teste") as c:
        caplog.set_level(logging.DEBUG)
        for rota in ("/v1/auth/login", "/v1/auth/cadastro"):
            r = await c.post(rota, json=corpo("qa1x@example.com"))
            assert (r.status_code, r.json()) == (503, MENSAGEM_503)
    await app.state.motor.dispose()
    assert "qa1x" not in caplog.text and "Traceback" not in caplog.text
    registros = [r for r in caplog.records if r.name == "artemis_backend.adapters.erros"]
    assert [r.getMessage() for r in registros] == [
        "Banco indisponível: BancoIndisponivel em POST /v1/auth/login",
        "Banco indisponível: BancoIndisponivel em POST /v1/auth/cadastro",
    ]


async def test_conexao_quebrada_da_503_e_depois_recupera(cliente, app, caplog):
    await cadastrar(cliente, email="qa2x@example.com")
    assert (await logar(cliente, "qa2x@example.com")).status_code == 200
    await ler_banco(
        app,
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        "WHERE datname = current_database() AND pid <> pg_backend_pid()",
    )
    caplog.set_level(logging.DEBUG)
    r = await logar(cliente, "qa2x@example.com")
    assert (r.status_code, r.json()) == (503, MENSAGEM_503)
    assert "qa2x" not in caplog.text and "Traceback" not in caplog.text
    assert (await logar(cliente, "qa2x@example.com")).status_code == 200


async def test_excecao_inesperada_da_500_json_sem_valores_no_log(app, cliente, caplog):
    @app.get("/_teste/quebra")
    async def quebra() -> None:
        raise RuntimeError("falha com qa3x@example.com e senha-xyz")

    caplog.set_level(logging.DEBUG)
    r = await cliente.get("/_teste/quebra")
    assert (r.status_code, r.json()) == (500, {"detail": "Erro interno"})
    assert "qa3x" not in r.text + caplog.text and "senha-xyz" not in caplog.text
    assert "Traceback" not in caplog.text
    assert "RuntimeError" in caplog.text and "/_teste/quebra" in caplog.text


async def test_404_e_405_continuam(cliente):
    assert (await cliente.get("/nao-existe")).status_code == 404
    assert (await cliente.get("/v1/auth/login")).status_code == 405
