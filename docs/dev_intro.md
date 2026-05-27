# Developer Introduction

## Overview 

ContentDB is a Python [Flask](https://flask.palletsprojects.com/en/2.0.x/) webservice.
There's a PostgreSQL database, manipulated using the [SQLAlchemy ORM](https://docs.sqlalchemy.org/en/14/). 

When a user makes a request, Python Flask will direct the request to a *route* in a *blueprint*. 
A [blueprint](https://flask.palletsprojects.com/en/2.0.x/blueprints/) is a Flask construct to hold a set of routes.
Routes are implemented using Python, and likely to respond by using database *models* and rendering HTML *templates*.

Routes may also use functions in the `app/domain/` module, which is a directory containing reusable functions. This
allows the API, background tasks, and the front-end to reuse code. 

To avoid blocking web requests, background tasks run as
[Celery](https://docs.celeryproject.org/en/stable/getting-started/introduction.html) tasks.


## Locations

### The App

The `app` directory contains the Python Flask application.

* `blueprints` contains all the Python code behind each endpoint / route.
* `templates` contains all the HTML templates used to generate responses. Each directory in here matches a directory in blueprints.
* `models` contains all the database table classes. ContentDB uses [SQLAlchemy](https://docs.sqlalchemy.org/en/14/) to interact with PostgreSQL.
* `flatpages` contains all the markdown user documentation, including `/help/`.
* `public` contains files that should be added to the web server unedited. Examples include CSS libraries, images, and JS scripts.
* `scss` contains the stylesheet files, that are compiled into CSS.
* `tasks` contains the background tasks executed by [Celery](https://docs.celeryproject.org/en/stable/getting-started/introduction.html).
* `domain` is a collection of reusable functions. For example, shared code to create a release or edit a package is here.
* `tests` contains the Unit Tests and UI tests.
* `utils` contain generic Python utilities, for example common code to manage Flask requests.

There are also a number of Python files in the `app` directory. The most important one is `querybuilder.py`,
which is used to generate SQLAlachemy queries for packages and topics.

### Supporting directories

* `migrations` contains code to manage database updates.
* `translations` contains user-maintained translations / locales.
* `utils` contains bash scripts to aid development and deployment.


## How to find stuff

Generally, you want to start by finding the endpoint and then seeing the code it calls.

Endpoints are sensibly organised in `app/blueprints`.

You can also use a file search. For example, to find the package edit endpoint, search for `"/packages/<author>/<name>/edit/"`.


## Users and Permissions

Many routes need to check whether a user can do a particular thing. Rather than hard coding this,
models tend to have a `check_perm` function which takes a user and a `Permission`.

A permission may be something like `Permission.EDIT_PACKAGE` or `Permission.DELETE_THREAD`.

```bash
if not package.check_perm(current_user, Permission.EDIT_PACKAGE):
	abort(403)
```


## Translations

ContentDB uses [Flask-Babel](https://flask-babel.tkte.ch/) for translation. All strings need to be tagged using
a gettext function.

### Translating templates (HTML)

```html
<div class="something" title="{{ _('This is translatable now') }}">
	{{ _("Please remember to do something related to this page or something") }}
</div>
```

With parameters:

```html
<p>
	{{ _("Hello %(username)s, you have %(count)d new messages", username=username, count=count) }}
</p>
```

See <https://pythonhosted.org/Flask-Babel/#flask.ext.babel.Babel.localeselector> and
<https://blog.miguelgrinberg.com/post/the-flask-mega-tutorial-part-xiv-i18n-and-l10n>.

### Translating Python

If the text is within a request, then you can use gettext like so:

```py
flash(gettext("Some error message"), "danger")
```

If the text is global, for example as part of a python class, then you need to use lazy_gettext:

```py
class PackageForm(FlaskForm):
	title            = StringField(lazy_gettext("Title (Human-readable)"), [InputRequired(), Length(1, 100)])
```
