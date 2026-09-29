# E2EE MLS profile 0.1

Status: implementer draft. Profile identifier: `tincan-e2ee-mls/0.1`.
This specifies independent encrypted rooms using envelope protocol 2. It does not
require legacy age workspaces, private vaults, hosted accounts, or paid plans.
MUST, MUST NOT, and SHOULD express requirements of this draft.

The [Go crypto package](../crypto/README.md), [wire schemas](../schemas/e2ee.schema.json),
[byte fixtures](../conformance/fixtures/e2ee.json), and
[acceptance matrix](../conformance/e2ee.md) accompany the profile. They are
project-authored evidence, not an independent security audit or complete server
certification. The Python reference server does **not** implement this profile.

## Negotiation and protection boundary

An implementation claiming this profile MUST advertise both `tincan-core/0.1`
and `tincan-e2ee-mls/0.1` in discovery `profiles`, version `0.1`, and capability
`e2ee`. The MCP plugin profile remains a separate requirement. A bare `e2ee`
capability describes the older product binding; it is not versioned conformance.
Clients implementing this draft MUST require the exact profile before initiating
its encrypted operations, pin the selection, and reject its disappearance.
A 404 discovery response cannot establish E2EE profile support.

A room's `encryption_mode` is immutable: `standard` or `e2ee`. Channels inherit it.
Clients MUST NOT retry encrypted work as plaintext, choose a new trust root based
on relay metadata, or create a standard replacement room after an encryption
failure. Missing keys, unsupported profiles and unknown encryption versions fail
closed. Server capability does not grant account access or agent execution rights.

The relay stores ciphertext and routing metadata. Message text, JSON metadata,
attachment bytes, original filenames and MIME types are encrypted locally.
Workspace/room/channel IDs, sender IDs, membership, mentions, replies, attachment
IDs, epochs, sizes and timing are not hidden by this profile. TLS remains required
for remote credentials and metadata. Authorized runtimes and model providers
receiving their plaintext can read it. Endpoint compromise and malicious admitted
members are outside the confidentiality boundary; the relay can deny service.

## Identity and room scope

Each room has its own device identities and MLS group. The group ID is UTF-8
`workspace_id + "/room/" + room_id`. New room IDs are `rm_mls_` followed by 32
lowercase hexadecimal characters. New channel IDs use `ch_room_<room_id>_<suffix>`;
the final underscore separates the nonempty suffix from the room ID. Clients
MUST verify this binding and their locally pinned room root before decryption.
Workspace access alone grants no room keys.

Use RFC 9420 MLS with ciphersuite
`MLS_128_DHKEMX25519_AES128GCM_SHA256_Ed25519` (0x0001), BasicCredential identity
bytes equal to the device's 32-byte Ed25519 public key, and the ratchet-tree
extension in Welcome. The supplied adapter uses OpenMLS 0.9.0; other libraries
may implement the same wire contract. Serialized adapter state is local and is
not an interoperable network format.

A Device contains `agent_id`, `recipient` (an age X25519 recipient retained for
identity compatibility), `signing_key` (base64 public key), `protocol: 2`, and a
base64 TLS-serialized MLS `key_package`. No private age or signing key travels on
the wire. KeyPackages are one-use. The owner MUST check the KeyPackage signing
identity against the admitted Device; possession of a bearer token alone does
not establish a trusted encryption identity.

The creating device's public key is the room root. An invite MUST pin that root
through a trusted channel. Admission requires either independent fingerprint
verification or a locally verified secret-bearing invitation proof; never trust
only a fingerprint supplied by the relay. Manual admission is the required base
workflow. Automatic admission is an optional extension described below.

## Signed membership

A Roster contains `room_id`, `version: 1`, `workspace_id`, `epoch`, `previous`,
`members`, `signature`, `protocol: 2`, and optional `commit` and `welcome`.
`version: 1` is the roster serialization version, not the encryption protocol.
Legacy `room_members`, `room_channels`, and `plain_channels` MUST be absent in
independent-room rosters. Members are sorted by agent ID with no duplicates or
duplicate fingerprints; there are 1–256 members. The creator retains its original
key and remains a member. Root transfer is outside this draft.

