# Testing work: handover notes

Written 2026-11-08 so another session can pick up phase 1 of the test coverage plan without the original
conversation. Delete this file once the work is finished. It isn't meant to be committed.

## Read first

- `.claude/CLAUDE.md`: run linters in full (`uv run mypy`, and
  `uv run --locked --only-group dev ruff check app utils`) and the relevant tests before finishing. A regression test
  must fail without its fix.
- `.claude/knowledgebase/writing-tests.md`: test layout, fixtures, factories and gotchas.
- `.claude/knowledgebase/test-coverage.md`: how coverage is measured, and the snapshot of what was untested.
- `.claude/knowledgebase/reauthentication.md` and `user-deletion.md`: background on recent features.

## The user's preferences

- Only commit when the user asks. Never add a `Co-Authored-By: Claude` line.
- When asked how to split work into commits, propose a split first. Make each commit pass on its own, building
  intermediate file versions where needed.
- If a test turns up a bug, fix small, clear bugs and call them out. Ask about anything that might be intended.
- For phase 1, the user asked that every new test be checked by mutation: introduce bugs into the code under test
  (for example, invert a permission check or remove a filter), and confirm the tests fail. Then restore the code.

## Running things

- `utils/tests.sh [pytest args]` runs tests in the throwaway Docker test stack. `utils/tests_cov.sh` runs the full
  suite with coverage, about 9 minutes, with a 60% minimum in `utils/test/coverage.cfg`.
- After a reboot, the test stack may need starting with `utils/test_stack.sh up`. `tests.sh` starts it if it's down.
- Full suite at the last commit: 633 passed, 60.46% coverage of application code.
- For mutation checks, use a small script that copies the file to a backup, applies a find/replace, runs the target
  tests, records pass or fail, and always restores the backup. Check afterwards that no `.bak` files are left and
  that `git diff` of the app code is clean.

## Done (committed)

- Phase 0, in commits `4d1a13e5` to `aecc74d8`:
  - The folder structure in `app/tests/integ/`: `accounts/`, `api/`, `packages/`, `moderation/`, `data/`, `core/`.
  - `conftest.py`, with the fixtures `client`, `http_stub`, `mailpit` and `eager_tasks`.
  - `factories.py`, with the `create_*` helpers, `login_as`, `client_request`, `make_session_stale`, `get_user`
    and `DEFAULT_PASSWORD`.
  - Coverage measured on application code only, with a minimum.

## Phase 1: done, committed in 47de0edb to 95d63e8f

All of phase 1's tests are written and pass, mutation-checked (127 mutations, 5 equivalent survivors, listed in
`.claude/knowledgebase/test-coverage.md`). The full suite has 840 tests and 64.88% coverage; `fail_under` is now 64.
mypy and ruff pass.

Fixes made (each regression test confirmed to fail without the fix):
- `Package.get_review_summary()` counted unapproved reviews.
- `report()` 500'd on a non-image attachment; the attachment is now uploaded before anything is created.
- `package_info_as_hypertext` didn't escape maintainer display names (and other lists).

Still open: three questions (approvers viewing packages awaiting review; the package
page hiding private threads from non-owner maintainers and watchers; `/threads/` hiding users' own private threads).

## Phase 2: done, committed in 1bc87444 to 59d20503

1008 tests, 69.84% coverage, `fail_under` 69. 95 mutations: 88 caught, 2 equivalent; the 5 gaps got new tests.

Fixes (each regression test fails without its fix):
- The release API and UI built the task URL from `release.task_id` after queuing the task, which clears it on
  success: a 500 if the worker finishes first. `do_create_*_release` now return `(release, task_id)`.
- `Package.get_thumb_url(abs=True)` returned the base URL for packages without screenshots (regression from
  63a42cc1), so clients fetched the homepage as a thumbnail.
- `PackageDevState.WIP.title` was "Looking for Maintainer" (copy-paste from f0039774).
- Unknown tag/content warning ids in the package edit API caused a 500.
- Git update detection queued `make_vcs_release` before committing the new release.

- `/api/packages/<a>/<n>/releases/` listed unapproved, failed and processing releases publicly. It now lists
  approved releases only, like the website does for visitors, and the API docs say so (decided by the user).

## Phase 3: done, committed in 083f3227 to 548eea5a

1068 tests, 72.03% coverage, `fail_under` 72. 47 mutations: all caught after strengthening 3 tests.

Fixes (each regression test fails without its fix):
- GitHub OAuth had no `state`: another site could send someone to the callback with its own code, to log them in
  as someone else (login CSRF) or link its GitHub account to their ContentDB account, then log in as them.
  `github_start` now stores a random state in the session, and `check_oauth_state` checks it before the code is
  exchanged.
- The GitHub callback raised a KeyError (500) when the GitHub API returned an error.
- `login_user_set_active` didn't save notification preferences for NOT_JOINED users (SQLAlchemy 2.0 doesn't
  cascade through backrefs).

