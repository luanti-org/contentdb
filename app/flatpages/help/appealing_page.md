title: Creating an appealing ContentDB page

## Title and short description

Make sure that your package's title is unique, short, and descriptive.

Expand on the title with the short description. You have a limited number
of characters, use them wisely!

```ini
# Bad, we know this is a mod for Luanti. Doesn't give much information other than "food"
description = The food mod for Luanti
# Much better, says what is actually in this mod!
description = Adds soup, cakes, bakes and juices
```

## Thumbnail

A good thumbnail goes a long way to making a package more appealing. It's one of the few things
a user sees before clicking on your package. Make sure it's possible to tell what a
thumbnail is when it's small.

For a preview of what your package will look like inside Luanti, see
Edit Package > Screenshots.

## Screenshots

Upload a good selection of screenshots that show what is possible with your packages.
You may wish to focus on a different key feature in each of your screenshots.

A lot of users won't bother reading text, and will just look at screenshots.

## Long description

The target audience of your package page is end users.
The long description should explain what your package is about,
why the user should choose it, and how to use it if they download it.

[NodeCore](https://content.luanti.org/packages/Warr1024/nodecore/) is a good
example of what to do. For inspiration, you might want to look at how games on
Steam write their descriptions.

Your long description might contain:

* What does the package contain/have? ie: list of high-level features.
* What makes it special? Why should users choose this over another package?
* How can you use it?

The following are redundant and should probably not be included:

* A heading with the title of the package
* The short description
* Links to a Git repository, the forum topic, the package's ContentDB page (ContentDB has fields for this)
* License (unless you need to give more information than ContentDB's license fields)
* API reference (unless your mod is a library only)
* Development instructions for your package (this should be in the repo's README)
* Screenshots that are already uploaded (unless you want to embed a recipe image in a specific place)
    * Note: you should avoid images in the long description as they won't be visible inside Luanti,
      when support for showing the long description is added.

## Localize / Translate your package

According to Google Play, 64% of Luanti Android users don't have English as their main language.
Adding translation support to your package increases accessibility. Using content translation, you
can also translate your ContentDB page. See Edit Package > Translation for more information.

<p>
    <a class="btn btn-primary me-2" href="https://rubenwardy.com/minetest_modding_book/en/quality/translations.html">
        {{ _("Translation - Luanti Modding Book") }}
    </a>
    <a class="btn btn-primary" href="https://api.luanti.org/translations/#translating-content-meta">
        {{ _("Translating content meta - lua_api.md") }}
    </a>
</p>
