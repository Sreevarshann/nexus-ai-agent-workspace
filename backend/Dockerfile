FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src UV_COMPILE_BYTECODE=1
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev && useradd -r -u 10001 nexus && mkdir -p /data && chown nexus /data
ENV PATH="/app/.venv/bin:$PATH"
USER nexus
EXPOSE 8010
CMD ["uvicorn", "nexus.main:app", "--host", "0.0.0.0", "--port", "8010"]
