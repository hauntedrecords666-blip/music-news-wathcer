import json
import os
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, parse_qs


LIST_URL = os.environ.get(
    "LARC_LIST_URL",
    "https://larc-en-ciel.com/s/n137/news/list?ima=4247"
)

SEEN_FILE = os.environ.get("SEEN_FILE", "larc_seen.json")

HEADERS = {"User-Agent": "Mozilla/5.0"}


# -------------------------
# seen管理
# -------------------------
def load_seen():
    try:
        with open(SEEN_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()


def save_seen(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(seen)), f, ensure_ascii=False, indent=2)


# -------------------------
# ID抽出（柔軟）
# まず path の末尾の数値を探す。見つからなければクエリの ima や id を探す。
# -------------------------
def extract_id(url):
    if not url:
        return None

    # クエリの ima を優先
    try:
        q = parse_qs(urlparse(url).query)
        for key in ("ima", "id"):
            if key in q and q[key]:
                v = q[key][0]
                if v.isdigit():
                    return int(v)
    except Exception:
        pass

    # path 末尾の数値を探す
    m = re.search(r"/(\d+)(?:/)?(?:$|[?#])", url)
    if m:
        return int(m.group(1))

    # 最後の頼みの綱：URL 全体から数字列を探す（保険）
    m = re.search(r"(\d+)", url)
    if m:
        return int(m.group(1))

    return None


# -------------------------
# list取得
# -------------------------
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

        # L'Arc-en-ciel サイトのニュースは /s/n137/news/ 以下にある想定
        if "/s/n137/news" in href:
            full = urljoin(list_url, href)
            # 完全なクエリを保持してもよいが、重複を避けるためパラメータはそのまま保存
            urls.add(full)

    urls = list(urls)

    print("[LIST] urls found:", len(urls))
    print("[LIST] sample:", urls[:5])

    return urls


# -------------------------
# 詳細取得
# -------------------------
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

    # 優先順: og:title -> h1 -> title
    title = None
    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        title = og.get("content").strip()

    if not title:
        h1 = soup.find("h1")
        if h1:
            title = h1.get_text(" ", strip=True)

    if not title:
        t = soup.find("title")
        if t:
            title = t.get_text(" ", strip=True)

    if not title:
        print("[DETAIL] title not found:", url)
        return None

    # 不要なサフィックスがあれば取り除く（サイトのタイトル付きの場合）
    title = re.sub(r"\s*[-|｜].*$", "", title).strip()

    print("[DETAIL] OK:", url, "=>", title)

    return {"url": url, "title": title}


# -------------------------
# Discord送信
# -------------------------
def send_discord(article):
    webhook = os.environ.get("LARC_WEBHOOK")

    # 環境変数が未設定の場合は何もしない（ユーザーの許可なしに送信しません）
    if not webhook:
        print("[DISCORD] webhook not set — skipping send (no action taken)")
        return

    print("[DISCORD] send:", article["url"])

    res = requests.post(
        webhook,
        json={
            "content": (
                f"【L'Arc-en-ciel NEWS】\n"
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

    # list 上の id を先に取得して base を計算
    ids = [extract_id(u) for u in list_urls]
    ids = [i for i in ids if i is not None]

    latest_list_id = max(ids) if ids else 0

    seen_ids = [extract_id(u) for u in seen if extract_id(u) is not None]
    latest_seen_id = max(seen_ids) if seen_ids else 0

    base = max(latest_list_id, latest_seen_id)

    print("[BASE] latest_list_id:", latest_list_id)
    print("[BASE] latest_seen_id:", latest_seen_id)
    print("[BASE] final base:", base)

    # 余裕を持った範囲でスキャン（リストが完全でない場合の補正）
    scan_range = range(base - 30, base + 50)

    print("[SCAN] range:", base - 30, "→", base + 50)

    candidates = []

    # 既知の list_urls は優先してチェック
    for u in list_urls:
        if u in seen:
            continue
        art = fetch_detail(u)
        if art:
            candidates.append(art)

    # 保険で id から組み立てる URL（サイト構造が変わっている可能性に備える）
    for i in scan_range:
        # detail のパスがどのようになっているかは不明なため、一般的な detail パターンを試す
        url = f"https://larc-en-ciel.com/s/n137/news/detail/{i}"
        if url in seen:
            continue
        if url in list_urls:
            continue

        art = fetch_detail(url)
        if art:
            candidates.append(art)

    print("[RESULT] candidates:", len(candidates))

    # 初回スキップ
    if not seen and candidates:
        print("[INIT] skip mode")
        for a in candidates:
            seen.add(a["url"])
        save_seen(seen)
        return

    # 通知
    for article in sorted(candidates, key=lambda x: extract_id(x["url"]) or 0):
        send_discord(article)
        seen.add(article["url"])

    save_seen(seen)

    print("=== DONE ===")


if __name__ == "__main__":
    main()
