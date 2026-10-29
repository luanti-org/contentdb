# Getting started

## Install dependencies

This is not required, but having the dependencies installed will make your code editor work better.

* Install Python 3.14+
* Install UV
* `uv sync`
* `source .venv/bin/activate`
* (Optional) Install Node.js 24+ and run `npm install`. This is only needed to run the e2e UI tests.

## Set up docker

Docker is the recommended way to develop and deploy ContentDB.

1. Install `docker` and `docker-compose`.

	Debian/Ubuntu:

		sudo apt install docker-ce docker-compose

2. Copy `config.example.cfg` to `config.cfg`.

	1. Set `SECRET_KEY` and `WTF_CSRF_SECRET_KEY` to different random values.

3. (Optional) Set up mail in config.cfg.
   Make sure to set `USER_ENABLE_EMAIL` to True.

4. (Optional) Set up GitHub integration
	1. Make a GitHub OAuth Client at <https://github.com/settings/developers>:
	2. Homepage URL - `http://localhost:5123/`
	3. Authorization callback URL - `http://localhost:5123/user/github/callback/`
	4. Put client id and client secret in `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` in config.cfg.

5. Create .env:

		POSTGRES_USER=contentdb
		POSTGRES_PASSWORD=password
		POSTGRES_DB=contentdb
		FLASK_DEBUG=1
		UPLOADS_DIR=./data/uploads
		COMPOSE_FILE=docker-compose.yml:docker-compose.dev.yml

	`COMPOSE_FILE` enables `docker-compose.dev.yml`, which mounts the source code for hot reloading.
	Leave it out in production.

6. Start docker images:

		docker compose up --build

7. Setup database:

		./utils/run_migrations.sh

8. Create initial data
	1. `./utils/bash.sh`
	2. Either `python utils/setup.py -t` or `python utils/setup.py -o`:
	  	1. `-o` creates just the admin, and static data like tags, and licenses.
	  	2. `-t` will do `-o` and also create test packages. (Recommended)

9. Make uploads writable:

		sudo chown $(whoami):5123 -R data/uploads

10. View at <http://localhost:5123>.
   The admin username is `rubenwardy` and the password is `tuckfrump`.

In the future, starting CDB is as simple as:

	docker compose up --build

With `FLASK_DEBUG=1` and `docker-compose.dev.yml` enabled, changes to python code and templates
are hot reloaded. Restart the worker to update tasks, and restart CDB to update config.

Now consider reading the [Developer Introduction](dev_intro.md).
