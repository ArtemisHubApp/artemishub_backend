# 🌙 Artemis — Backend

### API da plataforma Artemis 💜

Este repositório contém a **API** do Artemis: a camada que conecta a interface web aos agentes de IA e à base de conhecimento, além de cuidar das regras de negócio, da autenticação e da persistência dos dados.

> 🚧 **Em desenvolvimento.** Hoje existem `GET /health`, o cadastro com consentimento (`POST /v1/auth/cadastro`), o login (`POST /v1/auth/login`), o banco Postgres (tabelas `usuarias`, `conversas` e `mensagens`), as migrações e as rotas de conversas (criar, listar, abrir, apagar uma ou todas e perguntar), todas protegidas por sessão (token ou cookie). A pergunta chama o serviço de agentes por HTTP, mas o contrato ainda é um rascunho ([artemishub_agents#36](https://github.com/ArtemisHubApp/artemishub_agents/issues/36)) e o endpoint de lá ainda não existe: nos testes os agentes são simulados. Também existem `GET /v1/consentimento`, a troca do nome (`PATCH /v1/conta`) e a exclusão da conta (`DELETE /v1/conta`). O texto do consentimento ainda precisa ser revisado pela equipe no ADR de LGPD. O compose com Postgres e backend é a [backend#11](https://github.com/ArtemisHubApp/artemishub_backend/issues/11) e ainda não existe.

## 🎯 Responsabilidades

- 🔐 **Autenticação e contas:** cadastro, login e gestão do perfil da usuária.
- 📄 **Upload de currículo e documentos:** recebimento e armazenamento seguro dos arquivos enviados.
- 🤖 **Orquestração das chamadas de IA:** encaminhar as solicitações ao `artemishub_agents` e devolver respostas com as fontes citadas.
- 💾 **Persistência:** histórico de conversas, análises de perfil e simulações de negociação.
- 🛡️ **Privacidade e segurança:** proteção de dados pessoais (LGPD), validação de entrada e controle de acesso.

## 🔌 Integrações

```mermaid
flowchart LR
    FE[artemishub_frontend] -->|HTTP / JSON| BE[artemishub_backend]
    BE --> DB[(Banco de dados)]
    BE --> AG[artemishub_agents]
    AG --> RAG[artemishub_rag]
```

## 🧰 Stack

Python 3.12, [uv](https://docs.astral.sh/uv/), FastAPI, SQLAlchemy 2 (async) com asyncpg, Alembic e Postgres 16. Testes com pytest e testcontainers. O código segue camadas `domain`, `application` e `adapters`, com as dependências apontando para dentro. As decisões ficam como ADR no [artemishub_docs](https://github.com/ArtemisHubApp/artemishub_docs).

## ▶️ Como executar

1. Instale as dependências: `uv sync`.
2. Suba um Postgres local (só para desenvolvimento; troque a senha):

   ```bash
   docker run --name artemis-postgres -e POSTGRES_USER=artemis -e POSTGRES_PASSWORD=<senha> \
     -e POSTGRES_DB=artemis -p 5432:5432 -d postgres:16
   ```

3. Copie `.env.example` para `.env` e preencha as variáveis: `DATABASE_URL`, `ARTEMIS_JWT_SEGREDO`, `ARTEMIS_AGENTS_URL`, `ARTEMIS_AGENTS_TOKEN`, `ARTEMIS_ORIGEM` e `ARTEMIS_COOKIE_SEGURO` (veja [Sessão no navegador](#sessão-no-navegador)). `ARTEMIS_JWT_SEGREDO` e `ARTEMIS_AGENTS_TOKEN` vêm vazios no `.env.example` de propósito: gere o segredo (`openssl rand -base64 48`, ou `python -c "import secrets; print(secrets.token_urlsafe(48))"` no Windows) e peça o token dos agentes à equipe. A API não sobe sem `ARTEMIS_JWT_SEGREDO`, que precisa ter pelo menos 32 bytes. Na `DATABASE_URL`, a `<senha>` é a mesma `POSTGRES_PASSWORD` do passo 2. Nunca commite o `.env`.
4. Aplique as migrações: `uv run --env-file .env alembic upgrade head`.
5. Inicie a API: `uv run --env-file .env uvicorn artemis_backend.main:app_de_ambiente --factory`. Teste em `http://localhost:8000/health`.

### Rotas de autenticação

| Rota | Corpo | Resposta |
|---|---|---|
| `POST /v1/auth/cadastro` | `nome` (1 a 80 caracteres), `email`, `senha` (8 a 128 caracteres), `consentimento` (precisa ser o booleano `true`) | 201 com `{"id": ...}`; 409 se o e-mail já existe; 422 se algo for inválido |
| `POST /v1/auth/login` | `email`, `senha` | 200 com `{"token": ..., "tipo": "bearer"}` (JWT de 60 minutos, sem refresh) e o cookie de sessão; 401 para senha errada ou e-mail sem conta, com a mesma resposta |
| `POST /v1/auth/sair` | nenhum | 204 e apaga o cookie; também 204 sem sessão. Não invalida um token já copiado |

No cadastro e no login, se o cabeçalho `Origin` vier, precisa ser igual a `ARTEMIS_ORIGEM`; senão, 403.

O e-mail é normalizado (espaços e maiúsculas) no cadastro e no login. O nome é como a usuária quer ser chamada: aceita qualquer letra (acentos, nome social), perde os espaços das pontas, reduz os repetidos a um e não pode ter caractere de controle; 1 a 80 caracteres depois disso, senão 422 sem repetir o que veio. Contas anteriores à migração 0004 ficaram com o nome provisório `Usuária`. A senha é guardada com argon2. As respostas 422 não repetem o que foi enviado. O cadastro repetido usa `INSERT ... ON CONFLICT DO NOTHING`, para o e-mail não aparecer no log do Postgres.

### Sessão no navegador

O login grava o cookie `artemis_sessao` (`HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/`, 60 minutos), com o mesmo token do corpo. O frontend e a API ficam no mesmo endereço, sem CORS: em desenvolvimento, o Vite (`http://localhost:5173`) repassa `/v1` à API.

- As rotas protegidas aceitam `Authorization: Bearer <token>` ou o cookie. Com qualquer `Authorization`, mesmo inválido, o cookie é ignorado. `Authorization` ou cookie de sessão repetidos respondem 401.
- Com o cookie, todo método que não seja GET, HEAD ou OPTIONS exige `Origin` igual a `ARTEMIS_ORIGEM`; senão, 403 com `{"detail": "Origem não permitida"}`, antes de conferir a sessão. Sair com o cookie exige `Origin` mesmo com `Authorization`.
- As respostas de `/v1` levam `Cache-Control: no-store`.

| Variável | Valor |
|---|---|
| `ARTEMIS_ORIGEM` | obrigatória: `esquema://host[:porta]`, como o navegador escreve (minúsculas, sem a porta padrão, sem caminho nem barra no fim). `https`, exceto em `localhost` e `127.0.0.1` |
| `ARTEMIS_COOKIE_SEGURO` | `true` (padrão) ou `false`; `false` só com `ARTEMIS_ORIGEM` em `http` local |

A API não sobe com um valor fora disso.

### Conta e consentimento

| Rota | Resposta |
|---|---|
| `GET /v1/consentimento` | 200 com `{"texto": ...}`. Pública, para ser lida antes do cadastro. O texto cita o Google Gemini e o Langfuse, que recebem o texto das perguntas |
| `GET /v1/conta` | Exige sessão. 200 com `{"id": ..., "nome": ..., "email": ...}` da própria usuária; 401 sem sessão válida |
| `PATCH /v1/conta` | Exige sessão (com cookie, `Origin` igual a `ARTEMIS_ORIGEM`, senão 403). Corpo `{"nome": ...}` com as mesmas regras do cadastro; 200 com a conta; 422 se o nome for inválido. Só muda a conta da dona do token; `id` e e-mail do corpo são ignorados |
| `DELETE /v1/conta` | Exige sessão. 204 e apaga a conta, as conversas, as mensagens e o cookie, sem volta; 401 sem sessão válida, inclusive numa segunda exclusão da mesma conta. O e-mail pode ser cadastrado de novo, sem as conversas antigas |

**O que a exclusão não apaga:** os traces do Langfuse permanecem, e o texto do consentimento diz isso. O texto é provisório: a equipe o revisa no ADR de LGPD. Depois da exclusão, o token continua assinado, mas responde 401 em todas as rotas.

### Rotas de conversas

Exigem sessão, por `Authorization: Bearer <token>` ou cookie (401 sem sessão válida). Cada usuária só enxerga as próprias conversas: a de outra usuária responde 404, igual a uma que não existe.

| Rota | Resposta |
|---|---|
| `POST /v1/conversas` | 201 com a conversa vazia: `id`, `titulo` (nulo até a primeira pergunta), `criada_em`, `atualizada_em` |
| `GET /v1/conversas?limite=50&cursor=...` | 200 com `{"itens": [...], "proximo": ...}`, da mais recente para a mais antiga (por `atualizada_em`). `limite` de 1 a 100 (padrão 50); `proximo` é o `cursor` da página seguinte, ou nulo na última; 422 para limite ou cursor inválido. Nenhuma conversa se repete; uma atualizada entre duas páginas sobe para o topo e não aparece nas páginas seguintes |
| `DELETE /v1/conversas` | 204 e apaga todas as conversas da usuária, sem volta; 204 também se não há nenhuma. Uma pergunta em andamento recebe 404 |
| `GET /v1/conversas/{id}` | 200 com a conversa e `mensagens` em ordem cronológica (`id`, `papel`, `texto`, `criada_em`, `aprovada`, `bloqueada`, `pergunta_id`); 404; 422 se o id não for um UUID |
| `DELETE /v1/conversas/{id}` | 204 e apaga as mensagens, sem volta; 404 se não existe ou já foi apagada |
| `POST /v1/conversas/{id}/mensagens` | corpo `{"pergunta": "..."}` (até 1.000 caracteres, com espaços das pontas removidos ao guardar); 201 com `pergunta` e `resposta`, cada uma com os campos das mensagens acima; 404 (também se a conversa for apagada durante a resposta); 409 com `{"detail": ..., "codigo": ...}`: `ocupada` se já há uma pergunta em andamento (a nova não é gravada) ou `expirada` se ela passou de 60 s e outra tomou o lugar (a pergunta fica no histórico, a resposta é descartada); 422 para pergunta vazia, longa ou com caractere inválido |

A Artemis recebe até 3 trocas anteriores aprovadas da mesma conversa, a lembrança guardada e o id da conversa, nunca o e-mail nem o id da usuária. Se os agentes falharem ou passarem de 60 s no total, a resposta é 201 com "Não consegui responder agora, tente de novo" e `aprovada` falso, sem nova tentativa. A trava da conversa expira em 60 s, então uma queda da API não a deixa presa. O contrato com os agentes fica em [contratos/responder.v1.schema.json](contratos/responder.v1.schema.json).

Se o banco recusar, cair ou não responder (5 s para conectar, 10 s por comando), a API responde 503.

As datas saem em UTC (`...Z`). Endereço com barra no fim responde 404, sem redirecionar.

### Agentes simulados e OpenAPI, para o frontend

Para desenvolver sem o serviço real, ponha no `.env` `ARTEMIS_AGENTS_URL=http://127.0.0.1:8001` e qualquer valor em `ARTEMIS_AGENTS_TOKEN`, e rode em dois terminais:

```bash
uv run --env-file .env python -m ferramentas.agentes_simulados --porta 8001
uv run --env-file .env uvicorn artemis_backend.main:app_de_ambiente --factory
```

O simulador só atende em 127.0.0.1, exige o token e começa toda resposta com "[SIMULADO]". Um trecho na pergunta escolhe o modo: `#lento` (5 s), `#erro` (500), `#bloqueada` e `#escopo`. Fica fora do pacote de produção.

O frontend gera os tipos de [contratos/openapi.json](contratos/openapi.json). Mudou uma rota? Rode `uv run python -m ferramentas.exportar_openapi` e commite o arquivo; um teste confere.

Nova migração: `uv run --env-file .env alembic revision --autogenerate -m "<descrição>"` e revise o arquivo gerado.

## 🧪 Testes

`uv run pytest -q`. Os testes sobem um Postgres 16 descartável com testcontainers, então **o Docker precisa estar rodando**. Antes do PR: `uv run ruff check . && uv run ruff format --check . && uv lock --check`.

## 📋 Contribuindo

As tarefas são acompanhadas no [kanban do projeto](https://github.com/orgs/ArtemisHubApp/projects). Ao abrir um PR, inclua `Closes #<número>` na descrição para que a issue seja movida automaticamente.

## 🗂️ Repositórios do projeto

| Repositório | Responsabilidade |
|---|---|
| [artemishub_docs](https://github.com/ArtemisHubApp/artemishub_docs) | Documentação, decisões de arquitetura e kanban do projeto |
| [artemishub_frontend](https://github.com/ArtemisHubApp/artemishub_frontend) | Interface web da plataforma |
| [artemishub_backend](https://github.com/ArtemisHubApp/artemishub_backend) | API, regras de negócio, autenticação e persistência |
| [artemishub_agents](https://github.com/ArtemisHubApp/artemishub_agents) | Sistema multiagentes LLM, multimodalidade e modelos de ML |
| [artemishub_rag](https://github.com/ArtemisHubApp/artemishub_rag) | Base de conhecimento, indexação e recuperação com citações |

## 👩‍💻 Nossa equipe

Desenvolvido pelo **Grupo 11**. Todas somos **AI Builders**, cada uma com uma frente principal de atuação:

<table>
  <tr>
    <td align="center">
      <a href="https://github.com/CamilaSilvaC">
        <img src="https://github.com/CamilaSilvaC.png" width="90" alt="Camila"/><br/>
        <b>Camila</b>
      </a>
      <br/><sub>Engenharia de Dados · DevOps</sub>
    </td>
    <td align="center">
      <a href="https://github.com/AmandaElisa">
        <img src="https://github.com/AmandaElisa.png" width="90" alt="Amanda"/><br/>
        <b>Amanda</b>
      </a>
      <br/><sub>Fullstack</sub>
    </td>
    <td align="center">
      <a href="https://github.com/anajbsouza">
        <img src="https://github.com/anajbsouza.png" width="90" alt="Ana Julia"/><br/>
        <b>Ana Julia</b>
      </a>
      <br/><sub>Ciência de Dados · Engenharia de Dados</sub>
    </td>
    <td align="center">
      <a href="https://github.com/eduardaoliveirazorg-jpg">
        <img src="https://github.com/eduardaoliveirazorg-jpg.png" width="90" alt="Eduarda"/><br/>
        <b>Eduarda</b>
      </a>
      <br/><sub>Ciência de Dados · Arquitetura de Software</sub>
    </td>
  </tr>
</table>

---

<p align="center">
  <i>Artemis — Mais conhecimento, confiança e oportunidades para mulheres em STEM.</i> 💜
</p>
