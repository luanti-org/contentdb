# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


import contextlib
from typing import List, Optional, Tuple

import git
import gitdb
import os
import shutil
import signal
import subprocess
import tempfile
from urllib.parse import urlsplit

from git import GitCommandError
from git.util import remove_password_if_present

from app.tasks import TaskError
from app.utils.misc import random_string, normalize_line_endings
from app.utils.files import get_temp_dir

GIT_ENV = {
	"GIT_TERMINAL_PROMPT": "0",
	"GIT_CONFIG_NOSYSTEM": "1",
	"GIT_CONFIG_GLOBAL": "/dev/null",
	# Overrides any protocol.*.allow config, and is inherited by submodule clones
	"GIT_ALLOW_PROTOCOL": "http:https",
	"GIT_HTTP_LOW_SPEED_LIMIT": "1000",
	"GIT_HTTP_LOW_SPEED_TIME": "30",
	"GIT_CONFIG_COUNT": "1",
	"GIT_CONFIG_KEY_0": "core.symlinks",
	"GIT_CONFIG_VALUE_0": "false",
}

# Seconds before a git network operation is killed
GIT_TIMEOUT = 15
GIT_FETCH_TIMEOUT = 300


# GitPython's kill_after_timeout misses git's helper processes, so kill the whole group instead
def _run_git(args: List[str], timeout: int, cwd: Optional[str] = None) -> str:
	command = remove_password_if_present(["git"] + args)
	env = {**os.environ, **GIT_ENV, "LANGUAGE": "C", "LC_ALL": "C"}
	proc = subprocess.Popen(["git"] + args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
			stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)

	try:
		stdout, stderr = proc.communicate(timeout=timeout)
	except subprocess.TimeoutExpired:
		raise GitCommandError(command, "timeout", f"Timed out after {timeout} seconds") from None
	finally:
		if proc.returncode is None:
			with contextlib.suppress(ProcessLookupError):
				os.killpg(proc.pid, signal.SIGKILL)
			proc.communicate()

	if proc.returncode != 0:
		raise GitCommandError(command, proc.returncode, stderr)

	return stdout


def generate_git_url(urlstr: str) -> str:
	scheme, netloc, path, query, frag = urlsplit(urlstr)

	if not scheme.startswith("http"):
		scheme = "http"

	return scheme + "://" + netloc + path + query


# Clones a repo from an unvalidated URL.
# Returns a tuple of path and repo on sucess.
# Throws `TaskError` on failure.
@contextlib.contextmanager
def clone_repo(url_str, ref=None, recursive=False):
	git_dir = os.path.join(tempfile.gettempdir(), random_string(10))

	try:
		git_url = generate_git_url(url_str)
		print("Cloning from " + git_url)

		if ref is None:
			_run_git(["clone", "--depth=1"] + (["--recurse-submodules"] if recursive else []) + ["--", git_url, git_dir],
					GIT_FETCH_TIMEOUT)
			repo = git.Repo(git_dir)
			repo.git.update_environment(**GIT_ENV)
		else:
			assert ref != ""

			repo = git.Repo.init(git_dir)
			repo.git.update_environment(**GIT_ENV)
			origin = repo.create_remote("origin", url=git_url)
			assert origin.exists()
			_run_git(["fetch", "origin"], GIT_FETCH_TIMEOUT, cwd=git_dir)
			repo.git.checkout("--end-of-options", ref, "--")

			_run_git(["submodule", "update", "--init"], GIT_FETCH_TIMEOUT, cwd=git_dir)

		yield repo
		return

	except GitCommandError as e:
		# This is needed to stop the backtrace being weird
		err = e.stderr

	except gitdb.exc.BadName as e:
		err = "Unable to find the reference " + (ref or "?") + "\n" + str(e)

	finally:
		shutil.rmtree(git_dir, ignore_errors=True)

	raise TaskError(err.replace("stderr: ", "") \
			.replace("Cloning into '" + git_dir + "'...", "") \
			.strip())


def get_latest_commit(git_url, ref_name=None):
	git_url = generate_git_url(git_url)

	if ref_name:
		ref_name = "refs/heads/" + ref_name
	else:
		ref_name = "HEAD"

	remote_refs = {}
	for ref in _run_git(["ls-remote", "--", git_url], GIT_TIMEOUT).splitlines():
		hash_ref_list = ref.split('\t')
		remote_refs[hash_ref_list[1]] = hash_ref_list[0]

	return remote_refs.get(ref_name)


# @returns (tag_name, commit_hash, tag_message)
def get_latest_tag(git_url) -> Tuple[Optional[str], Optional[str], Optional[str]]:
	git_url = generate_git_url(git_url)

	with get_temp_dir() as git_dir:
		repo = git.Repo.init(git_dir)
		repo.git.update_environment(**GIT_ENV)
		origin = repo.create_remote("origin", url=git_url)
		_run_git(["fetch", "origin"], GIT_FETCH_TIMEOUT, cwd=git_dir)

		refs = repo.git.for_each_ref(sort="creatordate", format="%(objectname)\t%(refname)").split("\n")
		refs = [ref for ref in refs if "refs/tags/" in ref]
		if len(refs) == 0:
			return None, None, None

		last_ref = refs[-1]
		hash_ref_list = last_ref.split('\t')

		tag = hash_ref_list[1].replace("refs/tags/", "")
		# "^{}" means dereference the tag until an actual commit is found
		commit_hash = repo.git.rev_parse(tag + "^{}")

		# Get summary message of annotated tag from GitPython
		annotated_tag = repo.tag(tag).tag
		message: Optional[str] = None
		if annotated_tag:
			message = normalize_line_endings(str(annotated_tag.message))
			if message == "":
				message = None

		return tag, commit_hash, message


def get_commit_list(git_url: str, start: str, end: str) -> List[str]:
	git_url = generate_git_url(git_url)

	with (get_temp_dir() as git_dir):
		repo = git.Repo.init(git_dir)
		repo.git.update_environment(**GIT_ENV)
		origin = repo.create_remote("origin", url=git_url)
		_run_git(["fetch", "origin"], GIT_FETCH_TIMEOUT, cwd=git_dir)

		commits = repo.iter_commits(f"{start}..{end}")
		ret = [str(commit.summary) for commit in commits]
		ret.reverse()
		return ret


def get_release_notes(git_url: str, start: str, end: str) -> Optional[str]:
	commits = get_commit_list(git_url, start, end)
	commits = [x for x in commits if not x.startswith("Merge ")]
	if len(commits) == 0:
		return None

	text = "\n".join(map(lambda x: f"- {x}", commits)) + f"\n<!-- auto from {start[0:5]} to {end[0:5]} -->"
	return normalize_line_endings(text)
