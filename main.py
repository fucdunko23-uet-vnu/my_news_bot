import requests
import feedparser
import time
import os
import json
import hashlib
from datetime import datetime, timezone
from bs4 import BeautifulSoup

# --- Cấu hình qua Environment Variables ---
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8362778710:AAEeQPGwAtCD5dYIIoi3RrkqNS1gU1n95dI")
CHAT_ID = os.environ.get("CHAT_ID", "-1003363752562")
TOPIC_ID = int(os.environ.get("TOPIC_ID", "13423"))
ALPHA_VANTAGE_API_KEY = os.environ.get("ALPHA_VANTAGE_API_KEY", "KSL53W8ZY3CFF0EB")

# Tickers cổ phiếu muốn theo dõi
WATCH_TICKERS = os.environ.get("WATCH_TICKERS", "AAPL,MSFT,NVDA,GOOGL,TSLA")

# Danh sách nguồn RSS
SOURCES = {
    "Wired": "https://www.wired.com/feed/rss",
    "UploadVR": "https://uploadvr.com/rss/",
    "The Verge": "https://www.theverge.com/rss/index.xml",
}

# File cache để chống trùng lặp tin (persistent qua GitHub Actions cache)
CACHE_FILE = os.environ.get("CACHE_FILE", "sent_cache.json")
CACHE_MAX_ENTRIES = 500        # Giữ tối đa 500 entries
CACHE_EXPIRE_HOURS = 48        # Xoá entries cũ hơn 48h

# ═══════════════════════════════════════════
#  DEDUPLICATION CACHE
# ═══════════════════════════════════════════


def _url_hash(url):
    """Tạo hash ngắn từ URL để so sánh nhanh"""
    return hashlib.md5(url.strip().lower().encode()).hexdigest()


def load_cache():
    """Load cache từ file JSON. Trả về dict {hash: timestamp}"""
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Expire entries cũ
            now = time.time()
            expire_secs = CACHE_EXPIRE_HOURS * 3600
            data = {k: v for k, v in data.items() if now - v < expire_secs}
            return data
    except Exception as e:
        print(f"  ⚠ Không đọc được cache: {e}")
    return {}


def save_cache(cache):
    """Lưu cache ra file JSON, giới hạn số lượng entries"""
    try:
        # Nếu quá nhiều, giữ lại entries mới nhất
        if len(cache) > CACHE_MAX_ENTRIES:
            sorted_items = sorted(cache.items(), key=lambda x: x[1], reverse=True)
            cache = dict(sorted_items[:CACHE_MAX_ENTRIES])
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f)
        print(f"  💾 Đã lưu cache: {len(cache)} entries")
    except Exception as e:
        print(f"  ⚠ Không lưu được cache: {e}")


def filter_duplicates(items, cache):
    """Lọc bỏ các tin đã gửi trước đó. Trả về (new_items, updated_cache)"""
    new_items = []
    for item in items:
        h = _url_hash(item.get("link", ""))
        if h not in cache:
            new_items.append(item)
            cache[h] = time.time()
    return new_items, cache


# ═══════════════════════════════════════════
#  UTILITIES
# ═══════════════════════════════════════════

SENTIMENT_EMOJI = {
    "Bullish": "🟢",
    "Somewhat-Bullish": "🟡",
    "Somewhat_Bullish": "🟡",
    "Neutral": "⚪",
    "Somewhat-Bearish": "🟠",
    "Somewhat_Bearish": "🟠",
    "Bearish": "🔴",
}


def clean_html(html_text, max_len=280):
    """Làm sạch HTML và cắt ngắn mô tả"""
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text().strip()
    # Cắt tại câu gần nhất dưới max_len
    if len(text) > max_len:
        cut = text[:max_len].rfind(". ")
        if cut > 100:
            text = text[: cut + 1]
        else:
            text = text[:max_len] + "…"
    return text


