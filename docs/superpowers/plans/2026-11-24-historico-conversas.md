# Histórico de conversas (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** API em que a usuária se cadastra, conversa com a Artemis, consulta o histórico e apaga o que quiser.

**Architecture:** pacote `artemis_backend` em camadas (`domain`, `application`, `adapters`). Os casos de uso falam com portas (repositório, agentes, relógio). Postgres via SQLAlchemy async e Alembic; os agentes são um cliente HTTP, com dublê nos testes até a artemishub_agents#36 fechar o contrato.

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy 2 (async, asyncpg), Alembic, Postgres 16, argon2-cffi, pyjwt, httpx; pytest e testcontainers.

**Spec:** `docs/superpowers/specs/2026-11-19-historico-e-memoria-curta-design.md` (aprovado em 24/11).

## Fora deste plano

Memória curta e limpeza do histórico dentro do agents, `POST /v1/responder` (artemishub_agents#36, Eduarda), frontend, perfil e currículo (#3 e artemishub_agents#14).

## Entrega em PRs

| PR | Tasks | Issue |
|---|---|---|
| 1 | 1 | sub-issue da #13; parte da #2 (Amanda e Camila) |
| 2 | 2 | sub-issue da #13; parte da #3 (Camila) |
| 3 | 3 e 4 | sub-issue da #13; parte da #5 |
| 4 | 5 | #13, mais issues próprias no docs e no orquestrador |

Combinar com a Camila antes do PR 1 e do PR 2. Spec e plano vão no PR 1.

## Execução e QA (aprovado pela Amanda em 24/11)

Subagentes: um implementa e outro revisa cada task. Depois da revisão, um terceiro faz o **QA** e devolve um relatório com passos, resultado esperado e obtido. Ele não corrige código: o que achar volta para quem implementou, e o QA repete o caso. A task só fecha com revisão e QA aprovados.

- **O que testa:** a API rodando de verdade (uvicorn e Postgres em container), por HTTP, como uma usuária, e não a suíte de testes.
- **Sempre:** os critérios da task, os itens do Review Focus dela e uma tentativa de acessar dados de outra usuária.
- **Task 4:** agentes simulados lentos, fora do ar e com resposta inválida; duas perguntas simultâneas.
- **Final (depois da Task 5):** jornada completa: cadastro, conversa, histórico, exclusão da conversa e da conta; logs sem dados pessoais.
- **Sem LLM:** nenhuma chamada ao Gemini no QA; só dados fictícios `@example.com`.

## Global Constraints

- Pacote `artemis_backend`, nunca `src`: o nome `src` já colidiu entre agents e rag.
- Dependências só apontam para dentro; `domain` não importa FastAPI, SQLAlchemy nem httpx.
- Senha com argon2; JWT HS256 com `ARTEMIS_JWT_SEGREDO`, 60 minutos, sem refresh. Sem o segredo, a API não sobe.
- Conversa de outra usuária responde 404, nunca 403.
- Pergunta com mais de 1.000 caracteres: 422. Pergunta só com espaços: 422.
- Memória curta: até 3 trocas da mesma conversa, só com `aprovada=true`, mais antiga primeiro, texto como exibido (a limpeza é no agents).
- Agentes fora do ar ou acima de 60 s: pergunta gravada e resposta "Não consegui responder agora, tente de novo", `aprovada=false`. Sem nova tentativa automática.
- Uma pergunta por conversa por vez; a segunda recebe 409. A trava expira em 60 s.
- Excluir a conta apaga tudo no Postgres; os traces do Langfuse permanecem, e o texto do consentimento diz isso.
- Logs sem texto de mensagens, e-mail ou token. Nenhum dado pessoal real em fixtures (use `@example.com`).
- Nenhum e-mail ou id de usuária vai para os agentes: só o id da conversa.

## Review Focus

1. **Duplo clique em enviar:** duas perguntas ao mesmo tempo; só uma chama os agentes, a outra recebe 409 (Task 4).
2. **Processo cai no meio da resposta:** a conversa não fica travada; após 60 s aceita nova pergunta (Task 4).
3. **Conversa apagada enquanto os agentes respondem:** a resposta tardia é descartada, sem erro 500 e sem recriar a conversa (Task 4).
4. **E-mail com maiúsculas ou espaços:** `Ana@Example.com ` entra na mesma conta de `ana@example.com` (Task 2).
5. **Token de conta excluída:** continua assinado, mas responde 401 (Task 5).

---

### Task 1: esqueleto, banco e saúde

**Files:**
- Create: `pyproject.toml`, `uv.lock`, `.python-version` (`3.12`), `.gitignore`, `.env.example`, `.github/workflows/ci.yml`, `AGENTS.md`, `alembic.ini`, `migrations/`
- Create: `artemis_backend/{__init__,config,main}.py`, `artemis_backend/adapters/{banco,tabelas}.py`
- Modify: `README.md`
- Test: `tests/conftest.py`, `tests/test_saude.py`, `tests/test_migracoes.py`

**Interfaces:**
- Produces: `Config.de_ambiente() -> Config` (campos `database_url: str`, `jwt_segredo: str`, `agents_url: str`, `agents_token: str`); `criar_app(config: Config, agentes: Agentes | None = None) -> FastAPI`; tabelas `usuarias`, `conversas`, `mensagens`; fixtures `cliente` (httpx AsyncClient), `banco` (sessão) e `postgres` (container, escopo de sessão).

- [ ] **Step 1: testes que falham**

```python
async def test_saude(cliente):
    r = await cliente.get("/health")
    assert (r.status_code, r.json()) == (200, {"status": "ok"})

def test_config_sem_segredo_nao_sobe(monkeypatch):
    monkeypatch.delenv("ARTEMIS_JWT_SEGREDO", raising=False)
    with pytest.raises(ValueError, match="ARTEMIS_JWT_SEGREDO"):
        Config.de_ambiente()

def test_migracao_sobe_desce_e_bate_com_os_modelos(postgres):
    assert diferencas_entre_migracao_e_modelos(postgres) == []   # alembic.autogenerate.compare_metadata

async def test_apagar_usuaria_apaga_conversas_e_mensagens(banco):
    ...  # insere 1 usuária, 1 conversa, 2 mensagens; apaga a usuária; as três tabelas têm 0 linhas
```

- [ ] **Step 2: rodar** `uv run pytest -q` → FAIL (`No module named 'artemis_backend'`).
- [ ] **Step 3: implementar.** Colunas da seção Dados do spec, mais: `conversas.respondendo_desde` (timestamptz, nula) para a trava e `mensagens.pergunta_id` (uuid, nula, FK para `mensagens`, cascade) para ligar resposta e pergunta. Todas as FKs com `ON DELETE CASCADE`; datas em timestamptz (UTC); `papel` com CHECK `('usuaria','artemis')`; índice em `conversas(usuaria_id, atualizada_em)`. `ci.yml` chama `python-ci.yml@main` do orquestrador; os testes usam testcontainers (o workflow reutilizável não tem `services`).
- [ ] **Step 4: rodar** `uv run pytest -q && uv run ruff check . && uv run ruff format --check .` → tudo passa.
- [ ] **Step 5: commit** `feat: esqueleto da API com Postgres e migrações`.

### Task 2: cadastro e login

**Files:**
- Create: `artemis_backend/domain/usuaria.py`, `artemis_backend/application/contas.py`, `artemis_backend/adapters/{seguranca,repositorio_contas,rotas_auth}.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `normalizar_email(email: str) -> str`; `cadastrar(email, senha, consentimento) -> UUID`; `entrar(email, senha) -> str` (JWT, `sub` = id); dependência FastAPI `usuaria_atual() -> UUID` (401 se o token for inválido, vencido ou de usuária inexistente); fixture `entrar_como(email) -> dict` (cabeçalho Authorization).

- [ ] **Step 1: testes que falham.** Um por linha, com estes nomes e resultados:

| Teste | Resultado |
|---|---|
| `test_cadastro_e_login` | 201 e depois 200 com `{"token": ..., "tipo": "bearer"}` |
| `test_cadastro_sem_consentimento` (`false` e ausente) | 422 |
| `test_email_repetido_com_maiusculas_e_espacos` | 409 |
| `test_senha_curta_e_longa` (7 e 129 caracteres) | 422 |
| `test_login_errado_e_email_inexistente_tem_a_mesma_resposta` | 401 e corpos iguais |
| `test_senha_guardada_com_argon2` | `senha_hash` começa com `$argon2` e não contém a senha |
| `test_token_vencido_adulterado_e_alg_none` | 401 nos três |
| `test_logs_sem_email_senha_nem_token` | `caplog` não contém nenhum dos três |

- [ ] **Step 2: rodar** `uv run pytest -q tests/test_auth.py` → FAIL (404).
- [ ] **Step 3: implementar.** `usuaria_atual` decodifica com `algorithms=["HS256"]` e confere que a usuária existe. No login com e-mail inexistente, verificar um hash fixo, para o tempo de resposta não revelar quem tem conta.
- [ ] **Step 4: rodar** `uv run pytest -q` → passa.
- [ ] **Step 5: commit** `feat: cadastro com consentimento e login`.

### Task 3: conversas e mensagens guardadas

**Files:**
- Create: `artemis_backend/domain/conversa.py`, `artemis_backend/application/{portas,conversas}.py`, `artemis_backend/adapters/{repositorio_conversas,rotas_conversas}.py`
- Test: `tests/test_conversas.py`, `tests/test_memoria_curta.py`

**Interfaces:**
- Consumes: `usuaria_atual`, `entrar_como`.
- Produces: `Troca(pergunta: str, resposta: str)`; `Mensagem(id, papel, texto, criada_em, aprovada, bloqueada, trace_id, pergunta_id)`; `titulo_da_conversa(pergunta: str) -> str`; `memoria_curta(mensagens: list[Mensagem]) -> list[Troca]`; `RepositorioConversas` (Protocol).

- [ ] **Step 1: testes que falham**

```python
def test_memoria_curta_pega_as_3_ultimas_aprovadas_na_ordem():
    assert [t.pergunta for t in memoria_curta(trocas(5))] == ["p3", "p4", "p5"]

def test_memoria_curta_ignora_nao_aprovadas_e_pergunta_sem_resposta():
    # p1 aprovada, p2 bloqueada, p3 abstenção (aprovada=False), p4 sem resposta
    assert [t.pergunta for t in memoria_curta(mensagens)] == ["p1"]

def test_titulo_corta_em_60_sem_quebrar_palavra():
    assert titulo_da_conversa("curta") == "curta"
    assert len(titulo_da_conversa("palavra " * 20)) <= 60
```

Rotas: `test_lista_mais_recente_primeiro`, `test_conversa_de_outra_usuaria_responde_404` (GET e DELETE; a conversa continua existindo para a dona), `test_id_malformado_responde_422`, `test_apagar_conversa_apaga_mensagens` (204 e depois 404), `test_sem_token_responde_401` (todas as rotas).

- [ ] **Step 2: rodar** → FAIL.
- [ ] **Step 3: implementar** as rotas GET e POST `/v1/conversas`, GET e DELETE `/v1/conversas/{id}`. Toda consulta do repositório recebe `usuaria_id` e filtra por ele; não existe busca só por id.
- [ ] **Step 4: rodar** `uv run pytest -q` → passa.
- [ ] **Step 5: commit** `feat: histórico de conversas por usuária`.

### Task 4: perguntar à Artemis

**Files:**
- Create: `artemis_backend/application/perguntar.py`, `artemis_backend/adapters/agentes_http.py`, `contratos/responder.v1.schema.json`
- Modify: `artemis_backend/adapters/rotas_conversas.py`
- Test: `tests/test_perguntar.py`, `tests/test_agentes_http.py`

**Interfaces:**
- Consumes: `memoria_curta`, `RepositorioConversas`.
- Produces: `Agentes` (Protocol) com `async responder(pergunta: str, sessao: str, historico: list[Troca], lembranca: dict | None) -> RespostaAgentes`; `RespostaAgentes(resposta, aprovada, bloqueada, fora_de_escopo, lembranca, trace_id)`; `AgentesIndisponiveis(Exception)`; `AgentesHttp(url, token, timeout=60.0)`.

- [ ] **Step 1: testes que falham** (com `AgentesFake`)

| Teste | Resultado |
|---|---|
| `test_pergunta_grava_e_devolve_a_resposta` | 201; GET mostra pergunta e resposta ligadas por `pergunta_id` |
| `test_manda_historico_e_lembranca_da_conversa` | fake recebe 3 trocas, a lembrança guardada e `sessao` = id da conversa |
| `test_nao_manda_email_nem_id_da_usuaria` | nenhum dos dois aparece no pedido |
| `test_lembranca_nova_e_guardada` e `test_bloqueada_nao_altera_a_lembranca` | valor novo; valor antigo |
| `test_agentes_fora_do_ar` | 201, texto do Global Constraints, `aprovada=false`, trava liberada |
| `test_pergunta_vazia_e_longa` (espaços e 1.001 caracteres) | 422, agentes não chamados |
| `test_duas_perguntas_ao_mesmo_tempo` | um 201, um 409, uma chamada |
| `test_trava_velha_expira` (`respondendo_desde` há 61 s) | 201 |
| `test_conversa_apagada_durante_a_resposta` | 404, nenhuma mensagem recriada |
| `test_perguntas_em_conversa_alheia` | 404, agentes não chamados |
| `test_http_timeout_500_json_invalido_e_fora_do_schema` | `AgentesIndisponiveis` nos quatro (httpx.MockTransport) |
| `test_http_manda_token_de_servico` | cabeçalho `Authorization: Bearer <ARTEMIS_AGENTS_TOKEN>` |

- [ ] **Step 2: rodar** → FAIL.
- [ ] **Step 3: implementar.** Trava num só `UPDATE ... WHERE respondendo_desde IS NULL OR respondendo_desde < now() - interval '60 seconds' RETURNING respondendo_desde`; sem linha, 409. Gravar a pergunta e fechar a transação **antes** de chamar os agentes. Ao gravar a resposta, conferir que `respondendo_desde` ainda é o valor obtido; se não for (apagada ou expirada), descartar. O schema JSON é o contrato do comentário na artemishub_agents#36; se a Eduarda mudar, só muda este arquivo e `agentes_http.py`.
- [ ] **Step 4: rodar** `uv run pytest -q` → passa.
- [ ] **Step 5: commit** `feat: perguntas à Artemis com memória curta e trava por conversa`.

### Task 5: excluir conta, compose e documentação

**Files:**
- Create: `artemis_backend/adapters/rotas_conta.py`; Test: `tests/test_conta.py`
- Modify: `README.md`, `AGENTS.md`, `.env.example`
- Outros repos, com issue e PR próprios: `artemishub_docs/docs/adr/001-stack.md` (issue docs#3) e página de arquitetura; `artemishub_orchestration/docker-compose.yml` e `tests/test_compose_make.py`

**Interfaces:**
- Consumes: `usuaria_atual`. Produces: `DELETE /v1/conta`.

- [ ] **Step 1: testes que falham:** `test_excluir_conta_apaga_tudo_dela_e_nada_das_outras` (204; 0 linhas dela, as da outra intactas), `test_token_de_conta_excluida_responde_401`, `test_email_pode_ser_cadastrado_de_novo` (201, sem conversas antigas).
- [ ] **Step 2: rodar** → FAIL (404). **Step 3: implementar.** **Step 4: rodar** `uv run pytest -q` → passa.
- [ ] **Step 5: texto do consentimento** em `artemis_backend/domain/usuaria.py` (constante `CONSENTIMENTO`, devolvida por `GET /v1/consentimento`): "Guardamos suas conversas para você consultar depois. O texto das perguntas é enviado ao Google Gemini, para gerar a resposta, e ao Langfuse, para acompanhar a qualidade. No plano gratuito do Gemini, o Google pode usar esse texto para melhorar os produtos dele. Você pode apagar conversas e a conta quando quiser; os registros no Langfuse permanecem." Teste: cita Gemini, Langfuse e "permanecem". A equipe revisa o texto no ADR de LGPD.
- [ ] **Step 6: compose.** Serviço `postgres` (16, volume nomeado, healthcheck) e `backend` com `uv run uvicorn` no profile `app`; o teste do compose passa a esperar `{"rag","agents","backend","frontend","postgres"}`. Verificação: `docker compose --profile app up -d postgres backend` e `curl localhost:8000/health` → `{"status":"ok"}`.
- [ ] **Step 7: ADR-001** no formato do ADR-002, status `proposto`: FastAPI + Postgres no backend, agentes como serviço separado, alternativas do spec; o frontend fica em aberto. `mkdocs build --strict` verde.
- [ ] **Step 8: commit** `feat: exclusão de conta e texto de consentimento`.
