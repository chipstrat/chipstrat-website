# chipstrat-website

Static site for chipstrat.com, generated from the Chipstrat Substack archive.

- `site/build.py` builds `site/dist/`. `--refresh` merges recent public RSS entries into the retained post list; `--release` hides unconfirmed client names.
- `site/content/site.json` holds topics, company aliases, the client list, quotes and the newsletter URL (`newsletter_base`).
- `site/content/media.json` holds the TV clips shown on the Media page.
- `site/static/` holds the stylesheet, fonts and logo files.
- `tools/` holds the scripts used to update Substack branding through its API.
- `custom/` holds brand images derived from the kit (trimmed logos, clean welcome cover).
- `Chipstrat-Brand-Kit/` is a copy of the brand kit from `~/Documents/Chipstrat-Brand-Kit` on the XPS.

Preview locally: `cd site && python3 build.py && cd dist && python3 -m http.server 8765`.

## Automatic post refresh

The existing hourly Pages workflow fetches the documented public feed at
`https://chipstrat.substack.com/feed`. This source is independent of the website's
newsletter link setting, follows Substack's custom-domain redirects, and requires
no login cookies or Substack API token.

RSS currently returns 20 recent entries. Refreshes add new posts, update metadata
present in RSS, and retain every older entry in `site/content/posts.json`. Existing
topic labels, audience, numeric IDs and other metadata missing from RSS survive.
Substack's feed currently omits topic labels; new posts still appear on the main
archive and matching company pages, but do not acquire invented topic labels.
Older edits, deleted posts and older retagging require an explicit archive edit.

After tests and a successful build, a separate job saves changed public post
metadata to `main` using GitHub's built-in short-lived token. Only that job has
`contents: write`. It stages only `site/content/posts.json`, never force-pushes,
and refuses to overwrite a concurrent update. This keeps newly discovered posts
after they leave the RSS window, without relying on an evictable cache. Bot commits
do not start recursive deployments. No article bodies or subscriber data are saved.

Failed or malformed feeds stop the workflow before deployment, leaving the last
successful website live and the saved archive intact. The Actions run summary
reports the number of entries fetched, added and updated. GitHub may delay a
scheduled run; use **Actions → Deploy to GitHub Pages → Run workflow** on `main`
for an immediate refresh. Existing GitHub failure-notification preferences apply.

Checks: `python3 -m unittest discover -s site -p 'test_*.py'` and
`python3 site/build.py --refresh --release`.
