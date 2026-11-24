# Design: backend com histórico de conversas e memória curta da Artemis

**Issue:** ArtemisHubApp/artemishub_backend#13. Relacionadas: #2 (scaffold), #3 (login e LGPD), #5 (integração com os agentes), ArtemisHubApp/artemishub_agents#36 (orquestrador como API) e ArtemisHubApp/artemishub_docs#3 (ADR-001, a stack).
**Data:** 19/11/2026. Conversa de desenho com a Amanda.

## Por que

A usuária precisa ter acesso ao histórico das mensagens que trocou com a Artemis, na aba **Oráculo**. "Artemis" é o nome do agente; "Oráculo" é só o nome da aba. Também precisa que a Artemis tenha o **mínimo de memória curta** dentro de uma conversa ("e se eu tiver 5 anos de experiência?"), com **proteções para ela não ser contaminada pelo histórico**. Hoje a memória vive só no processo do chat do terminal e some quando ele fecha.

## Objetivos

1. **Conversas guardadas no Postgres:** cada usuária vê a lista das suas conversas, abre uma e vê as mensagens como foram respondidas (com fontes e limites dos dados), continua a conversa, apaga uma ou todas.
2. **Memória curta da Artemis:** as 3 últimas trocas da mesma conversa, mais a lembrança estruturada (intenção, ocupação e UF) que já existe.
3. **Proteções contra contaminação** (seção própria abaixo).
4. **Login básico:** uma usuária nunca vê o que é de outra (RNF-06).
5. **LGPD:** finalidade declarada e exclusão. Excluir a conta apaga tudo no Postgres; os traces no Langfuse permanecem, e o consentimento avisa (RNF-07 e RNF-16).

## Fora do escopo desta fatia

