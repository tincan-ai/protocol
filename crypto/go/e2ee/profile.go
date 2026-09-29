package e2ee

import (
	"errors"
	"slices"
)

const Profile = "tincan-e2ee-mls/0.1"

// RequireProfile checks an already fetched, validated discovery descriptor.
// It never fetches a URL, chooses an origin, or grants permission to send.
// A missing descriptor or the legacy bare e2ee capability cannot pass.
func RequireProfile(protocol string, versions, profiles, capabilities []string) error {
	if protocol != "tincan" || !slices.Contains(versions, "0.1") || !slices.Contains(profiles, "tincan-core/0.1") || !slices.Contains(profiles, Profile) || !slices.Contains(capabilities, "e2ee") {
		return errors.New("server does not advertise the exact Tincan E2EE MLS profile; plaintext fallback is forbidden")
	}
	return nil
}
