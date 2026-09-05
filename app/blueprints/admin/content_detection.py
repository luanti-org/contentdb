# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>


from typing import Dict

from flask import render_template, request
from flask_babel import lazy_gettext
from flask_wtf import FlaskForm
from wtforms import SubmitField, FileField
import json

from . import bp
from app.models import db, ContentDetectionDataset, UserRank, ContentDetectionDatasetEntry, \
	ContentDetectionDatasetEntryHash, PackageContentDetection, ContentDetectionState
from app.utils.user import rank_required


class UploadDatasetForm(FlaskForm):
	file_upload = FileField(lazy_gettext("File Upload"))
	submit = SubmitField(lazy_gettext("Update"))


def handle_update(data):
	pack_name = data["pack_name"]

	ContentDetectionDataset.query.filter_by(name=pack_name).delete()
	dataset = ContentDetectionDataset()
	dataset.name = pack_name
	db.session.add(dataset)

	for entry in data["entries"]:
		db_entry = ContentDetectionDatasetEntry()
		db_entry.path = entry["path"]
		db_entry.width = entry["width"]
		db_entry.height = entry["height"]
		dataset.entries.append(db_entry)

		hashes: Dict[str, any] = entry["hashes"]
		for hash in hashes.values():
			db_hash = ContentDetectionDatasetEntryHash()
			db_hash.phash = hash["phash"]
			db_hash.dhash = hash["dhash"]
			db_entry.hashes.append(db_hash)

	db.session.commit()


@bp.route("/admin/content_detection/datasets/", methods=["GET", "POST"])
@rank_required(UserRank.EDITOR)
def cd_datasets():
	form = UploadDatasetForm()

	if form.validate_on_submit():
		json_data = request.files[form.file_upload.name].read()
		data = json.loads(json_data)
		handle_update(data)

	return render_template("admin/content_detection/datasets.html", form=form, datasets=ContentDetectionDataset.query.all())


@bp.route("/admin/content_detection/matches/", methods=["GET"])
@rank_required(UserRank.EDITOR)
def cd_matches():
	matches = (PackageContentDetection.query
		.filter(PackageContentDetection.state != ContentDetectionState.IGNORED)
		.order_by(PackageContentDetection.confidence.asc())
		.all())
	return render_template("admin/content_detection/match_list.html", matches=matches)


@bp.route("/admin/content_detection/matches/<int:match_id>/", methods=["GET"])
@rank_required(UserRank.EDITOR)
def cd_match(match_id):
	match = PackageContentDetection.query.get_or_404(match_id)

	return render_template("admin/content_detection/match.html", match=match)
