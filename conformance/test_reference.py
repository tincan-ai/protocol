import concurrent.futures
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from reference.server import Server, Store
from check import Client, scenario


class ReferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.temp.name) / "state.sqlite")
        self.store = Store(self.path)
        self.server = Server(("127.0.0.1", 0), self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.client = Client(self.server.origin)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        # SSE handlers may still be unwinding; they only access state under lock.
        with self.store.lock:
            self.store.close()
        self.temp.cleanup()

    def bootstrap(self):
        row = self.client.api("POST", "/bootstrap", {"name": "Test", "agent_name": "Alice"})
        a = Client(self.server.origin, row["token"])
        channel = a.api("GET", "/channels")[0]["id"]
        return row, a, channel

    def test_core_scenario(self):
        self.assertEqual(scenario(self.server.origin)["core_scenario"], "passed")

    def test_concurrent_retry_restart_and_revoked_issuer(self):
        row, a, channel = self.bootstrap()
        payload = {"channel_id": channel, "text": "One durable send", "idempotency_key": "same-key"}
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            messages = list(pool.map(lambda _: a.api("POST", "/messages", payload), range(16)))
        self.assertEqual(len({m["id"] for m in messages}), 1)
        self.assertEqual(len(self.store.state["events"]), 1)
        # Reopen from committed SQLite state, with no shared Python objects.
        reopened = Store(self.path)
        try:
            self.assertEqual(reopened.call("POST", "/messages", row["token"], payload)["id"], messages[0]["id"])
            self.assertEqual(len(reopened.state["events"]), 1)
        finally:
            reopened.close()
        invite = a.api("POST", "/invites", {"room_id": row["room_id"]})
        a.api("DELETE", "/agents/" + row["agent_id"])
        self.client.api("POST", "/join", {"invite": invite["url"].split("#")[1], "name": "Late"}, expected=(400,))

    def test_cross_workspace_and_revoked_replay(self):
        alice, a, channel = self.bootstrap()
        other = self.client.api("POST", "/bootstrap", {"name": "Other", "agent_name": "Other"})
        outsider = Client(self.server.origin, other["token"])
        outsider.api("GET", "/messages?channel_id=" + channel, expected=(404,))
        a.api("PUT", "/rooms/" + alice["room_id"] + "/members/" + other["agent_id"], {}, expected=(404,))
        invite = a.api("POST", "/invites", {"room_id": alice["room_id"]})
        bob = self.client.api("POST", "/join", {"invite": invite["url"].split("#")[1], "name": "Bob"})
        a.api("POST", "/messages", {"channel_id": channel, "text": "Secret", "idempotency_key": "x"})
        a.api("DELETE", "/rooms/" + alice["room_id"] + "/members/" + bob["agent_id"])
        self.assertEqual(self.store.call("GET", "/event-page", bob["token"], query={"after": 0}), [])

    @unittest.skipUnless(os.environ.get("TINCAN_PLUGIN_BIN"), "Set TINCAN_PLUGIN_BIN to test the actual sidecar/plugin")
    def test_actual_plugin(self):
        def start():
            child = subprocess.Popen([os.environ["TINCAN_PLUGIN_BIN"], "sidecar", "--server", self.server.origin, "--state-dir", self.temp.name + "/client"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            messages = queue.Queue()
            thread = threading.Thread(target=lambda: [messages.put(json.loads(line)) for line in child.stdout], daemon=True)
            thread.start()
            return child, messages, thread

        def stop(child, thread):
            child.stdin.close()
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
            thread.join(timeout=2)
            child.stdout.close()
            child.stderr.close()

        process, output, reader = start()
        counter = 0

        def call(method, params):
            nonlocal counter
            counter += 1
            process.stdin.write(json.dumps({"id": counter, "method": method, "params": params}) + "\n")
            process.stdin.flush()
            while True:
                try:
                    response = output.get(timeout=20)
                except queue.Empty:
                    self.fail("Plugin did not respond to " + method)
                if response.get("id") == counter:
                    return response

        try:
            first = call("connect", {"name": "PluginAlice", "workspace": "Plugin test"})
            self.assertNotIn("error", first)
            a = first["result"]
            self.assertNotIn("setup_error", a)
            second = call("connect", {"name": "PluginBob", "url": a["share_url"]})
            self.assertNotIn("error", second)
            b = second["result"]
            self.assertNotIn("setup_error", b)
            sent = call("message_send", {"connection": a["connection"], "channel_id": a["channel_id"], "text": "Independent server", "mentions": [b["agent_id"]], "idempotency_key": "plugin-send"})
            self.assertNotIn("error", sent)
            history = call("messages_search", {"connection": b["connection"], "channel_id": a["channel_id"]})
            self.assertNotIn("error", history)
            self.assertIn(sent["result"]["id"], [m["id"] for m in history["result"]])
            unsupported = call("pages_list", {"connection": a["connection"], "channel_id": a["channel_id"]})
            self.assertIn("does not support", unsupported["error"])
            resumed = call("connect", {"connection": b["connection"]})
            self.assertEqual(resumed["result"]["agent_id"], b["agent_id"])
            status = call("status", {"connection": a["connection"]})
            self.assertEqual(status["result"]["server_protocol"]["capabilities"], [])
            stop(process, reader)
            process, output, reader = start()
            restarted = call("connect", {"connection": b["connection"]})
            self.assertNotIn("error", restarted)
            self.assertEqual(restarted["result"]["agent_id"], b["agent_id"])
            self.assertNotIn("setup_error", restarted["result"])
            history = call("messages_search", {"connection": b["connection"], "channel_id": a["channel_id"]})
            self.assertIn(sent["result"]["id"], [m["id"] for m in history["result"]])
        finally:
            if process.poll() is None:
                stop(process, reader)


if __name__ == "__main__":
    unittest.main()
