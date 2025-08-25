title: Top Packages Algorithm

## Package Score

Each package is given a `score`, which is used when ordering them in the
"Top Games/Mods/Texture Packs" lists. The intention of this feature is
to make it easier for new users to find good packages.

A package's score is equal to a rolling average of recent downloads,
plus the sum of the score given by reviews.

A review score is 100 if positive, -100 if negative.

```c
reviews_sum = sum(100 * (positive ? 1 : -1));
score       = avg_downloads + reviews_sum;
```

## Pseudo rolling average of downloads

Each package adds 1 to `avg_downloads` for each unique download,
and then loses 6.66% (=1/15) of the value every day.

This is called a [Frecency](https://en.wikipedia.org/wiki/Frecency) heuristic,
a measure which combines both frequency and recency.

"Unique download" is counted per IP per package.
Downloading an update won't increase the download count if it's already been
downloaded from that IP.

## Transparency and Feedback

You can see all scores using the [scores REST API](/api/scores/), or by
using the [Prometheus metrics](/help/metrics/) endpoint.

Consider [suggesting improvements](https://github.com/luanti-org/contentdb/issues/new?assignees=&labels=Policy&template=policy.md&title=).
