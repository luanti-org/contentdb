title: Content Flags

Content flags allow you to hide content based on your preferences.
The filtering is done server-side, which means that you don't need to update
your client to use new flags.

## Flags

Luanti allows you to specify a comma-separated list of flags to hide in the
client:

```
contentdb_flag_blacklist = nonfree, bad_language, drugs
```

A flag can be:

* `nonfree`: can be used to hide packages which do not qualify as
    'free software', as defined by the Free Software Foundation.
* `wip`: packages marked as Work in Progress
* `deprecated`: packages marked as Deprecated
* A content warning, given below.
* `*`: hides all content warnings.

There are also two meta-flags, which are designed so that we can change how different platforms filter the package list
without making a release.

* `android_default`: currently same as `*, deprecated`. Hides all content warnings and deprecated packages
* `desktop_default`: currently same as `deprecated`. Hides deprecated packages

## Content Warnings

Packages with mature content will be tagged with a content warning based
on the content type.

* `alcohol_tobacco`: alcohol or tobacco.
* `bad_language`: swearing.
* `gambling`
* `gore`: blood, etc.
* `horror`: shocking and scary content.
* `violence`: non-cartoon violence.
