import asyncio

from sqlalchemy import func, select

from artemis_backend.adapters.tabelas import Conversa, Mensagem
from tests.apoio.conversas import gravar, mensagem, nova_conversa
from tests.apoio.valores import ANA


async def test_apagar_conversa_apaga_mensagens(cliente, entrar_como, sessao):
    cabecalho = await entrar_como(ANA)
    id_ = await nova_conversa(cliente, cabecalho)
    outra = await nova_conversa(cliente, cabecalho)
    p = mensagem(id_, "usuaria", "p")
    await gravar(sessao, p)
    await gravar(sessao, mensagem(id_, "artemis", "r", segundos=1, pergunta_id=p.id))
    await gravar(sessao, mensagem(outra, "usuaria", "fica"))

    r = await cliente.delete(f"/v1/conversas/{id_}", headers=cabecalho)
    assert r.status_code == 204
    assert r.content == b""
    segunda = await cliente.delete(f"/v1/conversas/{id_}", headers=cabecalho)
    assert segunda.status_code == 404
    assert (await cliente.get(f"/v1/conversas/{id_}", headers=cabecalho)).status_code == 404

    sessao.expire_all()
    restantes = await sessao.scalars(select(Mensagem.texto))
    assert list(restantes) == ["fica"]
    assert await sessao.scalar(select(func.count()).select_from(Conversa)) == 1


async def test_apagar_duas_vezes_ao_mesmo_tempo_nao_da_500(cliente, entrar_como):
    cabecalho = await entrar_como(ANA)
    for _ in range(5):
        id_ = await nova_conversa(cliente, cabecalho)
        respostas = await asyncio.gather(
            *(cliente.delete(f"/v1/conversas/{id_}", headers=cabecalho) for _ in range(4))
        )
        assert sorted(r.status_code for r in respostas) == [204, 404, 404, 404]
