# -*- coding: utf-8 -*-
"""
A small Flask extension that makes it easy to use Sass (SCSS) with your
Flask application.

Code unabashedly adapted from https://github.com/weapp/flask-coffee2js

:copyright: (c) 2012 by Ivan Miric.
:license: MIT, see LICENSE for more details.
"""

import os
import os.path
import codecs
import sass
from flask import send_from_directory


def _convert(dir_path, src, dst):
	original_wd = os.getcwd()
	os.chdir(dir_path)

	source = codecs.open(src, 'r', encoding='utf-8').read()
	output = sass.compile(string=source)

	os.chdir(original_wd)

	outfile = codecs.open(dst, 'w', encoding='utf-8')
	outfile.write(output)
	outfile.close()


def _get_dir_path(app, original_path, create=False):
	path = original_path

	if not os.path.isdir(path):
		path = os.path.join(app.root_path, path)

	if not os.path.isdir(path):
		if create:
			os.makedirs(path, exist_ok=True)
		else:
			raise IOError("Unable to find " + original_path)

	return path


def init_app(app, input_dir='scss', dest='static', force=False, cache_dir="public/static"):
	input_dir = _get_dir_path(app, input_dir)
	cache_dir = _get_dir_path(app, cache_dir or dest, True)

	def _sass(filepath):
		scss_file = "%s/%s.scss" % (input_dir, filepath)
		cache_file = "%s/%s.css" % (cache_dir, filepath)

		if os.path.isfile(scss_file):
			if force or not os.path.isfile(cache_file) or \
					os.path.getmtime(scss_file) > os.path.getmtime(cache_file):
				_convert(input_dir, scss_file, cache_file)
				app.logger.debug('Compiled %s into %s' % (scss_file, cache_file))

			res = send_from_directory(cache_dir, filepath + ".css")
		else:
			# Not generated from SCSS, such as CSS from libraries
			res = send_from_directory(app.static_folder, filepath + ".css")


		res.headers["Cache-Control"] = "max-age=604800"  # 1 week
		return res

	app.add_url_rule("/%s/<path:filepath>.css" % dest, 'sass', _sass)