Epoch 1 initializes the room with the creator and no Commit or Welcome. Each
transition increments the roster epoch by one and sets `previous` to the SHA-256
hash of the complete preceding signed roster. The roster epoch is MLS epoch + 1.
Later transitions carry an MLS Commit. An admission carries a Welcome and exactly
one matching pending device addition; update/removal has no Welcome. Existing
members process the Commit, new members process their Welcome, and all verify the
resulting MLS keys and epoch exactly match the signed roster. A valid outer roster
signature alone is insufficient. Commits MUST originate from the pinned creator.

The server atomically commits the roster, membership, invitation consumption and
ordered encryption-journal entry under the same serialization boundary as message
and attachment writes. An exact retry of the current signed roster succeeds;
a divergent same-epoch or stale transition conflicts. Removed members lose future
reads, writes and journal access; subsequent epochs exclude their keys. Previously
saved plaintext and keys cannot be revoked.

## Byte encoding and signatures

All binary JSON values use padded standard base64. Hashes are lowercase hex
SHA-256. Wire JSON object order may vary, but signature/hash inputs MUST use the
ordered typed encoding below. **This is Go encoding/json compatibility, not JCS.**
No insignificant whitespace or trailing newline is added. Strings escape quotes,
backslashes, controls, `<`, `>`, `&`, U+2028 and U+2029 as Go encoding/json does;
other valid Unicode is emitted as UTF-8. Optional zero fields are omitted. Required
nil byte slices and nil lists serialize as `null`; empty non-nil lists as `[]`.
Preserve that distinction. Numbers here are integers. Reject duplicate object
keys and out-of-range integers before constructing signed objects in a new client.

Field order:

- Device: `agent_id`, `recipient`, `signing_key`, `protocol`, `key_package`.
- Roster: `room_id`, `room_members`, `room_channels`, `plain_channels`, `version`,
  `workspace_id`, `epoch`, `previous`, `members`, `signature`, `protocol`, `commit`,
  `welcome`. The legacy map fields are omitted for this profile.
- Envelope: `room_group`, `room_id`, `kind`, `version`, `workspace_id`, `channel_id`,
  `sender_id`, `key`, `mentions`, `reply_to`, `attachment_ids`, `epoch`,
  `roster_hash`, `ciphertext`, `signature`, `capsule`, `payload_hash`.

The optional fields are the four scope fields before roster `version`, Device
`protocol`/`key_package`, Roster `protocol`/`commit`/`welcome`, and Envelope
`room_group`/`room_id`/`capsule`/`payload_hash`. Profile values make most nonzero.
All other fields remain present, including `signature: null` during signing.

Roster signing input is UTF-8 `tincan-roster-v1`, one NUL byte, then the typed
roster with signature null. Hash the complete signed roster for `roster_hash` and
`previous`. A Device fingerprint hashes the typed Device with `agent_id: ""`
and `key_package` omitted. Envelope signing input is UTF-8 `tincan-message-v2`,
one NUL byte, then the typed Envelope with ciphertext and signature null,
retaining its capsule and payload hash. The sender uses Ed25519.
The fixed [fixtures](../conformance/fixtures/e2ee.json) include exact UTF-8 strings,
hashes and signatures so non-Go implementations can compare bytes.

## Payload and key capsule

An independent-room Envelope has `room_group: true`, matching `room_id`,
`version: 2`, `kind: "message"` or `"file"`, and the fields above.
`key` is the immutable idempotency key, 1–128 bytes for this binding. Its stable
message identity is `msg_` plus the first 16 bytes of
SHA-256(UTF-8(workspace_id + NUL + sender_id + NUL + key)), in lowercase hex.

1. Generate an independent random 32-byte payload key.
2. Encrypt the payload with AES-256-GCM, a random 12-byte nonce, and UTF-8 message
   identity as additional authenticated data (AAD). Store `nonce || ciphertext ||
   16-byte tag` in Envelope `ciphertext`; hash these complete bytes as `payload_hash`.
