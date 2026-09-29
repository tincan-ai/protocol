"""Optional schema validation, separate from standard-library runtime tests."""
import json
from pathlib import Path
import sys

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reference.server import DESCRIPTOR, Store

discovery = json.loads((ROOT / "schemas/discovery.schema.json").read_text())
core = json.loads((ROOT / "schemas/core.schema.json").read_text())
Draft202012Validator.check_schema(discovery)
Draft202012Validator.check_schema(core)
validator = Draft202012Validator(discovery)
validator.validate(DESCRIPTOR)
validator.validate(json.loads((ROOT / "examples/discovery.json").read_text()))
store = Store(":memory:")
try:
    identity = store.call("POST", "/bootstrap", body={"agent_name": "Schema", "name": "Schema"}, origin="http://127.0.0.1:8787")
    token = identity["token"]
    channel = store.call("GET", "/channels", token)[0]["id"]
    request = {"channel_id": channel, "text": "Example", "idempotency_key": "example"}
    message = store.call("POST", "/messages", token, request)
    event = store.call("GET", "/event-page", token)[0]
    for name, value in (("SendInput", request), ("Message", message), ("Event", event)):
        schema = dict(core, **{"$ref": "#/$defs/" + name})
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(value)
finally:
    store.close()
print("Discovery, request, message and event schemas validated")

# E2EE fixtures cover structural shapes only; Go tests verify crypto semantics.
from copy import deepcopy
from jsonschema import ValidationError

e2ee = json.loads((ROOT / "schemas/e2ee.schema.json").read_text())
Draft202012Validator.check_schema(e2ee)
validator.validate(json.loads((ROOT / "examples/discovery-e2ee.json").read_text()))
fixture = json.loads((ROOT / "conformance/fixtures/e2ee.json").read_text())
for name, value in (("Roster", fixture["roster"]), ("Envelope", fixture["envelope"]),
                    ("Device", fixture["roster"]["members"][0])):
    Draft202012Validator(dict(e2ee, **{"$ref": "#/$defs/" + name})).validate(value)
for kind, value in (("roster", fixture["roster"]), ("envelope", fixture["envelope"])):
    value = deepcopy(value)
    if kind == "envelope":
        value["ciphertext"] = None
    Draft202012Validator(dict(e2ee, **{"$ref": "#/$defs/JournalEntry"})).validate(
        {"seq": 1, "kind": kind, "payload": value})
for field, invalid in (("version", 1), ("room_group", False), ("room_id", "other"),
                       ("capsule", "not base64!"), ("payload_hash", "short")):
    value = dict(fixture["envelope"], **{field: invalid})
    try:
        Draft202012Validator(e2ee).validate(value)
    except ValidationError:
        pass
    else:
        raise AssertionError("Invalid E2EE fixture accepted: " + field)
print("E2EE shapes and malformed-envelope cases validated (not server conformance)")
