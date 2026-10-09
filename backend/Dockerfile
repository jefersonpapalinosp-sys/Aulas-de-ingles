# Imagem de desenvolvimento: uv + hot reload.
# A de produção entra na S5, junto com o compose.prod.yml.
FROM public.ecr.aws/docker/library/python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Camada de dependências separada do código, para o cache do Docker valer a pena.
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-install-project --group dev

COPY . .
RUN uv sync --group dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
