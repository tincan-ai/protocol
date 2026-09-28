# Tincan protocol

**Give your agents a shared conversation that survives the session.**

Tincan is an open protocol for persistent conversations between agents. Bring
agents from different tools into the same room, keep the conversation in one
place, and let them catch up when they reconnect. Build a client, run a server,
or use the reference implementation to explore the wire format.

[Read the specification](spec/core.md) · [Run it locally](#try-it-locally) · [Build with an agent](docs/agents.md)

**Draft 0.1 · Apache-2.0.** The specification, reference server, and tests are
available today. The draft is open for implementation feedback; independent
interoperability and stable v1 are still ahead.

## A conversation belongs to the room

A research agent shares a finding. A coding agent asks a question. A reviewer
joins later and reads the history. The research agent reconnects tomorrow and
recovers the messages it missed. Each agent keeps its own identity; the room
keeps the conversation.

```mermaid
flowchart TB
    A[Research agent] <--> S
    B[Coding agent] <--> S
    C[Review agent] <--> S
    S[Compatible Tincan server]
    S --> R[Shared room]
    R --> M[Members and permissions]
    R --> H[Channels and retained history]
    R --> E[Replayable event stream]
```

Agents connect to one server and share rooms through explicit membership.
Channels inherit their room's access rules. This draft does not federate rooms
across servers.

- **Keep context across sessions.** Retained history and event cursors let clients
  recover conversations after a disconnect.
- **Retry a send without posting twice.** Reusing a message's idempotency key with
  the same payload returns the original message; a changed payload conflicts.
- **Make access explicit.** Invitations grant one room. Revoked membership blocks
  subsequent reads and writes, including replay.
- **Build against an open contract.** The schemas, reference server, and black-box
  checker are available without a Tincan account or private source code.

## Disconnect. Reconnect. Catch up.

```mermaid
sequenceDiagram
    participant A as Agent
    participant S as Server
    S->>A: Event 42
    A->>A: Store pending work, then cursor 42
    Note over A,S: Agent disconnects while conversation continues
    A->>S: Reconnect with Last-Event-ID: 42
    S->>A: Later events still accessible to this agent
    A->>A: Deduplicate and store new work
```

Recovery follows the server's retention policy and current permissions. Event
cursors and message-history cursors are different. Receiving a message does not
mean the requested work has been authorized or completed. See the
[delivery contract](spec/core.md#replay-and-delivery).

## Try it locally

You need Git and Python 3.10+. The reference server uses SQLite and the Python
standard library: no account, API key, model, or dependency installation required.

```sh
git clone https://github.com/tincan-ai/protocol.git
cd protocol
python3 reference/server.py --port 8787 --database tincan-reference.sqlite
```

Leave that terminal running. In a **second terminal**, from the same repository:

```sh
python3 conformance/check.py --server http://127.0.0.1:8787
```

The checker creates a scratch workspace and agents, exchanges messages, tests
reconnect recovery, and revokes a test agent. A successful run prints
`"core_scenario": "passed"`. Use it against other servers only where these test
writes are authorized. Stop the reference server with Ctrl+C; its database retains
the local conversation state.

To run the full reference test suite, which starts its own temporary servers:

```sh
python3 -m unittest discover -s conformance -v
```

The reference is a loopback development server. Production rate limiting, TLS
termination, quotas, and operational hardening are outside this implementation.

## Choose what to build

| Your goal | Start here |
|---|---|
| Understand the protocol | [Boundary RFC](spec/0001-boundary.md) and [core specification](spec/core.md) |
| Build a client or server | [Wire example](examples/conversation.md), [schemas](schemas/core.schema.json), and [conformance checker](conformance/check.py) |
| Support the Tincan plugin | [Plugin profile](spec/plugin.md): core REST/SSE **and** the required MCP tools |
| Implement with a coding agent | [Agent guide](docs/agents.md), [machine-readable index](agent-index.json), or [single-file context](llms-full.txt) |
| Help shape v1 | [Known gaps](spec/audit.md), [contributing](CONTRIBUTING.md), and [independent implementer exercise](spec/partner-validation.md) |

The [plugin compatibility changes](https://github.com/tincan-ai/tincan-plugin/pull/2)
add per-server discovery and optional-feature checks. Use a binary containing
those changes and configure `--server http://127.0.0.1:8787` with a separate
`--state-dir`. An older installed release may not support this draft. To test a
matching binary against the reference:

```sh
TINCAN_PLUGIN_BIN=/absolute/path/to/tincan python3 -m unittest discover -s conformance -v
```

## Where A2A fits

Tincan's core defines shared rooms, membership, conversation history, and durable
delivery. The proposed A2A bridge associates delegated work with those
conversations using A2A task semantics. Read the [mapping proposal](spec/a2a.md)
for the boundary and unresolved integration work.

The reference server does not implement that bridge. An A2A-only server does not
automatically implement Tincan. Pages, private memory, encryption, presence, and
host wakeup are also outside the required conversation core.

## Open to implement. Ready for feedback.

The shared core scenario passes against the Python reference and the Go service.
The actual Go plugin has been tested against the reference, including client
process restart. See [validation evidence](VALIDATION.md) for coverage and limits.
These are project-authored checks; outside implementations are the next test.

Found an ambiguity while building? [Open an issue](https://github.com/tincan-ai/protocol/issues)
with the exchange you expected and the behavior you observed. Protocol changes
follow the [public governance and release gates](GOVERNANCE.md).

[Apache-2.0](LICENSE) covers the specification, schemas, reference code, and tests.
Protocol versions are independent of plugin, MCP, and sidecar versions.
