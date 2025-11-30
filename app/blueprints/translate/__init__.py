# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


from flask import Blueprint, render_template, request
from sqlalchemy import or_

from app.models import Package, PackageState, db, PackageTranslation

bp = Blueprint("translate", __name__)


@bp.route("/translate/")
def translate():
	query = Package.query.filter(
			Package.state == PackageState.APPROVED,
			or_(
				Package.translation_url.is_not(None),
				Package.translations.any(PackageTranslation.language_id != "en")
			))

	has_langs = request.args.getlist("has_lang")
	for lang in has_langs:
		query = query.filter(Package.translations.any(PackageTranslation.language_id == lang))

	not_langs = request.args.getlist("not_lang")
	for lang in not_langs:
		query = query.filter(~Package.translations.any(PackageTranslation.language_id == lang))

	supports_translation = (query
			.order_by(Package.translation_url.is_(None), db.desc(Package.score))
			.all())

	return render_template("translate/index.html",
			supports_translation=supports_translation, has_langs=has_langs, not_langs=not_langs)