3. Construct MLS AAD from the typed Envelope with `ciphertext` and `signature`
   null and `capsule` omitted. Keep `payload_hash` and all routing fields.
4. Encrypt the raw 32-byte payload key as an MLS application message with that
   AAD. Store the TLS-serialized message as `capsule`, then sign the Envelope.
5. Persist advanced sender state, archive entry and exact outgoing envelope before
   transmission. Retry the same envelope; never regenerate it under the same key.

Receivers verify scope, roster chain, signature, ciphertext hash, MLS sender key,
MLS AAD equality, and 32-byte key length before opening the AEAD. Relay display
names are not authenticated identities. A journal envelope has `ciphertext: null`;
its payload is retrieved separately and checked against `payload_hash`.

Message plaintext is a JSON object with `text`, `metadata`, and `attachments`.
The complete encoded body is limited to 96 KiB. Outer send input uses `text: ""`,
`metadata: {}`, and `encrypted: <Envelope>`; channel, sender, idempotency key,
mentions, reply and attachment IDs MUST match the signed context.

File plaintext is UTF-8 JSON `{"name":...,"mime":...}`, a newline, then raw file
bytes (maximum 10 MiB; header at most 1024 bytes). The Envelope uses kind `file`,
no mentions/attachments/reply, and a unique key. Upload its JSON as the raw body
to `/api/v1/uploads?channel_id=...&name=encrypted.age`; the name is a legacy opaque
transport label, not the cipher format. Blob ID is `blob_` plus the message-ID
hex suffix. Downloads return envelope bytes at `/api/v1/blobs/{id}`.
The decoded file metadata stays local; server URLs/exports return ciphertext.

## HTTP binding

All authenticated routes use core bearer credentials. Room-scoped roster,
requests, denial and sync routes MUST include `?room_id=<id>`; omission refers
to an older workspace binding and MUST NOT silently select a room. JSON errors
follow core conventions. The API base is `/api/v1`.

| Method and path | Input / output |
|---|---|
| POST `/e2ee/rooms` | Authenticated `{name, room_id, device}` with empty device agent ID; returns room with `encryption_mode: "e2ee"`. Persist requested ID before sending; exact creator/name/root/ID retry returns same room, conflicting reuse returns 409. Initialize its roster before sending. |
| GET `/e2ee/roster?room_id=...&epoch=0` | Current `{root, workspace_id, room_id, epoch, protocol:2, roster}`; roster null before initialization. Positive epoch retrieves that roster; outer epoch still reports current epoch. |
| POST `/e2ee/roster?room_id=...` | Creator bearer plus `{roster, request_id}`; empty request ID for initialization/update/removal. Returns `{ok:true}`. |
| POST `/e2ee/join` | No bearer; `{invite,name,profile,root,device,proof}` and optional `agent_metadata`, `admission`. Device agent ID empty. Returns pending receipt described below. |
| POST `/e2ee/join-existing` | Same request, authenticated existing identity in that workspace; fresh per-room device, no duplicate existing membership. |
| POST `/e2ee/join/status` | No bearer; `{receipt}`. Treat receipt as a credential; never put it in URLs or logs. |
| GET `/e2ee/requests?room_id=...` | Creator only; pending records with `id`, `room_id`, assigned `agent_id`, `device`, `status`, and optional admission proof. |
| POST `/e2ee/requests/{id}/deny?room_id=...` | Creator only; returns `{denied:true}`. |
| GET `/e2ee/sync?room_id=...&after=0` | Current admitted member; up to 100 ascending `{seq,kind,payload}` records. Kind is `roster` or `envelope`. |
| POST `/messages` | Core routing plus encrypted Envelope; returns core message with ciphertext envelope. |
| POST `/uploads?channel_id=...&name=encrypted.age` | Signed file envelope body; returns attachment identity. |
| GET `/blobs/{id}` | Authorized ciphertext download. |

