#!/usr/bin/env python3
"""Build the static chipstrat.com site from the Substack archive.

  python3 build.py              build dist/ from content/posts.json (preview: shows unconfirmed clients)
  python3 build.py --refresh    re-download the post list from Substack first
  python3 build.py --release    hide anything not confirmed in content/site.json
"""
import collections, datetime, html, json, os, pathlib, re, shutil, struct, sys, urllib.parse
from refresh_posts import refresh

ROOT = pathlib.Path(__file__).parent
DIST = ROOT / "dist"
CFG = json.loads((ROOT / "content/site.json").read_text())
MEDIA = json.loads((ROOT / "content/media.json").read_text())
RELEASE = "--release" in sys.argv
# Path prefix when the site is served from a subfolder (the temporary github.io address). Empty on chipstrat.com.
BASE = os.environ.get("SITE_BASE", "").rstrip("/")
NL = CFG["newsletter_base"]
e = html.escape
NOINDEX = '\n<meta name="robots" content="noindex">' if BASE else ""


# ---------- data ----------

def refresh_posts():
    """Add/update recent RSS entries without discarding the historical archive."""
    return refresh(ROOT / "content/posts.json")


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def load_posts():
    raw = json.loads((ROOT / "content/posts.json").read_text())
    topic_by_tag = {t.lower(): topic for topic in CFG["topics"] for t in topic["tags"]}
    matchers = []
    for c in CFG["companies"]:
        flags = 0 if c.get("case_sensitive") else re.I
        rx = re.compile(r"(?<![\w-])(" + "|".join(re.escape(a) for a in c["aliases"]) + r")(?![\w-])", flags)
        matchers.append((c, rx, {a.lower() for a in c["aliases"]}))
    posts = []
    for p in raw:
        tags = [t["name"] for t in (p.get("postTags") or [])]
        text = f"{p.get('title') or ''} . {p.get('subtitle') or ''}"
        companies = [c["name"] for c, rx, al in matchers if rx.search(text) or any(t.lower() in al for t in tags)]
        topics, seen = [], set()
        for t in tags:
            topic = topic_by_tag.get(t.lower())
            if topic and topic["slug"] not in seen:
                seen.add(topic["slug"])
                topics.append(topic)
        d = datetime.datetime.fromisoformat(p["post_date"].replace("Z", "+00:00"))
        posts.append(dict(title=(p.get("title") or "").strip(), subtitle=(p.get("subtitle") or "").strip(), date=d,
                          paid=p.get("audience") == "only_paid", kind=p.get("type"), url=f"{NL}/p/{p['slug']}",
                          slug=p["slug"], topics=topics, companies=companies, cover=p.get("cover_image")))
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


# ---------- components ----------

def page(title, desc, path, body, current=""):
    canon = CFG["site_url"] + path
    nav = [("Research", "/research/"), ("Analyst", "/analyst/"), ("Media", "/media/"), ("Disclosure", "/disclosure/")]
    links = "".join(f'<a href="{h}"{" aria-current=\"page\"" if h == current else ""}>{t}</a>' for t, h in nav)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="canonical" href="{canon}">{NOINDEX}
