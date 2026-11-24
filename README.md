# 🌙 Artemis — Backend

### API da plataforma Artemis 💜

Este repositório contém a **API** do Artemis: a camada que conecta a interface web aos agentes de IA e à base de conhecimento, além de cuidar das regras de negócio, da autenticação e da persistência dos dados.

> 🚧 **Em desenvolvimento.** Hoje existem `GET /health`, o cadastro com consentimento (`POST /v1/auth/cadastro`), o login (`POST /v1/auth/login`), o banco Postgres (tabelas `usuarias`, `conversas` e `mensagens`) e as migrações. As conversas, o texto do consentimento e a chamada aos agentes ainda não foram implementados, e ainda não há rota protegida por token.

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

3. Copie `.env.example` para `.env` e preencha as variáveis: `DATABASE_URL`, `ARTEMIS_JWT_SEGREDO`, `ARTEMIS_AGENTS_URL` e `ARTEMIS_AGENTS_TOKEN`. A API não sobe sem `ARTEMIS_JWT_SEGREDO`, que precisa ter pelo menos 32 bytes (use um valor aleatório). Na `DATABASE_URL`, a `<senha>` é a mesma `POSTGRES_PASSWORD` do passo 2. Nunca commite o `.env`.
4. Aplique as migrações: `uv run --env-file .env alembic upgrade head`.
5. Inicie a API: `uv run --env-file .env uvicorn artemis_backend.main:app_de_ambiente --factory`. Teste em `http://localhost:8000/health`.

### Rotas de autenticação

| Rota | Corpo | Resposta |
|---|---|---|
| `POST /v1/auth/cadastro` | `email`, `senha` (8 a 128 caracteres), `consentimento` (precisa ser o booleano `true`) | 201 com `{"id": ...}`; 409 se o e-mail já existe; 422 se algo for inválido |
| `POST /v1/auth/login` | `email`, `senha` | 200 com `{"token": ..., "tipo": "bearer"}` (JWT de 60 minutos, sem refresh); 401 para senha errada ou e-mail sem conta, com a mesma resposta |

O e-mail é normalizado (espaços e maiúsculas) no cadastro e no login. A senha é guardada com argon2. As respostas 422 não repetem o que foi enviado.

Nova migração: `uv run alembic revision --autogenerate -m "<descrição>"` e revise o arquivo gerado.

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
