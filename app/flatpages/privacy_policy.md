title: Privacy Policy
---

Last Updated: 2026-11-14
([View updates](https://github.com/luanti-org/contentdb/commits/master/app/flatpages/privacy_policy.md))

## What Information is Collected

**All users:**

* HTTP requests are logged, with the following information:
	* Time
	* IP address
	* Page URL
	* Platform and Operating System
* Preferred language/locale. This defaults to the browser's locale, but can be changed by the user
* View/download counters: Whether an IP address has downloaded or viewed a particular package in the last 14 days

**With an account:**

* Email address
* Passwords (hashed and salted using BCrypt)
* Profile information, such as website URLs and donation URLs
* Comments, threads, and reviews
* Audit log actions (such as edits and logins) and their time stamps
* The IP address, platform, and operating system of your session

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
* Requests (such as package views and downloads) are used for aggregated statistics and for
  calculating the popularity of packages. For example, download counts are shown
  for each package and release and there are also view and download graphs available for
  each package.
* Whether an IP address has viewed or downloaded a package or release is cached to prevent
  view or downloads from being counted multiple times per IP address, but this
  information is deleted after 14 days.
* IP addresses, platform, and operating system are used to monitor and combat abuse.
* The platform, operating system, and approximate location of your sessions are shown on your
  account settings page, so that you can recognise them.
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
* The platform, operating system, and approximate location of your sessions are visible to you,
  moderators, and the admin. Session IP addresses are not shown on the website, and can only be viewed by those
  with access to the database or a backup.
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

Account information is kept until your account is deleted. See "Deleting your
account" below.

Whether an IP address has downloaded a package or release is deleted after 14 days.

Sessions, including their IP address, platform, and operating system, are deleted when you
log out, when you change your password, or when they expire. Sessions expire after 30 days
without being used, or a year after you logged in.

## Deleting your account

You can delete your account from your account settings, as long as you don't own
any packages.

Your account will be deleted 7 days after you ask. During that time:

* You'll be signed out on all devices, and your API tokens will stop working.
* Signing in again cancels the deletion.
* If your account has an email address, we'll email you when you ask, the day
  before your account is deleted, and once it has been deleted.

When your account is deleted, we delete your email address, password, profile
information, login sessions, API tokens, notifications, comments, threads,
reviews and collections. Threads you started are deleted, including replies from
other users.

We keep the following, as they're needed for moderation:

* Audit log entries, no longer linked to your account. Some entries contain your
  username, such as the record that your account was deleted.
* Reports you made, no longer linked to your account.

ContentDB keeps a record of each username and forum topic on the forums, for use
in indexing mod/game topics. If you have mod or game topics on the forums, your
forum username and topics will be added back as an author who has not yet joined
ContentDB.

ContentDB uses usernames to identify packages, so an account that owns packages
can't be fully deleted. Transfer or delete your packages first, or
[raise a report](/report/?anon=0) to ask us to remove your personal information.
If we can't delete your account, it will instead be wiped and deactivated, ending
up exactly like an author who has not yet joined ContentDB. All personal
information will be removed from the profile, and any comments or threads will be
deleted.

## Future Changes to Privacy Policy

We will alert any future changes to the privacy policy via notices on the
ContentDB website.

By continuing to use this service, you agree to the privacy policy.
