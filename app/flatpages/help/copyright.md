title: Copyright Guide

## Why should I care?

Falling foul of copyright law can put you and ContentDB into legal trouble. Receiving a Cease and Desist, DMCA notice,
or a Court Summons isn't pleasant for anyone, and can turn out to be very expensive. This page contains some
guidance on how to ensure your content is clearly licensed and attributed to avoid these issues.

Additionally, ContentDB and the forums both have some
[requirements on the licenses](/policy_and_guidance/#41-allowed-licenses) you are allowed to use. Both require
[free distribution and modification](/help/non_free/), allowing us to remain an open community where people can fork
and remix each other's content. To this end, you need to make sure your content is clearly licensed.

**As always, we are not lawyers and this does not constitute legal advice.**


## What do I need to do?

### Follow the licenses

Make sure you understand the licenses for anything you copy into your content.
[TL;DR Legal](https://tldrlegal.com/license/mit-license) is a good resource for quickly understanding
licenses, although you should actually read the text as well.

If you use code from other sources (such as mods or games), you'll need to make sure you follow
their license. A common one is attribution, you should do this by adding a comment next to the
code and crediting the author in your LICENSE file.

It's sometimes fine to copy trivial/small amounts of code under fair use, but this
is a bit of a grey area. It's better to understand the solution and rewrite it yourself.

### List the sources of your media

It's a good idea to create a list of all the media you used in your package, as it allows
you to keep track of where the media came from. Media includes textures, 3d models,
sounds, and more.

You should have the following information:

* File name (as found in your package)
* Author name
* License
* Source (URL to the webpage, mod name, website name)

It's common to do this in README.md or LICENSE.md like so:

```md
* conquer_arrow_*.png from [Simple Shooter](https://github.com/stujones11/shooter) by Stuart Jones, CC0 1.0.
* conquer_arrow.b3d from [Simple Shooter](https://github.com/stujones11/shooter) by Stuart Jones, CC-BY-SA 3.0.
* conquer_arrow_head.png from MTG, CC-BY-SA 3.0.
* health_*.png from [Gauges](https://content.luanti.org/packages/Calinou/gauges/) by Calinou, CC0.
```

if you have a lot of media, then you can split it up by author like so:

```md
[Kenney](https://www.kenney.nl/assets/voxel-pack), CC0:

* mymod_fence.png

John Green, CC BY-SA 4.0 from [OpenGameArt](https://opengameart.org/content/tiny-16-basic):

* mymod_texture.png
* mymod_another.png

Your Name, CC BY-SA 4.0:

* mymod_texture_i_made.png
```


## Where can I get freely licensed media?

* [OpenGameArt](https://opengameart.org/) - everything
* [Kenney game assets](https://www.kenney.nl/assets) - everything
* [Free Sound](https://freesound.org/) - sounds
* [PolyHaven](https://polyhaven.com/) - 3d models and textures.
* Other Luanti mods/games

    Don't assume the author has correctly licensed their work.
    Make sure they have clearly indicated the source in a list [like above](#list-the-sources-of-your-media).
    If they didn't make it, then go to the actual source to check the license.


## Common Situations

### I made it myself, using X as a guide

Copying by hand is still copying, the law doesn't distinguish this from copy+paste.
Make your own art without copying colors or patterns from existing games/art.

If you need a good set of colors, see [LOSPEC](https://lospec.com/palette-list).

### I got it from Google Images / Search / the Internet

You do not have permission to use things unless you are given permission to do so by the author.
No license is exactly the same as "Copyright &copy; All Rights Reserved".
To use on ContentDB or the forums, you must also be given a clear license.

Try searching with "creative commons" in the search term, and then clicking through to the page
and looking for a license. Make sure the source looks trustworthy, as there are a lot of websites
that rip off art and give an incorrect license. But it might be better to use a trusted source directly, see
[the section above](#where-can-i-get-freely-licensed-media) for a list.

### I have permission from the author

You'll also need to make sure that the author gives you an explicit license for it, such as CC BY-SA 4.0.
Permission for *you* to use it doesn't mean that *everyone* has permission to use it. A license outlines the terms of
the permission, making things clearer and less vague.

### The author said it's free for anyone to use, is that enough?

No, you need an explicit license like CC0 or CC BY-SA 4.0. ContentDB does not allow custom licenses
or public domain.

### I used an AI

Errrr. This is a legally untested area, we highly recommend that **you don't use AI art/code** in packages
for that reason.

For now, we haven't banned AI art/code from ContentDB. Make sure to clearly include it in your package's
credit list (include the name of the AI tool used).

Check the tools terms and conditions to see if there are any constraints on use. It looks
like AI-generated art and code isn't copyrightable by itself, but the tool's T&Cs may still
impose conditions.

AI art/code may regurgitate copyrighted things. Make sure that you don't include the
names of any copyrighted materials in your AI prompts, such as names of games or artists.

## What does ContentDB do?

The package authors and maintainers are responsible for the licenses and copyright of packages on ContentDB.
ContentDB editors will check packages to make sure the package page's license matches up with the list of licenses
inside the package download, but do not investigate each piece of media or line of code.

If a copyright violation is reported to us, we will unlist the package and contact the author/maintainers.
Once the problem has been fixed, the package can be restored. Repeated copyright infringement may lead to
permanent bans.


## Where can I get help?

[Join](https://www.luanti.org/get-involved/) IRC, Matrix, or Discord to ask for help.
In Discord, there are the #assets or #contentdb channels. In IRC or Matrix, you can just ask in the main channels.

If your package is already on ContentDB, you can open a thread.
