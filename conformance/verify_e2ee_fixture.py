"""Verify Go-produced outer wire vectors independently with Python cryptography.

This checks serialization, Ed25519, SHA-256 and AES-GCM, not MLS or HTTP behavior.
All keys in the fixture are public synthetic test data.
"""
import base64
import hashlib
import json
from pathlib import Path

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {
    "device": "agent_id recipient signing_key protocol key_package".split(),
    "roster": "room_id room_members room_channels plain_channels version workspace_id epoch previous members signature protocol commit welcome".split(),
    "envelope": "room_group room_id kind version workspace_id channel_id sender_id key mentions reply_to attachment_ids epoch roster_hash ciphertext signature capsule payload_hash".split(),
}
OPTIONAL = {
    "device": {"protocol", "key_package"},
    "roster": {"room_id", "room_members", "room_channels", "plain_channels", "protocol", "commit", "welcome"},
    "envelope": {"room_group", "room_id", "capsule", "payload_hash"},
}


def typed(kind, value):
    if set(value) - set(FIELDS[kind]):
        raise ValueError("Unknown signed field")
    out = {}
    for name in FIELDS[kind]:
        item = value.get(name)
        if name in OPTIONAL[kind] and not item:
            continue
        if name == "members":
            item = [typed("device", member) for member in item]
        out[name] = item
    return out


def encode(kind, value):
    text = json.dumps(typed(kind, value), ensure_ascii=False, separators=(",", ":"))
    for char, escaped in (("<", r"\u003c"), (">", r"\u003e"), ("&", r"\u0026"),
                          ("\u2028", r"\u2028"), ("\u2029", r"\u2029")):
        text = text.replace(char, escaped)
    return text.encode("utf-8")


def binary(value):
    return base64.b64decode(value, validate=True)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def verify(fixture):
    roster, envelope = fixture["roster"], fixture["envelope"]
    unsigned = dict(roster, signature=None)
    signing = b"tincan-roster-v1\0" + encode("roster", unsigned)
    assert signing == fixture["roster_signing_input"].encode()
    Ed25519PublicKey.from_public_bytes(binary(fixture["root"])).verify(binary(roster["signature"]), signing)
    assert digest(encode("roster", roster)) == fixture["roster_hash"] == envelope["roster_hash"]
    device = dict(roster["members"][0], agent_id="", key_package=None)
    assert digest(encode("device", device)) == fixture["device_fingerprint"]
    identity = "msg_" + digest((envelope["workspace_id"] + "\0" + envelope["sender_id"] + "\0" + envelope["key"]).encode())[:32]
    assert identity == fixture["message_id"]
    unsigned = dict(envelope, ciphertext=None, signature=None)
    signing = b"tincan-message-v2\0" + encode("envelope", unsigned)
    assert signing == fixture["envelope_signing_input"].encode()
    sender = next(d for d in roster["members"] if d["agent_id"] == envelope["sender_id"])
    pub = Ed25519PublicKey.from_public_bytes(binary(sender["signing_key"]))
    pub.verify(binary(envelope["signature"]), signing)
    aad = encode("envelope", dict(unsigned, capsule=None))
    assert aad == fixture["mls_aad"].encode()
    ciphertext = binary(envelope["ciphertext"])
    assert digest(ciphertext) == envelope["payload_hash"]
    aead = AESGCM(binary(fixture["synthetic_payload_key"]))
    assert aead.decrypt(ciphertext[:12], ciphertext[12:], identity.encode()) == fixture["plaintext"].encode()
    # Assert rejection by independent primitives, not only expected-byte equality.
    bad = bytearray(signing)
    bad[-1] ^= 1
    try:
        pub.verify(binary(envelope["signature"]), bytes(bad))
    except InvalidSignature:
        pass
    else:
        raise AssertionError("Mutated signature input accepted")
    try:
        aead.decrypt(ciphertext[:12], ciphertext[12:], b"different-room-message")
    except InvalidTag:
        pass
    else:
        raise AssertionError("Wrong AEAD identity accepted")


if __name__ == "__main__":
    verify(json.loads((ROOT / "conformance/fixtures/e2ee.json").read_text()))
    print("Python verified Go outer-wire fixture: encoding, signatures, hashes and AEAD; not MLS/server conformance")