<meta property="og:type" content="website">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{canon}">
<meta property="og:image" content="{CFG['site_url']}/assets/social-preview.png">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#193C36">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="apple-touch-icon" href="/assets/apple-touch-icon.png">
<link rel="alternate" type="application/rss+xml" title="Chipstrat" href="{NL}/feed">
<link rel="stylesheet" href="/styles.css?v={VER}">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-head"><div class="wrap">
<a class="brand" href="/" aria-label="Chipstrat home"><img class="brand-mark" src="/assets/mark-detailed.svg" alt="" width="44" height="44"><img class="brand-word" src="/assets/wordmark.svg" alt="Chipstrat" width="172" height="23"></a>
<button class="menu-btn" aria-expanded="false" aria-controls="nav">Menu</button>
<nav class="nav" id="nav" aria-label="Main">{links}<a href="{CFG['semidoped_url']}">Semi Doped ↗</a><a class="btn" href="{NL}/">Newsletter ↗</a></nav>
</div></header>
<main id="main">
{body}
</main>
<section class="band"><div class="wrap">
<div><h2>Read Chipstrat</h2><p>Technical and strategic analysis of semiconductors and AI infrastructure. Free subscribers get a weekly preview. Paid subscribers get every article and the full archive.</p></div>
<a class="btn" href="{NL}/">Read the newsletter</a>
</div></section>
<footer class="site-foot"><div class="wrap">
<span>© {datetime.date.today().year} Chipstrat LLC. Independent research by Austin Lyons.</span>
<nav aria-label="Footer"><a href="/research/">Research</a><a href="/analyst/">Analyst</a><a href="/media/">Media</a><a href="/disclosure/">Disclosure</a><a href="{NL}/archive">Newsletter archive</a><a href="{NL}/subscribe">Subscribe</a><a href="{CFG['semidoped_url']}">Semi Doped</a></nav>
</div></footer>
<script src="/site.js?v={VER}" defer></script>
</body>
</html>
"""


def thumb(url, w, h):
    """Substack CDN URL for a cover image cropped to w x h."""
    if not url:
        return ""
    src = url[url.rindex("https%3A"):] if "https%3A" in url else urllib.parse.quote(url, safe="")
    return f"https://substackcdn.com/image/fetch/w_{w},h_{h},c_fill,f_auto,q_auto:good,fl_progressive:steep,g_auto/{src}"


def post_parts(p):
    cs = "".join(f'<a class="chip" href="/companies/{slugify(c)}/">{e(c)}</a>' if c in PAGED else f'<span class="chip">{e(c)}</span>' for c in p["companies"])
    tags = f'<div class="post-tags">{cs}</div>' if cs else ""
    kind = {"podcast": "Podcast", "video": "Video"}.get(p["kind"])
    badge = f'<span class="badge">{kind}</span>' if kind else ""
    kicker = f'<a class="kicker" href="/topics/{p["topics"][0]["slug"]}/">{e(p["topics"][0]["name"])}</a>' if p["topics"] else '<span class="kicker"></span>'
    meta = f'<div class="post-meta">{kicker}<span class="post-when"><time datetime="{p["date"]:%Y-%m-%d}">{p["date"]:%b %-d, %Y}</time>{badge}</span></div>'
    sub = f'<p class="post-sub">{e(p["subtitle"])}</p>' if p["subtitle"] else ""
    return meta, sub, tags


def post_li(p):
    meta, sub, tags = post_parts(p)
    img = f'<a class="thumb" href="{p["url"]}" tabindex="-1" aria-hidden="true"><img loading="lazy" src="{thumb(p["cover"], 480, 270)}" alt="" width="240" height="135"></a>' if p["cover"] else '<span class="thumb"></span>'
    search = e(f'{p["title"]} {p["subtitle"]} {" ".join(p["companies"])}'.lower())
    return (f'<li class="post" data-companies="{e("|".join(p["companies"]))}" data-search="{search}">{img}'
            f'<div class="post-main">{meta}<a class="post-title" href="{p["url"]}">{e(p["title"])}</a>{sub}{tags}</div></li>')


def featured(p):
    meta, sub, tags = post_parts(p)
    return (f'<article class="feature"><a class="feature-img" href="{p["url"]}" tabindex="-1" aria-hidden="true"><img src="{thumb(p["cover"], 960, 540)}" alt="" width="480" height="270"></a>'
            f'<div class="post-main">{meta}<a class="post-title" href="{p["url"]}">{e(p["title"])}</a>{sub}{tags}<p class="more" style="margin-top:14px"><a href="{p["url"]}">Read on Substack ↗</a></p></div></article>')


def by_year(posts):
    out = []
    for year, group in collections.OrderedDict((y, [p for p in posts if p["date"].year == y]) for y in sorted({p["date"].year for p in posts}, reverse=True)).items():
        out.append(f'<h2 class="year">{year}</h2><ul class="posts">{"".join(post_li(p) for p in group)}</ul>')
    return "".join(out)


def list_tools(posts, companies=True):
    """Search box, plus company filter buttons when the list spans several companies."""
    counts = collections.Counter(c for p in posts for c in p["companies"])
    top = [c for c, n in counts.most_common(14) if n >= 2] if companies else []
    btns = ""
    if len(top) >= 2:
        btns = '<div class="filter" role="group" aria-label="Filter by company"><button type="button" aria-pressed="true" data-filter="">All</button>' + "".join(
            f'<button type="button" aria-pressed="false" data-filter="{e(c)}">{e(c)} {counts[c]}</button>' for c in top) + "</div>"
    search = f'<label class="search"><span class="sr">Search these posts</span><input type="search" placeholder="Search {len(posts)} posts by title or company" autocomplete="off"></label>' if len(posts) >= 8 else ""
    return f'<div class="tools">{search}{btns}</div><p class="empty" hidden>No posts match.</p>' if search or btns else ""


def section(label, body, id_=""):
    return f'<section class="section"{f" id=\"{id_}\"" if id_ else ""}><div class="wrap"><div class="section-label"><p class="eyebrow">{label}</p></div><div class="section-body">{body}</div></div></section>'


def topic_cards(posts):
    out = []
    for t in CFG["topics"]:
        n = sum(1 for p in posts if t in p["topics"])
        out.append(f'<a class="card" href="/topics/{t["slug"]}/"><h3>{e(t["name"])}</h3><p>{e(t["blurb"])}</p><span class="count">{n} posts →</span></a>')
    return f'<div class="grid">{"".join(out)}</div>'


def company_links(counts, limit=None):
    items = sorted(PAGED, key=lambda c: (-counts[c], c))[:limit]
    return '<ul class="company-list">' + "".join(f'<li><a href="/companies/{slugify(c)}/">{e(c)} <span>{counts[c]}</span></a></li>' for c in items) + "</ul>"


def logo_ratio(f):
    """Width/height of a logo file, read from the SVG viewBox or size, or the PNG header."""
    data = f.read_bytes()
    if f.suffix == ".png":
        w, h = struct.unpack(">II", data[16:24])
        return w / h
    head = data[:3000].decode("utf-8", "replace")
    m = re.search(r'viewBox="\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', head)
    if not m:
        m = re.search(r'<svg[^>]*?width="([\d.]+)(?:px)?"[^>]*?height="([\d.]+)', head, re.S)
    return float(m.group(1)) / float(m.group(2)) if m and float(m.group(2)) else 3.0


def logo_size(ratio):
    """Give every logo about the same visual area, so wide wordmarks and square marks look equally weighted."""
    h = max(18, min(42, (2600 / ratio) ** 0.5))
    w = min(150, h * ratio)
    return round(w / ratio), round(w)


def audience():
    """Top names per row as logos; a name without a logo file is shown as text in the same slot."""
    out = []
    for g in CFG["audience"]:
        rows = ""
        for r in g["rows"]:
            items = ""
            for o in r["top"]:
                f = next((x for x in (ROOT / "static/assets/logos" / (o["logo"] + ext) for ext in (".svg", ".png")) if x.exists()), None)
                h, w = logo_size(logo_ratio(f)) if f else (0, 0)
                items += (f'<li><img loading="lazy" src="/assets/logos/{f.name}" alt="{e(o["name"])}" width="{w}" height="{h}" style="width:{w}px;height:{h}px"></li>' if f
                          else f'<li class="logo-text">{e(o["name"])}</li>')
            rows += f'<div class="aud-row"><dt>{e(r["label"])}</dt><dd><ul class="logos">{items}</ul></dd></div>'
        out.append(f'<div class="aud-group"><h3 class="subhead">{e(g["group"])}</h3><dl class="aud">{rows}</dl></div>')
    return "".join(out)


def clients_block():
    shown = [c for c in CFG["clients"] if c["confirmed"] or not RELEASE]
    if not shown:
        return ""
    items = ""
    for c in shown:
        f = next((x for x in (ROOT / "static/assets/logos" / (c.get("logo", "") + ext) for ext in (".svg", ".png")) if x.exists()), None)
        if f:
            h, w = logo_size(logo_ratio(f))
            items += f'<li class="has-logo"><img src="/assets/logos/{f.name}" alt="{e(c["name"])}" width="{w}" height="{h}" style="width:{w}px;height:{h}px"></li>'
        else:
            items += f"<li>{e(c['name'])}</li>"
    return f'<ul class="clients">{items}</ul>'


# ---------- pages ----------

def home(posts, counts):
    latest = "".join(post_li(p) for p in posts[1:6])
    seen = "".join(f'<a href="/media/#{slugify(o)}">{e(o)}</a>' for o in CFG["outlets"])
    quotes = "".join(f'<blockquote class="quote"><p>“{e(q["text"])}”</p><footer>{e(q["who"])}</footer></blockquote>' for q in CFG["quotes"])
    first = min(p["date"] for p in posts).year
    body = f"""
