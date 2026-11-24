# AGENTS.md: backend do Artemis

As regras para agentes e pessoas vivem no orquestrador: [artemishub_orchestration/AGENTS.md](https://github.com/ArtemisHubApp/artemishub_orchestration/blob/main/AGENTS.md). Leia lá antes de mexer aqui. Este arquivo só guarda o que é específico deste repo.

- Pacote `artemis_backend`, camadas `domain`, `application` e `adapters` (dependências só para dentro).
- Rodar: `uv run --env-file .env uvicorn artemis_backend.main:app_de_ambiente --factory` (variáveis em `.env.example`).
- Migrações: `uv run --env-file .env alembic upgrade head`.
- Testar: `uv run pytest -q` (precisa do Docker rodando) e `uv run ruff check . && uv run ruff format --check .`.
- Nunca registre em log o texto das mensagens, e-mail, tokens ou a senha do banco. Dados de teste só com `@example.com`.
- Contas: `POST /v1/auth/cadastro` e `POST /v1/auth/login`. A dependência `usuaria_atual` (em `adapters/rotas_auth.py`) protege as rotas futuras e devolve o id da usuária; 401 para token ausente, inválido, vencido ou de usuária inexistente. `ARTEMIS_JWT_SEGREDO` exige pelo menos 32 bytes.
- Hash de senha é pesado: chame sempre via `asyncio.to_thread`. Respostas 422 não podem repetir senha nem e-mail (`input` é removido em `main.py`).
- Conversas: `GET/POST /v1/conversas`, `GET/DELETE /v1/conversas/{id}` e `POST /v1/conversas/{id}/mensagens` (`adapters/rotas_conversas.py`). Todo método de `RepositorioConversas` recebe `usuaria_id` e filtra por ele na mesma consulta; não existe busca só por id. Conversa de outra usuária responde 404, nunca 403. A resposta não expõe `usuaria_id`, `lembranca`, `respondendo_desde` nem `trace_id`.
- Memória curta e título ficam em `domain/conversa.py` (`memoria_curta`, `titulo_da_conversa`).
- Perguntas: `application/perguntar.py` pega a trava e grava a pergunta numa transação, chama os agentes **sem** conexão do banco aberta e grava a resposta noutra, conferindo que `respondendo_desde` ainda é o valor obtido. Não segure sessão do banco durante a chamada. A trava expira em 60 s (`VALIDADE_DA_TRAVA`).
- Contrato com os agentes: só `adapters/agentes_http.py` e `contratos/responder.v1.schema.json` dependem dele, e mudam juntos (`tests/test_agentes_http.py` confere as mesmas amostras nos dois). É rascunho (artemishub_agents#36), não foi fechado nem testado com o serviço real: nos testes os agentes são simulados (`AgentesFake`, `httpx.MockTransport`). Nenhum e-mail nem id de usuária vai para os agentes.
- Erros: só `BancoIndisponivel` (levantada em `adapters/banco.py`) e o pool esgotado viram 503; o resto, inclusive `ProgrammingError` e `OSError` de outra origem, é 500.
- Conta: `DELETE /v1/conta` e `GET /v1/consentimento` (`adapters/rotas_conta.py`). A exclusão apaga só a dona do token e o cascade do banco leva conversas e mensagens; quem perde a corrida de duas exclusões recebe o mesmo 401 de token inválido. Os traces do Langfuse não são apagados. O texto `CONSENTIMENTO` (em `domain/usuaria.py`) é provisório até o ADR de LGPD.
- Cadastro usa `ON CONFLICT (email) DO NOTHING` (`repositorio_contas.py`): capturar a violação de unicidade deixaria o e-mail no log do Postgres (`tests/test_log_do_postgres.py`).
