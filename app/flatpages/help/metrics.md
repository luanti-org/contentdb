title: Prometheus Metrics

## What is Prometheus?

[Prometheus](https://prometheus.io) is an "open-source monitoring system with a
dimensional data model, flexible query language, efficient time series database
and modern alerting approach".

Prometheus Metrics can be accessed at [/metrics](/metrics), or you can view them
on the Grafana instance below.

{% if monitoring_url %}
<p>
    <a class="btn btn-primary" href="{{ monitoring_url }}">
        View ContentDB on Grafana
    </a>
</p>
{% endif %}

## Metrics

Unless stated otherwise, package metrics only include approved packages.

* `contentdb_packages` - Number of approved packages (gauge).
* `contentdb_users` - Number of registered users (gauge).
* `contentdb_authors` - Number of users with approved packages (gauge).
* `contentdb_users_active_1d` - Number of registered users active in the last day (gauge).
* `contentdb_users_active_1w` - Number of registered users active in the last week (gauge).
* `contentdb_users_active_1m` - Number of registered users active in the last 30 days (gauge).
* `contentdb_downloads` - Total downloads, deduplicated by IP (gauge).
* `contentdb_download_events_total{reason,platform}` - Number of download events, not deduplicated (counter).
  Resets periodically, so use `rate()` or `increase()`. `reason` is one of `new`, `dependency`, `update`, or `other`;
  `platform` is `luanti` or `other`.
* `contentdb_emails_total` - Number of emails sent (counter).
* `contentdb_reviews` - Number of approved reviews (gauge).
* `contentdb_comments` - Number of comments (gauge).
* `contentdb_collections` - Number of collections (gauge).
* `contentdb_score` - Total package score (gauge).
* `contentdb_packages_with_translations` - Number of packages with translations (gauge).
* `contentdb_packages_with_translations_meta` - Number of packages with a translated short description (gauge).
* `contentdb_languages_translated{language}` - Number of packages with translations, per language (gauge).
* `contentdb_languages_translated_meta{language}` - Number of packages with a translated short description,
  per language (gauge).
