FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock pyproject.toml alembic.ini ./
COPY requirements-firebase.txt ./
COPY alembic ./alembic
COPY app ./app
RUN pip install --no-cache-dir -r requirements.lock -r requirements-firebase.txt && pip install --no-cache-dir --no-deps .
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
