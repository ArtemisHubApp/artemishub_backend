"""Validação do pedido, igual a `pedido` em contratos/responder.v1.schema.json."""

from typing import Any

_PERGUNTA_MAXIMA = 1000
_TROCAS_MAXIMAS = 3
_CAMPOS = {"pergunta", "sessao", "historico", "lembranca"}
_CAMPOS_DA_TROCA = {"pergunta", "resposta"}
_BOOLEANOS_DA_LEMBRANCA = ("salario", "direitos")
_TEXTOS_DA_LEMBRANCA = {"cbo_familia": 20, "cbo_familia_nome": 200, "ocupacao": 200, "uf": 2}


def pedido_valido(valor: Any) -> bool:
    return (
        _tem_so(valor, _CAMPOS)
        and _texto(valor["pergunta"], minimo=1, maximo=_PERGUNTA_MAXIMA)
        and _texto(valor["sessao"], minimo=1)
        and isinstance(valor["historico"], list)
        and len(valor["historico"]) <= _TROCAS_MAXIMAS
        and all(_troca(troca) for troca in valor["historico"])
        and (valor["lembranca"] is None or _lembranca(valor["lembranca"]))
    )


def _tem_so(valor: Any, campos: set[str]) -> bool:
    return isinstance(valor, dict) and set(valor) == campos


def _texto(valor: Any, minimo: int = 0, maximo: int | None = None) -> bool:
    return (
        isinstance(valor, str)
        and len(valor) >= minimo
        and (maximo is None or len(valor) <= maximo)
        and not any(c == "\x00" or "\ud800" <= c <= "\udfff" for c in valor)
    )


def _troca(valor: Any) -> bool:
    return _tem_so(valor, _CAMPOS_DA_TROCA) and all(_texto(texto) for texto in valor.values())


def _lembranca(valor: Any) -> bool:
    return (
        _tem_so(valor, {*_BOOLEANOS_DA_LEMBRANCA, *_TEXTOS_DA_LEMBRANCA})
        and all(isinstance(valor[campo], bool) for campo in _BOOLEANOS_DA_LEMBRANCA)
        and all(
            valor[campo] is None or _texto(valor[campo], maximo=maximo)
            for campo, maximo in _TEXTOS_DA_LEMBRANCA.items()
        )
    )
