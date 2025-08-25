# ContentDB
# Copyright (C) rubenwardy
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import datetime

from .models import User, UserRank, LuantiRelease, Tag, License, Notification, NotificationType, Package, \
	PackageState, PackageType, PackageRelease, MetaPackage, Dependency
from .utils import make_flask_login_password


def populate(session):
	admin_user = User("rubenwardy")
	admin_user.is_active = True
	admin_user.password = make_flask_login_password("tuckfrump")
	admin_user.github_username = "rubenwardy"
	admin_user.forums_username = "rubenwardy"
	admin_user.rank = UserRank.ADMIN
	session.add(admin_user)

	system_user = User("ContentDB", active=False)
	system_user.email_confirmed_at = datetime.datetime.now() - datetime.timedelta(days=6000)
	system_user.rank = UserRank.BOT
	session.add(system_user)

	session.add(LuantiRelease("None", 0))
	session.add(LuantiRelease("0.4.16/17", 32))
	session.add(LuantiRelease("5.0", 37))
	session.add(LuantiRelease("5.1", 38))
	session.add(LuantiRelease("5.2", 39))
	session.add(LuantiRelease("5.3", 39))

	tags = {}
	for tag in ["Inventory", "Mapgen", "Building",
			"Mobs and NPCs", "Tools", "Player effects",
			"Environment", "Transport", "Maintenance", "Plants and farming",
			"PvP", "PvE", "Survival", "Creative", "Puzzle", "Multiplayer", "Singleplayer"]:
		row = Tag(tag)
		tags[row.name] = row
		session.add(row)

	licenses = {}
	for license in ["GPLv2.1", "GPLv3", "LGPLv2.1", "LGPLv3", "AGPLv2.1", "AGPLv3",
			"Apache", "BSD 3-Clause", "BSD 2-Clause", "CC0", "CC-BY-SA",
			"CC-BY", "MIT", "ZLib", "Other (Free)"]:
		row = License(license)
		licenses[row.name] = row
		session.add(row)

	for license in ["CC-BY-NC-SA", "Other (Non-free)"]:
		row = License(license, False)
		licenses[row.name] = row
		session.add(row)


