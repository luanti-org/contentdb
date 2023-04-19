title: API


## Resources

* [How the Minetest client uses the API](https://github.com/minetest/contentdb/blob/master/docs/minetest_client.md)


## Responses and Error Handling

If there is an error, the response will be JSON similar to the following with a non-200 status code:

```json
{
    "success": false,
    "error": "The error message"
}
```

Successful GET requests will return the resource's information directly as a JSON response.

Other successful results will return a dictionary with `success` equaling true, and
often other keys with information. For example:

```js
{
    "success": true,
    "release": {
        /* same as returned by a GET */
    }
}
```


### Paginated Results

Some API endpoints returns results in pages. The page number is specified using the `page` query argument, and
the number of items is specified using `num`

The response will be a dictionary with the following keys:

* `page`: page number, integer from 1 to max
* `per_page`: number of items per page, same as `n`
* `page_count`: number of pages
* `total`: total number of results
* `urls`: dictionary containing
    * `next`: url to next page
    * `previous`: url to previous page
* `items`: array of items


## Authentication

Not all endpoints require authentication, but it is done using Bearer tokens:

```bash
curl https://content.minetest.net/api/whoami/ \
    -H "Authorization: Bearer YOURTOKEN"
```

Tokens can be attained by visiting [Settings > API Tokens](/user/tokens/).

* GET `/api/whoami/`:  JSON dictionary with the following keys:
    * `is_authenticated`:  True on successful API authentication
    * `username`:  Username of the user authenticated as, null otherwise.
    * 4xx status codes will be thrown on unsupported authentication type, invalid access token, or other errors.


## Packages

* GET `/api/packages/` (List)
    * See [Package Queries](#package-queries)
* GET `/api/packages/<username>/<name>/` (Read)
* PUT `/api/packages/<author>/<name>/` (Update)
    * Requires authentication.
    * JSON dictionary with any of these keys (all are optional, null to delete Nullables):
        * `type`: One of `GAME`, `MOD`, `TXP`.
        * `title`: Human-readable title.
        * `name`: Technical name (needs permission if already approved).
        * `short_description`
        * `dev_state`: One of `WIP`, `BETA`, `ACTIVELY_DEVELOPED`, `MAINTENANCE_ONLY`, `AS_IS`, `DEPRECATED`,
            `LOOKING_FOR_MAINTAINER`.
        * `tags`: List of [tag](#tags) names.
        * `content_warnings`: List of [content warning](#content-warnings) names.
        * `license`: A [license](#licenses) name.
        * `media_license`: A [license](#licenses) name.
        * `long_description`: Long markdown description.
        * `repo`: Git repo URL.
        * `website`: Website URL.
        * `issue_tracker`: Issue tracker URL.
        * `forums`: forum topic ID.
        * `video_url`: URL to a video.
        * `donate_url`: URL to a donation page.
        * `game_support`: Array of game support information objects. Not currently documented, as subject to change.
* GET `/api/packages/<author>/<name>/hypertext/`
    * Converts the long description to [Minetest Markup Language](https://github.com/minetest/minetest/blob/master/doc/lua_api.md#markup-language)
      to be used in a `hypertext` formspec element.
    * Query arguments:
        * `formspec_version`: Required, maximum supported formspec version.
        * `include_images`: Optional, defaults to true.
    * Returns JSON dictionary with following key:
        * `head`: markup for suggested styling and custom tags, prepend to the body before displaying.
        * `body`: markup for long description.
        * `links`: dictionary of anchor name to link URL.
        * `images`: dictionary of img name to image URL
        * `image_tooltips`: dictionary of img name to tooltip text.
* GET `/api/packages/<username>/<name>/dependencies/`
    * Returns dependencies, with suggested candidates
    * If query argument `only_hard` is present, only hard deps will be returned.
* GET `/api/dependencies/`
    * Returns `provides` and raw dependencies for all packages.
    * Supports [Package Queries](#package-queries)
    * [Paginated result](#paginated-results), max 300 results per page
    * Each item in `items` will be a dictionary with the following keys:
        * `type`: One of `GAME`, `MOD`, `TXP`.
        * `author`: Username of the package author.
        * `name`: Package name.
        * `provides`: List of technical mod names inside the package.
        * `depends`: List of hard dependencies.
            * Each dep will either be a modname dependency (`name`), or a
                package dependency (`author/name`).
        * `optional_depends`: list of optional dependencies
            * Same as above.
* GET `/api/packages/<username>/<name>/stats/`
    * Returns daily stats for package, or null if there is no data.
    * Daily date is done based on the UTC timezone.
    * EXPERIMENTAL. This API may change without warning.
    * An object with the following keys:
        * `start`: start date, inclusive. Ex: 2022-10-22.
        * `end`: end date, inclusive. Ex: 2022-11-05.
        * `platform_minetest`: list of integers per day.
        * `platform_other`: list of integers per day.
        * `reason_new`: list of integers per day.
        * `reason_dependency`: list of integers per day.
        * `reason_update`: list of integers per day.
* GET `/api/package_stats/`
    * Returns last 30 days of daily stats for _all_ packages.
    * An object with the following keys:
        * `start`: start date, inclusive. Ex: 2022-10-22.
        * `end`: end date, inclusive. Ex: 2022-11-05.
        * `package_downloads`: map from package key to list of download integers.

You can download a package by building one of the two URLs:

```
https://content.minetest.net/packages/${author}/${name}/download/`
https://content.minetest.net/packages/${author}/${name}/releases/${release}/download/`
```

Examples:

```bash
# Edit package
curl -X PUT https://content.minetest.net/api/packages/username/name/ \
    -H "Authorization: Bearer YOURTOKEN" -H "Content-Type: application/json" \
    -d '{ "title": "Foo bar", "tags": ["pvp", "survival"], "license": "MIT" }'

# Remove website URL
curl -X PUT https://content.minetest.net/api/packages/username/name/ \
    -H "Authorization: Bearer YOURTOKEN" -H "Content-Type: application/json" \
    -d '{ "website": null }'
```

### Package Queries

Example:

    /api/packages/?type=mod&type=game&q=mobs+fun&hide=nonfree&hide=gore

Supported query parameters:

* `type`:  Package types (`mod`, `game`, `txp`).
* `q`:  Query string.
* `author`:  Filter by author.
* `tag`:  Filter by tags.
* `game`: Filter by [Game Support](/help/game_support/), ex: `Wuzzy/mineclone2`. (experimental, doesn't show items that support every game currently).
* `random`:  When present, enable random ordering and ignore `sort`.
* `limit`:  Return at most `limit` packages.
* `hide`:  Hide content based on [Content Flags](/help/content_flags/).
* `sort`:  Sort by (`name`, `title`, `score`, `reviews`, `downloads`, `created_at`, `approved_at`, `last_release`).
* `order`:  Sort ascending (`asc`) or descending (`desc`).
* `protocol_version`:  Only show packages supported by this Minetest protocol version.
* `engine_version`:  Only show packages supported by this Minetest engine version, eg: `5.3.0`.
* `fmt`:  How the response is formatted.
    * `keys`:  author/name only.
    * `short`:  stuff needed for the Minetest client.


### Releases

* GET `/api/releases/` (List)
    * Limited to 30 most recent releases.
    * Optional arguments:
        * `author`: Filter by author
        * `maintainer`: Filter by maintainer
    * Returns array of release dictionaries with keys:
        * `id`: release ID
        * `title`: human-readable title
        * `release_date`: Date released
        * `url`: download URL
        * `commit`: commit hash or null
        * `downloads`: number of downloads
        * `min_minetest_version`: dict or null, minimum supported minetest version (inclusive).
        * `max_minetest_version`: dict or null, minimum supported minetest version (inclusive).
        * `package`
            * `author`: author username
            * `name`: technical name
            * `type`: `mod`, `game`, or `txp`
* GET `/api/packages/<username>/<name>/releases/` (List)
    * Returns array of release dictionaries, see above, but without package info.
* GET `/api/packages/<username>/<name>/releases/<id>/` (Read)
* POST `/api/packages/<username>/<name>/releases/new/` (Create)
    * Requires authentication.
    * Body can be JSON or multipart form data. Zip uploads must be multipart form data.
    * `title`: human-readable name of the release.
    * For Git release creation:
        * `method`: must be `git`.
        * `ref`: (Optional) git reference, eg: `master`.
    * For zip upload release creation:
        * `file`: multipart file to upload, like `<input type="file" name="file">`.
        * `commit`: (Optional) Source Git commit hash, for informational purposes.
    * You can set min and max Minetest Versions [using the content's .conf file](/help/package_config/).
* DELETE `/api/packages/<username>/<name>/releases/<id>/` (Delete)
    * Requires authentication.
    * Deletes release.

Examples:

```bash
# Create release from Git
curl -X POST https://content.minetest.net/api/packages/username/name/releases/new/ \
    -H "Authorization: Bearer YOURTOKEN" -H "Content-Type: application/json" \
    -d '{ "method": "git", "title": "My Release", "ref": "master" }'

# Create release from zip upload
curl -X POST https://content.minetest.net/api/packages/username/name/releases/new/ \
    -H "Authorization: Bearer YOURTOKEN" \
    -F title="My Release" -F file=@path/to/file.zip

# Create release from zip upload with commit hash
curl -X POST https://content.minetest.net/api/packages/username/name/releases/new/ \
    -H "Authorization: Bearer YOURTOKEN" \
    -F title="My Release" -F commit="8ef74deec170a8ce789f6055a59d43876d16a7ea" -F file=@path/to/file.zip

# Delete release
curl -X DELETE https://content.minetest.net/api/packages/username/name/releases/3/ \
    -H "Authorization: Bearer YOURTOKEN"
```


### Screenshots

* GET `/api/packages/<username>/<name>/screenshots/` (List)
    * Returns array of screenshot dictionaries with keys:
        * `id`: screenshot ID
        * `approved`: true if approved and visible.
        * `title`: human-readable name for the screenshot, shown as a caption and alt text.
        * `url`: absolute URL to screenshot.
        * `created_at`: ISO time.
        * `order`: Number used in ordering.
        * `is_cover_image`: true for cover image.
* GET `/api/packages/<username>/<name>/screenshots/<id>/` (Read)
    * Returns screenshot dictionary like above.
* POST `/api/packages/<username>/<name>/screenshots/new/` (Create)
    * Requires authentication.
    * Body is multipart form data.
    * `title`: human-readable name for the screenshot, shown as a caption and alt text.
    * `file`: multipart file to upload, like `<input type=file>`.
    * `is_cover_image`: set cover image to this.
* DELETE `/api/packages/<username>/<name>/screenshots/<id>/` (Delete)
    * Requires authentication.
    * Deletes screenshot.
* POST `/api/packages/<username>/<name>/screenshots/order/`
    * Requires authentication.
    * Body is a JSON array containing the screenshot IDs in their order.
* POST `/api/packages/<username>/<name>/screenshots/cover-image/`
    * Requires authentication.
    * Body is a JSON dictionary with "cover_image" containing the screenshot ID.

Currently, to get a different size of thumbnail you can replace the number in `/thumbnails/1/` with any number from 1-3.
The resolutions returned may change in the future, and we may move to a more capable thumbnail generation.

Examples:

```bash
# Create screenshot
curl -X POST https://content.minetest.net/api/packages/username/name/screenshots/new/ \
    -H "Authorization: Bearer YOURTOKEN" \
    -F title="My Release" -F file=@path/to/screnshot.png

# Create screenshot and set it as the cover image
curl -X POST https://content.minetest.net/api/packages/username/name/screenshots/new/ \
    -H "Authorization: Bearer YOURTOKEN" \
    -F title="My Release" -F file=@path/to/screnshot.png -F is_cover_image="true"

# Delete screenshot
curl -X DELETE https://content.minetest.net/api/packages/username/name/screenshots/3/ \
    -H "Authorization: Bearer YOURTOKEN"

# Reorder screenshots
curl -X POST https://content.minetest.net/api/packages/username/name/screenshots/order/ \
    -H "Authorization: Bearer YOURTOKEN" -H "Content-Type: application/json" \
    -d "[13, 2, 5, 7]"

# Set cover image
curl -X POST https://content.minetest.net/api/packages/username/name/screenshots/cover-image/ \
    -H "Authorization: Bearer YOURTOKEN" -H "Content-Type: application/json" \
    -d "{ 'cover_image': 123 }"
```


### Reviews

* GET `/api/packages/<username>/<name>/reviews/` (List)
    * Returns array of review dictionaries with keys:
        * `user`: dictionary with `display_name` and `username`.
        * `title`: review title
        * `comment`: the text
        * `rating`: 1 for negative, 3 for neutral, 5 for positive
        * `is_positive`: boolean
        * `created_at`: iso timestamp
        * `votes`: dictionary with `helpful` and `unhelpful`,
* GET `/api/reviews/` (List)
    * Returns a paginated response. This is a dictionary with `page`, `url`, and `items`.
        * [Paginated result](#paginated-results)
        * `items`: array of review dictionaries, like above
            * Each review also has a `package` dictionary with `type`, `author` and `name`
    * Query arguments:
        * `page`: page number, integer from 1 to max
        * `n`: number of results per page, max 100
        * `author`: filter by review author username
        * `rating`: 1 for negative, 3 for neutral, 5 for positive
        * `is_positive`: true or false. Default: null
        * `q`: filter by title (case insensitive, no fulltext search)

Example:

```json
[
  {
    "comment": "This is a really good mod!",
    "created_at": "2021-11-24T16:18:33.764084",
    "is_positive": true,
    "title": "Really good",
    "user": {
      "display_name": "rubenwardy",
      "username": "rubenwardy"
    },
    "votes": {
      "helpful": 0,
      "unhelpful": 0
    }
  }
]
```


## Users

* GET `/api/users/<username>/`
    * `username`
    * `display_name`: human-readable name to be displayed in GUIs.
    * `rank`: ContentDB [rank](/help/ranks_permissions/).
    * `profile_pic_url`: URL to profile picture, or null.
    * `website_url`: URL to website, or null.
    * `donate_url`: URL to donate page, or null.
    * `connections`: object
        * `github`: GitHub username, or null.
        * `forums`: forums username, or null.
    * `links`: object
        * `api_packages`: URL to API to list this user's packages.
        * `profile`: URL to the HTML profile page.
* GET `/api/users/<username>/stats/`
    * Returns daily stats for the user's packages, or null if there is no data.
    * Daily date is done based on the UTC timezone.
    * EXPERIMENTAL. This API may change without warning.
    * A table with the following keys:
        * `from`: start date, inclusive. Ex: 2022-10-22.
        * `end`: end date, inclusive. Ex: 2022-11-05.
        * `package_downloads`: map of package title to list of integers per day.
        * `platform_minetest`: list of integers per day.
        * `platform_other`: list of integers per day.
        * `reason_new`: list of integers per day.
        * `reason_dependency`: list of integers per day.
        * `reason_update`: list of integers per day.


## Topics

* GET `/api/topics/` ([View](/api/topics/))
    * See [Topic Queries](#topic-queries)

### Topic Queries

Example:

    /api/topics/?q=mobs&type=mod&type=game

Supported query parameters:

* `q`:  Query string.
* `type`:  Package types (`mod`, `game`, `txp`).
* `sort`:  Sort by (`name`, `views`, `created_at`).
* `show_added`:  Show topics that have an existing package.
* `show_discarded`:  Show topics marked as discarded.
* `limit`:  Return at most `limit` topics.

## Types

### Tags

* GET `/api/tags/` ([View](/api/tags/)):  List of:
    * `name`:  technical name.
    * `title`:  human-readable title.
    * `description`:  tag description or null.
    * `is_protected`: boolean, whether the tag is protected (can only be set by Editors in the web interface).
    * `views`: number of views of this tag.

### Content Warnings

* GET `/api/content_warnings/` ([View](/api/content_warnings/)):  List of:
    * `name`:  technical name
    * `title`:  human-readable title
    * `description`:  tag description or null

### Licenses

* GET `/api/licenses/` ([View](/api/licenses/)):  List of:
    * `name`
    * `is_foss`: whether the license is foss

### Minetest Versions

* GET `/api/minetest_versions/` ([View](/api/minetest_versions/))
    * `name`: Version name.
    * `is_dev`: boolean, is dev version.
    * `protocol_version`: protocol version umber.


## Misc

* GET `/api/scores/` ([View](/api/scores/))
    * See [Top Packages Algorithm](/help/top_packages/).
    * Supports [Package Queries](#package-queries).
    * Returns list of:
        * `author`: package author name.
        * `name`: package technical name.
        * `downloads`: number of downloads.
        * `score`: total package score.
        * `score_reviews`: score from reviews.
        * `score_downloads`: score from downloads.
* GET `/api/homepage/` ([View](/api/homepage/)) - get contents of homepage.
    * `count`:  number of packages
    * `downloads`:  get number of downloads
    * `new`:  new packages
    * `updated`:  recently updated packages
    * `pop_mod`:  popular mods
    * `pop_txp`:  popular textures
    * `pop_game`:  popular games
    * `high_reviewed`:  highest reviewed
* GET `/api/welcome/v1/` ([View](/api/welcome/v1/)) - in-menu welcome dialog. Experimental (may change without warning)
    * `featured`: featured games
* GET `/api/cdb_schema/` ([View](/api/cdb_schema/))
    * Get JSON Schema of `.cdb.json`, including licenses, tags and content warnings.
    * See [JSON Schema Reference](https://json-schema.org/).
