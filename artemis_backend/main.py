from fastapi import FastAPI

from artemis_backend.config import Config


def criar_app(config: Config) -> FastAPI:
    app = FastAPI(title="Artemis API")
    app.state.config = config

    @app.get("/health")
    async def saude() -> dict[str, str]:
        return {"status": "ok"}

    return app


def app_de_ambiente() -> FastAPI:
    """Entrada para `uvicorn --factory`: lê a configuração do ambiente."""
    return criar_app(Config.de_ambiente())
