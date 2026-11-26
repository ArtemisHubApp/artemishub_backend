"""Regras do nome da usuária, no domínio."""

import pytest

from artemis_backend.domain.usuaria import NOME_MAXIMO, NomeInvalido, normalizar_nome


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("Ana", "Ana"),
        ("  Ana Souza  ", "Ana Souza"),
        ("Ana    Maria   Souza", "Ana Maria Souza"),
        ("Ana Souza", "Ana Souza"),
        ("José da Conceição", "José da Conceição"),
        ("Zoë Ñandú", "Zoë Ñandú"),
        ("李小龙", "李小龙"),
        ("a" * NOME_MAXIMO, "a" * NOME_MAXIMO),
        ("Ana 🌸", "Ana 🌸"),
        ("Zoë", "Zoë"),
        ("👩\u200d🔬", "👩\u200d🔬"),
        ("Jose\u0301", "José"),
        ("a\u200cb", "a\u200cb"),
        ("e\u0301" * NOME_MAXIMO, "é" * NOME_MAXIMO),
        ("a" * 20 + "   " + "b" * 19, "a" * 20 + " " + "b" * 19),
    ],
)
def test_nome_valido_e_normalizado(entrada, esperado):
    assert normalizar_nome(entrada) == esperado


@pytest.mark.parametrize(
    "entrada",
    ["", "   ", " ", "a" * (NOME_MAXIMO + 1), "Ana\x00", "Ana\x07", "Ana\nSouza", "Ana\tSouza"]
    + ["Ana\x7f", "Ana\x85Souza", "Ana\ud800", "\ud83d"]
    # Invisíveis (Cf, preenchimentos) e nomes sem letra, número ou símbolo.
    + ["Ana\u200b", "Ana\u200e", "Ana\u200f", "Ana\u202a", "Ana\u202e", "Ana\u2066"]
    + ["Ana\u2069", "\ufeffAna", "\u2800", "Ana\u3164", "\u3164", "\u0301", "\u0301\u0302"]
    + ["\u200d", "\u200c", "-", "...", "\u2800\u3164"],
)
def test_nome_invalido_e_recusado_sem_eco(entrada):
    with pytest.raises(NomeInvalido) as erro:
        normalizar_nome(entrada)
    assert str(erro.value) == "Nome inválido"
