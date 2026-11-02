# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import os
import shutil

import git
import pytest

from app.tasks import TaskError
from app.tasks.importtasks import get_meta
from app.utils import git as git_utils
from app.utils.git import get_latest_tag, get_latest_commit, clone_repo, get_commit_list

test_repo = "https://codeberg.org/rubenwardy/testmod"
test_private_repo = "https://github.com/luanti-org/discussions"
master_head = "9f67d5ad98106e954bef732e64d367d7efa66341"
test_branch_head = "0d644a2068caf34a13e8d96937aa4d950dba6316"
v4_commit = "c07d27c3a466d2102d1ba5473d172c74e6b3e0d7"
latest_tag_name = "v5"
latest_tag_commit = "23d12265ff6de84548b2e3e90dc7351a54f63f00"
latest_tag_message = """
* One thing
* Second
* Third
""".strip()
random_commit = "84a2e53ff046eacbdbb80f3a00c58510885fefca"


def test_get_latest_tag():
	tag, commit, message = get_latest_tag(test_repo)
	assert tag == latest_tag_name
	assert commit == latest_tag_commit
	assert message == latest_tag_message


def test_get_latest_commit():
	assert get_latest_commit(test_repo) == master_head
	assert get_latest_commit(test_repo, "test-branch") == test_branch_head


def test_get_commit_list():
	result = get_commit_list(test_repo, "4fd0d06df2cc502b0cbc3ee932217b540f0d92ad", "23d12265ff6de84548b2e3e90dc7351a54f63f00")
	assert result == [
		"Update .cdb.json",
		"Update mod.conf",
		"Update mod.conf",
		"Update mod.conf",
		"Update mod.conf",
		"Update mod.conf",
		"Update mod.conf",
	]


def test_git_clone_head():
	with clone_repo(test_repo, recursive=True) as repo:
		assert repo.head.commit.hexsha == master_head
		assert os.path.isfile(os.path.join(repo.working_tree_dir, "init.lua"))
		assert os.path.isfile(os.path.join(repo.working_tree_dir, "chatcmdbuilder", "init.lua"))
		assert not os.path.isfile(os.path.join(repo.working_tree_dir, "test-branch.txt"))


def test_git_clone_branch():
	with clone_repo(test_repo, "test-branch", recursive=True) as repo:
		assert repo.head.commit.hexsha == test_branch_head
		assert os.path.isfile(os.path.join(repo.working_tree_dir, "init.lua"))
		assert os.path.isfile(os.path.join(repo.working_tree_dir, "chatcmdbuilder", "init.lua"))
		assert os.path.isfile(os.path.join(repo.working_tree_dir, "test-branch.txt"))


def test_git_clone_tag():
	with clone_repo(test_repo, "v4", recursive=True) as repo:
		assert repo.head.commit.hexsha == v4_commit

		# v4 isn't on the master branch, let's check there's no master branch files
		assert os.path.isfile(os.path.join(repo.working_tree_dir, "init.lua"))
		assert not os.path.isfile(os.path.join(repo.working_tree_dir, "chatcmdbuilder", "init.lua"))
		assert not os.path.isfile(os.path.join(repo.working_tree_dir, "test-branch.txt"))


def test_git_clone_commit():
	with clone_repo(test_repo, random_commit, recursive=True) as repo:
		assert repo.head.commit.hexsha == random_commit
		assert os.path.isfile(os.path.join(repo.working_tree_dir, "init.lua"))
		assert not os.path.isfile(os.path.join(repo.working_tree_dir, "chatcmdbuilder", "init.lua"))
		assert not os.path.isfile(os.path.join(repo.working_tree_dir, "test-branch.txt"))


def test_git_clone_private_repo():
	with pytest.raises(TaskError):
		with clone_repo(test_private_repo, recursive=True):
			pytest.fail("Cloned a private repo")


@pytest.fixture
def symlink_repo(tmp_path, monkeypatch):
	"""
	Creates a local repo containing a symlink to a file outside the repo, and a
	submodule which also contains such a symlink.
	"""
	secret = tmp_path / "secret.txt"
	secret.write_text("secret")

	def make_repo(name: str) -> git.Repo:
		repo = git.Repo.init(tmp_path / name)
		with repo.config_writer() as cw:
			cw.set_value("user", "name", "Test")
			cw.set_value("user", "email", "test@example.com")
		(tmp_path / name / "init.lua").write_text("")
		os.symlink(secret, tmp_path / name / "README.md")
		repo.index.add(["init.lua", "README.md"])
		repo.index.commit("Initial commit")
		return repo

	make_repo("sub")
	main = make_repo("main")
	main.git.update_environment(GIT_CONFIG_COUNT="1",
			GIT_CONFIG_KEY_0="protocol.file.allow", GIT_CONFIG_VALUE_0="always")
	main.git.submodule("add", (tmp_path / "sub").as_uri(), "sub")
	main.index.commit("Add submodule")

	allow_local_clones(monkeypatch)

	return (tmp_path / "main").as_uri(), main.head.commit.hexsha


def allow_local_clones(monkeypatch):
	# Allow cloning from local paths, including submodules
	monkeypatch.setattr(git_utils, "generate_git_url", lambda url: url)
	monkeypatch.setattr(git_utils, "_check_submodule_url", lambda path, url: None)
	monkeypatch.setitem(git_utils.GIT_ENV, "GIT_ALLOW_PROTOCOL", "file")


