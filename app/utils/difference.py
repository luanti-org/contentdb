# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from typing import Dict, List, Optional
import deep_compare
from flask import current_app


def diff_dictionaries(one: Dict, two: Dict) -> List:
	if len(set(one.keys()).difference(set(two.keys()))) != 0:
		raise "Mismatching keys"

	retval = []

	for key, before in one.items():
		after = two[key]

		if isinstance(before, dict):
			diff = diff_dictionaries(before, after)
			if len(diff) != 0:
				retval.append({
					"key": key,
					"changes": diff,
				})
		elif not deep_compare.CompareVariables.compare(before, after):
			retval.append({
				"key": key,
				"before": before,
				"after": after,
			})

	return retval


def describe_difference(diff: List, available_space: int) -> Optional[str]:
	if len(diff) == 0 or available_space <= 0:
		return None

	if len(diff) == 1 and "before" in diff[0] and "after" in diff[0]:
		key = diff[0]["key"]
		before = diff[0]["before"]
		after = diff[0]["after"]

		if isinstance(before, str) and isinstance(after, str):
			if len(before) + len(after) <= available_space + 30:
				return f"{key}: {before} -> {after}"

		elif isinstance(before, list) and isinstance(after, list):
			removed = []
			added = []
			for x in before:
				if x not in after:
					removed.append(x)
			for x in after:
				if x not in before:
					added.append(x)

			parts = ["-" + str(x) for x in removed] + ["+" + str(x) for x in added]
			return f"{key}: {', '.join(parts)}"

	return ", ".join([x["key"] for x in diff])