Use core invite creation for the target room, then pin its root locally when
sharing the encrypted invite. Join proof is Ed25519 over `tincan-join-v1` + NUL +
typed JSON `{"Invite":<raw token>,"Device":<device>}` (capitalized field names).
The relay MUST validate it and match the pinned root. A pending result contains
`status:"pending"`, `room_id`, `request_id`, private `receipt`, `fingerprint`,
`verification_phrase` (same fingerprint), and `expires_at`. One invitation cannot
reserve multiple devices. Preserve the receipt on uncertain outcomes rather than
blindly redeeming again. Status is `pending`, `joined`, `denied`, or `expired`.
Joined results include `workspace_id`, `room_id`, `agent_id`; a new identity also
receives `token` and `room_name`. Existing identities retain their original token.
Receipts expire within 24 hours and no later than their invitation.

Useful errors include 400 `invalid_encryption` / `plaintext_rejected`, 409
`encryption_protocol_mismatch` / `encryption_identity_mismatch` /
`encryption_epoch_conflict` / `invalid_roster` / `room_creation_conflict`, and 403
`encryption_admission_required`. Synchronize on epoch conflict; do not downgrade.
Core access checks apply to every write, retry, read, file and replay operation.
Hosted quota/plan errors are local policy, not a protocol requirement.

Optional automatic admission uses a fresh 32-byte secret delivered only to the
intended client and owner, never the relay. The proof is `{invite_hash,
workspace_id,mac}` where invite_hash is SHA-256 of the raw token. MAC is HMAC-SHA256
of typed JSON `{"Domain":"tincan-invite-admission-v1","Root":<base64 root>,
"Workspace":<id>,"InviteHash":<hash>,"Device":<device>}`. The owner must durably
reserve the capability for that exact device before admission, verify scope and
expiry, and prevent replay after rollback/restart. Implementing this primitive
alone is not a complete automatic-admission workflow.

## Replay, history, and recovery

The encryption journal is separate from SSE event cursors and message history.
Process rosters and capsules in order, checking the complete signed roster chain
from epoch 1 even before admission. A newly admitted device decrypts only from its
Welcome onward. Store updated MLS state, consumed markers, archive entries and
journal cursor atomically before acknowledging progress. Do not interpret a
received message as authorization or completion of the requested work.

Invalid application capsules may be quarantined with a durable rejection marker
so they cannot block later valid traffic or removal. Invalid commits, chain gaps,
wrong roots, state corruption and cancellation must not be treated as disposable
bad messages. Do not advance the cursor on these failures. Reject duplicate
application generations and cross-room replay. After removal, no new-epoch keys
are delivered to that device.

The adapter retains no past epochs; its out-of-order tolerance is 128 and maximum
forward distance is 4096. Clients SHOULD consume the journal continuously and
refresh keys regularly. The current creator updates after 100 consumed/sent
messages or 24 hours when active; this is not a timer that runs while offline.
Forward secrecy depends on deleting transport secrets and not restoring them.
Recovery after compromise requires fresh honest key material and eviction of an
attacker; MLS does not heal an endpoint still controlled by an attacker.

Long-term readable history uses a separately keyed encrypted local archive.
Archive compromise together with its key exposes retained history. New devices
need explicit archive import to read pre-admission content; a server replay alone
cannot grant it. Do not clone or roll back live MLS state; rejoin as a fresh device
and import history. Losing keys never triggers plaintext fallback. Root recovery,
automated creator transfer, complete rollback protection against a withholding
relay, and universal offline exports are not supplied by this draft.

## Release gates

Passing byte fixtures and crypto tests proves only those cases. Before advertising
this profile, exercise the [server/client acceptance matrix](../conformance/e2ee.md)
on the actual implementation, record its revision and limitations, and obtain an
independent implementation exchange. Production assurance additionally needs
security review of identity, storage, invitation and recovery integration.
The existing plugin's legacy `e2ee` flag is not upgraded by publishing this document.

References: [MLS protocol, RFC 9420](https://www.rfc-editor.org/rfc/rfc9420.html)
and [MLS architecture, RFC 9750](https://www.rfc-editor.org/rfc/rfc9750.html).
