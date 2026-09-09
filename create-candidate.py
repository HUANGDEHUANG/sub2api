import copy
import http.client
import json
import socket
import sys
from urllib.parse import quote

BASE = "sub2api-v023-preserved-20260908"
CANDIDATE = "sub2api-v023-redis-active-20260908"
IMAGE = "sub2api:custom-v0.2.3-buaga-redis-active-20260908"


class DockerConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(60)
        self.sock.connect("/var/run/docker.sock")


def docker(method, path, payload=None):
    conn = DockerConnection("localhost", timeout=60)
    encoded = json.dumps(payload).encode() if payload is not None else None
    conn.request(method, path, encoded, {"Content-Type": "application/json"})
    response = conn.getresponse()
    data = response.read()
    conn.close()
    if response.status >= 300:
        # Docker errors can include arguments: do not echo configuration secrets.
        raise RuntimeError(f"Docker {method} {path} returned HTTP {response.status}")
    return json.loads(data) if data else {}


def effective_env(config):
    return dict(item.split("=", 1) for item in config["Env"])


baseline = docker("GET", f"/containers/{BASE}/json")
assert baseline["State"]["Running"] and baseline["State"]["Health"]["Status"] == "healthy"
assert baseline["Config"]["Image"] == "sub2api:custom-v0.2.3-buaga-preserved-20260908"

if sys.argv[1:] == ["create"]:
    docker("GET", f"/images/{quote(IMAGE, safe='')}/json")
    payload = copy.deepcopy(baseline["Config"])
    payload["Image"] = IMAGE
    payload.pop("Hostname", None)
    payload["Env"] = [
        item for item in payload["Env"]
        if not item.startswith("GATEWAY_SCHEDULING_SKIP_STARTUP_CLEANUP=")
    ] + ["GATEWAY_SCHEDULING_SKIP_STARTUP_CLEANUP=true"]
    payload["Labels"] = {
        **payload.get("Labels", {}),
        "buaga.release": "v0.2.3-redis-active-20260908",
        "buaga.rollback": BASE,
    }
    payload["HostConfig"] = copy.deepcopy(baseline["HostConfig"])
    payload["HostConfig"]["LogConfig"] = {"Type": "json-file", "Config": {"max-size": "50m", "max-file": "5"}}
    payload["HostConfig"]["PortBindings"] = {
            "8080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "18147"}]
    }
    docker("POST", f"/containers/create?name={CANDIDATE}", payload)
    docker("POST", f"/containers/{CANDIDATE}/start")

candidate = docker("GET", f"/containers/{CANDIDATE}/json")
before = effective_env(baseline["Config"])
after = effective_env(candidate["Config"])
before["GATEWAY_SCHEDULING_SKIP_STARTUP_CLEANUP"] = "true"
assert after == before, "Unexpected environment drift"
assert candidate["HostConfig"]["Binds"] == baseline["HostConfig"]["Binds"]
assert candidate["HostConfig"]["NetworkMode"] == baseline["HostConfig"]["NetworkMode"]
assert candidate["Config"]["Image"] == IMAGE
print(json.dumps({
    "candidate": CANDIDATE,
    "running": candidate["State"]["Running"],
    "health": candidate["State"].get("Health", {}).get("Status"),
    "configuration_match": True,
    "shared_data_and_redis": True,
    "startup_cleanup_skipped": True,
}))
