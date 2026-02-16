import requests
import feedparser
import time
from bs4 import BeautifulSoup

# --- Cấu hình ---
BOT_TOKEN = "8362778710:AAEeQPGwAtCD5dYIIoi3RrkqNS1gU1n95dI"
CHAT_ID = "-1003363752562" 
TOPIC_ID = 13423

# Danh sách nguồn tin phong phú
SOURCES = {
    "Wired": "https://www.wired.com/feed/rss",
    "UploadVR": "https://uploadvr.com/rss/",
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "TechCrunch": "https://techcrunch.com/feed/",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "9to5Mac": "https://9to5mac.com/feed/"
}

def clean_html(html_text):
    """Làm sạch HTML và cắt ngắn mô tả"""
    if not html_text:
        return ""
    soup = BeautifulSoup(html_text, "html.parser")
    text = soup.get_text()
    # Cắt ngắn khoảng 200 ký tự cho vắn tắt
    return (text[:200] + '...') if len(text) > 200 else text

def get_hacker_news(limit=3):
    items = []
    try:
        top_ids = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json").json()[:limit]
        for item_id in top_ids:
            item = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{item_id}.json").json()
            # Hacker News thường không có description trừ khi là bài thảo luận
            items.append({
                "source": "Hacker News",
                "title": item.get("title"),
                "link": item.get("url", f"https://news.ycombinator.com/item?id={item_id}"),
                "desc": f"Score: {item.get('score')} | Comments: {item.get('descendants')}"
            })
    except: pass
    return items

def get_rss_news(source_name, url, limit=2):
    items = []
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:limit]:
            # Lấy description và làm sạch
            description = clean_html(entry.get("summary", entry.get("description", "")))
            items.append({
                "source": source_name,
                "title": entry.title,
                "link": entry.link,
                "desc": description
            })
    except: pass
    return items

def send_to_telegram(item):
    """Gửi đoạn chat với tiêu đề, mô tả ngắn và link"""
    text = (
        f"<b>[{item['source']}]</b>\n"
        f"🚀 <b>{item['title']}</b>\n\n"
        f"<i>{item['desc']}</i>\n\n"
        f"🔗 <a href='{item['link']}'>Đọc chi tiết</a>"
    )
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "message_thread_id": TOPIC_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False # Để hiện ảnh thumbnail nếu có
    }
    requests.post(url, json=payload)

if __name__ == "__main__":
    all_news = []
    
    # Gom tin từ HN
    all_news.extend(get_hacker_news(3))
    
    # Gom tin từ các nguồn RSS
    for name, url in SOURCES.items():
        print(f"Đang lấy tin từ {name}...")
        all_news.extend(get_rss_news(name, url, 2))
    
    # Gửi đi từng tin một
    for news in all_news:
        send_to_telegram(news)
        time.sleep(2) # Nghỉ để không bị Telegram block do gửi quá nhanh