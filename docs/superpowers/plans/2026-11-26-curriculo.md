# Currículo por PDF ou foto (backend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A usuária envia um currículo (PDF ou foto), confere o texto extraído, guarda só o texto mascarado, informa o objetivo, conversa sobre o currículo e confirma competências sugeridas.

**Architecture:** Camadas do backend (`adapters` → `application` → `domain`). O arquivo passa só pela memória: o backend confere tipo e tamanho e manda os bytes ao serviço `leitor` por uma porta nova (`Leitor`), com um leitor falso nos testes. A máscara obrigatória roda no domínio, no servidor. Conversas ganham um tipo; só o tipo `curriculo` manda o texto e o objetivo aos agents, e a resposta dos agents passa a trazer competências estruturadas.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, Postgres 16, httpx, python-multipart, pytest com testcontainers, uv.

**Spec:** `docs/superpowers/specs/2026-11-26-curriculo-design.md`

## Global Constraints

- O arquivo enviado nunca é gravado: nem disco, nem banco, nem log. Só memória.
- Tipos aceitos, conferidos pelos primeiros bytes: PDF (`%PDF-`), JPEG (`FF D8 FF`), PNG (`89 50 4E 47 0D 0A 1A 0A`).
- Tamanho máximo do arquivo: 10 MB (`10 * 1024 * 1024` bytes). O limite de 5 páginas é do leitor.
- E-mail, telefone, CPF e CEP são **sempre** retirados pelo servidor, sem opção. Nome e endereço só saem se vierem em `retirar`.
- Substitutos da máscara: `[e-mail]`, `[telefone]`, `[CPF]`, `[CEP]`, `[retirado]`.
- Texto do currículo: até 30 000 caracteres, sem NUL, com algum caractere visível. Objetivo: até 300 caracteres. Competência: nome até 100, evidência até 500.
- Limite de espera pelo leitor: 90 s no total.
- Toda rota nova exige sessão (cookie + `Origin` em escrita, ou `Authorization`), e uma usuária nunca lê nem apaga o que é de outra (RNF-06).
- Excluir a conta apaga currículo, objetivo e competências (cascata).
- Só conversas do tipo `curriculo` mandam currículo e objetivo aos agents.
- Todo erro de `/v1` sai no formato de `esquemas_de_erro.py` e com `Cache-Control: no-store` (já garantido pelos middlewares).

## Review Focus

- **Arquivo com extensão certa e conteúdo errado** (um `.pdf` que é ZIP, um `.jpg` que é PDF): 415 pelo conteúdo, não pela extensão nem pelo `Content-Type`. Teste na Task 4.
- **Arquivo enorme**: 413 sem ler o arquivo inteiro para a memória (para na leitura do byte 10 MB + 1). Teste na Task 4.
- **Leitor fora do ar ou lento**: 503 e nada gravado no banco. Teste na Task 4.
- **Dados pessoais escritos de jeitos variados**: `(61) 9 9876-5432`, `+55 61 98765-4321`, `61987654321`, CPF sem pontos, CEP sem hífen, e-mail com `+`. Todos mascarados. Teste na Task 1.
- **Conversa de currículo sem currículo guardado**: 409 com código `sem_curriculo`, e a pergunta não é gravada. Teste na Task 6.

---

### Task 1: Domínio do currículo e máscara obrigatória

**Files:**
- Create: `artemis_backend/domain/curriculo.py`
- Test: `tests/test_curriculo_dominio.py`

