"""O esquema do pedido barra antes do serviço tudo o que o serviço recusaria."""

import pytest
from pydantic import ValidationError

from artemis_backend.adapters.esquemas_auth import PedidoCadastro
from artemis_backend.domain.usuaria import normalizar_email, validar_senha
from tests.apoio.valores import NOME_DE_TESTE, SENHA_DE_TESTE

EMAILS = [
    "ana@example.com",
    "  ANA@Example.COM ",
    "İnci@example.com",
    "ǅ@example.com",
    "a" * 240 + "@example.com",
    "ß@example.com",
    "K@example.com",
]


@pytest.mark.parametrize("email", EMAILS)
def test_email_aceito_pelo_esquema_tambem_passa_no_dominio(email):
    try:
        pedido = PedidoCadastro(
            nome=NOME_DE_TESTE, email=email, senha=SENHA_DE_TESTE, consentimento=True
        )
    except ValidationError:
        return
    assert normalizar_email(pedido.email) == pedido.email


@pytest.mark.parametrize("senha", ["a" * 8, "a" * 128, "á" * 128])
def test_senha_aceita_pelo_esquema_tambem_passa_no_dominio(senha):
    pedido = PedidoCadastro(
        nome=NOME_DE_TESTE, email="ana@example.com", senha=senha, consentimento=True
    )
    validar_senha(pedido.senha)


@pytest.mark.parametrize("consentimento", [False, "true", 1, None])
def test_consentimento_so_passa_se_for_true(consentimento):
    with pytest.raises(ValidationError):
        PedidoCadastro(
            nome=NOME_DE_TESTE,
            email="ana@example.com",
            senha=SENHA_DE_TESTE,
            consentimento=consentimento,
        )
