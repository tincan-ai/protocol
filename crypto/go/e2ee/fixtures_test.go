package e2ee

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
)

type wireFixture struct {
	Description          string   `json:"description"`
	Root                 []byte   `json:"root"`
	Roster               Roster   `json:"roster"`
	Envelope             Envelope `json:"envelope"`
	RosterSigningInput   string   `json:"roster_signing_input"`
	EnvelopeSigningInput string   `json:"envelope_signing_input"`
	Context              string   `json:"mls_aad"`
	RosterHash           string   `json:"roster_hash"`
	Fingerprint          string   `json:"device_fingerprint"`
	MessageID            string   `json:"message_id"`
	PayloadKey           []byte   `json:"synthetic_payload_key"`
	Plaintext            string   `json:"plaintext"`
}

func TestWireFixture(t *testing.T) {
	path := filepath.Join("..", "..", "..", "conformance", "fixtures", "e2ee.json")
	if os.Getenv("UPDATE_E2EE_FIXTURE") == "1" {
		id, err := NewIdentity()
		if err != nil {
			t.Fatal(err)
		}
		d, err := id.Device("ag_fixture")
		if err != nil {
			t.Fatal(err)
		}
		// Public, inert structural key package and capsule. Actual MLS is exercised
		// separately, never misrepresented as a cross-implementation MLS vector.
		d.Protocol = 2
		d.KeyPackage = bytes.Repeat([]byte{1}, 64)
		r := Roster{RoomID: "rm_mls_00000000000000000000000000000001", Version: 1, WorkspaceID: "ws_fixture", Epoch: 1, Members: []Device{d}, Protocol: 2}
		if err = r.Sign(*id); err != nil {
			t.Fatal(err)
		}
		e := Envelope{RoomGroup: true, RoomID: r.RoomID, Kind: "message", Version: 2, WorkspaceID: r.WorkspaceID, ChannelID: "ch_room_" + r.RoomID + "_fixture", SenderID: d.AgentID, Key: "fixture-<>&\u2028", Mentions: []string{}, ReplyTo: nil, AttachmentIDs: nil, Epoch: 1, RosterHash: r.Hash(), Capsule: bytes.Repeat([]byte{2}, 32)}
		f := wireFixture{Description: "Synthetic outer-envelope encoding/signature/AEAD vector. Capsule and KeyPackage are inert structural placeholders, NOT valid MLS messages. The payload key is public test data; never use it for real content.", Root: d.SigningKey, Roster: r, PayloadKey: bytes.Repeat([]byte{3}, 32), Plaintext: `{"text":"synthetic fixture","metadata":{},"attachments":[]}`}
		e.Ciphertext, err = SealLocal(f.PayloadKey, []byte(f.Plaintext), []byte(e.MessageID()))
		if err != nil {
			t.Fatal(err)
		}
		e.PayloadHash = PayloadHash(e.Ciphertext)
		if err = e.SignMLS(*id); err != nil {
			t.Fatal(err)
		}
		f.Envelope = e
		f.Context = string(e.MLSContext())
		f.RosterHash = r.Hash()
		f.Fingerprint = d.Fingerprint()
		f.MessageID = e.MessageID()
		unsigned := r
		unsigned.Signature = nil
		b, _ := json.Marshal(unsigned)
		f.RosterSigningInput = "tincan-roster-v1\x00" + string(b)
		unsignedE := e
		unsignedE.Ciphertext = nil
		unsignedE.Signature = nil
		b, _ = json.Marshal(unsignedE)
		f.EnvelopeSigningInput = "tincan-message-v2\x00" + string(b)
		b, _ = json.MarshalIndent(f, "", "  ")
		if err = os.WriteFile(path, append(b, '\n'), 0644); err != nil {
			t.Fatal(err)
		}
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var f wireFixture
	if err = json.Unmarshal(data, &f); err != nil {
		t.Fatal(err)
	}
	if err = f.Roster.Verify(f.Root, f.Roster.WorkspaceID); err != nil {
		t.Fatal(err)
	}
	if err = f.Envelope.Verify(f.Roster); err != nil {
		t.Fatal(err)
	}
	if f.Roster.Hash() != f.RosterHash || f.Roster.Members[0].Fingerprint() != f.Fingerprint || f.Envelope.MessageID() != f.MessageID || string(f.Envelope.MLSContext()) != f.Context {
		t.Fatal("wire encoding drift")
	}
	r := f.Roster
	r.Signature = nil
	b, _ := json.Marshal(r)
	if "tincan-roster-v1\x00"+string(b) != f.RosterSigningInput {
		t.Fatal("roster signing bytes drift")
	}
	e := f.Envelope
	e.Signature = nil
	e.Ciphertext = nil
	b, _ = json.Marshal(e)
	if "tincan-message-v2\x00"+string(b) != f.EnvelopeSigningInput {
		t.Fatal("envelope signing bytes drift")
	}
	plain, err := OpenLocal(f.PayloadKey, f.Envelope.Ciphertext, []byte(f.MessageID))
	if err != nil || string(plain) != f.Plaintext {
		t.Fatal("AEAD fixture failed", err)
	}
	for _, field := range []string{"room", "sender", "key", "ciphertext", "capsule", "version"} {
		t.Run(field, func(t *testing.T) {
			e := f.Envelope
			e.Ciphertext = append([]byte(nil), e.Ciphertext...)
			e.Capsule = append([]byte(nil), e.Capsule...)
			switch field {
			case "room":
				e.RoomID = "rm_mls_other"
			case "sender":
				e.SenderID = "ag_other"
			case "key":
				e.Key = "other"
			case "ciphertext":
				e.Ciphertext[0] ^= 1
			case "capsule":
				e.Capsule[0] ^= 1
			case "version":
				e.Version = 1
			}
			if e.Verify(f.Roster) == nil {
				t.Fatal("tampered fixture accepted")
			}
		})
	}
}
