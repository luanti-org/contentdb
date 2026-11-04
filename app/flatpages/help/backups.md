title: Daily ContentDB database dump

You can download a backup of the ContentDB database at `/uploads/backup-YYYY-MM-DD.zip`.

This contains all public database information on ContentDB. It does not include uploads such as images or zip files.

This is updated daily at 05:00 UTC.

Note: this is experimental, the format and filename may change without notice.

## Structure

* `backup/`
  * index.json - `version` of the dump format, currently 1, and `created_at` iso timestamp
  * licenses.json - `name`, `is_foss`, and `url` of each license
  * tags.json - `name`, `title`, `description`, `background_color`, and `text_color` of each tag
  * content_warnings.json - `name`, `title`, and `description` of each content warning
  * languages.json - `id` and `title` of each language
  * `<username>/` - for each author or maintainer of an approved package
    * index.json - user information
    * `<package name>/` - for each approved package
      * index.json - package information
        * `provides`, `depends`, and `optional_depends` are lists of mod names
        * `translations` maps a language id to its `title`, `short_desc`, and `desc`
        * `aliases` lists the old `author` and `name` that redirect to this package
        * `game_support` only includes approved games
      * releases.json - approved releases
      * screenshots.json - approved screenshots, with `title`, `order`, `filename`, `url`, `width`, `height`,
        `file_size_bytes`, `created_at`, and `is_cover_image`
