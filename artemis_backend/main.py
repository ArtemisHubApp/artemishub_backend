from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from artemis_backend.adapters.banco import criar_fabrica_de_sessoes, criar_motor
from artemis_backend.adapters.erros import ProtegeErros
from artemis_backend.adapters.repositorio_contas import RepositorioContasSql
from artemis_backend.adapters.rotas_auth import roteador as rotas_auth
from artemis_backend.adapters.seguranca import EmissorJwt, HasherArgon2, RelogioDoSistema
from artemis_backend.application.contas import ServicoContas
from artemis_backend.config import Config


async def _validacao_sem_eco(_: Request, erro: RequestValidationError) -> JSONResponse:
    """422 sem `input` nem `ctx`: o padrão do FastAPI devolveria a senha e o e-mail enviados."""
    detalhes = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in erro.errors()]
    return JSONResponse({"detail": detalhes}, 422)


def criar_app(config: Config) -> FastAPI:
    app = FastAPI(title="Artemis API")
    app.state.config = config
    app.add_exception_handler(RequestValidationError, _validacao_sem_eco)

    # O motor só conecta no primeiro uso, então criar o app não exige o banco no ar.
    app.state.motor = criar_motor(config.database_url)
    relogio = RelogioDoSistema()
    app.state.contas = ServicoContas(
        repositorio=RepositorioContasSql(criar_fabrica_de_sessoes(app.state.motor)),
        hasher=HasherArgon2(),
        emissor=EmissorJwt(config.jwt_segredo, relogio),
        relogio=relogio,
    )
    app.include_router(rotas_auth)
    app.add_middleware(ProtegeErros)

    @app.get("/health")
    async def saude() -> dict[str, str]:
        return {"status": "ok"}

    return app


def app_de_ambiente() -> FastAPI:
    """Entrada para `uvicorn --factory`: lê a configuração do ambiente."""
    return criar_app(Config.de_ambiente())
