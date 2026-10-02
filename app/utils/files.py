# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>

import contextlib
import os
import tempfile
import shutil
from .misc import random_string

@contextlib.contextmanager
def get_temp_dir():
	temp = os.path.join(tempfile.gettempdir(), random_string(10))
	yield temp
	shutil.rmtree(temp, ignore_errors=True)
