# Luanti's use of the API

This document explains how Luanti's ContentDB client interacts with ContentDB.
This is useful both for implementing your own client for ContentDB to install mods, 
or for implementing ContentDB compatible servers.

## Package List API call

The client makes a single [API](https://content.luanti.org/help/api/) request to `/api/packages/`.

The query arguments will include a list of supported types, the current
[engine version](https://content.luanti.org/api/minetest_versions/),
and any hidden [Content Flags](https://content.luanti.org/help/content_flags/).

Example URL:
<https://content.luanti.org/api/packages/?type=mod&type=game&type=txp&protocol_version=39&engine_version=5.3.0&hide=nonfree&hide=desktop_default>

Example response:

```json
[
    {
        "author": "Warr1023",
        "name": "nodecore",
        "release": 1234,
        "short_description": "A short description",
        "thumbnail": "https://content.luanti.org/thumbnails/1/abcdef.jpg",
        "title": "NodeCore",
        "type": "game"
    }
]
```

`thumbnail` is optional, but all other fields are required. 

`type` is one of `mod`, `game`, or `txp`.

`release` is the release ID. Newer releases have higher IDs.
Luanti compares this ID to a locally stored version to detect whether a package has updates.

Because the client specifies the engine version information, the response must contain a release
number and the package must be downloadable.

## Screenshots

The client can simply download the URL mentioned in `thumbnail`.

## Downloading and installing

The client downloads packages by constructing a URL for the release and downloading it:

```
https://content.luanti.org/packages/<author>/<name>/releases/<release>/download/
```

This supports redirects.

The client will edit the .conf of the installed content to add `author`, `name`, and `release` to
track the installed release to detect updates in the future.

## Resolving Dependencies

### Short version

Luanti uses `/api/packages/<author>/<name>/dependencies/?only_hard=1` to find out the hard
dependencies for a package.

Then, it resolves each dependency recursively. 

Say you're resolving for `basic_materials`, then it will attempt to find the mod in this order:

1. It first checks installed mods in the game and mods folder (ie: `mods/basic_materials/`)
2. Then it looks on ContentDB for exact name matches (ie: `VanessaE/basic_materials`)
3. Then it looks on ContentDB for modpacks which contain (=provides) the modname
   (ie: `VanessaE/dreambuilder`)

### Long version

When installing a package, an API request is made to ContentDB to find out the dependencies.
If there are no dependencies, then the mod is installed straight away.

If there are dependencies, it will resolve them and show a dialog with a list of mods to install.

Resolving works like this:

1. Fetch dependencies for the package from ContentDB's API
2. For each hard dependency:
    1. Check current game, exit if dep found
    2. Check installed mods, exit if found
    3. Check available mods from ContentDB:
        1. Choose a package to install. Prefer higher scores and exact base name matches
           (rather than modpacks).
        2. Resolve dependencies for this package - ie, goto 1.

The ContentDB API is a dictionary of packages to dependencies.
The dictionary will allow ContentDB to prefetch dependencies without any client changes.
For example, say you request the dependencies for Mobs Monster.
It's pretty likely that the next request you'll make is for Mobs Redo, and so ContentDB can prevent
the need for another request by including the dependency information for Mobs Redo in the
response for Mobs Monster.

## View in browser

The client will open the package in a browser by constructing the following URL

```
https://content.luanti.org/packages/<author>/<name>/
```
