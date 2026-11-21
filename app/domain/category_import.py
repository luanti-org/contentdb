# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 rubenwardy <rw@rubenwardy>

"""
Sets the categories of many games at once from a CSV file, such as the editors' category review spreadsheet.

Columns, matched case-insensitively:

* `Game`: the game's title, or `author/name`.
* `Main category`: a category's title or name.
* `Second category`: optional, a category's title or name.
* `Link`: optional, the package's URL. Used to find the game when present, as titles aren't unique.
"""

import csv
import io
import re
from dataclasses import dataclass, field

from app.domain.DomainError import DomainError
from app.domain.packages import do_edit_package
from app.models import db, Package, PackageType, PackageState, Tag, TagKind, User


REQUIRED_COLUMNS = {"game", "main category"}
MAX_ROWS = 2000

LINK_RE = re.compile(r"/packages/([A-Za-z0-9_\-]+)/([a-z0-9_]+)/?$")


@dataclass
class CategoryRow:
	row: int
	game: str
	main: str
	second: str
	link: str


@dataclass
class CategoryChange:
	row: int
	package: Package
	old_categories: list[Tag]
	new_categories: list[Tag]

	@property
	def is_change(self) -> bool:
		return {x.id for x in self.old_categories} != {x.id for x in self.new_categories}


@dataclass
class CategoryImportResult:
	changes: list[CategoryChange] = field(default_factory=list)
	unchanged: list[CategoryChange] = field(default_factory=list)
	skipped: list[tuple[int, str, str]] = field(default_factory=list)  # (row, game, reason)


def parse_category_csv(content: bytes) -> list[CategoryRow]:
	try:
		text = content.decode("utf-8-sig")
	except UnicodeDecodeError as e:
		raise DomainError(400, "The file must be a UTF-8 CSV file") from e

	reader = csv.DictReader(io.StringIO(text))
	columns = {(x or "").strip().lower(): x for x in (reader.fieldnames or [])}
	missing = REQUIRED_COLUMNS - set(columns.keys())
	if missing:
		raise DomainError(400, "Missing columns: " + ", ".join(sorted(missing)))

	def get(row: dict, column: str) -> str:
		key = columns.get(column)
		value = row.get(key) if key is not None else None
		return value.strip() if isinstance(value, str) else ""

	rows: list[CategoryRow] = []
	for row in reader:
		if len(rows) >= MAX_ROWS:
			raise DomainError(400, f"Too many rows, the maximum is {MAX_ROWS}")

		# Row 1 is the header
		rows.append(CategoryRow(reader.line_num, get(row, "game"), get(row, "main category"),
				get(row, "second category"), get(row, "link")))

	return rows


def find_game(row: CategoryRow) -> Package | str:
	"""Returns the game, or why it couldn't be found"""
	query = Package.query.filter(Package.type == PackageType.GAME, Package.state != PackageState.DELETED)

	match = LINK_RE.search(row.link) if row.link else None
	if match is None and "/" in row.game:
		match = re.fullmatch(r"([A-Za-z0-9_\-]+)/([a-z0-9_]+)", row.game)

	if match:
		package = query.join(Package.author) \
			.filter(User.username == match.group(1), Package.name == match.group(2)).first()
		return package or f"No game called {match.group(1)}/{match.group(2)}"

	if row.game == "":
		return "No game given"

	packages = query.filter(db.func.lower(Package.title) == row.game.lower()).all()
	if len(packages) == 0:
		return "No game with this title"
	elif len(packages) > 1:
		return "Several games have this title, give author/name or a Link column instead"

	return packages[0]


def import_categories(user: User, rows: list[CategoryRow], apply: bool) -> CategoryImportResult:
	"""
	Works out the categories of each game in `rows`. If `apply`, sets them, through do_edit_package so that each change is
	checked and audit logged like any other edit.
	"""
	categories = Tag.query.filter_by(kind=TagKind.CATEGORY).all()
	category_lookup = {x.title.lower(): x for x in categories} | {x.name.lower(): x for x in categories}

	result = CategoryImportResult()
	seen: dict[int, int] = {}
	for row in rows:
		package = find_game(row)
		if isinstance(package, str):
			result.skipped.append((row.row, row.game, package))
			continue

		if package.id in seen:
			result.skipped.append((row.row, row.game, f"Same game as row {seen[package.id]}"))
			continue
		seen[package.id] = row.row

		if row.main == "":
			result.skipped.append((row.row, row.game, "No main category"))
			continue

		new_categories: list[Tag] = []
		unknown = []
		for name in [row.main, row.second]:
			if name == "":
				continue

			category = category_lookup.get(name.lower())
			if category is None:
				unknown.append(name)
			elif category not in new_categories:
				new_categories.append(category)

		if unknown:
			result.skipped.append((row.row, row.game, "Not a category: " + ", ".join(unknown)))
			continue

		old_categories = [x for x in package.tags if x.kind == TagKind.CATEGORY]
		change = CategoryChange(row.row, package, old_categories, new_categories)
		if not change.is_change:
			result.unchanged.append(change)
			continue

		if apply:
			tags = [x.name for x in package.tags if x.kind != TagKind.CATEGORY] + [x.name for x in new_categories]
			try:
				# was_web, so that the categories are replaced rather than kept when there are none
				do_edit_package(user, package, False, True, {"tags": tags}, "Category import")
			except DomainError as e:
				db.session.rollback()
				result.skipped.append((row.row, row.game, str(e.message)))
				continue

		result.changes.append(change)

	return result
