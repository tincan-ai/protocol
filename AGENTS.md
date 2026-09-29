# Working in the Tincan protocol repository

This repository contains draft 0.1, a standalone reference server, schemas and
conformance tests. It is not the hosted product or plugin source repository.

## Read only what your task needs

Start with `docs/agents.md`. `agent-index.json` maps task types to ordered local
paths and gives structured command arguments. `llms.txt` is the compact remote
reading index; `llms-full.txt` is generated plain-text context for clients that
cannot follow links. Prefer individual files when context is limited.

`spec/core.md`, `spec/plugin.md`, and `spec/e2ee.md` define the draft requirements; schemas define
wire shapes. README marketing copy and examples explain those requirements.
`spec/a2a.md` is a proposal, not a shipped extension. If implementation and spec
disagree, reproduce the discrepancy and report it; do not silently redefine the
contract or claim the reference is automatically authoritative.

## Run from this repository's root

```sh
python3 -m unittest discover -s conformance -v
python3 scripts/build-agent-docs.py --check
```

The standard-library suite starts isolated loopback servers and uses temporary
databases. The actual-plugin test is skipped unless `TINCAN_PLUGIN_BIN` is an
absolute path to a compatible built binary. Report that skip when describing
coverage. JSON Schema validation separately needs `conformance/requirements.txt`:

```sh
python3 -m pip install -r conformance/requirements.txt
python3 conformance/validate_schemas.py
```

## Preserve the contract

- Keep event cursors distinct from message-history sequences. Persist received
  work before advancing its event cursor. Never equate receipt with completion.
- Check current room access on writes, retries, history and event replay.
- Preserve per-agent message idempotency; changed payloads with the same key
  conflict. Do not generalize that guarantee to bootstrap or invite redemption.
- Keep optional capabilities optional. Core compatibility alone does not imply
  the MCP/plugin profile, A2A, encryption, federation, or host wakeup.
- Keep credentials and state private. Examples use synthetic values. The external
  checker creates data and revokes test agents; use it only on an authorized target.

For protocol changes, update the relevant spec, schema, implementation, examples,
and behavioral tests together. Regenerate `llms-full.txt` with
`python3 scripts/build-agent-docs.py`; do not edit it directly. Add new reading
entry points to `agent-index.json` and `llms.txt`. CI checks local links, the index,
and bundle freshness. `EXPORT.json` records source export hashes; if changing this
public repository directly, update hashes for tracked deliverables before committing.

Keep the reference runtime dependency-free. Treat test passes as evidence for
covered cases, not production certification or independent external validation.

## Encryption work

Read `spec/e2ee.md`, `crypto/README.md`, and `conformance/e2ee.md` first. The
Python server does not implement E2EE. Run the separate Go/Rust crypto suite;
never report core tests or structural fixtures as encrypted server conformance.
Do not confuse roster version 1, envelope protocol 2, and profile version 0.1.
Preserve client-held keys, exact signed bytes, immutable room scope, atomic state
and fail-closed negotiation. Never publish live identities or MLS state in fixtures.
