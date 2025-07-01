title: Package Inclusion Policy and Guidance


## 1. General

The ContentDB admin reserves the right to remove packages for any reason,
including ones not covered by this document, and to ban users who abuse this service.


## 2. Accepted Content

### 2.1. Mature Content

See the [Terms of Service](/terms/) for a full list of prohibited content.

Other mature content is permitted providing that it is labelled correctly.
See [Content Flags](/help/content_flags/).

### 2.2. Useful Content / State of Completion

ContentDB should only currently contain playable content - content which is
sufficiently complete to be useful to end-users.

It's fine to add stuff which is still a Work in Progress (WIP) as long as it
adds sufficient value. You should make sure to mark Work in Progress stuff as
such in the "maintenance status" dropdown, as this will help advise players.

Adding non-player facing mods, such as libraries and server tools, is perfectly
fine and encouraged. ContentDB isn't just for player-facing things and adding
libraries allows Luanti to automatically install dependencies.

### 2.3. Language

We require packages to be in English with (optional) client-side translations for
other languages. This is because Luanti currently requires English as the base language
([Issue to change this](https://github.com/luanti-org/luanti/issues/6503)).

Your package's title and short description must be in English. You can use client-side
translations to [translate content meta](https://api.minetest.net/translations/#translating-content-meta).

### 2.4. Attempt to contribute before forking

You should attempt to contribute upstream before forking a package. If you choose
to fork, you should have a justification (different objectives, maintainer is unavailable, etc).

### 2.5. Copyright and trademarks

Your package must not violate copyright or trademarks. You should avoid the use of
trademarks in the package's title or short description. If you do use a trademark,
ensure that you phrase it in a way that does not imply official association or
endorsement.


## 3. Technical Names

### 3.1. Right to a Name

A package uses a name when it has that name or contains a mod that uses that name.

The first package to use a name based on the creation of its forum topic or
ContentDB submission has the right to the technical name. The use of a package
on a server or in private doesn't reserve its name. No other packages of the same
type may use the same name, except for the exception given by 3.2.

If it turns out that we made a mistake by approving a package and that the
name should have been given to another package, then we *may* unapprove the
package and give the name to the correct one.

If you submit a package where you don't have the right to the name you will be asked
to change the name of the package, or your package won't be accepted.

We reserve the right to issue exceptions for this where we feel necessary.

### 3.2. Forks and Reimplementations

An exception to the above is that mods are allowed to have the same name as a
mod if it's a fork of that mod (or a close reimplementation). In real terms, it
should be possible to use the new mod as a drop-in replacement.

We reserve the right to decide whether a mod counts as a fork or
reimplementation of the mod that owns the name.

### 3.3. Game Mod Namespacing

New mods introduced by a game must have a unique common prefix to avoid conflicts with
other games and standalone mods. The prefix must end in an underscore. This does not
apply to existing mods included in the game that are available standalone or in other
game (for example, awards).

Standalone mods may not use a game's namespace unless they have been permission to
do so.

For example, the NodeCore game's first-party mods all start with `nc_`: `nc_api`, `nc_doors`.
NodeCore could include an existing mod like `awards` without needing the namespace.

The exception given by 3.2 also applies to game namespaces - you may use another game's
prefix if your game is a fork.


## 4. Licenses

### 4.1. License file

You must have a LICENSE.txt/md or COPYING file describing the licensing of your package.
Please ensure that you correctly credit any resources (code, assets, or otherwise)
that you have used in your package.

For help on doing copyright correctly, see the [Copyright help page](/help/copyright/).

### 4.2. Allowed Licenses

**The use of licenses that do not allow derivatives or redistribution is not
permitted. This includes CC-ND (No-Derivatives) and lots of closed source licenses.
The use of licenses that discriminate between groups of people or forbid the use
of the content on servers or singleplayer is also not permitted.**

However, closed sourced licenses are allowed if they allow the above.

If the license you use is not on the list then please select "Other", and we'll
get around to adding it. We reject custom/untested licenses and reserve the right
to decide whether a license should be included.

Please note that the definitions of "free" and "non-free" is the same as that
of the [Free Software Foundation](https://www.gnu.org/philosophy/free-sw.en.html).

### 4.3. Recommended Licenses

It is highly recommended that you use a Free and Open Source software (FOSS)
license. FOSS licenses result in a sharing community and will increase the
number of potential users your package has. Using a closed source license will
result in your package not being shown in Luanti by default. See the help page
on [non-free licenses](/help/non_free/) for more information.

It is recommended that you use a proper license for code with a warranty
disclaimer, such as the (L)GPL or MIT. You should also use a proper media license
for media, such as a Creative Commons license.

The use of WTFPL is discouraged as it doesn't contain a
[valid warranty disclaimer](https://cubicspot.blogspot.com/2017/04/wtfpl-is-harmful-to-software-developers.html),
and also includes swearing which prevents settings like schools from using your content.
[Read more](/help/wtfpl/).

Public domain is not a valid license in many countries, please use CC0 or MIT instead.


## 5. Promotions and Advertisements (inc. asking for donations)

You may not place any promotions or advertisements in any metadata including
screenshots. This includes asking for donations, promoting online shops,
or linking to personal websites and social media. Please instead use the
fields provided on your user profile page to place links to websites and
donation pages.

ContentDB is for the community. We may remove any promotions if we feel that
they're inappropriate.


## 6. Reviews and Package Score

You may invite players to review your package(s). One way to do this is by sharing the link found in the
"Share and Badges" page of the package's settings.

You must not require anyone to review a package. You must not promise or provide incentives for reviewing a package,
including but not limited to monetary rewards, in-game items, features, and/or privileges.
You may give a cosmetic-only role or badge to those who review your package - this must not be tied to the content or
rating of the review.

You must not attempt to unfairly manipulate your package's ranking, whether by reviews or any other method.
Doing so may result in temporary or permanent suspension from ContentDB.


## 7. Screenshots

1.  We require all packages to have at least one screenshot. For packages without visual
    content, we recommend making a representative image with icons or text to depict the package.

2.  **Screenshots must not violate copyright.** You should have the rights to the
    screenshot.

3.  **Screenshots must depict the actual content of the package in some way, and
    not be misleading.**

    Do not use idealized mockups or blender concept renders if they do not
    accurately reflect in-game appearance.

    Content in screenshots that is prominently displayed or "focal" should be
    either present in, or interact with, the package in some way. These can
    include things in other packages if they have a dependency relationship
    (either way), or if the submitted package in some way enhances, extends, or
    alters that content.

    Unrelated package content can be allowed to show what the package content
    will look like in a typical/realistic game scene, but should be "in the
    background" only as far as possible.

4.  **Screenshots must only contain content appropriate for the Content Warnings of
    the package.**

5.  **Screenshots should be MOSTLY in-game screenshots, if applicable.** Some
    alterations on in-game screenshots are okay, such as collages, added text,
    some reasonable compositing.

    Don't just use one of the textures from the package; show it in-situ as it
    actually looks in the game.

6.  **Screenshots should be of reasonable dimensions.** We recommend using 1920x1080.


## 8. Security

The submission of malware is strictly prohibited. This includes software that
does not do as it advertises, for example, if it posts telemetry without stating
clearly that it does in the package meta.

Packages must not ask that users disable mod security (`secure.enable_security`).
Instead, they should use the insecure environment API.

Packages must not contain obfuscated code.


## 9. Reporting Violations

Please click "Report" on the package page.
