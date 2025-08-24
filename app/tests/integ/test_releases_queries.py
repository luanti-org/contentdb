from typing import List, Tuple, Optional

from app.default_data import populate_test_data
from app.models import db, License, PackageType, User, Package, PackageState, PackageRelease, LuantiRelease
from .utils import parse_json, validate_package_list
from .utils import client # noqa


def make_package(name: str, versions: List[Tuple[Optional[str], Optional[str]]]) -> List[int]:
	license = License.query.filter_by(name="MIT").first()
	author = User.query.first()

	mod = Package()
	mod.state = PackageState.APPROVED
	mod.name = name.lower()
	mod.title = name
	mod.license = license
	mod.media_license = license
	mod.type = PackageType.MOD
	mod.author = author
	mod.short_desc = "The content library should not be used yet as it is still in alpha"
	mod.desc = "This is the long desc"
	db.session.add(mod)

	rels = []

	for (minv, maxv) in versions:
		rel = PackageRelease()
		rel.package = mod
		rel.name = "test"
		rel.title = "test"
		rel.url = "https://github.com/ezhh/handholds/archive/master.zip"

		if minv:
			rel.min_rel = LuantiRelease.query.filter_by(name=minv).first()
			assert rel.min_rel
		if maxv:
			rel.max_rel = LuantiRelease.query.filter_by(name=maxv).first()
			assert rel.max_rel

		rel.approved = True
		db.session.add(rel)
		rels.append(rel)

	db.session.flush()

	return [rel.id for rel in rels]


def test_packages_with_protocol_multi_high(client):
	"""Start with a test database."""

	populate_test_data(db.session)
	db.session.commit()

	rv = client.get("/api/packages/?protocol_version=100")

	packages = parse_json(rv.data)

	for package in packages:
		assert package["name"] != "mesecons"
		assert package["name"] != "handholds"

	assert len(packages) == 4

	validate_package_list(packages, True)


def test_packages_with_protocol_multi_low(client):
	"""Start with a test database."""

	populate_test_data(db.session)
	db.session.commit()

	rv = client.get("/api/packages/?protocol_version=20")

	packages = parse_json(rv.data)

	assert len(packages) == 4

	for package in packages:
		assert package["name"] != "awards"

	validate_package_list(packages, True)


def test_packages_with_protocol_max_ver(client):
	"""Start with a blank database."""

	make_package("Bob", [ (None, "5.0") ])
	db.session.commit()

	packages = parse_json(client.get("/api/packages/?protocol_version=20").data)
	assert len(packages) == 1
	assert packages[0]["name"] == "bob"

	packages = parse_json(client.get("/api/packages/?protocol_version=32").data)
	assert len(packages) == 1
	assert packages[0]["name"] == "bob"

	packages = parse_json(client.get("/api/packages/?protocol_version=37").data)
	assert len(packages) == 1
	assert packages[0]["name"] == "bob"

	packages = parse_json(client.get("/api/packages/?protocol_version=38").data)
	assert len(packages) == 0

	packages = parse_json(client.get("/api/packages/?protocol_version=40").data)
	assert len(packages) == 0

	validate_package_list(packages, True)


def test_packages_with_protocol_min_ver(client):
	"""Start with a blank database."""

	make_package("Bob", [("5.0", None)])
	db.session.commit()

	packages = parse_json(client.get("/api/packages/?protocol_version=20").data)
	assert len(packages) == 0

	packages = parse_json(client.get("/api/packages/?protocol_version=32").data)
	assert len(packages) == 0

	packages = parse_json(client.get("/api/packages/?protocol_version=37").data)
	assert len(packages) == 1
	assert packages[0]["name"] == "bob"

	packages = parse_json(client.get("/api/packages/?protocol_version=38").data)
	assert len(packages) == 1
	assert packages[0]["name"] == "bob"

	packages = parse_json(client.get("/api/packages/?protocol_version=40").data)
	assert len(packages) == 1
	assert packages[0]["name"] == "bob"

	validate_package_list(packages, True)


def test_packages_with_protocol_engine_ver(client):
	"""Start with a blank database."""

	make_package("Bob", [("5.3", None)])
	db.session.commit()

	packages = parse_json(client.get("/api/packages/?protocol_version=20&engine_version=4.0").data)
	assert len(packages) == 0

	packages = parse_json(client.get("/api/packages/?protocol_version=38&engine_version=5.1").data)
	assert len(packages) == 0

	packages = parse_json(client.get("/api/packages/?protocol_version=39&engine_version=5.2").data)
	assert len(packages) == 0

	packages = parse_json(client.get("/api/packages/?protocol_version=39&engine_version=5.3").data)
	assert len(packages) == 1
	assert packages[0]["name"] == "bob"

	packages = parse_json(client.get("/api/packages/?protocol_version=40&engine_version=5.6").data)
	assert len(packages) == 1
	assert packages[0]["name"] == "bob"

	validate_package_list(packages, True)


def test_packages_with_protocol_exact(client):
	"""Start with a blank database."""

	make_package("Bob", [("5.0", "5.0")])
	db.session.commit()

	packages = parse_json(client.get("/api/packages/?protocol_version=20").data)
	assert len(packages) == 0

	packages = parse_json(client.get("/api/packages/?protocol_version=32").data)
	assert len(packages) == 0

	packages = parse_json(client.get("/api/packages/?protocol_version=37").data)
	assert len(packages) == 1
	assert packages[0]["name"] == "bob"

	packages = parse_json(client.get("/api/packages/?protocol_version=38").data)
	assert len(packages) == 0

	packages = parse_json(client.get("/api/packages/?protocol_version=40").data)
	assert len(packages) == 0

	validate_package_list(packages, True)


def test_packages_with_protocol_options(client):
	"""Start with a blank database."""

	rels = make_package("Bob", [(None, "0.4.16/17"), ("5.1", "5.1")])
	db.session.commit()

	packages = parse_json(client.get("/api/packages/?protocol_version=20").data)
	assert len(packages) == 1
	assert packages[0]["name"] == "bob"
	assert packages[0]["release"] == rels[0]

	packages = parse_json(client.get("/api/packages/?protocol_version=32").data)
	assert len(packages) == 1
	assert packages[0]["name"] == "bob"
	assert packages[0]["release"] == rels[0]

	packages = parse_json(client.get("/api/packages/?protocol_version=37").data)
	assert len(packages) == 0

	packages = parse_json(client.get("/api/packages/?protocol_version=38").data)
	assert len(packages) == 1
	assert packages[0]["name"] == "bob"
	assert packages[0]["release"] == rels[1]

	packages = parse_json(client.get("/api/packages/?protocol_version=40").data)
	assert len(packages) == 0

	validate_package_list(packages, True)
