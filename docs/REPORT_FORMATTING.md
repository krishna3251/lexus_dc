# Discord research report formatting

14 November 2026. Research presentation uses an application-owned formatter;
it does not make another model request or rewrite factual claims.

The formatter removes stray outer list numbers from report titles, decodes HTML
spacing artifacts in prose, normalizes spaced/grouped citation IDs, separates
findings with blank lines and converts standalone bold titles to Discord headings.
Fenced and inline code are preserved. Numbered procedural steps remain numbered.

The application renders one source section using compact clickable titles, with
one entry per paragraph. It removes duplicate model-generated Sources/References
footers, escapes labels, rejects non-public/credential source URLs, and includes
all ten allowed references. Unknown source IDs remain visibly unverified. Citation
identifier checks do not prove that a source supports every generated claim.

Illustrative layout, with placeholder content:

```markdown
## Company news — six-day report

**Period:** 9–14 November 2026

### Main developments

- **Leadership:** A sourced announcement, with any allegations attributed. [1]

- **Market context:** A sourced change with its measurement period stated. [2]

### Impact

A short explanation of what the findings mean.

### Sources

[1] [Official newsroom · Announcement](<https://example.com/announcement>)

[2] [Publisher · Market report](<https://example.org/report>)
```

When multiple Discord messages are needed, splitting avoids leaving a heading
alone or cutting a masked source link in half. Large reports retain a preview and
the complete Markdown attachment. Overlong individual links use an intact file
instead of a broken preview. Existing mention suppression and length limits remain.

The reported combination of an offline message and a completed report was not
reproduced from the current single-process wake-name adapters. A regression uses
the user's Nvidia request alongside both listeners and checks that only the
unified adapter handles it. The no-provider message now describes this running
instance's configuration rather than declaring all conversation models offline.
`lx aistatus` and result logs include a random, non-secret instance ID for checking
overlapping deployments. Hosted processes and their logs were not accessible, so
no production duplicate-instance cause is claimed as confirmed or fixed.

Research instructions also distinguish allegations from confirmed announcements
and keep financial measurements tied to their stated period. No live generated
report or provider credential was tested in this change.
