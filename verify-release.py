import hashlib
import http.client
import json
import subprocess
from html.parser import HTMLParser


def get(port, path):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=15)
    conn.request("GET", path)
    response = conn.getresponse()
    body = response.read()
    status = response.status
    conn.close()
    return status, body


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        url = values.get("src") if tag == "script" else values.get("href")
        if url and url.startswith("/assets/"):
            self.urls.add(url)


for port in [18135, 18136]:
    status, body = get(port, "/health")
    assert status == 200 and json.loads(body)["status"] == "ok"

old_status, old_settings = get(18135, "/api/v1/settings/public")
new_status, new_settings = get(18136, "/api/v1/settings/public")
assert old_status == new_status == 200
assert json.loads(old_settings) == json.loads(new_settings), "Public settings drift"

old_status, old_body = get(18135, "/login")
new_status, new_body = get(18136, "/login")
assert old_status == new_status == 200
old_assets, new_assets = Assets(), Assets()
old_assets.feed(old_body.decode())
new_assets.feed(new_body.decode())
assert old_assets.urls and old_assets.urls == new_assets.urls
for url in sorted(old_assets.urls):
    old_status, old_body = get(18135, url)
    new_status, new_body = get(18136, url)
    assert old_status == new_status == 200, url
    assert hashlib.sha256(old_body).digest() == hashlib.sha256(new_body).digest(), url

for path in ["/keys", "/admin/accounts", "/admin/subscriptions", "/admin/announcements", "/admin/channel-monitors", "/admin/scheduler"]:
    status, body = get(18136, path)
    assert status == 200 and b'<div id="app">' in body, path

baseline = json.loads(subprocess.check_output(["docker", "inspect", "sub2api-v022-production-candidate-20260908"]))[0]
candidate = json.loads(subprocess.check_output(["docker", "inspect", "sub2api-v022-scheduler-recovery-20260908"]))[0]
assert candidate["State"]["Health"]["Status"] == baseline["State"]["Health"]["Status"] == "healthy"
for property_name in ["Binds", "NetworkMode"]:
    assert candidate["HostConfig"][property_name] == baseline["HostConfig"][property_name]

log_result = subprocess.run(["docker", "logs", "--since", "10m", candidate["Id"]], capture_output=True, check=True)
logs = log_result.stdout + log_result.stderr
assert b"panic:" not in logs and b"fatal error:" not in logs
version = subprocess.check_output(["docker", "exec", candidate["Id"], "/app/sub2api", "--version"], stderr=subprocess.STDOUT).decode()
assert "0.2.2 (commit: buaga-custom-v0.2.2-scheduler-recovery-20260908" in version
print(json.dumps({"health": "both healthy", "frontend_entry_assets_identical": len(old_assets.urls), "page_routes": 6, "version": "0.2.2", "data_mounts_and_network_match": True}))
