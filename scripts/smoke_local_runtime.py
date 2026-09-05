"""Exercise the running Docker frontend/proxy/API; remove only our synthetic vehicle.

Run with backend/.venv/bin/python from the repository root. Demo credentials are
read from environment/.env, never logged. Refuses to invoke a paid LLM provider.
"""
import json
import io
import os
from pathlib import Path
import uuid

from dotenv import load_dotenv
import httpx
from PIL import Image


def smoke():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    base = os.getenv("SMOKE_BASE_URL", "http://localhost:3000").rstrip("/")
    direct_api = os.getenv("SMOKE_DIRECT_API_URL", "http://localhost:8000/api").rstrip("/")
    api = base + "/backend-api"
    checks = []

    def request(client, method, path, expected=200, **kwargs):
        response = client.request(method, path, **kwargs)
        if response.status_code != expected:
            raise AssertionError(f"{method} {path}: expected {expected}, got {response.status_code}")
        checks.append({"method": method, "path": path, "status": response.status_code})
        return response

    with httpx.Client(base_url=api, timeout=60, trust_env=False) as client:
        request(client, "GET", base + "/login")
        request(client, "GET", base + "/")
        proxied = request(client, "GET", "/health").json()
        direct = request(client, "GET", direct_api + "/health").json()
        assert proxied == direct and proxied["llm_provider"] == "mock"
        request(client, "GET", "/vehicles", expected=401)
        request(client, "POST", "/auth/login", expected=401, json={"email": "runtime-nobody@example.com", "password": "invalid-runtime-password"})
        login = request(client, "POST", "/auth/login", json={
            "email": os.getenv("DEMO_ADMIN_EMAIL", "admin@example.com"),
            "password": os.getenv("DEMO_ADMIN_PASSWORD", "demo-change-me"),
        })
        assert "HttpOnly" in login.headers["set-cookie"] and "SameSite=strict" in login.headers["set-cookie"]
        assert request(client, "GET", "/auth/me").json()["role"] == "admin"
        before = request(client, "GET", "/vehicles?page_size=100").json()
        for vehicle in before["items"]:
            request(client, "GET", f"/vehicles/{vehicle['id']}")
        sessions = request(client, "GET", "/diagnostic-sessions?page_size=100").json()
        for session in sessions["items"]:
            detail = request(client, "GET", f"/diagnostics/{session['id']}").json()
            assert detail["analysis_status"] in {"current", "not_available", "legacy_requires_review"}
            assert detail["analysis"] is None or "safetyAssessment" in detail["analysis"]
        request(client, "GET", "/dtcs?page_size=5")
        marker = "runtime-smoke-" + uuid.uuid4().hex
        created = request(client, "POST", "/vehicles", expected=201, json={
            "make": "Demo Motors", "model": marker, "year": 2020,
            "engine_name": "Synthetic runtime test", "engine_code": "DEMO-ENG-01",
            "is_demo_vehicle": True, "notes": marker,
        }).json()
        vehicle_id = created["id"]
        try:
            assert not {"vin", "vin_encrypted", "vin_fingerprint"} & created.keys()
            assert request(client, "GET", f"/vehicles/{vehicle_id}").json()["model"] == marker
            assert request(client, "GET", "/vehicles").json()["total"] == before["total"] + 1
            case = request(client, "POST", "/diagnostics", expected=201, json={
                "vehicle_id": vehicle_id, "symptoms": "Synthetic local runtime verification",
            }).json()
            path = f"/diagnostics/{case['id']}"
            png = io.BytesIO()
            Image.new("RGB", (2, 2), "white").save(png, "PNG")
            images = request(client, "POST", path + "/images", expected=201,
                             files={"files": ("runtime-test.png", png.getvalue(), "image/png")}).json()
            # Same prefix mapping used by the browser: /api/... -> /backend-api/...
            image_path = images[0]["url"].removeprefix("/api")
            request(client, "GET", image_path)
            request(client, "POST", path + "/fault-codes", expected=201, json={"fault_codes": [{"code": "P1351"}]})
            analysis = request(client, "POST", path + "/analyze").json()
            assert analysis["hypotheses"] == []
            assert analysis["safetyAssessment"]["decisionSource"] == "safety_engine"
            assert analysis["interpretedFaultCodes"][0]["meaning"] == "Definition unavailable for this vehicle configuration."
            assert request(client, "GET", path).json()["analysis_status"] == "current"
        finally:
            # The ID is solely the successful creation result of this run.
            request(client, "DELETE", f"/vehicles/{vehicle_id}", expected=204)
        request(client, "GET", f"/vehicles/{vehicle_id}", expected=404)
        request(client, "GET", path, expected=404)
        request(client, "GET", image_path, expected=404)
        assert request(client, "GET", "/vehicles").json()["total"] == before["total"]
        assert request(client, "GET", "/diagnostic-sessions").json()["total"] == sessions["total"]
        request(client, "POST", "/auth/logout", expected=204)
        request(client, "GET", "/auth/me", expected=401)
        request(client, "POST", "/auth/login", json={
            "email": os.getenv("DEMO_TECHNICIAN_EMAIL", "technician@example.com"),
            "password": os.getenv("DEMO_TECHNICIAN_PASSWORD", "demo-tech-change-me"),
        })
        assert request(client, "GET", "/auth/me").json()["role"] == "technician"
        request(client, "GET", "/vehicles")
        request(client, "POST", "/auth/logout", expected=204)
    print(json.dumps({"result": "passed", "checks": checks, "synthetic_data_removed": True,
                      "retained_vehicles": before["total"], "retained_diagnostics": sessions["total"]}, indent=2))


if __name__ == "__main__":
    smoke()
