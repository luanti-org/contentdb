# ContentDB
# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2018-2025 rubenwardy <rw@rubenwardy>


from typing import Tuple
from PIL import Image


def get_image_size(path: str) -> Tuple[int,int]:
	im = Image.open(path)
	return im.size
