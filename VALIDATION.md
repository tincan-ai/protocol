# Implementer preview validation — 2026-09-28

This is project-authored implementation evidence, not independent certification.

| Check | Evidence |
|---|---|
| Shared core scenario against Python/SQLite reference | Passed: bootstrap, invite reuse rejection, idempotent send/conflict, SSE replay and Last-Event-ID, late-join history, pagination, membership isolation, invalid mentions/replies, revoked replay and credentials |
| Same checker against Go/PostgreSQL service | Passed in an isolated database schema through `TestProtocolHostedConformance` |
| Actual Go plugin via sidecar against Python server | Passed: two identities, pairing setup, remote MCP send/history, unsupported pages error, identity resume, full client process restart |
| Concurrent send retries and storage recovery | Passed: sixteen concurrent identical submissions produce one message/event; reopening SQLite returns the original idempotent result |
| Discovery and optional-feature guards | Passed Go race tests: malformed/oversized documents, unavailable server, redirects, missing required tools, encryption rejection and legacy downgrade prevention |
| JSON schemas | Validated as draft 2020-12, with descriptor, send input, message and event instances |

Reproduce using README.md. `EXPORT.json` identifies the exact exported source
files. These checks do not establish production reference-server readiness,
complete hosted-service conformance, external A2A interoperability, federation,
host idle wakeup, or verification by an outside implementer. The Go changes must
be released separately before installed plugins have these capabilities.
