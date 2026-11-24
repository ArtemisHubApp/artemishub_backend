import asyncio
import uuid

from tests.conftest import SENHA_DE_TESTE


def logs_do_postgres(postgres) -> str:
    return postgres.get_wrapped_container().logs().decode("utf-8", "replace")


async def test_cadastro_repetido_nao_deixa_o_email_no_log_do_postgres(cliente, postgres):
    email = f"dup-{uuid.uuid4().hex}@example.com"
    corpo = {"email": email, "senha": SENHA_DE_TESTE, "consentimento": True}
    assert (await cliente.post("/v1/auth/cadastro", json=corpo)).status_code == 201
    antes = logs_do_postgres(postgres)

    sequencial = await cliente.post("/v1/auth/cadastro", json=corpo)
    simultaneos = await asyncio.gather(
        *(cliente.post("/v1/auth/cadastro", json=corpo) for _ in range(4))
    )
    await asyncio.sleep(1)
    depois = logs_do_postgres(postgres)

    assert sequencial.status_code == 409
    assert [r.status_code for r in simultaneos] == [409] * 4
    assert email not in antes
    assert email not in depois
    assert depois.count("already exists") == antes.count("already exists")


async def test_cadastros_simultaneos_sem_email_no_log_do_postgres(cliente, postgres):
    email = f"corrida-{uuid.uuid4().hex}@example.com"
    corpo = {"email": email, "senha": SENHA_DE_TESTE, "consentimento": True}

    respostas = await asyncio.gather(
        *(cliente.post("/v1/auth/cadastro", json=corpo) for _ in range(5))
    )
    await asyncio.sleep(1)

    assert sorted(r.status_code for r in respostas) == [201, 409, 409, 409, 409]
    assert email not in logs_do_postgres(postgres)
