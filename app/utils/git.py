# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


import contextlib
from typing import Dict, List, Optional, Set, Tuple

import git
import gitdb
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
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
	"GIT_ALLOW_PROTOCOL": "https",
	"GIT_HTTP_LOW_SPEED_LIMIT": "1000",
	"GIT_HTTP_LOW_SPEED_TIME": "30",
	"GIT_CONFIG_COUNT": "1",
	"GIT_CONFIG_KEY_0": "core.symlinks",
	"GIT_CONFIG_VALUE_0": "false",
}

# Hosts that package repos and submodules may be fetched from
ALLOWED_GIT_HOSTS = frozenset({
	"github.com",
	"codeberg.org",
	"gitlab.com",
	"bitbucket.org",
	"git.minetest.land",
	"gitgud.io",
	"notabug.org",
	"git.0x7be.net",
	"gitea.your-land.de",
	"cheapiesystems.com",
	"repo.or.cz",
	"git.sr.ht",
	"git.bananach.space",
	"forge.apps.education.fr",
	"git.noordstar.me",
	"minecaptain.com",
	"invent.kde.org",
	"gitoverit.ofafox.com",
	"gitea.com",
	"git.sp-codes.de",
	"forge.tedomum.net",
	"git.brn.systems",
	"bugs.1f616emo.xyz",
	"git.icynet.eu",
	"git.james-clarke.ynh.fr",
	"edugit.org",
	"git.savannah.nongnu.org",
	"gitea.eom.dev",
	"git.luanti.ru",
	"git.gay",
	"git.phreedom.club",
	"gitea.polonkai.eu",
	"git.cubesoftware.xyz",
	"git.medlab.host",
	"code.achtarmig.org",
	"git.tchncs.de",
})

MAX_SUBMODULE_DEPTH = 5
MAX_SUBMODULES = 200

# Seconds before a git network operation is killed
GIT_TIMEOUT = 15
GIT_FETCH_TIMEOUT = 300


# GitPython's kill_after_timeout misses git's helper processes, so kill the whole group instead
def _run_git(args: List[str], timeout: float, cwd: Optional[str] = None) -> str:
	command = remove_password_if_present(["git"] + args)
	env = {**os.environ, **GIT_ENV, "LANGUAGE": "C", "LC_ALL": "C"}
	proc = subprocess.Popen(["git"] + args, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
			stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)

	try:
		stdout, stderr = proc.communicate(timeout=timeout)
	except subprocess.TimeoutExpired:
		raise GitCommandError(command, "timeout", f"Timed out after {timeout:.0f} seconds") from None
	finally:
		if proc.returncode is None:
			with contextlib.suppress(ProcessLookupError):
				os.killpg(proc.pid, signal.SIGKILL)
			proc.communicate()

	if proc.returncode != 0:
		raise GitCommandError(command, proc.returncode, stderr)

	return stdout


# Returns the https URL to fetch from, or throws `TaskError` if the host isn't allowed.
def generate_git_url(urlstr: str) -> str:
	try:
		url = urlsplit(urlstr.strip())
	except ValueError:
		raise TaskError(f"Git URL is not valid: {urlstr!r}") from None

	if url.hostname is None or url.hostname not in ALLOWED_GIT_HOSTS:
		raise TaskError(f"Git host '{url.hostname or urlstr}' is not allowed. Please ask an editor to add it.")

	return "https://" + url.hostname + url.path


def _git_in(path: str) -> git.Git:
	g = git.Git(path)
	g.update_environment(**GIT_ENV)
	return g


def _read_gitmodules(repo_dir: str) -> Dict[str, Dict[str, str]]:
	if not os.path.isfile(os.path.join(repo_dir, ".gitmodules")):
		return {}

	try:
		output = _git_in(repo_dir).config("-f", ".gitmodules", "-z", "--get-regexp", r"^submodule\.")
	except GitCommandError as e:
		if e.status == 1:
			return {}
		raise

	modules: Dict[str, Dict[str, str]] = {}
	for entry in filter(None, output.split("\0")):
		key, _, value = entry.partition("\n")
		name, _, field = key[len("submodule."):].rpartition(".")
		modules.setdefault(name, {})[field] = value
	return modules


def _check_submodule_path(path: str):
	parts = path.split("/")
	if re.fullmatch(r"[A-Za-z0-9._/-]+", path) is None or path.startswith("-") or \
			any(part in ("", ".", "..") or part.lower() == ".git" for part in parts):
		raise TaskError(f"Submodule path is not allowed: {path!r}")


def _check_submodule_url(path: str, url: str):
	if not url.startswith("https://"):
		raise TaskError(f"Submodule '{path}' has a URL that doesn't use https://: {url!r}")

	expected = generate_git_url(url)
	if url != expected:
		raise TaskError(f"Submodule '{path}' has a URL that is not allowed: {url!r}. Please use {expected!r} instead.")


def _check_submodules(modules: Dict[str, Dict[str, str]]) -> List[str]:
	paths = []
	seen: Set[str] = set()
	for name, fields in modules.items():
		path = fields.get("path")
		url = fields.get("url")
		if path is None or url is None:
			raise TaskError(f"Submodule {name!r} needs both a path and a url")

		_check_submodule_path(path)
		if path.lower() in seen:
			raise TaskError(f"Submodule path is used twice: {path!r}")
		seen.add(path.lower())

		_check_submodule_url(path, url)
		paths.append(path)

	return paths


def _get_gitlinks(repo_dir: str) -> Set[str]:
	ret = set()
	for entry in filter(None, _git_in(repo_dir).ls_files("-z", "--stage").split("\0")):
		info, _, path = entry.partition("\t")
		if info.startswith("160000 "):
			ret.add(path)
	return ret


# Each level is validated before it is fetched, so nested .gitmodules are checked too
def _update_submodules(repo_dir: str, deadline: float, depth: int = 1, count: int = 0) -> int:
	modules = _read_gitmodules(repo_dir)
	if len(modules) == 0:
		return count

	gitlinks = _get_gitlinks(repo_dir)
	paths = _check_submodules({name: fields for name, fields in modules.items()
			if fields.get("path") in gitlinks})
	if len(paths) == 0:
		return count

	if depth > MAX_SUBMODULE_DEPTH:
		raise TaskError(f"Submodules are nested more than {MAX_SUBMODULE_DEPTH} levels deep")

	count += len(paths)
	if count > MAX_SUBMODULES:
		raise TaskError(f"Too many submodules, the limit is {MAX_SUBMODULES}")

	timeout = deadline - time.monotonic()
	if timeout <= 0:
		raise TaskError("Timed out fetching submodules")

	_run_git(["submodule", "update", "--init", "--"] + paths, timeout, cwd=repo_dir)

	for path in paths:
		count = _update_submodules(os.path.join(repo_dir, path), deadline, depth + 1, count)

	return count


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
			_run_git(["clone", "--depth=1", "--", git_url, git_dir], GIT_FETCH_TIMEOUT)
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

		if recursive:
			_update_submodules(git_dir, time.monotonic() + GIT_FETCH_TIMEOUT)

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