def populate_test_data(session):
	licenses = { x.name : x for x in License.query.all() }
	tags = { x.name : x for x in Tag.query.all() }
	admin_user = User.query.filter_by(rank=UserRank.ADMIN).first()
	v4 = LuantiRelease.query.filter_by(protocol=32).first()
	v51 = LuantiRelease.query.filter_by(protocol=38).first()

	ez = User("Shara")
	ez.github_username = "Ezhh"
	ez.forums_username = "Shara"
	ez.rank = UserRank.EDITOR
	session.add(ez)

	not1 = Notification(admin_user, ez, NotificationType.PACKAGE_APPROVAL, "Awards approved", "/packages/rubenwardy/awards/")
	session.add(not1)

	jeija = User("Jeija")
	jeija.github_username = "Jeija"
	jeija.forums_username = "Jeija"
	session.add(jeija)

	mod = Package()
	mod.state = PackageState.APPROVED
	mod.name = "alpha"
	mod.title = "Alpha Test"
	mod.license = licenses["MIT"]
	mod.media_license = licenses["MIT"]
	mod.type = PackageType.MOD
	mod.author = admin_user
	mod.tags.append(tags["mapgen"])
	mod.tags.append(tags["environment"])
	mod.repo = "https://github.com/ezhh/other_worlds"
	mod.issueTracker = "https://github.com/ezhh/other_worlds/issues"
	mod.forums = 16015
	mod.short_desc = "The content library should not be used yet as it is still in alpha"
	mod.desc = "This is the long desc"
	session.add(mod)

	rel = PackageRelease()
	rel.package = mod
	rel.name = "v1.0.0"
	rel.title = "v1.0.0"
	rel.url = "https://github.com/ezhh/handholds/archive/master.zip"
	rel.approved = True
	session.add(rel)

	mod1 = Package()
	mod1.state = PackageState.APPROVED
	mod1.name = "awards"
	mod1.title = "Awards"
	mod1.license = licenses["LGPLv2.1"]
	mod1.media_license = licenses["MIT"]
	mod1.type = PackageType.MOD
	mod1.author = admin_user
	mod1.tags.append(tags["player_effects"])
	mod1.repo = "https://github.com/rubenwardy/awards"
	mod1.issueTracker = "https://github.com/rubenwardy/awards/issues"
	mod1.forums = 4870
	mod1.short_desc = "Adds achievements and an API to register new ones."
	mod1.desc = """
Majority of awards are back ported from Calinou's old fork in Carbone, under same license.

```lua
awards.register_achievement("award_mesefind",{
    title = "First Mese Find",
    description = "Found some Mese!",
    trigger = {
        type   = "dig",          -- award is given when
        node   = "default:mese", -- this type of node has been dug
        target = 1,              -- this number of times
    },
})
```
"""

	rel = PackageRelease()
	rel.package = mod1
	rel.min_rel = v51
	rel.name = "v1.0.0"
	rel.title = "v1.0.0"
	rel.url = "https://github.com/rubenwardy/awards/archive/master.zip"
	rel.approved = True
	session.add(rel)

	mod2 = Package()
	mod2.state = PackageState.APPROVED
	mod2.name = "mesecons"
	mod2.title = "Mesecons"
	mod2.tags.append(tags["tools"])
	mod2.type = PackageType.MOD
	mod2.license = licenses["LGPLv3"]
	mod2.media_license = licenses["MIT"]
	mod2.author = jeija
	mod2.repo = "https://github.com/minetest-mods/mesecons/"
	mod2.issueTracker = "https://github.com/minetest-mods/mesecons/issues"
	mod2.forums = 628
	mod2.short_desc = "Mesecons adds everything digital, from all kinds of sensors, switches, solar panels, detectors, pistons, lamps, sound blocks to advanced digital circuitry like logic gates and programmable blocks."
	mod2.desc = """
MESECONS by Jeija and contributors

Mezzee-what?
------------
[Mesecons](http://mesecons.net/)! They're yellow, they're conductive, and they'll add a whole new dimension to Minetest's gameplay.

Mesecons is a mod for [Minetest](http://minetest.net/) that implements a ton of items related to digital circuitry, such as wires, buttons, lights, and even programmable controllers. Among other things, there are also pistons, solar panels, pressure plates, and note blocks.

Mesecons has a similar goal to Redstone in Minecraft, but works in its own way, with different rules and mechanics.

OK, I want in.
--------------
Go get it!

[DOWNLOAD IT NOW](https://github.com/minetest-mods/mesecons/archive/master.zip)

Now go ahead and install it like any other Minetest mod. Don't know how? Check out [the wonderful page about it](http://wiki.minetest.com/wiki/Mods) over at the Minetest Wiki. For your convenience, here's a quick summary:

1. If Mesecons is still in a ZIP file, extract the folder inside to somewhere on the computer.
2. Make sure that when you open the folder, you can directly find `README.md` in the listing. If you just see another folder, move that folder up one level and delete the old one.
3. Open up the Minetest mods folder - usually `/mods/`. If you see the `minetest` or folder inside of that, that is your mod folder instead.
4. Copy the Mesecons folder into the mods folder.

Don't like some parts of Mesecons? Open up the Mesecons folder and delete the subfolder containing the mod you don't want. If you didn't want movestones, for example, all you have to do is delete the `mesecons_movestones` folder and they will no longer be available.

There are no dependencies - it will work right after installing!

How do I use this thing?
------------------------
How about a [quick overview video](https://www.youtube.com/watch?v=6kmeQj6iW5k)?

Or maybe a [comprehensive reference](http://mesecons.net/items.html) is your style?

An overview for the very newest of new beginners? How does [this one](http://uberi.mesecons.net/projects/MeseconsBasics/index.html) look?

Want to get more into building? Why not check out the [Mesecons Laboratory](http://uberi.mesecons.net/), a website dedicated to advanced Mesecons builders?

Want to contribute to Mesecons itself? Check out the [source code](https://github.com/minetest-mods/mesecons)!

Who wrote it anyways?
---------------------
These awesome people made Mesecons possible!

| Contributor     | Contribution                     |
| --------------- | -------------------------------- |
| Hawk777         | Code for VoxelManip caching      |
| Jat15           | Various tweaks.                  |
| Jeija           | **Main developer! Everything.**  |
| Jordach         | Noteblock sounds.                |
| khonkhortistan  | Code, recipes, textures.         |
| Kotolegokot     | Nodeboxes for items.             |
| minerd247       | Textures.                        |
| Nore/Novatux    | Code.                            |
| RealBadAngel    | Fixes, improvements.             |
| sfan5           | Code, recipes, textures.         |
| suzenako        | Piston sounds.                   |
| Uberi/Temperest | Code, textures, documentation.   |
| VanessaE        | Code, recipes, textures, design. |
| Whiskers75      | Logic gates implementation.      |

There are also a whole bunch of other people helping with everything from code to testing and feedback. Mesecons would also not be possible without their help!

Alright, how can I use it?
--------------------------
All textures in this project are licensed under the CC-BY-SA 3.0 (Creative Commons Attribution-ShareAlike 3.0 Generic). That means you can distribute and remix them as much as you want to, under the condition that you give credit to the authors and the project, and that if you remix and release them, they must be under the same or similar license to this one.

All code in this project is licensed under the LGPL version 3 or later. That means you have unlimited freedom to distribute and modify the work however you see fit, provided that if you decide to distribute it or any modified versions of it, you must also use the same license. The LGPL also grants the additional freedom to write extensions for the software and distribute them without the extensions being subject to the terms of the LGPL, although the software itself retains its license.

No warranty is provided, express or implied, for any part of the project.

"""

	session.add(mod1)
	session.add(mod2)

	mod = Package()
	mod.state = PackageState.APPROVED
	mod.name = "handholds"
	mod.title = "Handholds"
	mod.license = licenses["MIT"]
	mod.media_license = licenses["MIT"]
	mod.type = PackageType.MOD
	mod.author = ez
	mod.tags.append(tags["player_effects"])
	mod.repo = "https://github.com/ezhh/handholds"
	mod.issueTracker = "https://github.com/ezhh/handholds/issues"
	mod.forums = 17069
	mod.short_desc = "Adds hand holds and climbing thingies"
	mod.desc = "This is the long desc"
	session.add(mod)

	rel = PackageRelease()
	rel.package = mod
	rel.name = "v1.0.0"
	rel.title = "v1.0.0"
	rel.max_rel = v4
	rel.url = "https://github.com/ezhh/handholds/archive/master.zip"
	rel.approved = True
	session.add(rel)

	mod = Package()
	mod.state = PackageState.APPROVED
	mod.name = "other_worlds"
	mod.title = "Other Worlds"
	mod.license = licenses["MIT"]
	mod.media_license = licenses["MIT"]
	mod.type = PackageType.MOD
	mod.author = ez
	mod.tags.append(tags["mapgen"])
	mod.tags.append(tags["environment"])
	mod.repo = "https://github.com/ezhh/other_worlds"
	mod.issueTracker = "https://github.com/ezhh/other_worlds/issues"
	mod.forums = 16015
	mod.short_desc = "Adds space with asteroids and comets"
	mod.desc = "This is the long desc"
	session.add(mod)

	mod = Package()
	mod.state = PackageState.APPROVED
	mod.name = "food"
	mod.title = "Food"
	mod.license = licenses["LGPLv2.1"]
	mod.media_license = licenses["MIT"]
	mod.type = PackageType.MOD
	mod.author = admin_user
	mod.tags.append(tags["player_effects"])
	mod.repo = "https://github.com/rubenwardy/food/"
	mod.issueTracker = "https://github.com/rubenwardy/food/issues/"
	mod.forums = 2960
	mod.short_desc = "Adds lots of food and an API to manage ingredients"
	mod.desc = "This is the long desc"
	session.add(mod)

	mod = Package()
	mod.state = PackageState.APPROVED
	mod.name = "food_sweet"
	mod.title = "Sweet Foods"
	mod.license = licenses["CC0"]
	mod.media_license = licenses["MIT"]
	mod.type = PackageType.MOD
	mod.author = admin_user
	mod.tags.append(tags["player_effects"])
	mod.repo = "https://github.com/rubenwardy/food_sweet/"
	mod.issueTracker = "https://github.com/rubenwardy/food_sweet/issues/"
	mod.forums = 9039
	mod.short_desc = "Adds sweet food"
	mod.desc = "This is the long desc"
	food_sweet = mod
	session.add(mod)

	game1 = Package()
	game1.state = PackageState.APPROVED
	game1.name = "capturetheflag"
	game1.title = "Capture The Flag"
	game1.type = PackageType.GAME
	game1.license = licenses["LGPLv2.1"]
	game1.media_license = licenses["MIT"]
	game1.author = admin_user
	game1.tags.append(tags["pvp"])
	game1.tags.append(tags["survival"])
	game1.tags.append(tags["multiplayer"])
	game1.repo = "https://github.com/rubenwardy/capturetheflag"
	game1.issueTracker = "https://github.com/rubenwardy/capturetheflag/issues"
	game1.forums = 12835
	game1.short_desc = "Two teams battle to snatch and return the enemy's flag, before the enemy takes their own!"
	game1.desc = """
As seen on the Capture the Flag server (minetest.rubenwardy.com:30000)

` `[`javascript:/*--></title></style></textarea></script></xmp><svg/onload='+/"/+/onmouseover=1/+/`](javascript:/*--%3E%3C/title%3E%3C/style%3E%3C/textarea%3E%3C/script%3E%3C/xmp%3E%3Csvg/onload='+/%22/+/onmouseover=1/+/)`[*/[]/+alert(1)//'>`

<IMG SRC="javascript:alert('XSS');">

<IMG SRC=javascript:alert(&amp;quot;XSS&amp;quot;)>

``<IMG SRC=`javascript:alert("RSnake says, 'XSS'")`>``

\<a onmouseover="alert(document.cookie)"\>xxs link\</a\>

\<a onmouseover=alert(document.cookie)\>xxs link\</a\>

<IMG SRC=javascript:alert(String.fromCharCode(88,83,83))>

<script>alert("hello");</script>

<SCRIPT SRC=`[`http://xss.rocks/xss.js></SCRIPT>`](http://xss.rocks/xss.js%3E%3C/SCRIPT%3E)`;`

`<IMG \"\"\">`

<SCRIPT>

alert("XSS")

</SCRIPT>

<IMG SRC= onmouseover="alert('xxs')">

<img src=x onerror="&#0000106&#0000097&#0000118&#0000097&#0000115&#0000099&#0000114&#0000105&#0000112&#0000116&#0000058&#0000097&#0000108&#0000101&#0000114&#0000116&#0000040&#0000039&#0000088&#0000083&#0000083&#0000039&#0000041">

"\>

Uses the CTF PvP Engine.
"""

	session.add(game1)

	rel = PackageRelease()
	rel.package = game1
	rel.name = "v1.0.0"
	rel.title = "v1.0.0"
	rel.url = "https://github.com/rubenwardy/capturetheflag/archive/master.zip"
	rel.approved = True
	session.add(rel)


	mod = Package()
	mod.state = PackageState.APPROVED
	mod.name = "pixelbox"
	mod.title = "PixelBOX Reloaded"
	mod.license = licenses["CC0"]
	mod.media_license = licenses["CC0"]
	mod.type = PackageType.TXP
	mod.author = admin_user
	mod.forums = 14132
	mod.short_desc = "This is an update of the original PixelBOX texture pack by the brillant artist Gambit"
	mod.desc = "This is the long desc"
	session.add(mod)

	rel = PackageRelease()
	rel.package = mod
	rel.name = "v1.0.0"
	rel.title = "v1.0.0"
	rel.url = "http://mamadou3.free.fr/Minetest/PixelBOX.zip"
	rel.approved = True
	session.add(rel)

	session.commit()

	metas = {}
	for package in Package.query.filter_by(type=PackageType.MOD).all():
		try:
			meta = metas[package.name]
		except KeyError:
			meta = MetaPackage(package.name)
			session.add(meta)
			metas[package.name] = meta
		package.provides.append(meta)

	dep = Dependency(food_sweet, meta=metas["food"])
	session.add(dep)