**Interfaces:**
- Produces:
  - `TipoDeArquivo = Literal["pdf", "jpeg", "png"]`, `Origem = Literal["pdf_texto", "pdf_escaneado", "foto"]`, `Categoria = Literal["email", "telefone", "cpf", "cep", "nome", "endereco"]`
  - `TAMANHO_MAXIMO = 10 * 1024 * 1024`, `TEXTO_MAXIMO = 30_000`, `RETIRAR_MAXIMO = 20`, `OBJETIVO_MAXIMO = 300`, `NOME_COMPETENCIA_MAXIMO = 100`, `EVIDENCIA_MAXIMA = 500`
  - `class ArquivoRecusado(ValueError)` com atributo `motivo: Literal["tipo", "tamanho"]`
  - `class TextoInvalido(ValueError)`
  - `def tipo_do_arquivo(inicio: bytes) -> TipoDeArquivo` (levanta `ArquivoRecusado("tipo")`)
  - `def mascarar(texto: str, retirar: Sequence[str]) -> str` (levanta `TextoInvalido`)
  - `@dataclass(frozen=True) TrechoPessoal(categoria: Categoria, texto: str)`
  - `@dataclass(frozen=True) LeituraDeCurriculo(texto: str, origem: Origem, modelo: str, trechos: tuple[TrechoPessoal, ...])`
  - `@dataclass(frozen=True) Curriculo(texto: str, origem: Origem, modelo: str, atualizado_em: datetime)`
  - `@dataclass(frozen=True) Competencia(id: uuid.UUID, nome: str, evidencia: str, confirmada_em: datetime)`
  - `@dataclass(frozen=True) CompetenciaSugerida(nome: str, evidencia: str)`
  - `@dataclass(frozen=True) ContextoDeCurriculo(texto: str, objetivo: str | None)`
  - `class CurriculoInexistente(Exception)`, `class CompetenciaInexistente(Exception)`

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from artemis_backend.domain.curriculo import ArquivoRecusado, TextoInvalido, mascarar, tipo_do_arquivo

@pytest.mark.parametrize("inicio,tipo", [
    (b"%PDF-1.7\n", "pdf"), (b"\xff\xd8\xff\xe0", "jpeg"), (b"\x89PNG\r\n\x1a\n", "png"),
])
def test_tipo_pelo_conteudo(inicio, tipo):
    assert tipo_do_arquivo(inicio) == tipo

@pytest.mark.parametrize("inicio", [b"PK\x03\x04", b"GIF89a", b"", b"%PD"])
def test_tipo_desconhecido_e_recusado(inicio):
    with pytest.raises(ArquivoRecusado) as erro:
        tipo_do_arquivo(inicio)
    assert erro.value.motivo == "tipo"

@pytest.mark.parametrize("pessoal,substituto", [
    ("ana.souza+cv@exemplo.com.br", "[e-mail]"),
    ("(61) 9 9876-5432", "[telefone]"), ("+55 61 98765-4321", "[telefone]"),
    ("61987654321", "[telefone]"), ("(61) 3333-4444", "[telefone]"),
    ("123.456.789-09", "[CPF]"), ("12345678909", "[CPF]"),
    ("70040-010", "[CEP]"), ("70040010", "[CEP]"),
])
def test_mascara_obrigatoria(pessoal, substituto):
    assert mascarar(f"Contato: {pessoal} fim", []) == f"Contato: {substituto} fim"

def test_retirar_e_escolha_da_usuaria():
    texto = "Ana Souza\nSQN 210 Bloco B\nPython, SQL"
    assert mascarar(texto, ["Ana Souza", "SQN 210 Bloco B"]) == "[retirado]\n[retirado]\nPython, SQL"

def test_sem_retirar_nome_fica():
    assert mascarar("Ana Souza\nPython", []) == "Ana Souza\nPython"

@pytest.mark.parametrize("texto", ["", "   \n", "a\x00b", "x" * 30_001])
def test_texto_invalido(texto):
    with pytest.raises(TextoInvalido):
        mascarar(texto, [])

def test_retirar_demais_e_invalido():
    with pytest.raises(TextoInvalido):
        mascarar("texto", ["a"] * 21)

def test_anos_e_datas_nao_viram_telefone_nem_cep():
    texto = "Estágio 2021-2023, nota 9,5, 40 h semanais"
    assert mascarar(texto, []) == texto
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_curriculo_dominio.py -q`
Expected: FAIL com `ModuleNotFoundError: artemis_backend.domain.curriculo`

- [ ] **Step 3: Implement `artemis_backend/domain/curriculo.py`**

Ordem da máscara: e-mail, CPF, telefone, CEP (CPF antes do telefone, porque 11 dígitos casam com os dois), depois cada trecho de `retirar` (vazio é ignorado). Expressões de partida, ajuste até os testes passarem:

```python
_EMAIL = re.compile(r"[^\s@<>()]+@[^\s@<>()]+\.[^\s@<>().,;]+")
_CPF = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_TELEFONE = re.compile(r"(?<!\d)(?:\+?55\s?)?\(?\d{2}\)?\s?(?:9\s?)?\d{4}[-\s]?\d{4}(?!\d)")
_CEP = re.compile(r"(?<!\d)\d{5}-?\d{3}(?!\d)")
```

Valide o texto (vazio, NUL, tamanho) antes de mascarar, e o tamanho de novo depois de mascarar.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_curriculo_dominio.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add artemis_backend/domain/curriculo.py tests/test_curriculo_dominio.py
git commit -m "feat: domínio do currículo com máscara obrigatória de dados pessoais"
```

