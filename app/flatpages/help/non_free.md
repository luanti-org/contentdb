title: Non-free Licenses

## What are Non-Free, Free, and Open Source licenses?

A non-free license is one that does not meet the
[Free Software Definition](https://www.gnu.org/philosophy/free-sw.en.html)
or the [Open Source Definition](https://opensource.org/osd).
ContentDB will clearly label any packages with non-free licenses,
and they will be subject to limited promotion.

## How does ContentDB deal with Non-Free Licenses?

**ContentDB does not allow new packages with Non-Free licenses.
Non-free packages will be removed from ContentDB in the future.**

Luanti is free and open source software, and is only as big as it is now
because of this. It's pretty amazing you can take nearly any published mod and modify it
to how you like - add some features, maybe fix some bugs - and then share those
modifications without the worry of legal issues. The project, itself, relies on open
source contributions to survive - if it were non-free, then it would have died
when celeron55 lost interest.

If you have played nearly any game with a large modding scene, you will find
that most mods are legally ambiguous. A lot of them don't even provide the
source code to allow you to bug fix or extend as you need.

Limiting the promotion of problematic licenses helps Luanti avoid ending up in
such a state. Licenses that prohibit redistribution or modification are
completely banned from ContentDB and the Luanti forums. Other non-free licenses
will be subject to limited promotion - they won't be shown by default in
the client.

Not providing full promotion on ContentDB, or not allowing your package at all,
doesn't mean you can't make such content - it just means we're not going to help
you spread it.

## What's so bad about licenses that forbid commercial use?

Please read [reasons not to use a Creative Commons -NC license](https://freedomdefined.org/Licenses/NC).
Here's a quick summary related to Luanti content:

1. They make your work incompatible with a growing body of free content, even if
   you do want to allow derivative works or combinations.
   This means that it can cause problems when another modder wishes to include your
   work in a modpack or game.
2. They may rule out other basic and beneficial uses that you want to allow.
   For example, CC -NC will forbid showing your content in a monetised YouTube
   video.
3. They are unlikely to increase the potential profit from your work, and a
   share-alike license serves the goal to protect your work from unethical
   exploitation equally well.

## How can I show non-free packages in the client?

Non-free packages are hidden in the client by default, partly in order to comply
with the rules of various Linux distributions.

Users can opt in to showing non-free software, if they wish:

1. In the main menu, go to Settings > All settings
2. Search for "ContentDB Flag Blacklist".
3. Edit that setting to remove `nonfree, `.

<figure class="figure my-4">
	<img class="figure-img img-fluid rounded" src="/static/contentdb_flag_blacklist.png" alt="Screenshot of the ContentDB Flag Blacklist setting">
	<figcaption class="figure-caption">Screenshot of the ContentDB Flag Blacklist setting</figcaption>
</figure>

The [`platform_default` flag](/help/content_flags/) is used to control what content
each platforms shows. It doesn't hide anything on Desktop, but hides all mature
content on Android. You may wish to remove all text from that setting completely,
leaving it blank. See [Content Warnings](/help/content_flags/#content-warnings)
for information on mature content.

## How can I hide non-free packages on the website?

Clicking "Hide non-free packages" in the footer of ContentDB will hide non-free packages from search results.
It will not hide non-free packages from user profiles.

## See also

* [List of non-free packages](/packages/?flag=nonfree)
* [Copyright Guide](/help/copyright)
