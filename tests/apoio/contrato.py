import json

import jsonschema

from tests.apoio.valores import RAIZ

CONTRATO = json.loads((RAIZ / "contratos" / "responder.v1.schema.json").read_text("utf-8"))


def validador(nome: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(
        {"$ref": f"#/$defs/{nome}", "$defs": CONTRATO["$defs"]},
    )
