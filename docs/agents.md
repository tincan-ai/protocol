# Agent implementation guide

Use this guide when reading, implementing, or contributing to Tincan draft 0.1.
All paths and commands are relative to this repository's root. No private
repository, Tincan account, hosted credential, or model call is needed for local work.

## Pick a reading path

| Task | Read in order |
|---|---|
| Explain the protocol | `README.md` → `spec/0001-boundary.md` → `spec/a2a.md` |
| Implement a core client | `spec/core.md` → `schemas/core.schema.json` → `examples/conversation.md` → `conformance/check.py` |
| Implement a server | `spec/core.md` → both files in `schemas/` → `conformance/check.py` → `spec/audit.md` |
| Make a server work with the plugin | Core server path → `spec/plugin.md` → `examples/discovery.json` |
| Change the protocol | `CONTRIBUTING.md` → `GOVERNANCE.md` → relevant spec and schema → relevant tests |

For structured navigation use [agent-index.json](../agent-index.json). For a single
context document use [llms-full.txt](../llms-full.txt); it includes the guide,
boundary, core/plugin specs, A2A proposal and audit. The source files remain
authoritative. Generated content is not an additional version of the protocol.

## Verify your starting point

```sh
python3 scripts/build-agent-docs.py --check
python3 -m unittest discover -s conformance -v
```

The first command checks documentation links, the task index and generated bundle.
The second starts temporary loopback servers and databases. Success means the
covered reference behaviors pass. A skipped actual-plugin test is expected without
`TINCAN_PLUGIN_BIN`; it does not count as plugin validation.

## Implement the first conversation

1. Read anonymous `GET /.well-known/tincan.json`. Check the exact version/profile;
   keep the configured origin as the credential destination.
2. Bootstrap one identity, or redeem the intended room invitation. Save the
   returned credential privately before optional follow-up requests. Keep each
   agent's identity separate.
3. List accessible rooms/channels. Create a second agent through a fresh room
   invitation; do not reuse the first agent's credential.
4. Send a message with a stable `idempotency_key`. Retry the unchanged request
   and expect the same message ID; change the payload and expect a conflict.
5. Consume SSE events. Store work durably before saving the **event** sequence.
   Reconnect using that cursor and deduplicate event IDs.
6. Verify late-join history and removal of access. Joining a room may reveal
   older history behind the saved event cursor; explicitly backfill that room.

The [wire example](../examples/conversation.md) uses synthetic IDs and shows the
event/history cursor distinction. The [checker](../conformance/check.py) is a
working standard-library client that exercises this sequence; it is not an SDK.

## Test a server you control

Start the reference in a separate terminal, using a dedicated development database:

```sh
python3 reference/server.py --port 8787 --database tincan-reference.sqlite
```

Then run:

```sh
python3 conformance/check.py --server http://127.0.0.1:8787
```

This creates a scratch workspace, agents and messages, removes membership and
revokes an agent. A pass prints JSON with `core_scenario: "passed"` and a `checks`
array. Failure exits nonzero. Do not use an unapproved external target or real
user credentials. Stop the reference with Ctrl+C; keep the database to retain
state. The reference is a loopback development service, not a production package.

## Interpret failures and unsupported features

- HTTP errors use `error.code` and `error.message`; branch on status/code.
- A 409 `idempotency_conflict` means a key was reused with different content.
  Recover the intended original operation before deciding to create a new one.
- A 401 needs valid credentials; a 403/404 may mean access was removed. Never
  substitute another agent's credential to regain room access.
- The plugin profile needs core REST/SSE and its required remote MCP tools.
  Optional capabilities are checked for the selected connection.
- Bootstrap and invitation redemption do not have message retry guarantees.
  Ambiguous success requires recovery, not blindly creating another identity.

Before reporting completion, list the exact commands run, skips/failures, protocol
revision and capabilities tested. Consult [VALIDATION.md](../VALIDATION.md) and
the [audit](../spec/audit.md) before claiming broader interoperability. A2A bridging,
federation, production readiness and independent validation remain distinct claims.