---

### Task 2: Contrato e cliente do leitor

**Files:**
- Create: `contratos/leitor.v1.schema.json`, `artemis_backend/adapters/leitor_http.py`, `tests/apoio/leitor.py`
- Modify: `artemis_backend/application/portas.py`, `artemis_backend/config.py`, `.env.example`, `tests/conftest.py`
- Test: `tests/test_leitor_http.py`, `tests/test_env_example.py` (já existe; passa a cobrir as variáveis novas)

**Interfaces:**
- Consumes: `TipoDeArquivo`, `LeituraDeCurriculo`, `TrechoPessoal` (Task 1)
- Produces:
  - em `portas.py`: `class LeitorIndisponivel(Exception)`; `class Leitor(Protocol): async def ler(self, conteudo: bytes, tipo: TipoDeArquivo) -> LeituraDeCurriculo` (levanta `LeitorIndisponivel` e `ArquivoRecusado("tipo")` quando o leitor responde 422)
  - `class LeitorHttp` com `__init__(self, url: str, token: str, timeout: float = 90.0)`, `async ler(...)`, `async fechar() -> None`
  - `Config` ganha `leitor_url: str` e `leitor_token: str = field(repr=False)`, lidas de `ARTEMIS_LEITOR_URL` e `ARTEMIS_LEITOR_TOKEN` (obrigatórias, como as dos agents)
  - `tests/apoio/leitor.py`: `class LeitorFake` com `chamadas: list[tuple[bytes, str]]`, `leitura: LeituraDeCurriculo`, `erro: Exception | None`; fixture `leitor` no `conftest.py`; `criar_app(config, agentes=None, leitor=None)`

**Contrato HTTP do leitor** (`contratos/leitor.v1.schema.json`, `$defs/leitura`):
- Pedido: `POST {leitor_url}/v1/ler`, corpo = bytes do arquivo, `Content-Type` = `application/pdf` | `image/jpeg` | `image/png`, `Authorization: Bearer <token>`.
- Resposta 200: `{"texto": str (1 a 30 000), "origem": "pdf_texto"|"pdf_escaneado"|"foto", "modelo": str (até 100), "trechos": [{"categoria": Categoria, "texto": str (até 300)}] (até 50)}`, sem campos extras.
- Resposta 422: arquivo ilegível (páginas demais, imagem grande demais, PDF corrompido).

