"""Exercise the running API with a manufacturer-specific P1351 session."""
import json
import os
from urllib.request import Request, urlopen

API = os.getenv("API_URL", "http://localhost:8000/api")
VEHICLE_ID = "00000000-0000-0000-0000-000000000003"


def call(path, method="GET", payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(f"{API}{path}", data=body, method=method)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    with urlopen(request) as response:
        return json.load(response)


session = call(
    "/diagnostic-sessions",
    "POST",
    {"vehicle_profile_id": VEHICLE_ID, "customer_complaint": "Smoke test P1351"},
)
call(
    f"/diagnostic-sessions/{session['id']}/observations",
    "POST",
    {"observation_type": "DTC", "key": "P1351", "value": {"status": "confirmed"}, "source": "smoke_test"},
)
analysis = call(f"/diagnostic-sessions/{session['id']}/analyze", "POST")
steps = call(f"/diagnostic-sessions/{session['id']}/steps")
assert analysis["hypotheses"][0]["suspected_component"] == "not_determined"
assert steps[0]["title"] == "Valider le contexte technique de P1351"
print(json.dumps({"session_id": session["id"], "summary": analysis["summary"], "step": steps[0]["title"]}, ensure_ascii=False))
