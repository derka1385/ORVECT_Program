import os
os.environ["DATABASE_URL"] = "sqlite:///./test.db"
os.environ["APP_ENVIRONMENT"] = "test"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["VIN_PROVIDER"] = "mock"
os.environ["REGISTRATION_PROVIDER"] = "mock"
os.environ["VEHICLE_PROVIDER_PRIMARY"] = "mock"
os.environ["VEHICLE_PROVIDER_FALLBACKS"] = ""
os.environ["VEHICLE_LOOKUP_ENABLE_MOCK"] = "true"
import pytest
from fastapi.testclient import TestClient
from app.database.models import Base
from app.database.session import SessionLocal, engine
from app.main import app
from app.seed import seed

@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = SessionLocal()
    seed(db)
    db.close()
    yield

@pytest.fixture
def client():
    client=TestClient(app, raise_server_exceptions=True)
    response=client.post("/api/auth/login",json={"email":"admin@example.com","password":"demo-change-me"})
    assert response.status_code==200
    return client
