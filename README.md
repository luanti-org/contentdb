# Content Database
![Build Status](https://github.com/minetest/contentdb/workflows/test/badge.svg)

Content database for Minetest mods, games, and more.\
Developed by rubenwardy, license AGPLv3.0+.

See [Getting Started](docs/getting_started.md).

## How-tos

```sh
# Hot/live reload (only works with FLASK_DEBUG=1)
./utils/reload.sh

# Cold update a running version of CDB with minimal downtime (production)
./utils/update.sh

# Enter docker
./utils/bash.sh

# Run migrations
./utils/run_migrations.sh

# Create new migration
./utils/create_migration.sh
```


### VSCode: Setting up Linting

* (optional) Install the [Docker extension](https://marketplace.visualstudio.com/items?itemName=ms-azuretools.vscode-docker)
* Install the [Python extension](https://marketplace.visualstudio.com/items?itemName=ms-python.python)
	* Click no to installing pylint (we don't want it to be installed outside of a virtual env)
* Set up a virtual env
	* Replace `psycopg2` with `psycopg2_binary` in requirements.txt (because postgresql won't be installed on the system)
	* `python3 -m venv env`
	* Click yes to prompt to select virtual env for workspace
	* Click yes to any prompts about installing pylint
	* `source env/bin/activate`
	* `pip install -r requirements`
	* `pip install pylint` (if a prompt didn't appear)
	* Undo changes to requirements.txt

### VSCode: Material Icon Folder Designations

```json
"material-icon-theme.folders.associations": {
	"packages": "",
	"tasks": "",
	"api": "",
	"meta": "",
	"blueprints": "routes",
	"scss": "sass",
	"flatpages": "markdown",
	"data": "temp",
	"migrations": "archive",
	"textures": "images",
	"sounds": "audio"
}
```


## Database


```mermaid
classDiagram

User "1" --> "*" Package
User --> UserEmailVerification
User "1" --> "*" Notification
Package "1" --> "*" Release
Package "1" --> "*" Dependency
Package "1" --> "*" Tag
Package "1" --> "*" MetaPackage : provides
Release --> MinetestVersion
Package --> License
Dependency --> Package
Dependency --> MetaPackage
MetaPackage "1" --> "*" Package
Package "1" --> "*" Screenshot
Package "1" --> "*" Thread
Thread "1" --> "*" Reply
Thread "1" --> "*" User : watchers
User "1" --> "*" Thread
User "1" --> "*" Reply
User "1" --> "*" ForumTopic

User --> "0..1" EmailPreferences
User "1" --> "*" APIToken
APIToken --> Package
```
