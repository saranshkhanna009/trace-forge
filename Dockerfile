FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY demo ./demo

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir ".[api]"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "traceforge.api:app", "--host", "0.0.0.0", "--port", "8000"]