def assert_no_symlinks(working_tree_dir: str):
	for path in [os.path.join(working_tree_dir, "README.md"), os.path.join(working_tree_dir, "sub", "README.md")]:
		assert os.path.lexists(path)
		assert not os.path.islink(path)
		with open(path, "r") as f:
			assert f.read() != "secret"


def test_symlink_repo_fixture_has_symlinks(symlink_repo, tmp_path):
	# Control: check that a normal clone does create symlinks, so the tests below are meaningful
	url, _ = symlink_repo
	control_dir = tmp_path / "control"
	git.Repo.clone_from(url, control_dir, multi_options=["--recurse-submodules"],
			env={"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "protocol.file.allow", "GIT_CONFIG_VALUE_0": "always"})
	assert os.path.islink(control_dir / "README.md")
	assert os.path.islink(control_dir / "sub" / "README.md")


def test_git_clone_head_no_symlinks(symlink_repo):
	url, _ = symlink_repo
	with clone_repo(url, recursive=True) as repo:
		assert_no_symlinks(repo.working_tree_dir)


def test_git_clone_ref_no_symlinks(symlink_repo):
	url, commit = symlink_repo
	with clone_repo(url, commit, recursive=True) as repo:
		assert repo.head.commit.hexsha == commit
		assert_no_symlinks(repo.working_tree_dir)


EVIL_SUBMODULE_NAME = "evil$(touch pwned)`touch pwned`"
GAME_SUBMODULE_PATHS = ["mods/foo", "mods/" + EVIL_SUBMODULE_NAME]


@pytest.fixture
def submodule_repo(tmp_path, monkeypatch, request):
	"""
	Creates a local game (or modpack, if parametrized with "modpack") repo whose
	mods are submodules, one of them with a path that runs a command if it ever
	reaches a shell.
	"""
	is_game = getattr(request, "param", "game") == "game"
	conf_file = "game.conf" if is_game else "modpack.conf"
	mods_dir = "mods/" if is_game else ""

	def init_repo(name: str) -> git.Repo:
		repo = git.Repo.init(tmp_path / name)
		with repo.config_writer() as cw:
			cw.set_value("user", "name", "Test")
			cw.set_value("user", "email", "test@example.com")
		return repo

	sub = init_repo("sub")
	(tmp_path / "sub" / "init.lua").write_text("")
	sub.git.add("init.lua")
	sub.git.commit("-m", "Initial commit")
	sub_sha = sub.head.commit.hexsha
	sub_url = (tmp_path / "sub").as_uri()

	foo_path = mods_dir + "foo"
	evil_path = mods_dir + EVIL_SUBMODULE_NAME

	main = init_repo("main")
	(tmp_path / "main" / conf_file).write_text("title = Test\n")
	(tmp_path / "main" / ".gitmodules").write_text(
			f"[submodule \"foo\"]\n\tpath = {foo_path}\n\turl = {sub_url}\n"
			f"[submodule \"evil\"]\n\tpath = {evil_path}\n\turl = {sub_url}\n")
	main.git.add(conf_file, ".gitmodules")
	for path in [foo_path, evil_path]:
		main.git.update_index("--add", "--cacheinfo", f"160000,{sub_sha},{path}")
	main.git.commit("-m", "Initial commit")

	allow_local_clones(monkeypatch)
	monkeypatch.chdir(tmp_path)

	return (tmp_path / "main").as_uri()


def assert_not_pwned(*dirs):
	for dir in dirs:
		for _, _, files in os.walk(dir):
			assert "pwned" not in files


def test_submodule_repo_fixture(submodule_repo, tmp_path):
	# Control: check that a recursive clone fetches both submodules, so the tests below are meaningful
	control_dir = tmp_path / "control"
	git.Repo.clone_from(submodule_repo, control_dir, multi_options=["--recurse-submodules"],
			env={"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "protocol.file.allow", "GIT_CONFIG_VALUE_0": "always"})
	for path in GAME_SUBMODULE_PATHS:
		assert os.path.isfile(control_dir / path / "init.lua")
	assert_not_pwned(tmp_path)


def test_git_clone_recursive_rejects_evil_submodule(submodule_repo, tmp_path):
	with pytest.raises(TaskError, match="path is not allowed"):
		with clone_repo(submodule_repo, recursive=True):
			pass
	assert_not_pwned(tmp_path)


def test_git_clone_skips_submodules_by_default(submodule_repo, tmp_path):
	with clone_repo(submodule_repo) as repo:
		for path in GAME_SUBMODULE_PATHS:
			path = os.path.join(repo.working_tree_dir, path)
			assert os.path.isdir(path)
			assert os.listdir(path) == []

		assert_not_pwned(repo.working_tree_dir, tmp_path)


@pytest.mark.parametrize("submodule_repo, expected_type", [("game", "GAME"), ("modpack", "MODPACK")],
		indirect=["submodule_repo"])
def test_get_meta_with_submodule_mods(submodule_repo, expected_type, tmp_path):
	# Any attempt to fetch a submodule will now fail
	shutil.rmtree(tmp_path / "sub")

	result = get_meta(submodule_repo, "test")
	assert result["type"] == expected_type
	assert result["title"] == "Test"
	assert_not_pwned(tmp_path)
