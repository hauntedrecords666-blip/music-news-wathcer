import json
import os
import re
import tempfile
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs, urlunparse, parse_qsl, urlencode


LIST_URL = os.environ.get(
    "HYDE_LIST_URL",
    "https://www.hyde.com/contents/official_news",
)

SEEN_FILE = os.environ.get("SEEN_FILE", "hyde_seen.json")

HEADERS = {"User-Agent": "Mozilla/5.0"}


def load_seen():
    try:
        with open(SEEN_FILE, encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                print("[SEEN] warning: failed to parse SEEN_FILE, treating as empty:", SEEN_FILE)
                return set()

            if isinstance(data, list):
                return set(normalize_url(u) for u in data if isinstance(u, str) and u)

            print("[SEEN] warning: unexpected format in SEEN_FILE, expected JSON array. Resetting.")
            return set()
    except FileNotFoundError:
        return set()


def save_seen(seen):
    data = json.dumps(sorted(list(seen)), ensure_ascii=False, indent=2)

    dir_name = os.path.dirname(SEEN_FILE) or "."
    base_name = os.path.basename(SEEN_FILE)

    fd, tmp_path = tempfile.mkstemp(prefix=f".{base_name}.", dir=dir_name, text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, SEEN_FILE)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def extract_id(url):
    if not url:
        return None

    try:
        q = parse_qs(urlparse(url).query)
        for key in ("ima", "id"):
            if key in q and q[key]:
                v = q[key][0]
                if v.isdigit():
                    return int(v)
    except Exception:
        pass

    m = re.search(r"/contents/(\d+)(?:/)?(?:$|[?#])", url)
    if m:
        return int(m.group(1))

    m = re.search(r"(\d+)", url)
    if m:
        return int(m.group(1))

    return None


def normalize_url(url):
    if not url:
        return url

    try:
        p = urlparse(url)
        qs = parse_qsl(p.query, keep_blank_values=True)
        qs = [(k, v) for (k, v) in qs if k != "ima"]
        new_query = urlencode(qs, doseq=True)
        new_p = p._replace(query=new_query)
        return urlunparse(new_p)
    except Exception:
        return url


def fetch_list(list_url=LIST_URL):
    print("[LIST] fetching...", list_url)

    r = requests.get(list_url, headers=HEADERS, timeout=10)
    print("[LIST] status:", r.status_code)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    urls = set()

    for a in soup.select("a[href]"):
        href = a.get("href")
        if not href:
            continue

        if "/contents/" not in href:
            continue
        if "/contents/official_news" in href or "/contents/official_live" in href:
            continue

        if re.search(r"/contents/\d+", href):
            full = urljoin(list_url, href)
            urls.add(normalize_url(full))

    urls = list(urls)
    print("[LIST] urls found:", len(urls))
    print("[LIST] sample:", urls[:5])
    return urls


def fetch_detail(url):
    print("[DETAIL] request:", url)

    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
    except Exception as e:
        print("[DETAIL] request error:", url, e)
        return None

    print("[DETAIL] status:", url, r.status_code)

    if r.status_code == 404:
        print("[DETAIL] 404 skip:", url)
        return None

    if r.status_code != 200:
        print("[DETAIL] non-200 skip:", url)
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    title = None

    candidates = [
        ".official-news-title",
        ".news-title",
        ".article-title",
        ".entry-title",
        "h1",
        "h2",
    ]
    for sel in candidates:
        el = soup.select_one(sel)
        if el:
            txt = el.get_text(" ", strip=True)
            if txt:
                title = txt
                break

    if not title:
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            title = og.get("content").strip()

    if not title:
        tw = soup.find("meta", attrs={"name": "twitter:title"})
        if tw and tw.get("content"):
            title = tw.get("content").strip()

    if not title:
        t = soup.find("title")
        if t:
            title = t.get_text(" ", strip=True)

    if not title:
        print("[DETAIL] title not found:", url)
        return None

    norm = normalize_url(url)
    print("[DETAIL] OK:", norm, "=>", title)

    return {"url": norm, "title": title}


def send_discord(article):
    webhook = os.environ.get("HYDE_WEBHOOK")

    if not webhook:
        print("[DISCORD] webhook not set — skipping send (no action taken)")
        return

    print("[DISCORD] send:", article["url"])

    res = requests.post(
        webhook,
        json={
            "content": (
                f"【HYDE NEWS】\n"
                f"{article['title']}\n"
                f"{article['url']}"
            )
        },
        timeout=10,
    )

    print("[DISCORD] status:", res.status_code)
    res.raise_for_status()


def main():
    print("=== START ===")

    seen = load_seen()
    print("[SEEN] size:", len(seen))

    list_urls = fetch_list()

    ids = [extract_id(u) for u in list_urls]
    ids = [i for i in ids if i is not None]

    latest_list_id = max(ids) if ids else 0

    seen_ids = [extract_id(u) for u in seen if extract_id(u) is not None]
    latest_seen_id = max(seen_ids) if seen_ids else 0

    base = max(latest_list_id, latest_seen_id)

    print("[BASE] latest_list_id:", latest_list_id)
    print("[BASE] latest_seen_id:", latest_seen_id)
    print("[BASE] final base:", base)

    candidates = []

    for u in list_urls:
        if u in seen:
            continue
        art = fetch_detail(u)
        if art:
            candidates.append(art)

    extra_scan = os.environ.get("HYDE_EXTRA_SCAN") in ("1", "true", "True", "yes", "YES")
    if extra_scan:
        scan_range = range(base - 30, base + 50)
        print("[SCAN] range:", base - 30, "→", base + 50)

        for i in scan_range:
            url = f"https://www.hyde.com/contents/{i}"
            if url in seen:
                continue
            if url in list_urls:
                continue

            art = fetch_detail(url)
            if art:
                candidates.append(art)
    else:
        print("[SCAN] extra scan disabled for HYDE (set HYDE_EXTRA_SCAN=1 to enable)")

    print("[RESULT] candidates:", len(candidates))

    send_on_init = os.environ.get("HYDE_SEND_ON_INIT") in ("1", "true", "True", "yes", "YES")
    if not seen and candidates and not send_on_init:
        print("[INIT] skip mode (no notifications to avoid spamming). Set HYDE_SEND_ON_INIT=1 to override.")
        for a in candidates:
            seen.add(a["url"])
        save_seen(seen)
        return
    if not seen and candidates and send_on_init:
        print("[INIT] send_on_init enabled — sending notifications for initial candidates")

    for article in sorted(candidates, key=lambda x: extract_id(x["url"]) or 0):
        send_discord(article)
        seen.add(article["url"])

    save_seen(seen)

    print("=== DONE ===")


if __name__ == "__main__":
    main()