<section class="hero"><div class="wrap">
<div>
<p class="eyebrow">Independent semiconductor research</p>
<h1>Chipstrat is independent research on semiconductors and AI infrastructure.</h1>
<p class="lede">I’m Austin Lyons. I write the Chipstrat newsletter, co-host the <a href="{CFG['semidoped_url']}">Semi Doped</a> podcast and work with semiconductor companies as an independent analyst. I trained as an electrical engineer, worked at Intel, built software startups and later earned an MBA. I cover how the technology works and why the business decisions around it get made.</p>
<div class="actions"><a class="btn" href="{NL}/">Read the newsletter</a><a class="btn ghost" href="/analyst/">Work with me</a></div>
<ul class="facts"><li>MSEE, University of Illinois Urbana-Champaign</li><li>MBA, University of Iowa</li><li>Formerly at Intel</li><li>{e(CFG['subscriber_line'])}</li></ul>
</div>
<div class="hero-photo"><img src="/assets/austin.jpg" alt="Austin Lyons in his studio" width="960" height="960"></div>
</div></section>
<section class="seen" aria-label="Media appearances"><div class="wrap"><span class="seen-label">As seen on</span>{seen}</div></section>
{section("Latest", f'{featured(posts[0])}<ul class="posts">{latest}</ul><p class="more" style="margin-top:22px"><a href="/research/all/">Browse all {len(posts)} posts →</a></p>', "latest")}
{section("Research", f'<h2>{len(posts)} posts since {first}</h2>{topic_cards(posts)}<h3 class="subhead">Most covered companies</h3>{company_links(counts, 14)}<p class="more" style="margin-top:20px"><a href="/research/">All topics and {len(PAGED)} companies →</a></p>', "research")}
{section("Readers", f'<h2>Who reads Chipstrat</h2>{audience()}<h3 class="subhead" style="margin-top:44px">What readers say</h3><div class="quotes">{quotes}</div>', "readers")}
{section("Analyst", f'<h2>I work with semiconductor companies as an independent analyst.</h2><p class="lede">Companies retain me for advisory calls, briefings, executive sessions and events. They get a candid outside view from someone who talks to their customers, competitors and investors every week. Coverage in Chipstrat is never part of a contract.</p><h3 class="subhead">Companies I work with or have worked with as an analyst</h3>{clients_block()}<p class="more" style="margin-top:20px"><a href="/analyst/">How I work with companies →</a></p>', "analyst")}
{section("Disclosure", '<div class="prose"><p>Chipstrat is published for information and analysis. It is not investment advice. I have paid relationships with some of the companies I cover, and I list them on this site. No company pays for coverage.</p><p class="more"><a href="/disclosure/">Read the full disclosure →</a></p></div>', "disclosure")}
"""
    return page("Chipstrat | Independent semiconductor research by Austin Lyons",
                "Independent research on semiconductors, AI infrastructure and business strategy by Austin Lyons.", "/", body)


def research(posts, counts):
    body = f"""
