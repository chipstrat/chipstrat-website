"""GET a Chipstrat Substack API path with the stored session cookies; print JSON."""
import json, sys, urllib.request
STATE = "/home/austin/claude/semidoped/yt-transcript/state/chipstrat-state.json"

def cookie_header(host="www.chipstrat.com"):
    cs = json.load(open(STATE))["cookies"]
    return "; ".join(f"{c['name']}={c['value']}" for c in cs
                     if host.endswith(c["domain"].lstrip(".")))

def get(path):
    req = urllib.request.Request("https://www.chipstrat.com" + path, headers={
        "Cookie": cookie_header(), "User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

if __name__ == "__main__":
    print(json.dumps(get(sys.argv[1]), indent=1))
