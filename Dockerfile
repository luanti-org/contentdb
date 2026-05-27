FROM python:3.14.5-alpine

RUN addgroup --gid 5123 cdb && \
    adduser --uid 5123 -S cdb -G cdb

WORKDIR /home/cdb

RUN \
	apk add --no-cache postgresql-libs git bash unzip uv libmagic && \
	apk add --no-cache --virtual .build-deps gcc musl-dev postgresql-dev g++

RUN mkdir /var/cdb
RUN chown -R cdb:cdb /var/cdb

USER cdb

COPY pyproject.toml pyproject.toml
COPY uv.lock uv.lock

ENV UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3 \
    UV_PROJECT_ENVIRONMENT=/home/cdb/.venv

RUN uv sync --locked --no-install-project
ENV PATH=/home/cdb/.venv/bin:$PATH

COPY utils utils
COPY config.cfg config.cfg
COPY migrations migrations
COPY app app
COPY translations translations

USER root

RUN pybabel compile -d translations
RUN chown -R cdb:cdb /home/cdb

USER cdb
