# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from logging import Filter

import flask
from celery import Celery, signals
from celery.schedules import crontab
from app import app


class TaskError(Exception):
	def __init__(self, value):
		self.value = value

	def __str__(self):
		return repr("TaskError: " + self.value)


class FlaskCelery(Celery):
	app: flask.app

	def __init__(self, *args, **kwargs):
		super(FlaskCelery, self).__init__(*args, **kwargs)
		self.app = None
		self.patch_task()

		if 'app' in kwargs:
			self.init_app(kwargs['app'])

	def patch_task(self):
		BaseTask : celery.Task = self.Task
		_celery = self

		class ContextTask(BaseTask):
			abstract = True

			def __call__(self, *args, **kwargs):
				if flask.has_app_context():
					return super(BaseTask, self).__call__(*args, **kwargs)
				else:
					with _celery.app.app_context():
						return super(BaseTask, self).__call__(*args, **kwargs)

		self.Task = ContextTask

	def init_app(self, app):
		self.app = app
		self.config_from_object(app.config)


def make_celery(app):
	celery = FlaskCelery(app.import_name, backend=app.config['CELERY_RESULT_BACKEND'],
					broker=app.config['CELERY_BROKER_URL'], task_track_started=True)

	celery.init_app(app)
	return celery


celery = make_celery(app)


CELERYBEAT_SCHEDULE = {
	'topic_list_import': {
		'task': 'app.tasks.forumtasks.import_topic_list',
		'schedule': crontab(minute=1, hour=1), # 0101
	},
	'package_score_update': {
		'task': 'app.tasks.pkgtasks.update_package_scores',
		'schedule': crontab(minute=10, hour=1), # 0110
	},
	'check_for_updates': {
		'task': 'app.tasks.importtasks.check_for_updates',
		'schedule': crontab(minute=10, hour=2), # 0210
	},
	'send_pending_notifications': {
		'task': 'app.tasks.emails.send_pending_notifications',
		'schedule': crontab(minute='*/15'), # every 15 minutes
	},
	'send_notification_digests': {
		'task': 'app.tasks.emails.send_pending_digests',
		'schedule': crontab(minute=0, hour=14), # 1400
	},
	'delete_inactive_users': {
		'task': 'app.tasks.usertasks.delete_inactive_users',
		'schedule': crontab(minute=15), # every hour at quarter past
	},
	'upgrade_new_members': {
		'task': 'app.tasks.usertasks.upgrade_new_members',
		'schedule': crontab(minute=10, hour=3), # 0310
	},
	'delete_old_notifications': {
		'task': 'app.tasks.usertasks.delete_old_notifications',
		'schedule': crontab(minute=10, hour=3),  # 0310
	},
}
celery.conf.beat_schedule = CELERYBEAT_SCHEDULE


from . import importtasks, forumtasks, emails, pkgtasks, usertasks, admintasks
