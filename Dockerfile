FROM python:3.13-slim

WORKDIR /app

# Copy uv binary from official image (fast, no pip install)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy

# Install deps only (cached layer, no dev deps for production)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

# Copy source, install project, fix line endings, create runtime dirs
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev \
    && sed -i 's/\r$//' entrypoint.sh \
    && chmod +x entrypoint.sh \
    && mkdir -p uploads

EXPOSE 8000

CMD ["./entrypoint.sh"]
