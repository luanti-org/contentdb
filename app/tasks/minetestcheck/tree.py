import os, re
from . import MinetestCheckError, ContentType
from .config import parse_conf

basenamePattern = re.compile("^([a-z0-9_]+)$")

def get_base_dir(path):
	if not os.path.isdir(path):
		raise IOError("Expected dir")

	root, subdirs, files = next(os.walk(path))
	if len(subdirs) == 1 and len(files) == 0:
		return get_base_dir(path + "/" + subdirs[0])
	else:
		return path


def detect_type(path):
	if os.path.isfile(path + "/game.conf"):
		return ContentType.GAME
	elif os.path.isfile(path + "/init.lua"):
		return ContentType.MOD
	elif os.path.isfile(path + "/modpack.txt") or \
			os.path.isfile(path + "/modpack.conf"):
		return ContentType.MODPACK
	# elif os.path.isdir(path + "/mods"):
	# 	return ContentType.GAME
	elif os.path.isfile(path + "/texture_pack.conf"):
		return ContentType.TXP
	else:
		return ContentType.UNKNOWN


def get_csv_line(line):
	if line is None:
		return []

	return [x.strip() for x in line.split(",") if x.strip() != ""]


class PackageTreeNode:
	def __init__(self, baseDir, relative, author=None, repo=None, name=None):
		self.baseDir  = baseDir
		self.relative = relative
		self.author   = author
		self.name	 = name
		self.repo	 = repo
		self.meta	 = None
		self.children = []

		# Detect type
		self.type = detect_type(baseDir)
		self.read_meta()

		if self.type == ContentType.GAME:
			if not os.path.isdir(baseDir + "/mods"):
				raise MinetestCheckError("Game at {} does not have a mods/ folder".format(self.relative))
			self.add_children_from_mod_dir("mods")
		elif self.type == ContentType.MOD:
			if self.name and not basenamePattern.match(self.name):
				raise MinetestCheckError(f"Invalid base name for mod {self.name} at {self.relative}, names must only contain a-z0-9_.")
			self.check_dir_casing(["textures", "media", "sounds", "models", "locale"])
		elif self.type == ContentType.MODPACK:
			self.add_children_from_mod_dir(None)

	def check_dir_casing(self, dirs):
		for dir in next(os.walk(self.baseDir))[1]:
			lowercase = dir.lower()
			if lowercase != dir and lowercase in dirs:
				raise MinetestCheckError(f"Incorrect case, {dir} should be {lowercase} at {self.relative}{dir}")

	def getReadMePath(self):
		for filename in os.listdir(self.baseDir):
			path = os.path.join(self.baseDir, filename)
			if os.path.isfile(path) and filename.lower().startswith("readme."):
				return path

	def getMetaFileName(self):
		if self.type == ContentType.GAME:
			return "game.conf"
		elif self.type == ContentType.MOD:
			return "mod.conf"
		elif self.type == ContentType.MODPACK:
			return "modpack.conf"
		elif self.type == ContentType.TXP:
			return "texture_pack.conf"
		else:
			return None

	def read_meta(self):
		result = {}

		# Read .conf file
		meta_file_name = self.getMetaFileName()
		if meta_file_name is not None:
			meta_file_rel = self.relative + meta_file_name
			meta_file_path = self.baseDir + "/" + meta_file_name
			try:
				with open(meta_file_path or "", "r") as myfile:
					conf = parse_conf(myfile.read())
					for key, value in conf.items():
						result[key] = value
			except SyntaxError as e:
				raise MinetestCheckError("Error while reading {}: {}".format(meta_file_rel , e.msg))
			except IOError:
				pass

			if "release" in result:
				raise MinetestCheckError("{} should not contain 'release' key, as this is for use by ContentDB only.".format(meta_file_rel))


		# description.txt
		if not "description" in result:
			try:
				with open(self.baseDir + "/description.txt", "r") as myfile:
					result["description"] = myfile.read()
			except IOError:
				pass

		# Read dependencies
		if "depends" in result or "optional_depends" in result:
			result["depends"] = get_csv_line(result.get("depends"))
			result["optional_depends"] = get_csv_line(result.get("optional_depends"))

		elif os.path.isfile(self.baseDir + "/depends.txt"):
			pattern = re.compile("^([a-z0-9_]+)\??$")

			with open(self.baseDir + "/depends.txt", "r") as myfile:
				contents = myfile.read()
				soft = []
				hard = []
				for line in contents.split("\n"):
					line = line.strip()
					if pattern.match(line):
						if line[len(line) - 1] == "?":
							soft.append( line[:-1])
						else:
							hard.append(line)

				result["depends"] = hard
				result["optional_depends"] = soft

		else:
			result["depends"] = []
			result["optional_depends"] = []


		def checkDependencies(deps):
			for dep in deps:
				if not basenamePattern.match(dep):
					if " " in dep:
						raise MinetestCheckError("Invalid dependency name '{}' for mod at {}, did you forget a comma?" \
							.format(dep, self.relative))
					else:
						raise MinetestCheckError(
								"Invalid dependency name '{}' for mod at {}, names must only contain a-z0-9_." \
									.format(dep, self.relative))

		# Check dependencies
		checkDependencies(result["depends"])
		checkDependencies(result["optional_depends"])

		# Fix games using "name" as "title"
		if self.type == ContentType.GAME and "name" in result:
			result["title"] = result["name"]
			del result["name"]

		# Calculate Title
		if "name" in result and not "title" in result:
			result["title"] = result["name"].replace("_", " ").title()

		# Calculate short description
		if "description" in result:
			desc = result["description"]
			idx = desc.find(".") + 1
			cutIdx = min(len(desc), 200 if idx < 5 else idx)
			result["short_description"] = desc[:cutIdx]

		if "name" in result:
			self.name = result["name"]
			del result["name"]

		self.meta = result

	def add_children_from_mod_dir(self, subdir):
		dir = self.baseDir
		relative = self.relative
		if subdir:
			dir += "/" + subdir
			relative += subdir + "/"

		for entry in next(os.walk(dir))[1]:
			path = os.path.join(dir, entry)
			if not entry.startswith('.') and os.path.isdir(path):
				child = PackageTreeNode(path, relative + entry + "/", name=entry)
				if not child.type.isModLike():
					raise MinetestCheckError("Expecting mod or modpack, found {} at {} inside {}" \
						.format(child.type.value, child.relative, self.type.value))

				if child.name is None:
					raise MinetestCheckError("Missing base name for mod at {}".format(self.relative))

				self.children.append(child)

	def getModNames(self):
		return self.fold("name", type_=ContentType.MOD)

	# attr: Attribute name
	# key: Key in attribute
	# retval: Accumulator
	# type_: Filter to type
	def fold(self, attr, key=None, retval=None, type_=None):
		if retval is None:
			retval = set()

		# Iterate through children
		for child in self.children:
			child.fold(attr, key, retval, type_)

		# Filter on type
		if type_ and type_ != self.type:
			return retval

		# Get attribute
		at = getattr(self, attr)
		if not at:
			return retval

		# Get value
		value = at if key is None else at.get(key)
		if isinstance(value, list):
			retval |= set(value)
		elif value:
			retval.add(value)

		return retval

	def get(self, key):
		return self.meta.get(key)

	def validate(self):
		for child in self.children:
			child.validate()
