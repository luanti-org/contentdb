# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

from . import redis_client

# This file acts as a facade between the rest of the code and redis,
# and also means that the rest of the code avoids knowing about `app`


EXPIRY_TIME_S = 2*7*24*60*60  # 2 weeks


def make_download_key(ip, package):
	return "{}/{}/{}".format(ip, package.author.username, package.name)


def set_temp_key(key, v):
	redis_client.set(key, v, ex=EXPIRY_TIME_S)


def check_and_set_temp_key(key, v):
	redis_client.setnx(key, v, ex=EXPIRY_TIME_S)


def has_key(key):
	return redis_client.exists(key)


def increment_key(key):
	redis_client.incrby(key, 1)


def get_key(key, default=None):
	return redis_client.get(key) or default
