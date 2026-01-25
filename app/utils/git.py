# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


import contextlib
from typing import List, Optional, Tuple

import git
import gitdb
import os
import shutil
import tempfile
from urllib.parse import urlsplit

from git import GitCommandError

from app.tasks import TaskError
from app.utils.misc import random_string, normalize_line_endings


def generate_git_url(urlstr):
	scheme, netloc, path, query, frag = urlsplit(urlstr)

	if not scheme.startswith("http"):
		scheme = "http"

	return scheme + "://:@" + netloc + path + query


@contextlib.contextmanager
def get_temp_dir():
	temp = os.path.join(tempfile.gettempdir(), random_string(10))
	yield temp
	shutil.rmtree(temp)


# Clones a repo from an unvalidated URL.
# Returns a tuple of path and repo on sucess.
# Throws `TaskError` on failure.
# Caller is responsible for deleting returned directory.
@contextlib.contextmanager
def clone_repo(url_str, ref=None, recursive=False):
	git_dir = os.path.join(tempfile.gettempdir(), random_string(10))

	try:
		git_url = generate_git_url(url_str)
		print("Cloning from " + git_url)

		if ref is None:
			repo = git.Repo.clone_from(git_url, git_dir,
					progress=None, env=None, depth=1, recursive=recursive, kill_after_timeout=15)
		else:
			assert ref != ""

			repo = git.Repo.init(git_dir)
			origin = repo.create_remote("origin", url=git_url)
			assert origin.exists()
			origin.fetch()
			repo.git.checkout(ref)

			repo.git.submodule('update', '--init')

		yield repo
		shutil.rmtree(git_dir)
		return

	except GitCommandError as e:
		# This is needed to stop the backtrace being weird
		err = e.stderr

	except gitdb.exc.BadName as e:
		err = "Unable to find the reference " + (ref or "?") + "\n" + e.stderr

	raise TaskError(err.replace("stderr: ", "") \
			.replace("Cloning into '" + git_dir + "'...", "") \
			.strip())


def get_latest_commit(git_url, ref_name=None):
	git_url = generate_git_url(git_url)

	if ref_name:
		ref_name = "refs/heads/" + ref_name
	else:
		ref_name = "HEAD"

	g = git.cmd.Git()

	remote_refs = {}
	for ref in g.ls_remote(git_url).split('\n'):
		hash_ref_list = ref.split('\t')
		remote_refs[hash_ref_list[1]] = hash_ref_list[0]

	return remote_refs.get(ref_name)


# @returns (tag_name, commit_hash, tag_message)
def get_latest_tag(git_url) -> Tuple[Optional[str], Optional[str], Optional[str]]:
	with get_temp_dir() as git_dir:
		repo = git.Repo.init(git_dir)
		origin = repo.create_remote("origin", url=git_url)
		origin.fetch()

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
		if annotated_tag:
			message = annotated_tag.message
			message = normalize_line_endings(message)
			if message == "":
				message = None
		else:
			message = None

		return tag, commit_hash, message


def get_commit_list(git_url: str, start: str, end: str) -> List[str]:
	with (get_temp_dir() as git_dir):
		repo = git.Repo.init(git_dir)
		origin = repo.create_remote("origin", url=git_url)
		origin.fetch()

		commits = repo.iter_commits(f"{start}..{end}")
		ret = [commit.summary for commit in commits]
		ret.reverse()
		return ret


def get_release_notes(git_url: str, start: str, end: str) -> Optional[str]:
	commits = get_commit_list(git_url, start, end)
	commits = [x for x in commits if not x.startswith("Merge ")]
	if len(commits) == 0:
		return None

	text = "\n".join(map(lambda x: f"- {x}", commits)) + f"\n<!-- auto from {start[0:5]} to {end[0:5]} -->"
	return normalize_line_endings(text)
