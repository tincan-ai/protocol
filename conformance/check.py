#!/usr/bin/env python3
"""Black-box core scenario. Creates scratch data; never use existing credentials."""
import argparse
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class Client:
    def __init__(self, origin, token=""):
        u = urllib.parse.urlsplit(origin)
        if u.scheme not in ("http", "https") or not u.netloc or u.username or u.password or u.path not in ("", "/") or u.query or u.fragment:
            raise ValueError("Use a server origin, not a URL containing credentials or a path")
        if u.scheme == "http" and u.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError("Non-loopback servers require HTTPS")
        self.origin, self.token = origin.rstrip("/"), token
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, method, path, body=None, expected=(200,)):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.origin + path, data, headers, method=method)
        try:
            response = self.opener.open(request, timeout=35)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            payload = json.loads(response.read())
            if response.code not in expected:
                code = payload.get("error", {}).get("code", "unknown") if isinstance(payload, dict) else "unknown"
                raise AssertionError("%s %s returned %s (%s)" % (method, path, response.code, code))
            return payload

    def api(self, method, path, body=None, expected=(200,)):
        return self.request(method, "/api/v1" + path, body, expected)

    def events_until(self, after, wanted, last_event_id=None):
        headers = {"Authorization": "Bearer " + self.token, "Accept": "text/event-stream"}
        if last_event_id is not None:
            headers["Last-Event-ID"] = str(last_event_id)
        req = urllib.request.Request(self.origin + "/api/v1/events?after=" + str(after), headers=headers)
        events, deadline = [], time.monotonic() + 10
        with self.opener.open(req, timeout=10) as response:
            assert response.headers.get_content_type() == "text/event-stream"
            event_id = None
            while time.monotonic() < deadline:
                line = response.readline().decode().strip()
                if line.startswith("id:"):
                    event_id = int(line[3:].strip())
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:])
                assert event_id == event["seq"]
                assert event["seq"] > (events[-1]["seq"] if events else (last_event_id if last_event_id is not None else after))
                events.append(event)
                if event.get("payload", {}).get("id") == wanted:
                    return events
        raise AssertionError("Expected message did not arrive through replay")


def scenario(origin):
    anonymous = Client(origin)
    descriptor = anonymous.request("GET", "/.well-known/tincan.json")
    assert descriptor["protocol"] == "tincan" and "0.1" in descriptor["versions"]
    assert "tincan-core/0.1" in descriptor["profiles"]
    unique = secrets.token_hex(4)
    alice = anonymous.api("POST", "/bootstrap", {"name": "Protocol check " + unique, "agent_name": "Alice-" + unique, "profile": "Conformance scratch agent"})
    a = Client(origin, alice["token"])
    room = alice["room_id"]
    channels = a.api("GET", "/channels")
    channel = next(c["id"] for c in channels if c["room_id"] == room and not c["private"])

    def join(display):
        invite = a.api("POST", "/invites", {"room_id": room})
        token = urllib.parse.urlsplit(invite["url"]).fragment
        joined = anonymous.api("POST", "/join", {"invite": token, "name": display + "-" + unique})
        anonymous.api("POST", "/join", {"invite": token, "name": "Duplicate-" + unique}, expected=(400, 409, 410))
        return joined, Client(origin, joined["token"])

    bob, b = join("Bob")
    message = {"channel_id": channel, "text": "Before disconnect", "mentions": [bob["agent_id"]], "idempotency_key": "first-" + unique, "metadata": {"test": True}}
    first = a.api("POST", "/messages", message)
    assert a.api("POST", "/messages", message)["id"] == first["id"]
    conflict = a.api("POST", "/messages", dict(message, text="Conflicting retry"), expected=(409,))
    assert conflict["error"]["code"] == "idempotency_conflict"
    initial = b.events_until(0, first["id"])
    cursor = initial[-1]["seq"]
    second = a.api("POST", "/messages", {"channel_id": channel, "text": "While Bob is offline", "reply_to": first["id"], "idempotency_key": "second-" + unique})
    carol, c = join("Carol")
    history = c.api("GET", "/messages?channel_id=" + channel)
    assert [m["id"] for m in history[:2]] == [second["id"], first["id"]]
    replay = b.events_until(0, second["id"], last_event_id=cursor)
    assert first["id"] not in [event.get("payload", {}).get("id") for event in replay]
    assert replay[-1]["payload"]["reply_to"] == first["id"]
    assert b.api("GET", "/me")["agent"]["id"] == bob["agent_id"]
    older = a.api("GET", "/messages?" + urllib.parse.urlencode({"channel_id": channel, "before": second["seq"], "limit": 1}))
    assert older[0]["id"] == first["id"]
    private_room = a.api("POST", "/rooms", {"name": "Separate room"})
    private_channel = a.api("POST", "/channels", {"room_id": private_room["id"], "name": "restricted"})
    assert private_room["id"] not in [r["id"] for r in c.api("GET", "/rooms")]
    a.api("POST", "/messages", {"channel_id": private_channel["id"], "text": "Invalid mention", "mentions": [carol["agent_id"]], "idempotency_key": "invalid-mention"}, expected=(400,))
    a.api("POST", "/messages", {"channel_id": private_channel["id"], "text": "Invalid reply", "reply_to": first["id"], "idempotency_key": "invalid-reply"}, expected=(400,))
    b.api("PUT", "/rooms/" + room + "/members/" + carol["agent_id"], {}, expected=(403,))
    a.api("DELETE", "/rooms/" + room + "/members/" + bob["agent_id"])
    hidden = b.api("GET", "/messages?channel_id=" + channel, expected=(200, 403, 404))
    assert hidden == [] or isinstance(hidden, dict) and "error" in hidden
    b.api("POST", "/messages", {"channel_id": channel, "text": "Not allowed", "idempotency_key": "removed"}, expected=(403, 404))
    a.api("PUT", "/rooms/" + private_room["id"] + "/members/" + bob["agent_id"], {})
    sentinel = a.api("POST", "/messages", {"channel_id": private_channel["id"], "text": "New room only", "idempotency_key": "sentinel"})
    filtered = b.events_until(0, sentinel["id"])
    assert not any(event.get("channel_id") == channel for event in filtered)
    a.api("DELETE", "/agents/" + bob["agent_id"])
    b.api("GET", "/me", expected=(401,))
    b.api("GET", "/events?after=0", expected=(401,))
    return {"core_scenario": "passed", "checks": ["bootstrap", "single-use invite", "idempotency", "conflict", "SSE replay", "Last-Event-ID", "late join history", "pagination", "membership isolation", "mention/reply scope", "revocation"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", required=True)
    args = parser.parse_args()
    print(json.dumps(scenario(args.server), indent=2))
