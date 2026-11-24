# AGENTS.md: backend do Artemis

As regras para agentes e pessoas vivem no orquestrador: [artemishub_orchestration/AGENTS.md](https://github.com/ArtemisHubApp/artemishub_orchestration/blob/main/AGENTS.md). Leia lá antes de mexer aqui. Este arquivo só guarda o que é específico deste repo.

- Pacote `artemis_backend`, camadas `domain`, `application` e `adapters` (dependências só para dentro).
- Rodar: `uv run --env-file .env uvicorn artemis_backend.main:app_de_ambiente --factory` (variáveis em `.env.example`).
- Migrações: `uv run --env-file .env alembic upgrade head`.
- Testar: `uv run pytest -q` (precisa do Docker rodando) e `uv run ruff check . && uv run ruff format --check .`.
- Nunca registre em log o texto das mensagens, e-mail, tokens ou a senha do banco. Dados de teste só com `@example.com`.
- Contas: `POST /v1/auth/cadastro` e `POST /v1/auth/login`. A dependência `usuaria_atual` (em `adapters/rotas_auth.py`) protege as rotas futuras e devolve o id da usuária; 401 para token ausente, inválido, vencido ou de usuária inexistente. `ARTEMIS_JWT_SEGREDO` exige pelo menos 32 bytes.
- Hash de senha é pesado: chame sempre via `asyncio.to_thread`. Respostas 422 não podem repetir senha nem e-mail (`input` é removido em `main.py`).
