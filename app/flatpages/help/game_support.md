title: Supported Games

## Why?

The supported/compatible games feature allows mods to specify the games that
they work with, which improves user experience.


## Support sources

### mod.conf / texture_pack.conf

You can use `supported_games` to specify games that your mod/modpack/texture
pack is compatible with.

You can use `unsupported_games` to specify games that your package doesn't work
with, which is useful for overriding ContentDB's automatic detection.

Both of these are comma-separated lists of game technical ids. Any `_game`
suffixes are ignored, just like in Luanti.

    supported_games = minetest_game, repixture
    unsupported_games = lordofthetest, nodecore, whynot

If your package supports all games by default, you can put "*" in
supported_games. You can still use unsupported_games to mark games as
unsupported. You can also specify games that you've tested in supported_games.

    # Should work with all games but I've only tested using Minetest Game:
    supported_games = *, minetest_game

    # But doesn't work in capturetheflag
    unsupported_game = capturetheflag

### Dependencies

ContentDB will analyse hard dependencies and work out which games a mod
supports.

This uses a recursive algorithm that works out whether a dependency can be
installed independently, or if it requires a certain game.

### On ContentDB

You can define supported games on ContentDB, but using .conf is recommended
instead.


## Combining all the sources

.conf will override anything ContentDB detects. The manual override on ContentDB
overrides .conf and dependencies.

See also: [Package Configuration: .conf files](/help/package_config/#conf-files)
