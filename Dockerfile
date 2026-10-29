ARG PYTHON_IMAGE=python:3.14.9-alpine

#
# BUILD
#

FROM ${PYTHON_IMAGE} AS builder

RUN apk add --no-cache uv gcc g++ musl-dev postgresql-dev

WORKDIR /home/cdb

ENV UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3 \
    UV_PROJECT_ENVIRONMENT=/home/cdb/.venv

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

RUN mkdir /var/cdb && chown cdb:cdb /var/cdb

WORKDIR /home/cdb

ENV PATH=/home/cdb/.venv/bin:$PATH \
    FLASK_CONFIG=/run/config/config.cfg

COPY --from=builder --chown=cdb:cdb /home/cdb/.venv .venv

COPY --chown=cdb:cdb utils utils
COPY --chown=cdb:cdb migrations migrations
COPY --chown=cdb:cdb app app
COPY --from=builder --chown=cdb:cdb /home/cdb/translations translations

USER cdb
