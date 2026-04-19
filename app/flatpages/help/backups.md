title: Daily ContentDB database dump

You can download a backup of the ContentDB database at `/uploads/backup-YYYY-MM-DD.zip`.

This contains all public database information on ContentDB. It does not include uploads such as images or zip files.

This is updated daily at 05:15 UTC.

Note: this is experimental, the format and filename may change without notice.

## Structure

* `backup/`
  * index.json - `created_at` iso timestamp
  * `<username>/`
    * index.json - user information
    * `<package name>/`
      * index.json
      * releases.json
