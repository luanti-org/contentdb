#!/bin/bash

set -e

docker compose build worker
docker compose up --no-deps -d worker
