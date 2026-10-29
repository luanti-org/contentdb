ARG PYTHON_IMAGE=python:3.14.9-alpine

#
# BUILD
#

FROM ${PYTHON_IMAGE} AS builder

RUN apk add --no-cache uv gcc g++ musl-dev postgresql-dev

WORKDIR /home/cdb

ENV UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3 \
    UV_PROJECT_ENVIRONMENT=/home/cdb/.venv \
    UV_COMPILE_BYTECODE=1

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY translations translations
RUN .venv/bin/pybabel compile -d translations


#
# RUNTIME
#

FROM ${PYTHON_IMAGE}

RUN addgroup --gid 5123 cdb && \
    adduser --uid 5123 -S cdb -G cdb

RUN apk add --no-cache postgresql-libs git bash unzip libmagic libstdc++

# Writable locations
RUN mkdir -p /var/cdb/thumbnails /var/cdb/beat && chown -R cdb:cdb /var/cdb

WORKDIR /home/cdb

ENV PATH=/home/cdb/.venv/bin:$PATH \
    FLASK_CONFIG=/run/config/config.cfg

COPY --from=builder /home/cdb/.venv .venv

COPY utils utils
COPY migrations migrations
COPY app app
COPY --from=builder /home/cdb/translations translations

# Python can't write __pycache__ at runtime
RUN python -m compileall -q app migrations utils

USER cdb
