package e2ee

import (
	"bytes"
	"context"
	"encoding/json"
	"testing"
)

func TestIndependentRoomEnvelopeLifecycle(t *testing.T) {
	owner, _ := NewIdentity()
	peer, _ := NewIdentity()
	room := "rm_mls_00000000000000000000000000000002"
	group := "ws_test/room/" + room
	a := &mlsPeer{identity: *owner, group: group}
	b := &mlsPeer{identity: *peer, group: group}
	ownerKP := a.run(t, "key_package", nil, nil, nil)
	a.run(t, "create", nil, nil, nil)
	beforeJoin := a.run(t, "encrypt", []byte("before admission"), nil, nil)
	kp := b.run(t, "key_package", nil, nil, nil)
	added := a.run(t, "add", kp.Data, nil, peer.SigningKey[32:])
	a.run(t, "finalize", nil, nil, nil)
	b.run(t, "join", added.Welcome, nil, nil)
	if _, err := MLS(context.Background(), MLSRequest{Op: "decrypt", State: b.state, SigningKey: peer.SigningKey, Group: group, Data: beforeJoin.Data}); err == nil {
		t.Fatal("new member read pre-admission content")
	}
	da, _ := owner.Device("ag_owner")
	db, _ := peer.Device("ag_peer")
	da.Protocol = 2
	db.Protocol = 2
	da.KeyPackage = ownerKP.Data
	db.KeyPackage = kp.Data
	r := Roster{RoomID: room, WorkspaceID: "ws_test", Epoch: 2, Protocol: 2, Members: []Device{da, db}}
	if err := r.Sign(*owner); err != nil {
		t.Fatal(err)
	}
	for _, kind := range []string{"message", "file"} {
		e := Envelope{RoomGroup: true, RoomID: room, Kind: kind, Version: 2, WorkspaceID: r.WorkspaceID, ChannelID: "ch_room_" + room + "_test", SenderID: da.AgentID, Key: kind + "-one", Epoch: r.Epoch, RosterHash: r.Hash()}
		plain := []byte(`{"text":"hello","metadata":{},"attachments":[]}`)
		if kind == "file" {
			plain = []byte("{\"name\":\"hello.txt\",\"mime\":\"text/plain\"}\nhello")
		}
		key := bytes.Repeat([]byte{7}, 32)
		var err error
		e.Ciphertext, err = SealLocal(key, plain, []byte(e.MessageID()))
		if err != nil {
			t.Fatal(err)
		}
		e.PayloadHash = PayloadHash(e.Ciphertext)
		sealed := a.run(t, "encrypt", key, e.MLSContext(), nil)
		e.Capsule = sealed.Data
		if err = e.SignMLS(*owner); err != nil {
			t.Fatal(err)
		}
		// Serialize on transport, then verify through the public binding.
		wire, _ := json.Marshal(e)
		var got Envelope
		if err = json.Unmarshal(wire, &got); err != nil {
			t.Fatal(err)
		}
		if err = got.Verify(r); err != nil {
			t.Fatal(err)
		}
		wrong := &mlsPeer{identity: *peer, group: "ws_test/room/rm_mls_other"}
		wrong.run(t, "create", nil, nil, nil)
		if _, err = MLS(context.Background(), MLSRequest{Op: "decrypt", State: wrong.state, SigningKey: peer.SigningKey, Group: wrong.group, Data: got.Capsule}); err == nil {
			t.Fatal("other room decrypted capsule")
		}
		out := b.run(t, "decrypt", got.Capsule, nil, nil)
		if !bytes.Equal(out.AAD, got.MLSContext()) || !bytes.Equal(out.Sender, owner.SigningKey[32:]) {
			t.Fatal("unbound sender/context")
		}
		opened, err := OpenLocal(out.Data, got.Ciphertext, []byte(got.MessageID()))
		if err != nil || !bytes.Equal(opened, plain) {
			t.Fatal("payload round trip", err)
		}
		if _, err = MLS(context.Background(), MLSRequest{Op: "decrypt", State: b.state, SigningKey: peer.SigningKey, Group: group, Data: got.Capsule}); err == nil {
			t.Fatal("duplicate capsule accepted")
		}
	}
}