def format_time_ago(timestamp_str):
    """Chuyển epoch timestamp thành dạng 'X giờ trước'"""
    try:
        ts = int(timestamp_str)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        delta = datetime.now(tz=timezone.utc) - dt
        hours = int(delta.total_seconds() // 3600)
        if hours < 1:
            mins = int(delta.total_seconds() // 60)
            return f"{mins} phút trước"
        elif hours < 24:
            return f"{hours} giờ trước"
        else:
            days = hours // 24
            return f"{days} ngày trước"
    except Exception:
        return ""


def format_av_time(time_str):
    """Chuyển '20260223T040356' -> '23/02/2026 04:03'"""
    try:
        dt = datetime.strptime(time_str, "%Y%m%dT%H%M%S")
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return time_str or ""


# ═══════════════════════════════════════════
#  ALPHA VANTAGE — Tin tức thị trường
# ═══════════════════════════════════════════


def get_alpha_vantage_news(tickers=None, topics=None, limit=5):
    """Lấy tin tức chứng khoán kèm sentiment từ Alpha Vantage"""
    items = []
    try:
        params = {
            "function": "NEWS_SENTIMENT",
            "apikey": ALPHA_VANTAGE_API_KEY,
            "sort": "LATEST",
            "limit": limit,
        }
        if tickers:
            params["tickers"] = tickers
        if topics:
            params["topics"] = topics

        resp = requests.get(
            "https://www.alphavantage.co/query", params=params, timeout=15
        )
        data = resp.json()

        # Kiểm tra lỗi API (rate limit, key không hợp lệ, ...)
        if "feed" not in data:
            print(f"  ⚠ Alpha Vantage: {data.get('Note', data.get('Information', 'No feed data'))}")
            return items

        for article in data.get("feed", [])[:limit]:
            # Sentiment badge
            sentiment_label = article.get("overall_sentiment_label", "Neutral")
            sentiment_score = article.get("overall_sentiment_score", 0)
            emoji = SENTIMENT_EMOJI.get(sentiment_label, "⚪")

            # Ticker sentiment highlights
            ticker_parts = []
            for ts in article.get("ticker_sentiment", [])[:3]:
                ticker = ts.get("ticker", "")
                t_label = ts.get("ticker_sentiment_label", "")
                t_score = ts.get("ticker_sentiment_score", "0")
                t_emoji = SENTIMENT_EMOJI.get(t_label, "⚪")
                try:
                    score_val = float(t_score)
                    sign = "+" if score_val >= 0 else ""
                    ticker_parts.append(f"{t_emoji}{ticker} ({sign}{score_val:.2f})")
                except ValueError:
                    ticker_parts.append(f"{t_emoji}{ticker}")

            ticker_line = " | ".join(ticker_parts) if ticker_parts else ""

            # Topic tags
            topic_tags = " ".join(
                [f"#{t['topic']}" for t in article.get("topics", [])[:3]]
            )

            # Build description
            summary = clean_html(article.get("summary", ""), max_len=250)
            pub_time = format_av_time(article.get("time_published", ""))
            source = article.get("source", "Unknown")

            desc_lines = []
            if ticker_line:
                desc_lines.append(ticker_line)
            desc_lines.append(f"\n📝 {summary}")
            desc_lines.append(f"📰 {source} • {pub_time}")
            if topic_tags:
                desc_lines.append(f"🏷️ {topic_tags}")

            items.append(
                {
                    "section": "market",
                    "source": source,
                    "title": article.get("title", ""),
                    "link": article.get("url", ""),
                    "sentiment_emoji": emoji,
                    "sentiment_label": sentiment_label,
                    "desc": "\n".join(desc_lines),
                }
            )
    except Exception as e:
        print(f"  ❌ Alpha Vantage error: {e}")
    return items


# ═══════════════════════════════════════════
#  HACKER NEWS — Top stories + comments
# ═══════════════════════════════════════════


def get_hacker_news(limit=5):
    """Lấy top stories từ HN kèm author, score, và top comment preview"""
    items = []
    try:
        top_ids = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json", timeout=10
        ).json()[:limit]

        for item_id in top_ids:
            story = requests.get(
                f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json",
                timeout=10,
            ).json()

            if not story:
                continue

            author = story.get("by", "unknown")
            score = story.get("score", 0)
            num_comments = story.get("descendants", 0)
            time_ago = format_time_ago(story.get("time", 0))
            hn_link = f"https://news.ycombinator.com/item?id={item_id}"
            link = story.get("url", hn_link)

            # Fetch top comment preview
            top_comment_text = ""
            kids = story.get("kids", [])
            if kids:
                try:
                    comment = requests.get(
                        f"https://hacker-news.firebaseio.com/v0/item/{kids[0]}.json",
                        timeout=5,
                    ).json()
                    if comment and comment.get("text"):
                        raw = clean_html(comment["text"], max_len=120)
                        if raw:
                            top_comment_text = raw
                except Exception:
                    pass

            # Build description
            desc_lines = [
                f"⬆️ {score} pts  •  💬 {num_comments} replies  •  👤 {author}  •  🕐 {time_ago}"
            ]
            if top_comment_text:
                desc_lines.append(f'\n💬 Top: "{top_comment_text}"')
            if link != hn_link:
                desc_lines.append(f"🗣️ Thảo luận: {hn_link}")

            items.append(
                {
                    "section": "hackernews",
                    "source": "Hacker News",
                    "title": story.get("title", ""),
                    "link": link,
                    "desc": "\n".join(desc_lines),
                }
            )
    except Exception as e:
        print(f"  ❌ Hacker News error: {e}")
    return items


# ═══════════════════════════════════════════
#  RSS FEEDS — Wired, The Verge, etc.
# ═══════════════════════════════════════════


def get_rss_news(source_name, url, limit=3):
    """Lấy tin từ RSS feeds kèm ngày, tác giả, tags"""
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:limit]:
            # Lấy description và làm sạch
            summary = clean_html(
                entry.get("summary", entry.get("description", "")), max_len=250
            )

            # Ngày đăng
            pub_date = ""
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                try:
                    dt = datetime(*entry.published_parsed[:6])
                    pub_date = dt.strftime("%d/%m/%Y")
                except Exception:
                    pub_date = entry.get("published", "")[:16]
            elif entry.get("published"):
                pub_date = entry["published"][:20]

            # Tác giả
            author = entry.get("author", entry.get("dc_creator", ""))

            # Tags / categories
            tags = []
            if hasattr(entry, "tags"):
                tags = [t.get("term", "") for t in entry.tags[:4] if t.get("term")]

            # Build description
            desc_lines = []
            meta_parts = []
            if pub_date:
                meta_parts.append(f"📅 {pub_date}")
            if author:
                meta_parts.append(f"✍️ {author}")
            if meta_parts:
                desc_lines.append(" • ".join(meta_parts))

            desc_lines.append(f"\n📝 {summary}")

            if tags:
                desc_lines.append("🏷️ " + " ".join([f"#{t}" for t in tags]))

            items.append(
                {
                    "section": "tech",
                    "source": source_name,
                    "title": entry.title,
                    "link": entry.link,
                    "desc": "\n".join(desc_lines),
                }
            )
    except Exception as e:
        print(f"  ❌ RSS {source_name} error: {e}")
    return items


