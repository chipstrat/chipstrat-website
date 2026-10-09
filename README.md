# chipstrat-website

Static site for chipstrat.com, generated from the Chipstrat Substack archive.

- `site/build.py` builds `site/dist/`. `--refresh` re-downloads the post list, `--release` hides unconfirmed client names.
- `site/content/site.json` holds topics, company aliases, the client list, quotes and the newsletter URL (`newsletter_base`).
- `site/content/media.json` holds the TV clips shown on the Media page.
- `site/static/` holds the stylesheet, fonts and logo files.
- `tools/` holds the scripts used to update Substack branding through its API.
- `custom/` holds brand images derived from the kit (trimmed logos, clean welcome cover).
- `Chipstrat-Brand-Kit/` is a copy of the brand kit from `~/Documents/Chipstrat-Brand-Kit` on the XPS.

Preview locally: `cd site && python3 build.py && cd dist && python3 -m http.server 8765`.
