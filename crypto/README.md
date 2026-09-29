# Reusable E2EE crypto binding

This Go module exposes the same envelope, roster, admission-proof and OpenMLS
adapter primitives used by the Tincan client. It is an **experimental crypto
binding**, not a complete client SDK: applications still implement trusted
admission, HTTP, atomic state persistence, outbox retries and archive management.
Read the [E2EE profile](../spec/e2ee.md) before integrating it.

The import path is `github.com/tincan-ai/protocol/crypto/go/e2ee`.
Pin a reviewed commit; no stable version is published. The module needs Go 1.25+
and the compiled OpenMLS WASI module. No private hosted-service source is needed.
The separate Python core reference continues to need only Python's standard library.

## Build and test from the repository root

Install Rust 1.92+ with the `wasm32-wasip1` target, Go 1.25+, and Python 3.10+.
These commands download locked Rust/Go dependencies and write build caches:

```sh
rustup target add wasm32-wasip1
python3 scripts/build-mls.py
export TINCAN_MLS_MODULE="$PWD/.tools/mls/wasm32-wasip1/release/tincan-mls.wasm"
go -C crypto/go test -race ./... -count=1
```

Ship `tincan-mls.wasm` beside your executable or provide its absolute path through
`TINCAN_MLS_MODULE`. Installed clients never download/compile it on demand. The
adapter runs in wazero with no mounted filesystem, network, environment or model
access. Its private JSON state contains secrets: never expose the helper as a
remote tool or log requests/responses. Use a durable single-writer store per device.

## API responsibilities

| API | Use |
|---|---|
| `RequireProfile` | Require exact core/E2EE profile and capability on each discovered connection; missing/legacy support fails closed. Caller validates discovery transport and pins room identity. |
| `NewIdentity`, `Identity.Device` | Generate local identity and public device record. `Identity` contains private material; never transmit it. |
| `MLS` | KeyPackage, create, add, finalize, join, update, remove, encrypt, decrypt and commit operations. Pass returned state to the next call and durably store it. |
| `Roster.Sign`, `Roster.Verify`, `Roster.Hash` | Typed signing and public membership verification. Caller must also check chain, epoch and actual MLS membership. |
| `Envelope.MLSContext`, `Envelope.SignMLS`, `Envelope.Verify` | Bind routing, ciphertext hash and key capsule. Outer verification alone is **not** MLS/AEAD authentication. |
| `SealLocal`, `OpenLocal`, `PayloadHash` | AES-256-GCM payload/archive operations; the caller supplies the correct context and securely stores keys. |
| `JoinProof`, `VerifyJoin`, `AdmissionMAC`, `VerifyAdmission` | Admission primitives; capability reservation, expiry and replay prevention remain caller responsibilities. |

MLS operations `add`, `update` and `remove` stage a pending commit. Publish the
exact signed roster, then `finalize` after confirmed acceptance. On uncertain
outcomes retain the staged state and retry; do not blindly discard or recreate it.
`ErrMLSApplicationRejected` identifies a rejectable application message. State,
runtime and commit failures are different and cannot be safely skipped.

Legacy age APIs remain for compatibility with the source implementation. Calling
`Envelope.Seal` creates protocol 1, **not this profile**. For protocol 2, follow
[Payload and key capsule](../spec/e2ee.md#payload-and-key-capsule), use `MLS`, then
`SignMLS`. Do not infer encryption protocol from a filename such as `encrypted.age`.

## Test layers and provenance

[Fixed vectors](../conformance/fixtures/e2ee.json) cover typed signing bytes,
Ed25519 verification, hashes, AES-GCM and null/empty/escaping behavior. Their inert
capsule and KeyPackage placeholders are explicitly **not MLS test vectors**.
The Go suite separately executes real OpenMLS joins, tampering, out-of-order
messages, removal, key erasure, restart, room isolation and envelope delivery.
Neither layer alone certifies a live server; see the [acceptance matrix](../conformance/e2ee.md).

Source primitives were extracted from `internal/e2ee` and the pinned Rust adapter
in the Tincan development workspace. This publication changes packaging and adds
profile/fixture tests; it is not a new cryptographic construction. Apache-2.0
covers this repository's code; dependencies retain their respective licenses.