<div class="wrap page-head"><p class="eyebrow">Research</p><h1>Research by topic and company</h1></div>
{section("Topics", topic_cards(posts))}
{section("Companies", f'<p class="muted small" style="margin-bottom:16px">Every company with at least {CFG["company_page_min_posts"]} posts. The number is the post count.</p>{company_links(counts)}')}
{section("Everything", f'<p><a href="/research/all/">Browse all {len(posts)} posts</a> in date order, with search.</p>')}
"""
    return page("Research by topic and company | Chipstrat", "Every Chipstrat article, grouped by topic and by company.", "/research/", body, "/research/")


def listing(kind, name, blurb, posts, path, crumb):
    intro = f'<p class="lede">{e(blurb)}</p>' if blurb else ""
    body = f"""
<div class="wrap page-head"><p class="crumbs"><a href="/research/">Research</a> / {crumb}</p><h1>{e(name)}</h1>{intro}<p class="muted small">{len(posts)} posts</p></div>
<section class="section" style="padding-top:36px"><div class="wrap" style="display:block">{list_tools(posts, companies=kind != "company")}<div data-list>{by_year(posts)}</div></div></section>
"""
    return page(f"{name} | Chipstrat", (blurb or f"Every Chipstrat article about {name}.")[:155], path, body, "/research/")


def all_posts(posts):
    body = f"""