- [ ] **Step 1: Write the failing tests** em `tests/test_leitor_http.py`, com `httpx.MockTransport`:
  - `test_envia_bytes_tipo_e_token`: o pedido chega em `/v1/ler` com o corpo igual aos bytes, `Content-Type: image/jpeg` e `Authorization: Bearer token-leitor`.
  - `test_resposta_valida_vira_leitura`: devolve `LeituraDeCurriculo` com `trechos` como tupla de `TrechoPessoal`.
  - `test_resposta_fora_do_contrato_e_indisponivel`: campo extra, origem desconhecida ou texto vazio levantam `LeitorIndisponivel`.
  - `test_erro_de_rede_e_5xx_sao_indisponivel`.
  - `test_422_vira_arquivo_recusado`.
  - `test_estoura_o_tempo_total`: um transporte que dorme além do limite (use `timeout=0.05`) levanta `LeitorIndisponivel`.
  - `test_nao_registra_corpo`: com `caplog`, nenhum registro contém os bytes nem o texto lido.
  - Um teste de contrato que valida respostas de exemplo contra `contratos/leitor.v1.schema.json`, com `tests/apoio/contrato.py` (o mesmo `validador` usado para o `responder`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_leitor_http.py tests/test_env_example.py -q`
Expected: FAIL (módulo e variáveis inexistentes)

- [ ] **Step 3: Implement** `LeitorHttp` copiando o padrão de `agentes_http.py`: modelos Pydantic estritos com `extra="forbid"` que espelham o JSON Schema, `asyncio.timeout(self._timeout)` no total e nenhum log do corpo. Acrescente as variáveis no `Config`, no `_VARIAVEIS` e no `.env.example`, com comentário no mesmo estilo dos agents.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_leitor_http.py tests/test_env_example.py tests/test_config_da_sessao.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add contratos/leitor.v1.schema.json artemis_backend/adapters/leitor_http.py artemis_backend/application/portas.py artemis_backend/config.py .env.example tests/apoio/leitor.py tests/conftest.py tests/test_leitor_http.py
git commit -m "feat: contrato e cliente HTTP do leitor de currículo"
```

---

### Task 3: Tabelas e repositório do currículo

**Files:**
- Create: `migrations/versions/0005_curriculo.py`, `artemis_backend/adapters/repositorio_curriculos.py`
- Modify: `artemis_backend/adapters/tabelas.py`, `artemis_backend/application/portas.py`
- Test: `tests/test_repositorio_curriculos.py`, `tests/test_migracoes.py` (já existe; cobre a 0005)

**Interfaces:**
- Consumes: `Curriculo`, `Competencia`, `Origem` (Task 1)
- Produces:
  - tabelas `curriculos` (`usuaria_id` PK e FK em cascata, `texto`, `origem`, `modelo`, `atualizado_em`), `objetivos` (`usuaria_id` PK e FK em cascata, `texto`, `atualizado_em`), `competencias` (`id` UUID PK, `usuaria_id` FK em cascata e indexado, `nome`, `evidencia`, `confirmada_em`, único em `(usuaria_id, lower(nome))`)
  - `conversas.tipo` texto não nulo, padrão `'comum'`, com `CHECK (tipo IN ('comum','curriculo'))`
  - `mensagens.competencias` JSONB nulo (sugestões que vieram na resposta)
  - `class RepositorioCurriculos(Protocol)` em `portas.py`, implementado por `RepositorioCurriculosSql(sessoes)`:
    - `async obter(usuaria_id: uuid.UUID) -> Curriculo | None`
    - `async salvar(usuaria_id: uuid.UUID, texto: str, origem: Origem, modelo: str) -> Curriculo` (substitui o anterior)
    - `async apagar(usuaria_id: uuid.UUID) -> bool`
    - `async obter_objetivo(usuaria_id: uuid.UUID) -> str | None`
    - `async salvar_objetivo(usuaria_id: uuid.UUID, texto: str) -> str`
    - `async listar_competencias(usuaria_id: uuid.UUID) -> list[Competencia]` (mais antiga primeiro)
    - `async confirmar_competencia(usuaria_id: uuid.UUID, nome: str, evidencia: str) -> Competencia` (o mesmo nome, sem diferença de maiúsculas, devolve a existente e atualiza a evidência)
    - `async descartar_competencia(usuaria_id: uuid.UUID, competencia_id: uuid.UUID) -> bool`

- [ ] **Step 1: Write the failing tests** (Postgres real, fixtures `banco` e `sessao`):
  - `test_salvar_substitui_o_anterior`: dois `salvar` deixam uma linha só, com o texto novo.
  - `test_outra_usuaria_nao_ve`: `obter`, `apagar`, `listar_competencias` e `descartar_competencia` com o id da BIA não enxergam nada da ANA.
  - `test_confirmar_mesmo_nome_nao_duplica`: `"Python"` e depois `"python"` produzem uma competência só.
  - `test_excluir_conta_apaga_tudo`: apagar a linha de `usuarias` zera `curriculos`, `objetivos` e `competencias` dela (use `tests/apoio/banco.contar`).
  - Em `test_migracoes.py`: a 0005 sobe e desce, e as conversas existentes ficam com `tipo = 'comum'`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_repositorio_curriculos.py tests/test_migracoes.py -q`
Expected: FAIL

- [ ] **Step 3: Implement** a migração 0005, os modelos em `tabelas.py` e o repositório, no padrão de `repositorio_conversas.py` (toda consulta filtra por `usuaria_id`; `salvar` com `INSERT ... ON CONFLICT (usuaria_id) DO UPDATE`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_repositorio_curriculos.py tests/test_migracoes.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/0005_curriculo.py artemis_backend/adapters/tabelas.py artemis_backend/adapters/repositorio_curriculos.py artemis_backend/application/portas.py tests/test_repositorio_curriculos.py tests/test_migracoes.py
git commit -m "feat: tabelas de currículo, objetivo e competências confirmadas"
```

---

### Task 4: Rotas de envio, conferência e "Meu currículo"

**Files:**
- Create: `artemis_backend/application/curriculos.py`, `artemis_backend/adapters/rotas_curriculo.py`, `artemis_backend/adapters/esquemas_curriculo.py`
- Modify: `artemis_backend/main.py`, `artemis_backend/domain/usuaria.py` (texto do consentimento), `pyproject.toml` e `uv.lock` (`uv add python-multipart`)
- Test: `tests/test_curriculo_envio.py`, `tests/test_curriculo_guarda.py`, `tests/test_conta.py` (consentimento)

**Interfaces:**
- Consumes: `Leitor`, `LeitorIndisponivel` (Task 2); `RepositorioCurriculos` (Task 3); `tipo_do_arquivo`, `mascarar`, `ArquivoRecusado`, `TextoInvalido` (Task 1)
- Produces:
  - `class ServicoCurriculos(repositorio: RepositorioCurriculos, leitor: Leitor)` com `ler(conteudo: bytes) -> LeituraDeCurriculo`, `salvar(usuaria_id, texto: str, origem: Origem, modelo: str, retirar: list[str]) -> Curriculo`, `obter(usuaria_id) -> Curriculo` (levanta `CurriculoInexistente`), `apagar(usuaria_id) -> None` (levanta `CurriculoInexistente`), `contexto(usuaria_id) -> ContextoDeCurriculo | None`; em `app.state.curriculos`
  - Rotas (tag `curriculo`):
    - `POST /v1/curriculo/leitura`: multipart, campo `arquivo` → 200 `LeituraSaida {texto, origem, modelo, trechos: [{categoria, texto}]}`; 413 tamanho; 415 tipo ou ilegível; 503 leitor; nada é gravado
    - `PUT /v1/curriculo`: `PedidoCurriculo {texto, origem, modelo, retirar: list[str]}` → 200 `CurriculoSaida {texto, origem, modelo, atualizado_em}`; 422 texto inválido
    - `GET /v1/curriculo` → 200 `CurriculoSaida` ou 404
    - `DELETE /v1/curriculo` → 204 ou 404
  - `CONSENTIMENTO` ganha uma frase sobre o currículo: "Se você enviar um currículo, guardamos só o texto que você conferir, sem e-mail, telefone, CPF e CEP; o arquivo é descartado na hora. Esse texto vai ao Google Gemini e ao Langfuse quando você conversa sobre o currículo."

- [ ] **Step 1: Write the failing tests**
  - `test_le_pdf_e_devolve_texto_sem_gravar`: o `LeitorFake` recebe os bytes; a resposta traz texto e trechos; `contar(sessao, Curriculo) == 0`.
  - `test_extensao_mentirosa_e_415`: `nome="cv.pdf"` e `Content-Type: application/pdf` com conteúdo `PK\x03\x04...` → 415; o leitor não é chamado.
  - `test_arquivo_grande_e_413_sem_ler_tudo`: um corpo de 10 MB + 1 byte → 413; o leitor não é chamado. (Leia o `UploadFile` em blocos de 64 KiB e pare ao passar de `TAMANHO_MAXIMO`.)
  - `test_leitor_fora_e_503_sem_gravar` e `test_leitor_422_e_415`.
  - `test_salvar_mascara_sempre`: `PUT` com e-mail, telefone, CPF e CEP no texto e `retirar=[]` → o texto guardado só tem os substitutos.
  - `test_salvar_retira_o_que_ela_escolheu`: `retirar=["Ana Souza"]` some do texto guardado.
  - `test_ver_e_apagar`: `GET` → 200; `DELETE` → 204; `GET` → 404; `DELETE` → 404.
  - `test_bia_nao_ve_curriculo_da_ana`.
  - `test_rotas_exigem_sessao_e_origem`: acrescente as quatro rotas em `tests/apoio/sessao.rotas_protegidas`, para os testes de sessão existentes cobrirem 401 e 403 de `Origin`.
  - `test_log_sem_texto_do_curriculo`: com `caplog`, nem o texto nem o nome aparecem nos registros de nenhuma das rotas.
  - Atualize `TEXTO_DO_CONSENTIMENTO` em `tests/test_conta.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_curriculo_envio.py tests/test_curriculo_guarda.py tests/test_conta.py -q`
Expected: FAIL

- [ ] **Step 3: Implement** serviço, esquemas e rotas no padrão de `rotas_conta.py` (`Usuaria`, `erros(...)`, exceções de domínio convertidas para HTTP na rota) e registre o roteador em `criar_app`. `criar_app` cria e fecha o `LeitorHttp` como faz com `AgentesHttp`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: PASS (suite inteira, com Docker ligado)

- [ ] **Step 5: Commit**

```bash
git add artemis_backend tests pyproject.toml uv.lock
git commit -m "feat: envio, conferência e guarda do currículo"
```

---

### Task 5: Objetivo e competências confirmadas

**Files:**
- Modify: `artemis_backend/application/curriculos.py`, `artemis_backend/adapters/rotas_curriculo.py`, `artemis_backend/adapters/esquemas_curriculo.py`
- Test: `tests/test_objetivo_e_competencias.py`

**Interfaces:**
- Consumes: `RepositorioCurriculos` (Task 3), `ServicoCurriculos` (Task 4)
- Produces:
  - `ServicoCurriculos.salvar_objetivo(usuaria_id, texto) -> str`, `obter_objetivo(usuaria_id) -> str | None`, `listar_competencias(usuaria_id) -> list[Competencia]`, `confirmar_competencia(usuaria_id, nome, evidencia) -> Competencia`, `descartar_competencia(usuaria_id, competencia_id) -> None` (levanta `CompetenciaInexistente`)
  - `PUT /v1/objetivo {objetivo}` → 200 `{objetivo}`; `GET /v1/objetivo` → 200 `{objetivo: str | null}`
  - `GET /v1/competencias` → 200 `[{id, nome, evidencia, confirmada_em}]`; `POST /v1/competencias {nome, evidencia}` → 201; `DELETE /v1/competencias/{id}` → 204 ou 404
  - Nome e evidência passam pela mesma máscara obrigatória antes de guardar.

- [ ] **Step 1: Write the failing tests**: objetivo vazio ou com mais de 300 caracteres → 422; sem objetivo, `GET` devolve `null`; confirmar duas vezes o mesmo nome → uma competência; evidência com e-mail é guardada mascarada; a BIA não lista nem apaga competência da ANA; as rotas novas entram em `rotas_protegidas`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_objetivo_e_competencias.py -q`
Expected: FAIL

- [ ] **Step 3: Implement** serviço e rotas no mesmo padrão da Task 4.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_objetivo_e_competencias.py tests/test_sessao_cookie.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add artemis_backend tests
git commit -m "feat: objetivo profissional e competências confirmadas"
```

---

### Task 6: Conversa sobre o currículo e contrato com os agents

**Files:**
- Modify: `contratos/responder.v1.schema.json`, `artemis_backend/adapters/agentes_http.py`, `artemis_backend/application/portas.py`, `artemis_backend/application/perguntar.py`, `artemis_backend/application/conversas.py`, `artemis_backend/domain/conversa.py`, `artemis_backend/adapters/rotas_conversas.py`, `artemis_backend/adapters/rotas_perguntas.py`, `artemis_backend/adapters/esquemas_conversas.py`, `artemis_backend/adapters/repositorio_conversas.py`, `artemis_backend/adapters/repositorio_perguntas.py`, `ferramentas/agentes_simulados/` (pedido e resposta), `tests/apoio/agentes.py`
- Test: `tests/test_conversa_curriculo.py`, `tests/test_agentes_http.py`, `tests/test_agentes_simulados.py`

**Interfaces:**
- Consumes: `ServicoCurriculos.contexto` (Task 4), `ContextoDeCurriculo`, `CompetenciaSugerida` (Task 1)
- Produces:
  - Contrato `responder v1`, mudança compatível: pedido ganha `curriculo` opcional, `{"texto": texto (1 a 30 000), "objetivo": texto (até 300) | null} | null`; resposta ganha `competencias` opcional, `[{"nome": até 100, "evidencia": até 500}]` (até 20), com padrão `[]`. A descrição do schema registra a mudança e cita a agents#36.
  - `Agentes.responder(pergunta, sessao, historico, lembranca, curriculo: ContextoDeCurriculo | None = None) -> RespostaAgentes`
  - `RespostaAgentes.competencias: tuple[CompetenciaSugerida, ...] = ()`
  - `Conversa.tipo: Literal["comum", "curriculo"]`; `POST /v1/conversas` aceita corpo opcional `{"tipo": "comum"|"curriculo"}` (sem corpo vale `comum`); as saídas de conversa trazem `tipo`
  - Mensagem da Artemis traz `competencias: [{nome, evidencia}]`, gravadas em `mensagens.competencias`
  - `Motivo` do 409 ganha `"sem_curriculo"`

- [ ] **Step 1: Write the failing tests**
  - `test_conversa_comum_nunca_manda_curriculo`: com currículo e objetivo guardados, uma pergunta numa conversa `comum` chega ao `AgentesFake` com `curriculo=None`.
  - `test_conversa_de_curriculo_manda_texto_mascarado_e_objetivo`.
  - `test_conversa_de_curriculo_sem_curriculo_e_409`: `codigo == "sem_curriculo"`, e nenhuma mensagem é gravada.
  - `test_trocar_curriculo_vale_para_a_proxima_pergunta`: depois de um `PUT` novo, a próxima pergunta leva o texto novo.
  - `test_competencias_sugeridas_ficam_na_mensagem`: aparecem no `GET` da conversa.
  - Em `test_agentes_http.py`: o pedido sem currículo continua sem a chave `curriculo` (compatível com agents antigos); resposta sem `competencias` vira `()`; resposta com mais de 20 competências → `AgentesIndisponiveis`.
  - O pedido e a resposta de exemplo validam contra o schema atualizado.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_conversa_curriculo.py tests/test_agentes_http.py tests/test_agentes_simulados.py -q`
Expected: FAIL

- [ ] **Step 3: Implement**: `ServicoPerguntas` recebe `ServicoCurriculos` (ou uma porta só de leitura do contexto) e só busca o contexto quando `iniciada` vem de conversa `curriculo`. Confira a existência do currículo **antes** de gravar a pergunta, para o 409 não deixar pergunta órfã. Atualize o simulador de agents para aceitar os campos novos.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add contratos artemis_backend ferramentas tests
git commit -m "feat: conversa sobre o currículo e competências no contrato com os agents"
```

---

### Task 7: OpenAPI, README, AGENTS.md e site

**Files:**
- Modify: `contratos/openapi.json` (gerado por `uv run python -m ferramentas.exportar_openapi`), `README.md`, `AGENTS.md`
- Test: `tests/test_openapi.py` (já confere se o `openapi.json` está atualizado)

- [ ] **Step 1: Run** `uv run python -m ferramentas.exportar_openapi` and `uv run pytest tests/test_openapi.py -q`. Expected: PASS
- [ ] **Step 2: Update** o README (rotas novas, variáveis `ARTEMIS_LEITOR_URL` e `ARTEMIS_LEITOR_TOKEN`, que o arquivo nunca é gravado) e o `AGENTS.md` (máscara obrigatória no domínio; o leitor fica atrás de uma porta).
- [ ] **Step 3: Run** `uv run pytest -q` e `uv run ruff check`. Expected: PASS
- [ ] **Step 4: Commit**

```bash
git add contratos/openapi.json README.md AGENTS.md
git commit -m "docs: rotas do currículo, leitor e máscara obrigatória"
```

- [ ] **Step 5:** Abra um PR no `artemishub_docs` atualizando `docs/arquitetura/backend.md` (rotas, privacidade do currículo) e cite os dois PRs um no outro.

---

## Dependências fora deste repositório

- **Leitor** (`artemishub_agents`, plano `docs/superpowers/plans/2026-11-26-leitor-de-curriculo.md`): implementa `contratos/leitor.v1.schema.json`. A primeira tarefa é o teste comparativo, em que a Ana Julia escolhe o modelo. O backend não espera: os testes usam o `LeitorFake`.
- **Agents** (agents#36): passam a aceitar `curriculo` e a devolver `competencias`, tratando o currículo como dado não confiável (agents#21).
- **Frontend** (frontend#2): telas de envio, conferência, "Meu currículo", objetivo e confirmação de competências. Plano próprio depois do push do MVP.
- **Docs**: ADR do modelo de leitura; consentimento do currículo no ADR de LGPD; RF-03 do PDR passa a incluir foto.
