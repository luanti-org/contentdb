title: Daily ContentDB database dump

You can download a backup of the ContentDB database at [/uploads/backup.zip](/uploads/backup.zip).

This contains all public database information on ContentDB. It does not include uploads images or files.

This is updated daily at 05:15 UTC.

## Structure

* `backup/`
  * index.json - `created_at` iso timestamp
  * `<username>/`
    * index.json - user information
    * `<package name>/`
      * index.json
      * releases.json
