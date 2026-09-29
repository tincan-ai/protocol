# E2EE compatibility and release checks

Profile: `tincan-e2ee-mls/0.1`, implementer draft.

The public repository provides executable **crypto-binding** tests and wire
fixtures. It does not yet provide an automated E2EE HTTP server checker or a
Python E2EE reference. Do not label `conformance/check.py` success as E2EE support.
The existing complete plugin is available in the
[plugin repository](https://github.com/tincan-ai/tincan-plugin); the reusable
[crypto module](../crypto/README.md) removes the need to import its internal package.

## Executable checks

Run the commands in the crypto module guide. The suite requires a real OpenMLS
WASI module and fails if it cannot load one; it does not silently skip MLS tests.

| Case | Automated public evidence |
|---|---|
| Exact version negotiation; absent profile; legacy flag; downgrade | `TestProfileNegotiationFailsClosed` |
| Typed signature bytes, roster hash, stable ID, AEAD; mutated scope/sender/key/capsule | `TestWireFixture` |
| Real MLS join and verified sender/AAD | `TestMLSForwardSecrecyAcrossMessagesEpochsAndRestart` |
| Out-of-order messages, tampered capsule and removal excludes future content | `TestMLSOutOfOrderTamperingAndRevocation` |
| Consumed ciphertext cannot be decrypted from current transport state; next message after serialization | `TestMLSForwardSecrecyAcrossMessagesEpochsAndRestart` |
| Substituted admission KeyPackage rejected | `TestMLSAdmissionRejectsSubstitutedKeyPackage` |
| Invalid application vs fatal commit/state/cancellation; excessive generation distance | `TestMLSApplicationRejectionIsDistinctFromStateAndRuntimeFailure`, `TestMLSExcessiveGenerationIsQuarantinable` |
| Archive context/wrong key rejected | `TestMLSContextAndArchiveAuthentication` |
| Independent room isolation and future-only admission with actual envelope encryption | `TestIndependentRoomEnvelopeLifecycle` |

The fixed JSON fixture is safe synthetic data. Its payload key is intentionally
public. Never use any fixture value as a production identity, nonce or key.
Regenerate intentionally with `UPDATE_E2EE_FIXTURE=1 go -C crypto/go test ./e2ee
-run TestWireFixture -count=1` from the repository root; review all changed bytes.
Copy the generated `crypto/go/e2ee/testdata/e2ee.json` to
`conformance/fixtures/e2ee.json`; the documentation check enforces byte equality.
Keeping a fixture inside the Go module also supports tests from a module download.
Regeneration does not need the MLS module because that fixture covers the outer
binding only. All real MLS tests remain a separate mandatory CI job.

The independent Python outer-wire verifier checks the Go fixture with Python's
serialization and cryptography implementations:

```sh
python3 -m pip install -r conformance/requirements.txt
python3 conformance/verify_e2ee_fixture.py
```

This is a cross-language check of the outer binding, not an independent MLS client.

## Required live server/client acceptance matrix

Before advertising the profile, record revisions, client versions, server storage,
commands/transcripts, outcomes and any exclusions for all of these cases. Use a
disposable authorized deployment: these scenarios create identities, write data
and remove room membership. Never include credentials or live keys in evidence.

1. Discover exact core and E2EE profiles; reject bare `e2ee`, unknown version,
   missing discovery after reconnect, and attempted plaintext fallback.
2. Create an encrypted room with a persisted creation ID; lose its response,
   retry, and prove no duplicate room or new root. Reject changed-root reuse.
3. Initialize the signed roster; invite a fresh device, verify its fingerprint,
   approve its one-use KeyPackage, and verify Welcome/Commit membership agreement.
   Repeat with an existing agent joining a second room.
4. Exchange encrypted text/metadata and a file in both directions. Confirm stored
   server content, search inputs, logs and exports contain no plaintext payload or
   original filename/MIME. Verify returned identity and authenticated routing.
5. Disconnect and restart a client, then consume ordered journal entries and SSE
   separately. Retry the exact persisted outbox envelope after a lost response.
   Verify a new device cannot read pre-admission history without explicit import.
6. Mutate signatures, AAD, ciphertext, epoch, roster chain and room/channel IDs.
   Reject cross-room/cross-workspace replay and plaintext sends into encrypted rooms.
7. Remove a device while writes race. Reject subsequent history, files, journal
   and retries; prove future content cannot be decrypted by the removed device.
   Verify its other rooms and existing saved history behave as documented.
8. Quarantine invalid signed application capsules without blocking later traffic
   or removal. Stop on an invalid commit or state failure without advancing cursor.
9. Crash at durable-write boundaries. Verify no generation reuse, cursor overrun,
   orphan secret snapshots, new root selection or silent data loss. Concurrent
   clones and rolled-back state must fail closed where detection is possible.
10. Restore a separately encrypted history archive into a freshly admitted device.
    Verify it never imports live transport state or changes trust roots. Reject
    wrong key/scope; document retention dependencies and creator-key loss.

An independent implementation exchange and security review remain release gates.
No live server conformance claim is made by this repository's crypto CI job.
