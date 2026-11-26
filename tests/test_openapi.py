import json

import pytest

from ferramentas import exportar_openapi
from ferramentas.exportar_openapi import ARQUIVO, documento
from tests.apoio.sessao import rotas_protegidas
from tests.apoio.valores import ORIGEM_DE_TESTE

ERROS = {
    ("GET", "/health"): set(),
    ("POST", "/v1/auth/cadastro"): {"403", "409", "422", "503"},
    ("POST", "/v1/auth/login"): {"401", "403", "422", "503"},
    ("POST", "/v1/auth/sair"): {"403"},
    ("GET", "/v1/consentimento"): set(),
    ("GET", "/v1/conta"): {"401", "503"},
    ("PATCH", "/v1/conta"): {"401", "403", "422", "503"},
    ("DELETE", "/v1/conta"): {"401", "403", "503"},
    ("GET", "/v1/conversas"): {"401", "422", "503"},
    ("POST", "/v1/conversas"): {"401", "403", "503"},
    ("DELETE", "/v1/conversas"): {"401", "403", "503"},
    ("GET", "/v1/conversas/{conversa_id}"): {"401", "404", "422", "503"},
    ("DELETE", "/v1/conversas/{conversa_id}"): {"401", "403", "404", "422", "503"},
    ("POST", "/v1/conversas/{conversa_id}/mensagens"): {
        *("401", "403", "404", "409", "422", "503"),
    },
}
DOCUMENTO = json.loads(documento())
OPERACOES = {
    (metodo.upper(), caminho): operacao
    for caminho, operacoes in DOCUMENTO["paths"].items()
    for metodo, operacao in operacoes.items()
}


def esquema(operacao: dict, status: str) -> dict:
    conteudo = operacao["responses"][status]["content"]["application/json"]["schema"]
    if "$ref" not in conteudo:
        return conteudo
    return DOCUMENTO["components"]["schemas"][conteudo["$ref"].rsplit("/", 1)[1]]


def test_openapi_salvo_esta_atualizado():
    assert ARQUIVO.read_text("utf-8") == documento(), (
        "rode: uv run python -m ferramentas.exportar_openapi"
    )


def test_comando_exporta_sem_variavel_de_ambiente(monkeypatch, tmp_path):
    for nome in ("DATABASE_URL", "ARTEMIS_JWT_SEGREDO", "ARTEMIS_AGENTS_TOKEN", "ARTEMIS_ORIGEM"):
        monkeypatch.delenv(nome, raising=False)
    destino = tmp_path / "openapi.json"
    monkeypatch.setattr(exportar_openapi, "ARQUIVO", destino)
    exportar_openapi.main()
    assert destino.read_bytes() == documento().encode("utf-8")


def test_todas_as_rotas_dizem_os_erros_que_podem_dar():
    achados = {
        rota: {s for s in operacao["responses"] if s >= "400"}
        for rota, operacao in OPERACOES.items()
    }
    assert achados == ERROS


@pytest.mark.parametrize("rota", ERROS, ids=" ".join)
def test_erros_tem_o_corpo_real(rota):
    for status in ERROS[rota]:
        corpo = esquema(OPERACOES[rota], status)
        if status == "409" and rota[1].endswith("/mensagens"):
            assert set(corpo["properties"]) == {"detail", "codigo"}
            assert DOCUMENTO["components"]["schemas"]["ErroDeConflito"]["properties"]["codigo"][
                "enum"
            ] == ["ocupada", "expirada"]
        else:
            assert list(corpo["properties"]) == ["detail"]
            assert corpo["properties"]["detail"]["type"] == (
                "array" if status == "422" else "string"
            )


def test_422_documentado_sem_input_nem_ctx():
    esquemas = DOCUMENTO["components"]["schemas"]
    assert set(esquemas["DetalheDeValidacao"]["properties"]) == {"loc", "msg", "type"}
    assert "HTTPValidationError" not in esquemas


def test_toda_resposta_de_sucesso_com_corpo_tem_modelo():
    for rota, operacao in OPERACOES.items():
        [status] = [s for s in operacao["responses"] if s < "400"]
        if status == "204":
            assert "content" not in operacao["responses"]["204"], rota
        else:
            corpo = esquema(operacao, status)
            assert corpo["properties"] and "additionalProperties" not in corpo, rota


def test_sessao_por_bearer_ou_cookie_so_nas_rotas_protegidas(app):
    esquemas = DOCUMENTO["components"]["securitySchemes"]
    assert esquemas["bearer"] == {"type": "http", "scheme": "bearer"}
    assert esquemas["cookie"] == {"type": "apiKey", "in": "cookie", "name": "artemis_sessao"}
    protegidas = {rota for rota, o in OPERACOES.items() if "security" in o}
    assert protegidas == set(rotas_protegidas(app))
    for rota in protegidas:
        # Itens separados na lista: um ou outro.
        assert OPERACOES[rota]["security"] == [{"bearer": []}, {"cookie": []}]


def test_documento_nao_leva_configuracao():
    assert ORIGEM_DE_TESTE not in documento()
    assert "postgresql" not in documento()


def test_datas_sao_date_time():
    esquemas = DOCUMENTO["components"]["schemas"]
    for modelo, campos in [
        ("ConversaSaida", ("criada_em", "atualizada_em")),
        ("MensagemSaida", ("criada_em",)),
    ]:
        for campo in campos:
            assert esquemas[modelo]["properties"][campo] == {
                "type": "string",
                "format": "date-time",
                "title": campo.replace("_", " ").title(),
            }
