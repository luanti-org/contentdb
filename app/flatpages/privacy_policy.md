title: Privacy Policy
---

Last Updated: 2024-04-30
([View updates](https://github.com/luanti-org/contentdb/commits/master/app/flatpages/privacy_policy.md))

## What Information is Collected

**All users:**

* HTTP requests are logged, with the following information:
	* Time
	* IP address
	* Page URL
	* Platform and Operating System
* Preferred language/locale. This defaults to the browser's locale, but can be changed by the user
* Whether an IP address has downloaded a particular package in the last 14 days

**With an account:**

* Email address
* Passwords (hashed and salted using BCrypt)
* Profile information, such as website URLs and donation URLs
* Comments, threads, and reviews
* Audit log actions (such as edits and logins) and their time stamps

ContentDB collects usernames of content creators from the forums,
as this is required to index forum topics.

Packages, including releases, screenshots, and any meta information,
are not considered personal information.

Please avoid giving other personal information as we do not want it.

## How this information is used

* Logged HTTP requests may be used for debugging ContentDB and combating abuse.
* Email addresses are used to:
    * Provide essential system messages, such as password resets and privacy policy updates.
    * Send notifications - the user may configure this to their needs, including opting out.
    * The admin may use ContentDB to send emails when they need to contact a user.
* Passwords are used to authenticate the user.
* The audit log is used to record actions that may be harmful.
* Preferred language/locale is used to translate emails and the ContentDB interface.
* Requests (such as downloads) are used for aggregated statistics and for
  calculating the popularity of packages. For example, download counts are shown
  for each package and release and there are also download graphs available for
  each package.
* Whether an IP address has downloaded a package or release is cached to prevent
  downloads from being counted multiple times per IP address, but this
  information is deleted after 14 days.
* IP addresses are used to monitor and combat abuse.
* Other information is displayed as part of ContentDB's service.

## Who has access

* Only the admin has access to the HTTP requests.
  The logs may be shared with others to aid in debugging, but care will be taken to remove any personal information.
* Encrypted backups may be shared with selected Luanti staff members (moderators + core devs).
  The keys and the backups themselves are given to different people,
  requiring at least two staff members to read a backup.
* Email addresses are visible to moderators and the admin.
  They have access to assist users, and they are not permitted to share email addresses.
* Hashing protects passwords from being read whilst stored in the database or in backups.
* Profile information is public, including URLs and linked accounts.
* The visibility of comments depends on the visibility of threads.
  They are either public, or visible only to the package author and editors.
* The complete audit log is visible to moderators.
  Users may see their own audit log actions on their account settings page.
  Owners, maintainers, and editors can see the actions on a package.
* Preferred language can only be viewed by those with access to the database or a backup.
* We may be required to share information with law enforcement.

## Third-parties

We do not share any personal information with third parties.

We use <a href="https://sentry.io/">Sentry.io</a> for error logging and performance monitoring.

## Location

The ContentDB production server is currently located in Germany.
Backups are stored in the UK.
Encrypted backups may be stored in other countries, such as the US or EU.

By using this service, you give permission for the data to be moved within the
United Kingdom and/or EU.

## Period of Retention

Logged HTTP requests are automatically deleted within 2 weeks.

Usernames may be kept indefinitely, but other user information will be deleted
if requested. See below.

Whether an IP address has downloaded a package or release is deleted after 14 days.

## Removal Requests

Please [raise a report](/report/?anon=0) if you wish to remove your personal
information.

ContentDB keeps a record of each username and forum topic on the forums, for use
in indexing mod/game topics. ContentDB also requires the use of a username to
uniquely identify a package. Therefore, an author cannot be removed completely
from ContentDB if they have any packages or mod/game topics on the forum.

If we are unable to remove your account for one of the above reasons, your user
account will instead be wiped and deactivated, ending up exactly like an author
who has not yet joined ContentDB. All personal information will be removed from
the profile, and any comments or threads will be deleted.

## Future Changes to Privacy Policy

We will alert any future changes to the privacy policy via notices on the
ContentDB website.

By continuing to use this service, you agree to the privacy policy.
