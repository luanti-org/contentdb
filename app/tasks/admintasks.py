# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from . import celery
from app.models import db, Thread


@celery.task
def delete_empty_threads():
	query = Thread.query.filter(~Thread.replies.any())
	count = query.count()
	for thread in query.all():
		thread.watchers.clear()
		db.session.delete(thread)
	db.session.commit()
