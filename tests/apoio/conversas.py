import uuid
from datetime import UTC, datetime, timedelta

from artemis_backend.adapters.tabelas import Mensagem

INICIO = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
CAMPOS_DA_CONVERSA = {"id", "titulo", "criada_em", "atualizada_em"}
TEXTO_INDISPONIVEL = "Não consegui responder agora, tente de novo"
LEMBRANCA = {
    "salario": True,
    "direitos": False,
    "cbo_familia": "2124",
    "cbo_familia_nome": "Analistas",
    "ocupacao": None,
    "uf": "SP",
}


async def nova_conversa(cliente, cabecalho) -> str:
    r = await cliente.post("/v1/conversas", headers=cabecalho)
    assert r.status_code == 201
    return r.json()["id"]


def mensagem(conversa_id: str, papel: str, texto: str, segundos: int = 0, **extra) -> Mensagem:
    return Mensagem(
        id=uuid.uuid4(),
        conversa_id=uuid.UUID(conversa_id),
        papel=papel,
        texto=texto,
        criada_em=INICIO + timedelta(seconds=segundos),
        **extra,
    )


async def gravar(sessao, *mensagens: Mensagem) -> None:
    sessao.add_all(mensagens)
    await sessao.commit()
