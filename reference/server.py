#!/usr/bin/env python3
"""Loopback Tincan draft reference. Standard library, SQLite, no hosted code."""
import argparse
import copy
import hashlib
import json
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


TOOLS = {
    "workspace_info": ("GET", "/me", []),
    "rooms_list": ("GET", "/rooms", []),
    "channels_list": ("GET", "/channels", []),
    "agents_list": ("GET", "/agents", []),
    "room_members": ("GET", "/rooms/{room_id}/members", ["room_id"]),
    "room_create": ("POST", "/rooms", ["name"]),
    "channel_create": ("POST", "/channels", ["room_id", "name"]),
    "room_member_update": ("PUT", "/rooms/{room_id}/members/{agent_id}", ["room_id", "agent_id", "present"]),
    "message_send": ("POST", "/messages", ["channel_id", "idempotency_key"]),
    "messages_search": ("GET", "/messages", []),
    "invite_create": ("POST", "/invites", ["room_id"]),
    "events_wait": ("GET", "/event-page", []),
}
DESCRIPTOR = {"protocol": "tincan", "versions": ["0.1"],
              "profiles": ["tincan-core/0.1", "tincan-plugin/0.1"],
              "capabilities": [], "tools": sorted(TOOLS)}


def identifier(prefix):
    return prefix + secrets.token_hex(16)


def stamp(value=None):
    return datetime.fromtimestamp(value or time.time(), timezone.utc).isoformat().replace("+00:00", "Z")


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


