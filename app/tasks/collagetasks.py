# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

import hashlib
import os
import sys
import tempfile

from PIL import Image

from app.models import db, Package, PackageState, Tag, TagKind
from app.tasks import celery
from app.uploads import copy_to_uploads, delete_upload_after_commit, get_upload_local_path
from app.utils.collage import render_collage, visible_cell_count


def get_collage_images(tag: Tag) -> list[Image.Image]:
	"""
	The main screenshots of the tag's top approved packages, one for each cell of the collage that can be seen, so
	that there are only repeats when the tag doesn't have enough packages
	"""
	packages = Package.query \
		.filter(Package.state == PackageState.APPROVED, Package.tags.contains(tag), Package.main_screenshot.has()) \
		.order_by(db.desc(Package.score)) \
		.limit(visible_cell_count()) \
		.all()

	images = []
	for package in packages:
		path = get_upload_local_path(package.main_screenshot.upload_path)
		if path is None:
			continue

		try:
			with Image.open(path) as image:
				image.load()
				images.append(image.copy())
		except OSError as e:
			print(f"Unable to read screenshot of {package.get_id()} for a collage: {e}", file=sys.stderr)

	return images


def update_tag_collage(tag: Tag) -> bool:
	"""
	Renders and uploads the tag's collage. The file is named after its contents, so an unchanged collage keeps its
	URL and isn't uploaded again. Returns whether the tag's collage changed.
	"""
	images = get_collage_images(tag)
	old_path = tag.collage_path

	new_path = None
	if images:
		with tempfile.TemporaryDirectory() as tmp_dir:
			tmp_path = os.path.join(tmp_dir, "collage.webp")
			render_collage(images).save(tmp_path, "WEBP", quality=80)
			with open(tmp_path, "rb") as f:
				digest = hashlib.sha256(f.read()).hexdigest()[:10]

			filename = f"category-{tag.name}-{digest}.webp"
			if old_path is not None and os.path.basename(old_path) == filename:
				return False

			new_path = copy_to_uploads(tmp_path, filename)

	if new_path == old_path:
		return False

	tag.collage_path = new_path
	db.session.commit()
	delete_upload_after_commit(old_path)
	return True


@celery.task()
def update_category_collages():
	"""Updates the collage of each category tag, as their top packages change"""
	for tag in Tag.query.filter_by(kind=TagKind.CATEGORY).order_by(db.asc(Tag.id)).all():
		update_tag_collage(tag)