<div class="wrap page-head"><p class="crumbs"><a href="/research/">Research</a> / All posts</p><h1>All posts</h1><p class="muted small">{len(posts)} posts</p></div>
<section class="section" style="padding-top:36px"><div class="wrap" style="display:block">{list_tools(posts)}<div data-list>{by_year(posts)}</div></div></section>
"""
    return page("All posts | Chipstrat", "Every Chipstrat article in date order, searchable by title and company.", "/research/all/", body, "/research/")


def analyst():
    body = f"""
<div class="wrap page-head"><p class="eyebrow">Independent analyst</p><h1>How I work with companies</h1>
<p class="lede">I have been an independent analyst since October 2026, working through Chipstrat LLC. Before that I was an analyst at Creative Strategies.</p></div>
<section class="section" style="padding-top:40px"><div class="wrap" style="display:block"><div class="prose">
<h2 style="margin-top:0">What companies retain me for</h2>
<ul>
<li>Advisory calls and briefings with analyst relations, product and strategy teams</li>
<li>Feedback on positioning, messaging and competitive perspective before a launch</li>
<li>Executive sessions, strategy days and internal talks</li>
<li>Panel moderation and interviews at company events</li>
<li>Diligence support for corporate venture teams</li>
</ul>
<h2>Companies I work with or have worked with as an analyst</h2>
{clients_block()}
<p class="muted small">Past and present, including work done while I was at Creative Strategies.</p>
<h2>Editorial independence</h2>
<div class="callout">
<p><strong>Coverage is never part of a contract.</strong> A company can pay for my time and attention. It cannot pay for an article, a podcast segment or a social post.</p>
</div>
<h2>Elsewhere</h2>
<div class="two">
<a class="card" href="/media/"><h3>Media</h3><p>TV appearances on CNBC, BBC, Yahoo Finance, The Information and Schwab Network.</p></a>
<a class="card" href="{CFG['semidoped_url']}"><h3>Semi Doped ↗</h3><p>The semiconductor podcast I co-host.</p></a>
</div>
</div></div></section>
"""
    return page("Independent analyst | Chipstrat", "How Austin Lyons works with semiconductor companies as an independent analyst, and who he works with.", "/analyst/", body, "/analyst/")


def media():
    blocks = []
    for outlet in CFG["outlets"]:
        vids = [m for m in MEDIA if m["outlet"] == outlet]
        if not vids:
            continue
        cards = "".join(f'<a class="video" href="https://www.youtube.com/watch?v={m["id"]}"><img loading="lazy" src="https://i.ytimg.com/vi/{m["id"]}/mqdefault.jpg" alt="" width="320" height="180"><span>{e(m["title"] or outlet)}</span></a>' for m in vids)
        blocks.append(section(e(outlet), f'<div class="videos">{cards}</div>', slugify(outlet)))
    body = f"""
