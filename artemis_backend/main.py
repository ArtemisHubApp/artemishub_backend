from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from artemis_backend.adapters.agentes_http import AgentesHttp
from artemis_backend.adapters.banco import criar_fabrica_de_sessoes, criar_motor
from artemis_backend.adapters.erros import ProtegeErros
from artemis_backend.adapters.repositorio_contas import RepositorioContasSql
from artemis_backend.adapters.repositorio_conversas import RepositorioConversasSql
from artemis_backend.adapters.rotas_auth import roteador as rotas_auth
from artemis_backend.adapters.rotas_conta import roteador as rotas_conta
from artemis_backend.adapters.rotas_conversas import roteador as rotas_conversas
from artemis_backend.adapters.seguranca import EmissorJwt, HasherArgon2, RelogioDoSistema
from artemis_backend.adapters.sem_cache import SemCache
from artemis_backend.application.contas import ServicoContas
from artemis_backend.application.conversas import ServicoConversas
from artemis_backend.application.perguntar import ServicoPerguntas
from artemis_backend.application.portas import Agentes
from artemis_backend.config import Config


async def _validacao_sem_eco(_: Request, erro: RequestValidationError) -> JSONResponse:
    """422 sem `input` nem `ctx`: o padrão do FastAPI devolveria a senha e o e-mail enviados."""
    detalhes = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in erro.errors()]
    return JSONResponse({"detail": detalhes}, 422)


def criar_app(config: Config, agentes: Agentes | None = None) -> FastAPI:
    """Sem `agentes`, usa (e fecha ao desligar) o cliente HTTP do serviço configurado."""
    proprios = AgentesHttp(config.agents_url, config.agents_token) if agentes is None else None

    @asynccontextmanager
    async def ciclo_de_vida(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if proprios is not None:
                await proprios.fechar()

    app = FastAPI(title="Artemis API", lifespan=ciclo_de_vida)
    app.state.config = config
    app.add_exception_handler(RequestValidationError, _validacao_sem_eco)

    # O motor só conecta no primeiro uso, então criar o app não exige o banco no ar.
    app.state.motor = criar_motor(config.database_url)
    sessoes = criar_fabrica_de_sessoes(app.state.motor)
    relogio = RelogioDoSistema()
    app.state.contas = ServicoContas(
        repositorio=RepositorioContasSql(sessoes),
        hasher=HasherArgon2(),
        emissor=EmissorJwt(config.jwt_segredo, relogio),
        relogio=relogio,
    )
    conversas = RepositorioConversasSql(sessoes)
    app.state.agentes = agentes or proprios
    app.state.conversas = ServicoConversas(conversas)
    app.state.perguntas = ServicoPerguntas(conversas, app.state.agentes)
    app.include_router(rotas_auth)
    app.include_router(rotas_conversas)
    app.include_router(rotas_conta)
    app.add_middleware(ProtegeErros)
    # Por último para ficar por fora e alcançar as respostas do ProtegeErros.
    app.add_middleware(SemCache)

    @app.get("/health")
    async def saude() -> dict[str, str]:
        return {"status": "ok"}

    return app


def app_de_ambiente() -> FastAPI:
    """Entrada para `uvicorn --factory`: lê a configuração do ambiente."""
    return criar_app(Config.de_ambiente())
