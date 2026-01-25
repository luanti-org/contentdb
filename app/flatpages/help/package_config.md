title: Package Configuration and Releases Guide

## Introduction

ContentDB will read configuration files in your package when doing several
tasks, including package and release creation. This page details how you can use
this to your advantage.

## .conf files

### What is a content .conf file?

Every type of content can have a `.conf` file that contains the metadata.

The filename of the `.conf` file depends on the content type:

* `mod.conf` for mods.
* `modpack.conf` for mod packs.
* `game.conf` for games.
* `texture_pack.conf` for texture packs.

The `.conf` uses a key-value format, separated using equals.

Here's a simple example of `mod.conf`, `modpack.conf`, or `texture_pack.conf`:

	name = mymod
	title = My Mod
	description = A short description to show in the client.

Here's a simple example of `game.conf`:

	title = My Game
	description = A short description to show in the client.

Note that you should not specify `name` in game.conf.

### Understood values

ContentDB understands the following information:

* `title` - A human-readable title.
* `description` - A short description to show in the client.
* `depends` - Comma-separated hard dependencies.
* `optional_depends` - Comma-separated soft dependencies.
* `min_minetest_version` - The minimum Luanti version this runs on, see [Min and Max Luanti Versions](#min_max_versions).
* `max_minetest_version` - The maximum Luanti version this runs on, see [Min and Max Luanti Versions](#min_max_versions).

and for mods only:

* `name` - the mod technical name.
* `supported_games` - List of supported game technical names.
* `unsupported_games` - List of not supported game technical names. Useful to override game support detection.


## .cdb.json

You can include a `.cdb.json` file in the root of your content directory (ie: next to a .conf)
to update the package meta.

It should be a JSON dictionary with one or more of the following optional keys:

* `type`: One of `GAME`, `MOD`, `TXP`.
* `title`: Human-readable title.
* `name`: Technical name (needs permission if already approved).
* `short_description`
* `dev_state`: One of `WIP`, `BETA`, `ACTIVELY_DEVELOPED`, `MAINTENANCE_ONLY`, `AS_IS`, `DEPRECATED`,
    `LOOKING_FOR_MAINTAINER`.
* `ai_disclosure`: One of `NONE`, `ASSISTED`, `GENERATED`.
* `tags`: List of tag names, see [/api/tags/](/api/tags/).
* `content_warnings`: List of content warning names, see [/api/content_warnings/](/api/content_warnings/).
* `license`: A license name, see [/api/licenses/](/api/licenses/).
* `media_license`: A license name.
* `long_description`: Long markdown description.
* `repo`: Source repository (eg: Git).
* `website`: Website URL.
* `issue_tracker`: Issue tracker URL.
* `forums`: forum topic ID.
* `video_url`: URL to a video.
* `donate_url`: URL to a donation page.
* `translation_url`: URL to send users interested in translating your package.

Use `null` or `[]` to unset fields where relevant.

Example:

```json
{
    "title": "Foo bar",
    "tags": ["pvp", "survival"],
    "license": "MIT",
    "website": null
}
```

## Controlling Release Creation

### Git-based Releases and Submodules

ContentDB can create releases from a Git repository.
It will include submodules in the resulting archive.
Simply set VCS Repository in the package's meta to a Git repository, and then
choose Git as the method when creating a release.

### Automatic Release Creation

See [Git Update Detection](/help/update_config/).
You can also use [GitLab/GitHub webhooks](/help/release_webhooks/) or the [API](/help/api/)
to create releases.

### Min and Max Luanti Versions

<a name="min_max_versions" />

When creating a release, the `.conf` file will be read to determine what Luanti
versions the release supports. If the `.conf` doesn't specify, then it is assumed
that it supports all versions.

This happens when you create a release via the ContentDB web interface, the
[API](/help/api/), or using a [GitLab/GitHub webhook](/help/release_webhooks/).

Here's an example config:

	name = mymod
	min_minetest_version = 5.0
	max_minetest_version = 5.3

Leaving out min or max to have them set as "None".

### Excluding files

When using Git to create releases,
you can exclude files from a release by using [gitattributes](https://git-scm.com/docs/gitattributes):


	.*		export-ignore
	sources		export-ignore
	*.zip		export-ignore


This will prevent any files from being included if they:

* Beginning with `.`
* or are named `sources` or are inside any directory named `sources`.
* or have an extension of "zip".
