import asyncio
import uuid
from datetime import UTC, datetime

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from artemis_backend.adapters.tabelas import Base, Conversa, Mensagem, Usuaria
from tests.apoio.banco import config_alembic


async def nomes_de_tabelas(url: str) -> set[str]:
    motor = create_async_engine(url)
    async with motor.connect() as conexao:
        nomes = await conexao.run_sync(lambda c: set(inspect(c).get_table_names()))
    await motor.dispose()
    return nomes - {"alembic_version"}


async def diferencas_entre_migracao_e_modelos(url: str) -> list:
    motor = create_async_engine(url)
    async with motor.connect() as conexao:

        def comparar(c):
            contexto = MigrationContext.configure(c, opts={"compare_type": True})
            return compare_metadata(contexto, Base.metadata)

        diferencas = await conexao.run_sync(comparar)
    await motor.dispose()
    return diferencas


async def test_migracao_sobe_desce_e_bate_com_os_modelos(criar_banco_vazio):
    url = await criar_banco_vazio()
    alembic = config_alembic(url)

    await asyncio.to_thread(command.upgrade, alembic, "head")
    assert await nomes_de_tabelas(url) == {"usuarias", "conversas", "mensagens"}

    await asyncio.to_thread(command.downgrade, alembic, "base")
    assert await nomes_de_tabelas(url) == set()

    await asyncio.to_thread(command.upgrade, alembic, "head")
    assert await diferencas_entre_migracao_e_modelos(url) == []


def nova_usuaria(email: str = "ana@example.com") -> Usuaria:
    return Usuaria(id=uuid.uuid4(), email=email, senha_hash="hash", consentiu_em=datetime.now(UTC))


async def test_apagar_usuaria_apaga_conversas_e_mensagens(banco):
    usuaria = nova_usuaria()
    conversa = Conversa(id=uuid.uuid4(), usuaria_id=usuaria.id)
    pergunta = Mensagem(id=uuid.uuid4(), conversa_id=conversa.id, papel="usuaria", texto="oi")
    resposta = Mensagem(
        id=uuid.uuid4(),
        conversa_id=conversa.id,
        papel="artemis",
        texto="olá",
        pergunta_id=pergunta.id,
    )
    banco.add(usuaria)
    await banco.flush()
    banco.add(conversa)
    await banco.flush()
    banco.add(pergunta)
    await banco.flush()
    banco.add(resposta)
    await banco.commit()

    await banco.delete(usuaria)
    await banco.commit()

    for modelo in (Usuaria, Conversa, Mensagem):
        assert await banco.scalar(select(func.count()).select_from(modelo)) == 0


async def test_papel_invalido_e_recusado(banco):
    usuaria = nova_usuaria()
    conversa = Conversa(id=uuid.uuid4(), usuaria_id=usuaria.id)
    banco.add(usuaria)
    await banco.flush()
    banco.add(conversa)
    await banco.flush()
    banco.add(Mensagem(id=uuid.uuid4(), conversa_id=conversa.id, papel="robo", texto="x"))
    with pytest.raises(IntegrityError, match="papel"):
        await banco.flush()


async def test_email_repetido_e_recusado(banco):
    banco.add(nova_usuaria("maria@example.com"))
    await banco.flush()
    banco.add(nova_usuaria("maria@example.com"))
    with pytest.raises(IntegrityError, match="email"):
        await banco.flush()


async def test_indice_de_conversas_por_usuaria_e_data_existe(banco):
    resultado = await banco.execute(
        text("SELECT indexdef FROM pg_indexes WHERE tablename = 'conversas'")
    )
    definicoes = [linha[0] for linha in resultado]
    assert any("(usuaria_id, atualizada_em)" in d for d in definicoes)


async def test_indice_de_mensagens_por_conversa_existe(banco):
    resultado = await banco.execute(
        text("SELECT indexdef FROM pg_indexes WHERE tablename = 'mensagens'")
    )
    definicoes = [linha[0] for linha in resultado]
    assert any("(conversa_id)" in d for d in definicoes)


async def test_mensagens_tem_indice_em_pergunta_id(criar_banco_vazio):
    url = await criar_banco_vazio()
    await asyncio.to_thread(command.upgrade, config_alembic(url), "head")
    motor = create_async_engine(url)
    async with motor.connect() as conexao:
        indices = await conexao.run_sync(lambda c: inspect(c).get_indexes("mensagens"))
    await motor.dispose()
    assert any(
        i["name"] == "ix_mensagens_pergunta_id" and i["column_names"] == ["pergunta_id"]
        for i in indices
    )