<div class="wrap page-head"><p class="eyebrow">Media</p><h1>TV appearances</h1><p class="lede">I am a regular guest discussing Nvidia, AMD, Intel, Apple, Tesla, Google, Amazon, Rivian, Micron and the wider semiconductor market.</p></div>
{"".join(blocks)}
"""
    return page("Media and TV appearances | Chipstrat", "Austin Lyons on CNBC, BBC, Yahoo Finance, The Information and Schwab Network.", "/media/", body, "/media/")


def disclosure():
    body = f"""
<div class="wrap page-head"><p class="eyebrow">Disclosure</p><h1>Disclosure</h1><p class="muted small">Last updated {datetime.date.today():%B %-d, %Y}.</p></div>
<section class="section" style="padding-top:40px"><div class="wrap" style="display:block"><div class="prose">
<h2 style="margin-top:0">Not investment advice</h2>
<p>Chipstrat is published by Chipstrat LLC for informational and analytical purposes. It is written for institutional, professional and industry readers as one input to their own research. I do not provide price targets, ratings or investment recommendations. Nothing here is investment, legal, tax or accounting advice, or a recommendation to buy, sell or hold any security.</p>
<p>The views are mine as of the date of publication and can change without notice. Readers should make their own evaluation of any company, security or market discussed and consult their own advisors.</p>
<h2>Business relationships</h2>
<p>Chipstrat LLC has paid relationships with some of the companies I write about. These include analyst retainers, advisory work, event and speaking fees, corporate subscriptions and podcast sponsorship. The companies are listed on the <a href="/analyst/">analyst page</a>.</p>
<p>No company pays for coverage. Sponsored content is labeled as sponsored.</p>
<h2>Personal holdings</h2>
<p>I invest through funds, not individual stocks. Some of those funds hold companies I write about. I do not trade on embargoed or confidential information that companies share with me, and I do not trade around the articles I publish.</p>
<h2>Reuse</h2>
<p>Chipstrat articles may not be reproduced, redistributed or republished, in whole or in part, without written permission.</p>
</div></div></section>
"""
    return page("Disclosure | Chipstrat", "Chipstrat disclosure covering investment advice, business relationships and editorial independence.", "/disclosure/", body, "/disclosure/")


def not_found():
    return page("Page not found | Chipstrat", "Page not found.", "/404.html",
                f'<div class="wrap page-head"><p class="eyebrow">404</p><h1>That page is not here.</h1><p class="lede">Articles live in the <a href="{NL}/archive">newsletter archive</a>. Topic and company pages are under <a href="/research/">Research</a>.</p></div>')


JS = """document.querySelector('.menu-btn')?.addEventListener('click',e=>{const b=e.currentTarget,o=b.getAttribute('aria-expanded')!=='true';b.setAttribute('aria-expanded',o);document.getElementById('nav').classList.toggle('open',o)});
(()=>{const list=document.querySelector('[data-list]');if(!list)return;const input=document.querySelector('.search input'),filter=document.querySelector('.filter'),empty=document.querySelector('.empty');let company='';
const apply=()=>{const q=(input?.value||'').trim().toLowerCase();let shown=0;list.querySelectorAll('.post').forEach(p=>{const ok=(!company||p.dataset.companies.split('|').includes(company))&&(!q||p.dataset.search.includes(q));p.hidden=!ok;if(ok)shown++});list.querySelectorAll('.year').forEach(y=>{y.hidden=!y.nextElementSibling.querySelector('.post:not([hidden])')});if(empty)empty.hidden=shown>0};
input?.addEventListener('input',apply);
filter?.addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;company=b.dataset.filter;filter.querySelectorAll('button').forEach(x=>x.setAttribute('aria-pressed',x===b));apply()})})();
"""

import hashlib
VER = hashlib.sha1((ROOT / "static/styles.css").read_bytes() + JS.encode()).hexdigest()[:8]

# Old Substack hub pages mapped to their replacements. Used once chipstrat.com points at this site.
OLD_PAGES = {
    "about-austin": "/", "paid-subscription": "/", "disclosure": "/disclosure/", "tv-appearances": "/media/", "series": "/research/",
    "interviews": "/topics/interviews/", "foundry": "/topics/foundry/", "fundamentals": "/topics/fundamentals/", "gpus-xpus": "/topics/gpus-xpus-cpus/",
    "ai": "/topics/gpus-xpus-cpus/", "ai-networking": "/topics/optics-and-networking/", "autonomy-physical-ai": "/topics/autonomy-physical-ai/",
    "automotive": "/topics/autonomy-physical-ai/", "robotics": "/topics/autonomy-physical-ai/", "chiplets": "/topics/chiplets-and-packaging/",
    "startups": "/research/", "nuclear": "/research/", "nvidia": "/companies/nvidia/", "amd": "/companies/amd/", "intel": "/companies/intel/",
    "apple": "/companies/apple/", "arm": "/companies/arm/", "google": "/companies/google/", "qualcomm": "/companies/qualcomm/",
}


def redirects():
    nl = "https://newsletter.chipstrat.com"
    lines = ["# Active once chipstrat.com serves this site and Substack moves to newsletter.chipstrat.com"]
    lines += [f"/p/{old} {new} 301" for old, new in OLD_PAGES.items()]
    lines += [f"/t/{t['tags'][0].lower().replace(' / ', '-').replace(' & ', '-and-').replace(' ', '-')} /topics/{t['slug']}/ 301" for t in CFG["topics"]]
    lines += ["/about / 301"]
    lines += [f"{p} {nl}{p.replace('*', ':splat')} 301" for p in ("/p/*", "/archive", "/subscribe", "/podcast", "/feed", "/account", "/sign-in", "/t/*", "/s/*", "/i/*", "/api/*", "/embed", "/chat", "/notes", "/leaderboard", "/recommendations", "/publish/*")]
    return "\n".join(lines) + "\n"


def write(path, text):
    f = DIST / path.lstrip("/")
    f.parent.mkdir(parents=True, exist_ok=True)
    if BASE and f.suffix == ".html":
        text = re.sub(r'(href|src)="/(?!/)', rf'\1="{BASE}/', text)
    f.write_text(text)


if __name__ == "__main__":
    if "--refresh" in sys.argv:
        try:
            refresh_posts()
        except Exception as err:
            print(f"::error::Post refresh failed ({err}); no replacement site was built")
            sys.exit(1)
    posts = load_posts()
    counts = collections.Counter(c for p in posts for c in p["companies"])
    PAGED = {c for c, n in counts.items() if n >= CFG["company_page_min_posts"]}
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copytree(ROOT / "static", DIST)
    urls = ["/", "/research/", "/analyst/", "/media/", "/disclosure/"]
    write("index.html", home(posts, counts))
    write("research/index.html", research(posts, counts))
    write("research/all/index.html", all_posts(posts))
    urls.append("/research/all/")
    write("analyst/index.html", analyst())
    write("media/index.html", media())
    write("disclosure/index.html", disclosure())
    write("404.html", not_found())
    for t in CFG["topics"]:
        path = f"/topics/{t['slug']}/"
        write(path + "index.html", listing("topic", t["name"], t["blurb"], [p for p in posts if t in p["topics"]], path, "Topics"))
        urls.append(path)
    for c in sorted(PAGED):
        path = f"/companies/{slugify(c)}/"
        write(path + "index.html", listing("company", c, "", [p for p in posts if c in p["companies"]], path, "Companies"))
        urls.append(path)
    write("site.js", JS)
    write("_redirects", redirects())
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {CFG['site_url']}/sitemap.xml\n")
    write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(f"<url><loc>{CFG['site_url']}{u}</loc></url>\n" for u in urls) + "</urlset>\n")
    untagged = [p for p in posts if not p["topics"]]
    if "--refresh" in sys.argv:
        print(f"::notice::Built from {len(posts)} posts, newest {posts[0]['date']:%Y-%m-%d}")
    print(f"{len(posts)} posts | {len(CFG['topics'])} topic pages | {len(PAGED)} company pages | {len(untagged)} posts with no topic | {sum(1 for p in posts if not p['companies'])} with no company")
    print("companies:", ", ".join(f"{c} {counts[c]}" for c in sorted(PAGED, key=lambda c: -counts[c])))
