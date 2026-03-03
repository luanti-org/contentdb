title: Creating Releases using Webhooks

## What does this mean?

A webhook is a notification from one service to another. Put simply, a webhook
is used to notify ContentDB that the git repository has changed.

ContentDB offers the ability to automatically create releases using webhooks
from either GitHub or GitLab. If you're not using either of those services,
you can also use the [API](../api) to create releases.

ContentDB also offers the ability to poll a Git repo and check for updates
without any web hooks, this is limited to once a day.
See [Git Update Detection](/help/update_config/).

The process is as follows:

1. The user creates an API Token and a webhook to use it.
2. The user pushes a commit to the git host (GitLab or GitHub).
3. The git host posts a webhook notification to ContentDB, using the API token assigned to it.
4. ContentDB checks the API token and issues a new release.
    * If multiple packages match, then only the first will have a release created.

### Branch filtering

By default, "New commit" or "push" based webhooks will only work on "master"/"main" branches.
You can configure the branch used by changing "Branch name" in [Git update detection](update_config).

For example, to support production and beta packages you can have multiple packages with the same VCS repo URL
but different [Git update detection](update_config) branch names.

Tag-based webhooks are accepted on any branch.


## Setting up

### GitHub

1. Create a ContentDB API Token at [Profile > API Tokens: Manage](/user/tokens/).
2. Copy the access token that was generated.
3. Go to the Github repository's settings > Webhooks > Add Webhook.
4. Set the payload URL to `https://content.luanti.org/github/webhook/`
5. Set the content type to JSON.
6. Set the secret to the access token that you copied.
7. Set the events
    * If you want a rolling release, choose "just the push event".
    * Or if you want a stable release cycle based on tags, choose "Let me select" > Branch or tag creation.
8. Create.
9. If desired, change [Git update detection](update_config) > Branch name to configure the [branch filtering](#branch-filtering).

### GitLab

1. Create a ContentDB API Token at [Profile > API Tokens: Manage](/user/tokens/).
2. Copy the access token that was generated.
3. Go to the GitLab repository's settings > Webhooks.
4. Set the URL to `https://content.luanti.org/gitlab/webhook/`
6. Set the secret token to the ContentDB access token that you copied.
7. Set the events
    * If you want a rolling release, choose "Push events".
    * Or if you want a stable release cycle based on tags,
      choose "Tag push events".
8. Add webhook.
9. If desired, change [Git update detection](update_config) > Branch name to configure the [branch filtering](#branch-filtering).

## Configuring Release Creation

See the [Package Configuration and Releases Guide](/help/package_config/) for
documentation on configuring the release creation.

From the Git repository, you can set the min/max Luanti versions, which files are included,
and update the package meta.
