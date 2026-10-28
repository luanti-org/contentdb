# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Zenon Seth <Zenon.Seth@gmail.com>

import contextlib
import os
import socket
import subprocess
import tempfile
import threading
import time
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