class Failure(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


def require(condition, status=400, code="invalid_input", message="Invalid request"):
    if not condition:
        raise Failure(status, code, message)


def name(value):
    require(isinstance(value, str) and 1 <= len(value.encode()) <= 80)
    return value


class Store:
    """A serialized, transactionally persisted state machine; intentionally small.

    One process owns one database. State/event allocation is serialized with the
    durable commit, so readers never advance past uncommitted earlier events.
    This is a reference for semantics, not a scalable storage architecture.
    """
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)")
        row = self.db.execute("SELECT body FROM state WHERE id=1").fetchone()
        self.state = json.loads(row[0]) if row else {"agents": {}, "tokens": {}, "rooms": {}, "channels": {}, "invites": {}, "messages": [], "events": [], "receipts": {}}

    def close(self):
        self.db.close()

    def agent(self, token):
        aid = self.state["tokens"].get(digest(token))
        a = self.state["agents"].get(aid)
        require(a and not a.get("revoked"), 401, "unauthorized", "Valid agent credential required")
        return a

    def room(self, a, rid):
        room = self.state["rooms"].get(rid)
        require(room and a["id"] in room["members"] and room["workspace_id"] == a["workspace_id"], 404, "not_found", "Room not accessible")
        return room

    def channel(self, a, cid):
        channel = self.state["channels"].get(cid)
        require(channel, 404, "not_found", "Channel not accessible")
        self.room(a, channel["room_id"])
        return channel

    @staticmethod
    def public(value):
        return {k: v for k, v in value.items() if k not in ("members", "creator", "revoked")}

    def new_agent(self, workspace, display, profile="", admin=False):
        require(isinstance(profile, str) and len(profile) <= 2000)
        aid, token = identifier("ag_"), identifier("tc_")
        a = {"id": aid, "workspace_id": workspace, "name": name(display), "profile": profile,
             "admin": admin, "encryption_mode": "standard", "a2a_enabled": False,
             "browser_only": False, "connected_at": stamp()}
        self.state["agents"][aid] = a
        self.state["tokens"][digest(token)] = aid
        return a, token

    def new_room(self, a, display):
        r = {"id": identifier("room_"), "workspace_id": a["workspace_id"], "name": name(display),
             "members": [a["id"]], "creator": a["id"], "private": False, "archived": False, "encryption_mode": "standard"}
        self.state["rooms"][r["id"]] = r
        return r

    def new_channel(self, a, rid, display, description=""):
        self.room(a, rid)
        require(isinstance(description, str))
        ch = {"id": identifier("ch_"), "room_id": rid, "name": name(display), "description": description,
              "private": False, "archived": False, "encryption_mode": "standard"}
        self.state["channels"][ch["id"]] = ch
        return ch

    def invite(self, a, rid, origin):
        self.room(a, rid)
        token, expiry = secrets.token_urlsafe(16), time.time() + 86400
        self.state["invites"][digest(token)] = {"room_id": rid, "issuer": a["id"], "expires": expiry}
        return {"url": origin + "/join#" + token, "expires_at": stamp(expiry)}

    def events(self, a, after):
        result = []
        for event in self.state["events"]:
            if event["seq"] <= after:
                continue
            ch = self.state["channels"][event["channel_id"]]
            room = self.state["rooms"][ch["room_id"]]
            if a["id"] in room["members"]:
                result.append(event)
        return result[:100]

    def call(self, method, path, token="", body=None, query=None, origin=""):
        body, query = body or {}, query or {}
        require(isinstance(body, dict))
        with self.lock:
            previous = copy.deepcopy(self.state) if method != "GET" else None
            try:
                result = self.dispatch(method, path, token, body, query, origin)
                if previous is not None:
                    with self.db:
                        self.db.execute("INSERT OR REPLACE INTO state VALUES (1,?)", (json.dumps(self.state, separators=(",", ":")),))
                return copy.deepcopy(result)
            except Exception:
                if previous is not None:
                    self.state = previous
                raise

    def dispatch(self, method, path, token, b, q, origin):
        s = self.state
        if method == "POST" and path == "/bootstrap":
            require(not b.get("e2ee"), 400, "unsupported", "Encryption is not supported")
            a, credential = self.new_agent(identifier("ws_"), b.get("agent_name"), b.get("profile", ""), True)
            room = self.new_room(a, b.get("name") or "Shared room")
            self.new_channel(a, room["id"], "general")
            invite = self.invite(a, room["id"], origin)
            return {"token": credential, "agent_id": a["id"], "room_id": room["id"], "room_name": room["name"], "share_url": invite["url"], "share_expires_at": invite["expires_at"]}
        if method == "POST" and path == "/join":
            invite = b.get("invite", "")
            require(isinstance(invite, str))
            item = s["invites"].get(digest(invite))
            require(item and item["expires"] > time.time(), 400, "invalid_invite", "Invite invalid, expired or used")
            issuer = s["agents"][item["issuer"]]
            require(not issuer.get("revoked"), 400, "invalid_invite", "Issuer revoked")
            room = self.room(issuer, item["room_id"])
            a, credential = self.new_agent(room["workspace_id"], b.get("name"), b.get("profile", ""))
            room["members"].append(a["id"])
            del s["invites"][digest(invite)]
            return {"token": credential, "agent_id": a["id"], "room_id": room["id"], "room_name": room["name"]}
        a = self.agent(token)
        if method == "GET" and path == "/me":
            return {"agent": self.public(a), "workspace": {"id": a["workspace_id"], "claimed": False}}
        if path == "/rooms":
            if method == "GET":
                return [self.public(r) for r in s["rooms"].values() if a["id"] in r["members"]]
            if method == "POST":
                require(not b.get("e2ee"), 400, "unsupported", "Encryption is not supported")
                return self.public(self.new_room(a, b.get("name")))
        if path == "/channels":
            if method == "GET":
                return [ch for ch in s["channels"].values() if a["id"] in s["rooms"][ch["room_id"]]["members"]]
            if method == "POST":
                return self.new_channel(a, b.get("room_id"), b.get("name"), b.get("description", ""))
        if path == "/agents" and method == "GET":
            return [self.public(peer) for peer in s["agents"].values() if peer["workspace_id"] == a["workspace_id"] and not peer.get("revoked")]
        parts = path.strip("/").split("/")
        if len(parts) in (3, 4) and parts[0] == "rooms" and parts[2] == "members":
            room = self.room(a, parts[1])
            if method == "GET" and len(parts) == 3:
                return [self.public(s["agents"][aid]) for aid in room["members"] if not s["agents"][aid].get("revoked")]
            require(len(parts) == 4 and method in ("PUT", "DELETE"))
            require(a["admin"] or room["creator"] == a["id"] or (method == "DELETE" and parts[3] == a["id"]), 403, "forbidden", "Room manager required")
            require(not (method == "DELETE" and parts[3] == room["creator"]), 409, "room_owner_required", "Creator must remain a member")
            target = s["agents"].get(parts[3])
            require(target and not target.get("revoked") and target["workspace_id"] == a["workspace_id"], 404, "not_found", "Agent not accessible")
            if method == "PUT" and target["id"] not in room["members"]:
                room["members"].append(target["id"])
            if method == "DELETE" and target["id"] in room["members"]:
                room["members"].remove(target["id"])
                for invitation in s["invites"].values():
                    if invitation["room_id"] == room["id"] and invitation["issuer"] == target["id"]:
                        invitation["expires"] = 0
            return {"ok": True}
        if len(parts) == 2 and parts[0] == "agents" and method == "DELETE":
            target = s["agents"].get(parts[1])
            require(a["admin"], 403, "forbidden", "Admin required")
            require(target and target["workspace_id"] == a["workspace_id"], 404, "not_found", "Agent not accessible")
            target["revoked"] = True
            return {"ok": True}
        if path == "/invites" and method == "POST":
            return self.invite(a, b.get("room_id"), origin)
        if path == "/messages" and method == "POST":
            ch = self.channel(a, b.get("channel_id"))
            text, key = b.get("text"), b.get("idempotency_key")
            require(isinstance(text, str) and text.strip() and len(text.encode()) <= 65536)
            require(isinstance(key, str) and 1 <= len(key.encode()) <= 128)
            mentions = b.get("mentions", [])
            if mentions is None:
                mentions = []
            require(isinstance(mentions, list) and len(mentions) <= 50 and all(isinstance(x, str) for x in mentions))
            metadata = b.get("metadata", {})
            require(len(json.dumps(metadata, ensure_ascii=False).encode()) <= 16384)
            require(not b.get("attachment_ids") and not b.get("encrypted"), 400, "unsupported", "Attachments and encryption are optional and unavailable")
            payload = {"channel_id": ch["id"], "text": text, "metadata": metadata, "mentions": mentions, "reply_to": b.get("reply_to")}
            receipt_key = a["id"] + ":" + key
            receipt = s["receipts"].get(receipt_key)
            if receipt:
                require(receipt["payload"] == payload, 409, "idempotency_conflict", "Key reused for a different message")
                return receipt["message"]
            room = self.room(a, ch["room_id"])
            require(all(aid in room["members"] and not s["agents"][aid].get("revoked") for aid in mentions), 400, "invalid_mention", "Mention requires room membership")
            if payload["reply_to"] is not None:
                require(any(m["id"] == payload["reply_to"] and m["channel_id"] == ch["id"] for m in s["messages"]), 400, "invalid_reply", "Reply must be in this channel")
            msg = dict(payload, id=identifier("msg_"), seq=len(s["messages"]) + 1,
                       agent_id=a["id"], agent_name=a["name"], attachments=[], created_at=stamp())
            s["messages"].append(msg)
            # Deliberately different sequence spaces to catch client confusion.
            event_seq = (s["events"][-1]["seq"] if s["events"] else 0) + 2
            s["events"].append({"seq": event_seq, "kind": "message", "channel_id": ch["id"], "payload": msg})
            s["receipts"][receipt_key] = {"payload": payload, "message": msg}
            return msg
        if path == "/messages" and method == "GET":
            require(not q.get("query") and not q.get("q") and not q.get("metadata") and q.get("mentioned") not in (True, "true"), 400, "unsupported", "Search filters are not implemented")
            cid = q.get("channel_id", "")
            if cid:
                self.channel(a, cid)
            before, after, limit = int(q.get("before", 0)), int(q.get("after", 0)), int(q.get("limit", 50))
            require(before >= 0 and after >= 0 and 1 <= limit <= 100)
            visible = [m for m in s["messages"] if (not cid or cid == m["channel_id"]) and a["id"] in s["rooms"][s["channels"][m["channel_id"]]["room_id"]]["members"] and (not before or m["seq"] < before) and m["seq"] > after]
            return list(reversed(visible))[:limit]
        if path == "/event-page" and method == "GET":
            after = int(q.get("after", 0))
            require(after >= 0)
            return self.events(a, after)
        raise Failure(404, "unsupported", "Operation is not implemented by this server")


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, store):
        self.store = store
        super().__init__(address, Handler)
        self.origin = "http://127.0.0.1:" + str(self.server_port)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass  # No request bodies, credentials, or invitation tokens in logs.

    def reply(self, status, value):
        data = json.dumps(value, separators=(",", ":"), allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def handle_request(self):
        try:
            url = urlsplit(self.path)
            query = {key: value[-1] for key, value in parse_qs(url.query).items()}
            require(not self.headers.get("Transfer-Encoding"), 400, "invalid_input", "Chunked requests unsupported")
            length = int(self.headers.get("Content-Length", "0"))
            require(0 <= length <= 1024 * 1024)
            body = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError())) if length else {}
            require(isinstance(body, dict))
            authorization = self.headers.get("Authorization", "")
            token = authorization[7:] if authorization.startswith("Bearer ") else ""
            if self.command == "GET" and url.path == "/.well-known/tincan.json":
                return self.reply(200, DESCRIPTOR)
            if url.path == "/mcp":
                if self.command != "POST":
                    return self.reply(405, {"error": {"code": "method_not_allowed", "message": "Use POST"}})
                return self.mcp(body, token)
            if self.command == "GET" and url.path == "/join":
                return self.reply(200, {"message": "Use the complete invite URL with a Tincan client."})
            require(url.path.startswith("/api/v1/"), 404, "not_found", "Unknown route")
            path = url.path[len("/api/v1"):]
            if self.command == "GET" and path == "/events":
                after = int(self.headers.get("Last-Event-ID", query.get("after", "0")))
                require(after >= 0)
                return self.stream(token, after)
            value = self.server.store.call(self.command, path, token, body, query, self.server.origin)
            self.reply(200, value)
        except Failure as e:
            self.reply(e.status, {"error": {"code": e.code, "message": e.message}})
        except (ValueError, TypeError, KeyError, RecursionError):
            self.reply(400, {"error": {"code": "invalid_input", "message": "Malformed request"}})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass

    do_GET = do_POST = do_PUT = do_DELETE = handle_request

    def stream(self, token, after):
        store = self.server.store
        store.call("GET", "/event-page", token, query={"after": after})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            try:
                # Keep membership/credential check and emission in one serialized
                # batch. Bound socket writes so slow readers cannot pin the lock.
                self.connection.settimeout(2)
                with store.lock:
                    events = store.events(store.agent(token), after)
                    for event in events:
                        self.wfile.write(("id: %s\ndata: %s\n\n" % (event["seq"], json.dumps(event))).encode())
                        after = event["seq"]
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
            except Failure:
                return
            time.sleep(0.1)

    def mcp(self, request, token):
        require(request.get("jsonrpc") == "2.0" and isinstance(request.get("method"), str))
        rid, method, params = request.get("id"), request["method"], request.get("params", {})
        require(isinstance(params, dict))
        if rid is None:
            self.send_response(202)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        result = None
        if method == "initialize":
            requested = params.get("protocolVersion")
            version = requested if requested in ("2025-03-26", "2025-06-18") else "2025-06-18"
            result = {"protocolVersion": version, "capabilities": {"tools": {}}, "serverInfo": {"name": "tincan-reference", "version": "0.1.0"}}
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": [{"name": key, "description": "Tincan core " + key, "inputSchema": {"type": "object", "additionalProperties": True}} for key in TOOLS]}
        elif method == "tools/call":
            try:
                tool, args = params.get("name"), params.get("arguments", {})
                require(isinstance(args, dict) and tool in TOOLS, 400, "unsupported", "Tool unavailable")
                verb, path, required = TOOLS[tool]
                require(all(key in args for key in required))
                if tool == "room_member_update":
                    require(isinstance(args["present"], bool))
                    verb = "PUT" if args["present"] else "DELETE"
                value = self.server.store.call(verb, path.format(**args), token, args, args, self.server.origin)
                result = {"content": [{"type": "text", "text": json.dumps(value)}], "isError": False}
                if isinstance(value, dict):
                    result["structuredContent"] = value
            except Failure as e:
                result = {"content": [{"type": "text", "text": json.dumps({"error": {"code": e.code, "message": e.message}})}], "isError": True}
        else:
            return self.reply(200, {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "Method not found"}})
        self.reply(200, {"jsonrpc": "2.0", "id": rid, "result": result})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--database", default="tincan-reference.sqlite")
    args = parser.parse_args()
    os.umask(0o077)
    store = Store(args.database)
    server = Server(("127.0.0.1", args.port), store)
    print("Tincan reference listening on " + server.origin, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        store.close()


if __name__ == "__main__":
    main()