# ═══════════════════════════════════════════
#  TELEGRAM — Gửi tin nhắn đẹp
# ═══════════════════════════════════════════


def send_section_header(header_text):
    """Gửi header phân cách section"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "message_thread_id": TOPIC_ID,
        "text": header_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    requests.post(url, json=payload)


def send_news_item(item):
    """Gửi 1 tin nhắn đã format đẹp"""
    section = item.get("section", "tech")

    if section == "market":
        emoji = item.get("sentiment_emoji", "⚪")
        sentiment = item.get("sentiment_label", "")
        text = (
            f"{emoji} <b>{sentiment}</b>\n"
            f"🚀 <b>{item['title']}</b>\n\n"
            f"{item['desc']}\n\n"
            f"🔗 <a href='{item['link']}'>Đọc chi tiết</a>"
        )
    elif section == "hackernews":
        text = (
            f"🚀 <b>{item['title']}</b>\n\n"
            f"{item['desc']}\n\n"
            f"🔗 <a href='{item['link']}'>Đọc chi tiết</a>"
        )
    else:
        text = (
            f"<b>[{item['source']}]</b>\n"
            f"🚀 <b>{item['title']}</b>\n\n"
            f"{item['desc']}\n\n"
            f"🔗 <a href='{item['link']}'>Đọc chi tiết</a>"
        )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "message_thread_id": TOPIC_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    resp = requests.post(url, json=payload)
    if not resp.ok:
        print(f"  ⚠ Telegram error: {resp.status_code} — {resp.text[:200]}")


# ═══════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════

if __name__ == "__main__":
    print("🤖 News Bot đang chạy...")
    print(f"   Thời gian: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n")

    # Load cache chống trùng lặp
    cache = load_cache()
    cached_count = len(cache)
    print(f"📦 Cache: {cached_count} tin đã gửi trước đó\n")

    total_fetched = 0
    total_sent = 0

    # ── Section 1: Thị trường & Cổ phiếu ──
    print("📊 Đang lấy tin thị trường từ Alpha Vantage...")
    market_news = get_alpha_vantage_news(tickers=WATCH_TICKERS, topics="technology,financial_markets", limit=5)
    total_fetched += len(market_news)
    market_news, cache = filter_duplicates(market_news, cache)

    if market_news:
        send_section_header("📊 ═══ <b>THỊ TRƯỜNG &amp; CỔ PHIẾU</b> ═══")
        time.sleep(1)
        for news in market_news:
            send_news_item(news)
            time.sleep(2)
        total_sent += len(market_news)
        print(f"  ✅ Đã gửi {len(market_news)} tin thị trường (mới)")
    else:
        print("  ⏭️ Không có tin thị trường mới")

    # ── Section 2: Hacker News ──
    print("\n🔥 Đang lấy tin từ Hacker News...")
    hn_news = get_hacker_news(20)
    total_fetched += len(hn_news)
    hn_news, cache = filter_duplicates(hn_news, cache)

    if hn_news:
        send_section_header("🔥 ═══ <b>HACKER NEWS TOP</b> ═══")
        time.sleep(1)
        for news in hn_news:
            send_news_item(news)
            time.sleep(2)
        total_sent += len(hn_news)
        print(f"  ✅ Đã gửi {len(hn_news)} tin Hacker News (mới)")
    else:
        print("  ⏭️ Không có tin HN mới")

    # ── Section 3: Tech News từ RSS ──
    print("\n🌐 Đang lấy tin từ RSS feeds...")
    tech_news = []
    for name, url in SOURCES.items():
        print(f"  📡 {name}...")
        tech_news.extend(get_rss_news(name, url, 3))
    total_fetched += len(tech_news)
    tech_news, cache = filter_duplicates(tech_news, cache)

    if tech_news:
        send_section_header("🌐 ═══ <b>TECH NEWS</b> ═══")
        time.sleep(1)
        for news in tech_news:
            send_news_item(news)
            time.sleep(2)
        total_sent += len(tech_news)
        print(f"  ✅ Đã gửi {len(tech_news)} tin tech (mới)")
    else:
        print("  ⏭️ Không có tin tech mới")

    # Lưu cache
    save_cache(cache)

    skipped = total_fetched - total_sent
    print(f"\n🎉 Hoàn tất! Fetched: {total_fetched} | Gửi mới: {total_sent} | Bỏ qua (trùng): {skipped}")