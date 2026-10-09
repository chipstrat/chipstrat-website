"""Upload brand kit images to Substack and set them on the Chipstrat publication."""
import base64, json, sys, urllib.request, urllib.error
import ss_get

BASE = "https://www.chipstrat.com"
KIT = "/home/austin/claude/chipstrat-website/Chipstrat-Brand-Kit/fjord-clay/substack/"

def call(method, path, body):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method=method, headers={
        "Cookie": ss_get.cookie_header(), "User-Agent": "Mozilla/5.0", "Accept": "application/json",
        "Content-Type": "application/json", "Origin": BASE, "Referer": BASE + "/publish/settings"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:400].decode(errors="replace")

def upload(fname):
    b64 = base64.b64encode(open(KIT + fname, "rb").read()).decode()
    status, body = call("POST", "/api/v1/image", {"image": "data:image/png;base64," + b64})
    assert status == 200, (status, body)
    return body["url"]

if __name__ == "__main__":
    for pair in sys.argv[1:]:
        field, fname = pair.split("=")
        url = upload(fname)
        status, body = call("PUT", "/api/v1/publication", {field: url})
        got = body["publication"].get(field) if isinstance(body, dict) and "publication" in body else body
        print(field, status, "\n  uploaded:", url, "\n  now:     ", str(got)[:300])
