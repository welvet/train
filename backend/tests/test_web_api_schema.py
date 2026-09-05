from __future__ import annotations

import json
from pathlib import Path

from train.domain.vocabulary import PUBLIC_EVENTS
from train.modules.web_api.schema import openapi_document

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_CONTRACT = REPO_ROOT / "web/src/api/generated/openapi.json"


def test_generated_web_contract_is_current() -> None:
    assert json.loads(GENERATED_CONTRACT.read_text()) == openapi_document()


def test_contract_contains_every_public_event() -> None:
    document = openapi_document()
    schemas = document["components"]["schemas"]
    public_event = schemas["PublicEvent"]
    refs = public_event["oneOf"]
    names = {
        schemas[ref["$ref"].rsplit("/", 1)[-1]]["properties"]["type"]["const"]
        for ref in refs
    }

    assert names == {spec.name for spec in PUBLIC_EVENTS}
