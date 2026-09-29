package e2ee

import "testing"

func TestProfileNegotiationFailsClosed(t *testing.T) {
	good := []string{"tincan-core/0.1", Profile}
	if err := RequireProfile("tincan", []string{"0.1"}, good, []string{"e2ee"}); err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		name, protocol                   string
		versions, profiles, capabilities []string
	}{
		{"no descriptor", "", nil, nil, nil},
		{"legacy flag", "tincan", []string{"0.1"}, []string{"tincan-core/0.1"}, []string{"e2ee"}},
		{"unknown profile version", "tincan", []string{"0.1"}, []string{"tincan-core/0.1", "tincan-e2ee-mls/0.2"}, []string{"e2ee"}},
		{"capability disappeared", "tincan", []string{"0.1"}, good, nil},
		{"core missing", "tincan", []string{"0.1"}, []string{Profile}, []string{"e2ee"}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			if RequireProfile(tc.protocol, tc.versions, tc.profiles, tc.capabilities) == nil {
				t.Fatal("unsupported encryption accepted")
			}
		})
	}
}
