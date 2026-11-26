import asyncio
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

from tests.apoio.valores import SENHA_DE_TESTE

PRAZO_DO_LOG = 20  # segundos


def logs_do_postgres(postgres) -> str:
    return postgres.get_wrapped_container().logs().decode("utf-8", "replace")


async def logs_ate_o_marcador(postgres) -> str:
    """Provoca um erro inofensivo, com marcador único, em outra conexão e espera o log dele.

    O log do Postgres é sequencial: quando o marcador aparece, tudo o que aconteceu antes
    dele já está nos logs. Sem isso, "e-mail ausente" poderia ser só log que ainda não chegou.
    """
    marcador = f"marcador-{uuid.uuid4().hex}"
    motor = create_async_engine(postgres.get_connection_url())
    try:
        async with motor.connect() as conexao:
            with pytest.raises(DBAPIError):
                await conexao.execute(text(f"SELECT '{marcador}'::int"))
    finally:
        await motor.dispose()
    async with asyncio.timeout(PRAZO_DO_LOG):
        while marcador not in (logs := logs_do_postgres(postgres)):
            await asyncio.sleep(0.2)
    return logs


async def test_cadastro_repetido_nao_deixa_o_email_no_log_do_postgres(cliente, postgres):
    email = f"dup-{uuid.uuid4().hex}@example.com"
    corpo = {"email": email, "senha": SENHA_DE_TESTE, "consentimento": True}
    assert (await cliente.post("/v1/auth/cadastro", json=corpo)).status_code == 201

    sequencial = await cliente.post("/v1/auth/cadastro", json=corpo)
    simultaneos = await asyncio.gather(
        *(cliente.post("/v1/auth/cadastro", json=corpo) for _ in range(4))
    )
    logs = await logs_ate_o_marcador(postgres)

    assert sequencial.status_code == 409
    assert [r.status_code for r in simultaneos] == [409] * 4
    assert email not in logs


async def test_cadastros_simultaneos_sem_email_no_log_do_postgres(cliente, postgres):
    email = f"corrida-{uuid.uuid4().hex}@example.com"
    corpo = {"email": email, "senha": SENHA_DE_TESTE, "consentimento": True}

    respostas = await asyncio.gather(
        *(cliente.post("/v1/auth/cadastro", json=corpo) for _ in range(5))
    )
    logs = await logs_ate_o_marcador(postgres)

    assert sorted(r.status_code for r in respostas) == [201, 409, 409, 409, 409]
    assert email not in logs


async def test_controle_positivo_a_violacao_de_unicidade_poe_o_email_no_log(postgres, banco):
    """Prova que o log mostraria o e-mail se o cadastro ainda gerasse a violação."""
    email = f"controle-{uuid.uuid4().hex}@example.com"
    inserir = text(
        "INSERT INTO usuarias (id, email, senha_hash, consentiu_em) "
        "VALUES (gen_random_uuid(), :email, 'h', now())"
    )
    await banco.execute(inserir, {"email": email})
    await banco.commit()
    with pytest.raises(DBAPIError):
        await banco.execute(inserir, {"email": email})
    await banco.rollback()

    assert email in await logs_ate_o_marcador(postgres)
