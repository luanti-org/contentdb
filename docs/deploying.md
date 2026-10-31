# Deploying

Production runs the images that CI publishes to `ghcr.io/luanti-org/contentdb`, tagged by
full commit SHA. CI only publishes commits on `master` that pass the tests.

The server doesn't need a checkout of the code, and shouldn't have one, so nothing can
build an image there by mistake. It only needs:

* `docker-compose.yml`, downloaded at the commit being deployed, so it matches the image.
* `docker-compose.override.yml`, for anything specific to the server, such as ports and paths.
* `config.cfg`, see `config.example.cfg`.
* `.env`, as in [Getting Started](getting_started.md) but without `COMPOSE_FILE`, with
  `FLASK_DEBUG=0` and `CDB_TAG` set to the full commit SHA.

content.luanti.org is deployed with Ansible, which pins the commit and creates these files.

## Deploying a commit

1. Wait for CI to finish on the commit.

2. Download the compose file for it, and set `CDB_TAG` in `.env` to the full SHA:

		curl -fsSLo docker-compose.yml https://raw.githubusercontent.com/luanti-org/contentdb/<sha>/docker-compose.yml

3. Pull the images. This fails if CI hasn't published the commit, leaving the running
   version untouched:

		docker compose pull

4. Run migrations using the new image:

		docker compose run --rm app sh -c "FLASK_APP=app/__init__.py flask db upgrade"

5. Restart with the new image:

		docker compose up -d --scale worker=4

To roll back, deploy an earlier commit. This doesn't undo migrations.
