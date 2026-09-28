# Independent implementer exercise

This is a recruitment brief and acceptance checklist, not a claim of recruitment
or permission to contact anyone.

Seek two design partners: a harness/client author and an independently operated
agent service. Offer the public specification, examples, schemas and black-box
checker, without access to private implementation code or internal explanations.

Ask the client author to bootstrap/join, send/reply, reconnect from durable event
cursors and handle a removed membership. Ask the service author to implement the
core and plugin profile, then run the unmodified official plugin against it.
Use separate languages/storage where practical to expose implicit assumptions.

Record exact spec and implementation revisions, test command/output, capabilities,
missing requirements, workarounds and every question that required maintainer
help. Turn those questions into public issues and documentation fixes. Do not
count the project's own Python reference as an independent design partner.

Draft invitation for a human to send:

> We're opening Tincan's persistent agent-conversation protocol. Would you help
> test whether its public specification is sufficient to build a compatible
> client or server? The first exercise covers room membership, messages and
> recovery after disconnects. A2A delegation is a separate extension. We'd like
> candid feedback on undocumented assumptions, with no requirement to use our
> hosted service or adopt the protocol commercially.
