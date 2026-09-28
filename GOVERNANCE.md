# Governance and release gates

Tincan maintainers steward the draft through public issues and pull requests.
Protocol versioning is independent from product releases. During 0.x, breaking
changes require a new explicitly advertised version and migration notes; after
v1, supported versions retain their documented behavior until a publicly
announced deprecation date. Unknown optional extensions must remain ignorable.

Proposals describe the problem, wire changes, security/access implications,
compatibility, examples, and executable tests. Significant decisions record
alternatives and implementation evidence. Outside maintainers can be added based
on sustained specification, implementation and review contributions; foundation
transfer is not a prerequisite for public review.

## Release gates

- Draft: public spec, schemas, reference implementation, tests, reproducible export.
- Plugin preview: actual CLI/plugin/sidecar tested against the standalone server,
  including reconnect and unsupported features; publish exact tested revisions.
- Hosted compatibility: run the same scenario against an isolated hosted-service
  fixture; resolve failures rather than adding implementation-specific exceptions.
- Independent preview: at least two design partners; one independent client and
  preferably an independent server implemented from public material only.
- v1: close audit gaps, publish version support/deprecation policy and evidence
  matrix, independently demonstrate cross-implementation interoperability.

Federation, A2A bridging and production reference hosting each need separate
tests and claims. Passing core tests does not certify those extensions or host
wakeup. Recruitment requires explicit outreach authorization; a repository does
not by itself establish external adoption.

## Rollout order

Deploy and verify the anonymous discovery route on a server before releasing a
plugin that requires negotiation there. Old hosted deployments may return HTML
with HTTP 200 at unknown paths; the plugin correctly rejects that as an invalid
descriptor. A 404 alone enables legacy fallback. Do not weaken malformed-response
handling to compensate for a client-first deployment. Keep the previous plugin
release available until server deployment and compatibility checks pass.

Publishing this draft repository does not deploy the hosted service, publish a
new plugin binary, or change existing users' connections.