## To fix later (decided by the user, 2026-11-08)

From phase 2:
- `/api/homepage/`'s "updated" list joins releases without filtering by state, so a failed or unapproved upload
  counts as an update (`endpoints.py`, `homepage()`).
- Editing a release doesn't apply the name format rule or check for duplicate names and titles, unlike creating one
  (`EditPackageReleaseForm` and `edit_release` in `blueprints/packages/releases.py`).
- API tokens only work on packages the token's owner authored (`APIToken.can_operate_on_package`), so maintainers
  who aren't the owner can't use the API for releases, screenshots or edits.
- Odd status codes: duplicate or invalid release names return 403 (`check_can_create_release`), and a too-small
  screenshot returns 429 (`do_create_screenshot`, which also leaves the uploaded file on disk).
- `/api/packages/<a>/<n>/releases/<id>/` still returns unapproved releases by id.
- The JSON feed outputs `"image": null` for packages without screenshots; leaving the key out would be tidier
  (`blueprints/feeds/__init__.py`).
- `/api/packages/` picks the release with the highest id (`QueryBuilder.get_releases`), but `for-client/` and
  `/api/packages/<a>/<n>/` pick the newest by `created_at` (`Package.get_download_release`). They normally agree.
- The maintainer editor accepts banned users and the ContentDB system user (`edit_maintainers`).

From phase 3 (questions, not yet decided):
- Approval of new reviews is only decided when they're created, so a new member can post a review without links,
  which is approved, then edit it to add links (`review()` in `blueprints/packages/reviews.py`).
- Daily digests include notifications that were already read on the site (`send_pending_digests`).
- Maintainers are notified about new reviews that are held for moderation.

From phase 1 (still open questions, not yet decided):
- Approvers get the "gone" page for packages awaiting review, as VIEW_PACKAGE falls back to EDIT_PACKAGE.
- The package page hides private threads from maintainers who aren't the owner, and from watchers, though they can
  open them directly.
- `/threads/` hides users' own private threads unless they're Approver or above.
- Smaller notes: unsafe zips raise a generic exception, so no bot message is posted; `handle_entityref` in
  `luanti_hypertext.py` is never called and has a "gr" typo; moderators can't edit replies in locked threads;
  `Thread.get_visible_to` is unused; no `MAX_CONTENT_LENGTH` is set.

## Later phases (from the agreed plan)

- **Phase 2:** release publishing through the API and UI, a client API contract (the JSON shape of `/api/packages/`,
  `for-client/`, `/api/updates/`, `/api/dependencies/`, `/api/homepage/`), the package lifecycle (create and edit,
  `move_to_state`, remove, maintainers, aliases), and git update checking.
- **Phase 3:** reviews and scores, notification and digest emails through Mailpit, and the GitHub OAuth callback
  (stubbed).
- **Phase 4:** collections UI, destructive admin actions, profile and to-do pages, the forum and phpBB parser,
  querybuilder, and the Bunny storage backend.
- **End-to-end:** use integration tests for nearly everything. Cypress only for about 5–8 journeys that need a
  browser: JavaScript editors, CSRF (turned off in integration tests), the real worker, and re-authentication round
  trips. Add a parametrised integration test with CSRF turned on, checking every form includes the token. Seed
  Cypress data through `utils/setup.py -t`, not test-only routes.