- Perfil profissional, upload de currículo, oportunidades e plano (o resto da #3 e a #4).
- Frontend: a fatia entrega a API e um contrato OpenAPI que o frontend usa depois.
- Streaming (SSE): a resposta volta inteira. O streaming entra com o frontend.
- Deploy na nuvem (#6); aqui é só o docker-compose local.
- Recuperação de senha por e-mail.

## Anti-objetivos (falha mesmo funcionando)

- O texto antigo de uma conversa mudar números ou fontes de uma resposta nova.
- Memória **entre** conversas: o Artemis "lembrar" de uma conversa em outra.
- E-mail ou outro identificador da usuária chegar ao Langfuse ou ao LLM, ou o texto de uma conversa ser usado em outra. (O texto da pergunta, inclusive um salário escrito nela, vai para o LLM e para o trace no Langfuse: decisão da Amanda em 24/11, sem máscara.)
- Uma usuária conseguir ler ou apagar conversa de outra.

## Abordagens consideradas

| Abordagem | Troca | Decisão |
|---|---|---|
| **1. FastAPI + Postgres no backend; agentes como serviço separado, sem banco** | Dois serviços e um contrato de API; em troca, dados pessoais num só lugar, o backend sem PyTorch, issues como já divididas | **Escolhida pela Amanda** |
| 2. Backend importa os agentes como biblioteca | Um serviço só; backend herda LangGraph, RAG e PyTorch, mistura banco e IA, conflita com a #36 | Descartada |
| 3. Supabase (Postgres e login gerenciados) + FastAPI fino | Login pronto e políticas por linha; dado pessoal em terceiro, menos controle, ferramenta nova | Descartada |

## Arquitetura

```
frontend (depois) ──HTTP+JWT──► artemishub_backend (FastAPI)
                                   │  usuárias, conversas, mensagens (Postgres)
                                   │  monta a memória curta e a lembrança
                                   ▼
                          artemishub_agents (FastAPI, sem banco)
                                   │  grafo LangGraph (Orquestrador, Pesquisa, Análise, Validação)
                                   ├─► artemishub_rag (busca com citações)
                                   ├─► RAIS (agregados)
                                   └─► LLM (Gemini) · Langfuse (traces, prompts)
```

- **Backend** (`artemishub_backend`): Python 3.12, FastAPI, SQLAlchemy 2 (ORM, async) com Alembic para migrações, Postgres 16, `uv`, camadas hexagonais (`domain`, `application`, `adapters`), como no agents. É dono de toda informação pessoal.
- **Agentes** (`artemishub_agents`): um app FastAPI fino na frente do grafo (`POST /v1/responder`), sem banco. A porta `MemoriaDaConversa` ganha um adaptador "em requisição": a memória chega pronta no corpo do pedido.
- **Postgres e os dois serviços** sobem no docker-compose do orquestrador (`--profile app`, que hoje imprime "sem scaffold").

## Dados (Postgres)

| Tabela | Campos principais | Observações |
|---|---|---|
| `usuarias` | id (uuid), email (único), senha_hash (argon2), criada_em, consentiu_em | Consentimento registrado no cadastro: "guardar minhas conversas para eu consultar depois" |
| `conversas` | id, usuaria_id, titulo, criada_em, atualizada_em, lembranca (jsonb: salario, direitos, cbo_familia, cbo_familia_nome, ocupacao, uf) | Título = começo da primeira pergunta (60 caracteres); a lembrança substitui a `MemoriaEmProcesso` |
| `mensagens` | id, conversa_id, papel (usuaria/artemis), texto, criada_em, aprovada (bool), bloqueada (bool), trace_id | `texto` da Artemis = resposta final formatada (com Limites e Fontes) |

- Exclusão: apagar uma conversa apaga as mensagens (cascade). Apagar a conta apaga tudo (cascade). Não há "lixeira": apagar é definitivo.
- Retenção: até a usuária apagar ou excluir a conta. O prazo automático fica como decisão em aberto para o ADR de LGPD.

## API do backend (primeira fatia)

| Método e rota | O que faz |
|---|---|
| `POST /v1/auth/cadastro` | email, senha, `consentimento=true` obrigatório → cria a usuária |
| `POST /v1/auth/login` | devolve JWT de acesso (curto, 60 min) |
| `GET /v1/conversas` | lista da usuária, mais recentes primeiro |
| `POST /v1/conversas` | cria conversa vazia |
| `GET /v1/conversas/{id}` | mensagens da conversa |
| `POST /v1/conversas/{id}/mensagens` | grava a pergunta, chama os agentes, grava e devolve a resposta |
| `DELETE /v1/conversas/{id}` | apaga a conversa |
| `DELETE /v1/conta` | apaga a conta e tudo dela |
| `GET /health` | saúde |

Toda rota com `{id}` confere que a conversa é da usuária do token. Uma conversa de outra usuária responde 404, não 403, para não revelar que ela existe.

## Contrato com os agentes (`POST /v1/responder`)

```json
pedido:   {"pergunta": "...", "sessao": "<id da conversa>",
           "historico": [{"pergunta": "...", "resposta": "..."}],   // até 3, mais antiga primeiro
           "lembranca": {"salario": true, "direitos": false, "cbo_familia": "2124", ...} | null}
resposta: {"resposta": "...", "aprovada": true, "bloqueada": false, "fora_de_escopo": false,
           "lembranca": {...} | null, "trace_id": "...", "passos": ["..."]}
```

O backend é quem guarda a lembrança devolvida e a manda de volta na próxima pergunta; o agents não guarda nada.

## Proteções contra contaminação pelo histórico

1. **Só a mesma conversa e só as 3 últimas trocas.** Nada de outras conversas. A pergunta antiga é cortada em 500 caracteres e a resposta antiga em 800.
2. **Só trocas limpas entram:** as trocas bloqueadas pelo guardrail e as abstenções ficam no histórico da tela, mas **não** entram na memória curta. Uma tentativa de injeção nunca volta ao LLM.
3. **A resposta antiga entra sem fontes nem limites:** as seções "Limites dos dados" e "Fontes" são retiradas, e as citações `[FONTE N]` e `[RAIS]` são removidas do texto. Assim a Artemis não reutiliza ids de evidências de outra rodada.
4. **O histórico é dado, não instrução:** ele entra no prompt numa variável própria (`{{historico}}`) entre delimitadores. O prompt no Langfuse diz que o histórico serve só para entender a pergunta atual e nunca como fonte de números ou de direitos.
5. **Os números continuam presos à rodada atual:** a Validação só aceita valores da RAIS e das evidências **desta** pergunta. Um número que vier do histórico (de uma resposta antiga ou do que a usuária escreveu) reprova a resposta, e a Análise refaz.
6. **O guardrail também lê o histórico:** cada pergunta antiga passa de novo pelo guardrail antes de entrar. Se algo não passar (por exemplo, uma regra nova), a troca sai da memória curta.
7. **Nada de persona:** sexo, raça e origem não são campos de nada. A referência para negociar é a mesma para todas (relatório de vieses).
8. **Teste contrafactual:** o mesmo histórico, trocando só o gênero das palavras da usuária, precisa gerar os mesmos números e a mesma referência. Fica como teste automatizado com LLM simulado e como dataset no Langfuse.

## Como a memória curta muda o comportamento (esclarecido na revisão, proposta a aprovar)

- **Onde entra:** no prompt da Análise (`{{historico}}`) e na decisão de continuação do Orquestrador. Não vira parâmetro: UF, ocupação e salário vêm só da pergunta atual ou da lembrança.
- **Continuação:** hoje "e se eu tiver 5 anos de experiência?" cai em fora de escopo. Com histórico limpo, uma pergunta sem tema próprio que comece como continuação ("e se", "e para", "explica", "por quê", "qual deles") herda a intenção da lembrança. "Qual a capital da França?" continua fora de escopo.
- **Experiência, escolaridade e jornada:** devem ser usadas (pedido da Amanda em 24/11), vindas do currículo ou da conversa. O cálculo é da `estimar_faixa` (artemishub_agents#53 e #54); a leitura do currículo é a artemishub_agents#14 e o perfil, a artemishub_backend#3. Até existirem, a resposta explica que o número ainda não considera a experiência, mostra a faixa do grupo e pode orientar com base no que a usuária contou, sem inventar valor.
- **O que entra na memória curta:** só trocas com `aprovada=true`. Ficam de fora as bloqueadas, as abstenções, as fora de escopo e os erros.
- **Quem limpa:** o backend manda o texto como foi exibido; o agents remove "Limites", "Fontes" e citações e só depois corta (500/800 caracteres). A limpeza fica perto do LLM e testada num lugar só.
- **Salário no histórico:** o texto antigo pode trazer um salário, mas ele não conta como número permitido. Só o salário da pergunta atual pode aparecer na resposta nova.
- **Grafo sem estado:** o grafo é montado uma vez por processo; `historico` e `lembranca` entram no estado de cada pedido, e a lembrança nova sai no estado final. A porta `MemoriaDaConversa` continua só no chat do terminal.
- **Prompt:** o código passa a enviar `historico` antes; a versão do prompt com `{{historico}}` é testada com o label `staging` e só depois recebe `production`.
- **Timeout:** 60 s no backend, sem nova tentativa automática. Uma resposta que chegue depois é descartada, e a trava da conversa (409) é liberada no timeout.
- **Compose:** o serviço agents usa o pacote `artemis_rag` (artemishub_agents#37) e monta o índice como volume somente leitura. O teste ponta a ponta no compose é manual nesta fatia.

## Login e segurança

- Senha com argon2 (`argon2-cffi`). JWT HS256 assinado com `ARTEMIS_JWT_SEGREDO` (no `.env`, nunca no repo), 60 minutos, sem refresh nesta fatia.
- Os agentes ficam na rede interna do compose, sem porta pública. O backend chama com um token de serviço (`ARTEMIS_AGENTS_TOKEN`).
- Logs do backend sem o texto das mensagens. O Langfuse recebe a pergunta, o histórico curto e a resposta (são a entrada e a saída do trace), mas não o e-mail; a sessão no Langfuse é o id da conversa.

## Erros e limites

- Agentes fora do ar ou demorando (timeout de 60 s): a pergunta fica gravada, a resposta vira "Não consegui responder agora, tente de novo", com `aprovada=false`, e não entra na memória curta.
- Pergunta com mais de 1.000 caracteres: 422, igual ao guardrail.
- Concorrência: uma pergunta por conversa por vez. Uma segunda pergunta enquanto a primeira roda recebe 409.

## Testes

- **Backend:** pytest com Postgres de verdade num container (testcontainers ou o serviço do compose no CI). Testes de isolamento entre usuárias, cascade na exclusão, montagem da memória curta (corte, filtros e retirada de citações) e cliente dos agentes falso.
- **Agentes:** os testes do grafo com histórico. O número que vem do histórico é reprovado, a troca bloqueada não entra e o teste contrafactual de gênero.
- **Contrato:** um schema JSON versionado do `/v1/responder`, testado dos dois lados.

## O que fica para quem constrói

- A biblioteca exata de JWT (`pyjwt`) e a organização dos routers.
- O formato do título da conversa além dos 60 caracteres.
- Se o teste do backend usa testcontainers ou o Postgres do compose.

## Decisões em aberto (para o time)

- Prazo de retenção automático das conversas e o texto do consentimento: ADR de LGPD. O consentimento precisa citar o Gemini e o Langfuse, que recebem o texto das perguntas.
- **Exclusão no Langfuse (decidido pela Amanda em 24/11):** excluir a conta apaga tudo no Postgres, mas **não** apaga os traces. O texto do consentimento precisa dizer isso, e o ADR de LGPD precisa justificar a retenção (os traces contêm o texto das perguntas).
- **Divisão com a Eduarda (decidido em 24/11):** o `POST /v1/responder` é dela, na artemishub_agents#36, onde está o rascunho do contrato. O backend usa um cliente falso até o contrato fechar.
