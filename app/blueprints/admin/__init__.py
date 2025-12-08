# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


from flask import Blueprint

bp = Blueprint("admin", __name__)

from . import admin, audit, licenseseditor, tagseditor, versioneditor, warningseditor, languageseditor, approval_stats, update_config
