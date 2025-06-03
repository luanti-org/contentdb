title: Package Inclusion Policy and Guidance

## 0. Overview

ContentDB is for the community, and as such listings should be useful to the
community. To help with this, there are a few rules to improve the quality of
the listings and to combat abuse.

* **No inappropriate content.** <sup>2.1</sup>
* **Content must be playable/useful, but not necessarily finished.** <sup>2.2</sup>
* **Don't use the name of another mod unless your mod is a fork or reimplementation.** <sup>3</sup>
* **Licenses must allow derivatives, redistribution, and must not discriminate.** <sup>4</sup>
* **Don't put promotions or advertisements in any package metadata.** <sup>5</sup>
* **Don't manipulate package placement using reviews or downloads.** <sup>6</sup>
* **Screenshots must not be misleading.** <sup>7</sup>
* **Don't submit malware, clearly disclose telemetry, no obfuscated code.** <sup>8</sup>
* **Use a vcs system for mods and games** <sup>9</sup>
* **The ContentDB admin reserves the right to remove packages for any reason**,
  including ones not covered by this document, and to ban users who abuse
  this service. <sup>1</sup>


## 1. General

The ContentDB admin reserves the right to remove packages for any reason,
including ones not covered by this document, and to ban users who abuse this service.


## 2. Accepted Content

### 2.1. Acceptable Content

Sexually-orientated content is not permitted.
If in doubt at what this means, [contact us by raising a report](/report/).

Content which depicts or encourages the use of illegal drugs (under the laws of the United Kingdom) is not permitted.

Mature content is permitted providing that it is labelled correctly.
See [Content Flags](/help/content_flags/).

### 2.2. State of Completion

ContentDB should only currently contain playable content - content which is
sufficiently complete to be useful to end-users. It's fine to add stuff which is
still a Work in Progress (WIP) as long as it adds sufficient value; Note that
this doesn't mean that you should add a thing you started working on yesterday,
it's worth adding all the basic stuff to make your package useful.

You should make sure to mark Work in Progress stuff as such in the "maintenance
status" column, as this will help advise players.

Adding non-player facing mods, such as libraries and server tools, is perfectly
fine and encouraged. ContentDB isn't just for player-facing things, and adding
libraries allows them to be installed when a mod depends on it.


## 3. Technical Names

### 3.1 Right to a name

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

### 3.2. Mod Forks and Reimplementations

An exception to the above is that mods are allowed to have the same name as a
mod if it's a fork of that mod (or a close reimplementation). In real terms, it
should be possible to use the new mod as a drop-in replacement.

We reserve the right to decide whether a mod counts as a fork or
reimplementation of the mod that owns the name.


## 4. Licenses

### 4.1. Allowed Licenses

Please ensure that you correctly credit any resources (code, assets, or otherwise)
that you have used in your package. For help on doing copyright correctly, see
the [Copyright help page](/help/copyright/).

**The use of licenses that do not allow derivatives or redistribution is not
permitted. This includes CC-ND (No-Derivatives) and lots of closed source licenses.
The use of licenses that discriminate between groups of people or forbid the use
of the content on servers or singleplayer is also not permitted.**

However, closed sourced licenses are allowed if they allow the above.

If the license you use is not on the list then please select "Other", and we'll
get around to adding it. We tend to reject custom/untested licenses, and
reserve the right to decide whether a license should be included.

Please note that the definitions of "free" and "non-free" is the same as that
of the [Free Software Foundation](https://www.gnu.org/philosophy/free-sw.en.html).

### 4.2. Recommended Licenses

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

1.  **Screenshots must not violate copyright.** You should have the rights to the
    screenshot.

2.  **Screenshots must depict the actual content of the package in some way, and
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

3.  **Screenshots must only contain content appropriate for the Content Warnings of
    the package.**

4.  **Screenshots should be MOSTLY in-game screenshots, if applicable.** Some
    alterations on in-game screenshots are okay, such as collages, added text,
    some reasonable compositing.

    Don't just use one of the textures from the package; show it in-situ as it
    actually looks in the game.

5.  **Packages should have a screenshot when reasonably applicable.**

6.  **Screenshots should be of reasonable dimensions.** We recommend using 1920x1080.


## 8. Security

The submission of malware is strictly prohibited. This includes software that
does not do as it advertises, for example, if it posts telemetry without stating
clearly that it does in the package meta.

Packages must not ask that users disable mod security (`secure.enable_security`).
Instead, they should use the insecure environment API.

Packages must not contain obfuscated code.

## 9. Version Control System

For mods, and games a version control system (such as git) is required. Texture packs are currently exempt.

## Reporting Violations

Please click "Report" on the package page.