# syntax=docker/dockerfile:1
# pfx2gas — full toolchain image: Python 3.11 + uv (converter) + Node 20
# (syntax checks, JS tests) + clasp (Apps Script deploy).
#
# Build:   docker compose build
# Convert: docker compose run --rm pfx2gas convert /workspace/app.msapp -o /workspace/output/app
# Tests:   docker compose run --rm test
# Deploy:  docker compose run --rm clasp login --no-localhost   (once)
#          docker compose run --rm -w /workspace/output/app clasp push --force

FROM node:20-slim AS nodejs

FROM python:3.11-slim AS runtime

# Node binary + npm from the official image (same Debian family; node is
# self-contained — openssl is bundled).
COPY --from=nodejs /usr/local/bin/node /usr/local/bin/node
COPY --from=nodejs /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN set -eux; \
    ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm; \
    ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx; \
    node --version; npm --version

# clasp for `clasp login/push/deploy` of converted apps
RUN npm install -g --no-fund --no-audit --silent @google/clasp \
    && clasp --version

# uv for fast, locked installs
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# Dependencies first (cached unless the lockfile changes); the project itself
# is installed after its source is copied, or the wheel would be empty.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Project code; static/ runtime libs are needed by synthesis
COPY src ./src
COPY static ./static
COPY tests ./tests
COPY scripts ./scripts
COPY README.md .env.example ./

RUN uv sync --frozen

ENV PATH="/app/.venv/bin:${PATH}"

# Default: the converter CLI. Test/soak/clasp services override the entrypoint.
ENTRYPOINT ["/app/.venv/bin/pfx2gas"]
CMD ["--help"]
