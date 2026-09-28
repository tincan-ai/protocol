# A2A bridge proposal

Status: design proposal, not a required core capability or a conformance claim.
Baseline: https://a2a-protocol.org/latest/specification/ (consult the explicitly
selected A2A version when implementing; do not silently track latest at runtime).

| Tincan concept | Proposed A2A association |
|---|---|
| Explicit delegated request message | SendMessage to the selected agent endpoint |
| Conversation within a channel | A bridge-maintained contextId mapping, scoped to endpoint and participants |
| Delegated unit of work | Server-returned task ID, persisted with request message ID |
| Progress | Correlated conversation update; not a new delegated request |
| Artifact | Authorized attachment/reference linked to task and originating request |
| Completion | A2A terminal task state; never inferred from transport receipt |
| Clarification | Follow-up to the existing task/context where permitted |

No raw room ID is automatically a globally meaningful A2A context. A channel can
contain unrelated requests; the bridge persists `(server, channel, request,
endpoint, context, task)` mappings and their ownership. Source room membership
does not authorize forwarding all history to an external endpoint. Explicit
delegation determines the minimum context and destination permitted to cross.

Retries need a durable bridge outbox and correlation IDs. A lost A2A submission
response is ambiguous unless the selected implementation guarantees deduplication
or lookup; never blindly resubmit and assert exactly-once execution. Received
updates may duplicate or skip intermediate states; reconcile task snapshots.
Cancellation is a request whose effect must be confirmed. Completed artifacts
must remain available under an explicit retention/access policy.

Existing private bridge audit: optional per-agent cards, send/stream, get/list,
cancel/subscribe and artifacts exist. Cards advertise no push notifications.
Current routes are workspace-authenticated. Full A2A conformance, external endpoint
delegation, durable correlation/reconciliation and an independent implementation
test remain release gates. The standalone reference advertises no A2A capability.

Before release: pin the A2A version, test message-only and task responses,
input/auth-required interruption, cancellation races, duplicate status/artifact
updates, restart after ambiguous submission, revoked source access, and deliberate
context minimization. Use a real independent A2A SDK/server. Do not invent a
second task lifecycle in Tincan core to bypass these requirements.
