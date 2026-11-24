import random
import uuid
from datetime import UTC, datetime, timedelta

from artemis_backend.domain.conversa import Mensagem, Troca, memoria_curta, titulo_da_conversa

INICIO = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)


def pergunta(n: int, minuto: int | None = None) -> Mensagem:
    return Mensagem(
        id=uuid.uuid4(),
        papel="usuaria",
        texto=f"p{n}",
        criada_em=INICIO + timedelta(minutes=n if minuto is None else minuto),
        aprovada=False,
        bloqueada=False,
        trace_id=None,
        pergunta_id=None,
    )


def resposta(
    p: Mensagem,
    texto: str | None = None,
    aprovada: bool = True,
    bloqueada: bool = False,
    segundos: int = 1,
) -> Mensagem:
    return Mensagem(
        id=uuid.uuid4(),
        papel="artemis",
        texto=texto if texto is not None else p.texto.replace("p", "r"),
        criada_em=p.criada_em + timedelta(seconds=segundos),
        aprovada=aprovada,
        bloqueada=bloqueada,
        trace_id="t",
        pergunta_id=p.id,
    )


def trocas(quantas: int) -> list[Mensagem]:
    mensagens = []
    for n in range(1, quantas + 1):
        p = pergunta(n)
        mensagens += [p, resposta(p)]
    return mensagens


def perguntas_da_memoria(mensagens: list[Mensagem]) -> list[str]:
    return [t.pergunta for t in memoria_curta(mensagens)]


def test_memoria_curta_pega_as_3_ultimas_aprovadas_na_ordem():
    assert perguntas_da_memoria(trocas(5)) == ["p3", "p4", "p5"]


def test_memoria_curta_devolve_pergunta_e_resposta_como_exibidas():
    assert memoria_curta(trocas(1)) == [Troca(pergunta="p1", resposta="r1")]


def test_memoria_curta_ignora_nao_aprovadas_e_pergunta_sem_resposta():
    p1, p2, p3, p4 = (pergunta(n) for n in range(1, 5))
    mensagens = [
        p1,
        resposta(p1),
        p2,
        resposta(p2, aprovada=True, bloqueada=True),
        p3,
        resposta(p3, aprovada=False),
        p4,
    ]
    assert perguntas_da_memoria(mensagens) == ["p1"]


def test_memoria_curta_vazia_ou_com_menos_de_3_trocas():
    assert memoria_curta([]) == []
    assert perguntas_da_memoria(trocas(2)) == ["p1", "p2"]


def test_a_ordem_de_entrada_nao_importa():
    mensagens = trocas(5)
    for semente in range(20):
        embaralhadas = random.Random(semente).sample(mensagens, len(mensagens))
        assert perguntas_da_memoria(embaralhadas) == ["p3", "p4", "p5"]


def test_resposta_e_ligada_a_pergunta_pelo_id_e_nao_pela_posicao():
    p1, p2 = pergunta(1), pergunta(2)
    # A resposta de p1 chega depois da pergunta p2 e a de p2 vem antes da de p1.
    r1 = resposta(p1, "r1", segundos=300)
    r2 = resposta(p2, "r2", segundos=10)
    assert memoria_curta([p1, p2, r2, r1]) == [Troca("p1", "r1"), Troca("p2", "r2")]


def test_resposta_de_pergunta_que_nao_esta_na_lista_e_ignorada():
    sozinha = resposta(pergunta(9))
    assert memoria_curta([sozinha, *trocas(1)]) == [Troca("p1", "r1")]


def test_so_uma_resposta_por_pergunta():
    p = pergunta(1)
    assert memoria_curta([p, resposta(p, "r1"), resposta(p, "outra", segundos=5)]) == [
        Troca("p1", "r1")
    ]


def test_empate_de_data_mantem_a_ordem_de_entrada():
    p1, p2 = pergunta(1, minuto=0), pergunta(2, minuto=0)
    mensagens = [p1, resposta(p1), p2, resposta(p2)]
    assert perguntas_da_memoria(mensagens) == ["p1", "p2"]
    assert perguntas_da_memoria(mensagens[2:] + mensagens[:2]) == ["p2", "p1"]


def test_texto_vai_sem_corte_nem_limpeza():
    p = pergunta(1)
    longo = "  linha 1\n\nlinha 2 [FONTE 1]\n\nFontes\n- x  " + "y" * 5000
    troca = memoria_curta([p, resposta(p, longo)])[0]
    assert troca.resposta == longo


def test_titulo_curto_fica_igual():
    assert titulo_da_conversa("curta") == "curta"


def test_titulo_corta_em_60_sem_quebrar_palavra():
    titulo = titulo_da_conversa("palavra " * 20)
    assert len(titulo) <= 60
    assert titulo == ("palavra " * 7).strip()


def test_titulo_com_60_caracteres_exatos_fica_inteiro():
    texto = "a" * 29 + " " + "b" * 30
    assert titulo_da_conversa(texto) == texto


def test_titulo_nao_corta_palavra_que_termina_no_limite():
    texto = "a" * 55 + " " + "b" * 4 + " ccc"
    assert titulo_da_conversa(texto) == "a" * 55 + " " + "b" * 4


def test_titulo_com_uma_palavra_de_100_caracteres_corta_em_60():
    assert titulo_da_conversa("x" * 100) == "x" * 60


def test_titulo_normaliza_espacos_e_quebras_de_linha():
    assert titulo_da_conversa("  Qual\n o\t\tsalário   médio?  ") == "Qual o salário médio?"


def test_titulo_de_texto_so_com_espacos_e_vazio():
    assert titulo_da_conversa(" \n\t ") == ""
