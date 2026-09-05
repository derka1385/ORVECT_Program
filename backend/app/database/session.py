from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

database_url=settings.database_url
if database_url.startswith("postgres://"):
    database_url="postgresql+psycopg://"+database_url.removeprefix("postgres://")
elif database_url.startswith("postgresql://"):
    database_url="postgresql+psycopg://"+database_url.removeprefix("postgresql://")
connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
engine = create_engine(database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()
