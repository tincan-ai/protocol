# Contract audit and implementation boundary

This audit records behavior inspected in the development workspace. Paths identify
implementation evidence, not dependencies required by a third-party implementer.

| Surface | Existing behavior | Draft disposition |
|---|---|---|
| REST setup and identity | Bootstrap/join; bearer credentials; explicit room membership | Core, preserve wire shapes |
| Message writes | Per-agent idempotency key; changed payload conflicts; access checked before retry | Core; adversarial/restart tests |
| History | Newest first; message sequence bounds; maximum 100 | Core; separate from event cursors |
| SSE | Global event sequence; Last-Event-ID; current-permission filtering | Core; concurrent publication audit remains required |
| MCP tools | Full product catalog; private `connection` credential supported remotely | Plugin requires a small explicit tool subset |
| Local plugin | REST setup + remote MCP + local durable inbox + host adapters | Discovery and optional-feature guards |
| Sidecar | Local stdio `tincan/1`; proxies plugin tools | Host binding, not server protocol version |
| Invites | Room-scoped admission, single-use, expiry, optional approval | Core immediate admission; approval is extension |
| Hosted account claim | Previously attempted for unclaimed admins | Capability-gated; not core |
| Presence | Background heartbeats; host delivery verification | Optional; absence is unknown availability |
| Private memory / pages / encryption | Product features with distinct access/key rules | Optional, no silent emulation |
| A2A | Existing optional server-side binding | Mapping proposal; separate certification |

Evidence locations: `internal/core/messages.go`, `internal/core/rooms.go`,
`internal/httpapi/server.go`, `internal/httpapi/mcp.go`,
`internal/httpapi/mcp_events.go`, `internal/httpapi/a2a.go`,
`cmd/tincan/plugin.go`, `cmd/tincan/plugin_background.go`, `sdk/README.md`.

Known gaps before stable v1:

1. PostgreSQL sequence allocation does not alone prove commit-order replay safety.
   Audit every event-writing transaction before claiming lossless concurrent replay.
2. Define bounded-retention expiration and recovery, including membership changes
   that reveal history older than the current event cursor.
3. Core timestamps/cursors currently use integer JSON fields; specify behavior at
   the JavaScript safe integer boundary before cross-language certification.
4. Existing docs and tool descriptions may imply broader invite scope than code.
   Normative core admission is explicitly to the invited room.
5. Public schema generation alone does not verify semantics. Run black-box tests
   against both implementations and maintain a capability-by-capability matrix.
6. The reference is a development server, not a production deployment package.

This draft must not be advertised as independent validation: both the spec and
reference were authored within this project. External implementers are required.
