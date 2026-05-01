import os
import time
import telebot
import schedule
import feedparser
from threading import Thread
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
from playwright.sync_api import sync_playwright

load_dotenv()

# --- CONFIG ---
TOKEN = os.getenv("TELEGRAM_TOKEN")
GROUP_ID = os.getenv("GROUP_CHAT_ID")
TOPIC_ID = int(os.getenv("TOPIC_ID") or 0)

# Hỗ trợ nhiều API Key cách nhau bằng dấu phẩy
API_KEYS = [k.strip() for k in (os.getenv("GEMINI_API_KEY") or "").split(",") if k.strip()]
if not API_KEYS:
    print("⚠️ WARNING: Chưa cấu hình GEMINI_API_KEY")
    client = None
else:
    current_key_idx = 0
    client = genai.Client(api_key=API_KEYS[current_key_idx])

bot_username = None

MARIA_SYSTEM_PROMPT = """Bạn là Maria Tokuda, trợ lý công nghệ chuyên nghiệp.
PHONG CÁCH: Chuyên nghiệp, súc tích, tập trung vào giá trị cốt lõi. Xưng hô: 'anh yêu'.
NHIỆM VỤ:
1. Viết bài tóm tắt tin tức ngắn gọn, súc tích, làm nổi bật thông tin chính.
2. Dịch/viết lại bằng tiếng Việt chuẩn, đọc dễ hiểu.
3. LUÔN kèm theo link gốc của bài viết hoặc nguồn báo ở cuối bài.
4. Trình bày đẹp mắt bằng Markdown, dùng emoji phù hợp."""

bot = telebot.TeleBot(TOKEN)


def call_gemini(prompt: str) -> str:
    global current_key_idx, client
    if not API_KEYS:
        return "⚠️ Em không có API Key để suy nghĩ (GEMINI_API_KEY trống)."
        
    attempts_per_key = 2
    total_attempts = len(API_KEYS) * attempts_per_key
    
    for attempt in range(total_attempts):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    system_instruction=MARIA_SYSTEM_PROMPT,
                ),
            )
            return response.text
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                print(f"⚠️ Rate limit ở Key thứ {current_key_idx + 1}... (Lỗi: {e})")
                if len(API_KEYS) > 1 and attempt % attempts_per_key == attempts_per_key - 1:
                    current_key_idx = (current_key_idx + 1) % len(API_KEYS)
                    client = genai.Client(api_key=API_KEYS[current_key_idx])
                    print(f"🔄 Đã chuyển sang API key thứ {current_key_idx + 1}")
                elif attempt < total_attempts - 1:
                    time.sleep(5)
                else:
                    raise Exception("Đã thử tất cả các API Key nhưng vẫn bị giới hạn Rate limit (429).")
            else:
                raise e


def get_github_trending():
    print("Đang cào GitHub Trending bằng Playwright...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://github.com/trending", timeout=60000)
            page.wait_for_selector("article.Box-row", timeout=10000)

            repo = page.query_selector("article.Box-row")
            if repo:
                title_elem = repo.query_selector("h2 a")
                desc_elem = repo.query_selector("p")

                title = title_elem.inner_text().strip().replace(" ", "").replace("\n", "") if title_elem else "Unknown"
                link = "https://github.com" + title_elem.get_attribute("href") if title_elem else ""
                desc = desc_elem.inner_text().strip() if desc_elem else "No description"

                browser.close()
                return {"title": title, "link": link, "desc": desc}
            browser.close()
    except Exception as e:
        print(f"Playwright error: {e}")
    return None


def get_rss_news():
    import requests
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    sources = {
        "Hacker News": "https://news.ycombinator.com/rss",
        "TechCrunch": "https://techcrunch.com/feed/",
        "Reddit r/technology": "https://www.reddit.com/r/technology/top/.rss?t=day"
    }
    news_items = []
    for source_name, url in sources.items():
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            if feed.entries:
                # Lấy 1 tin hot nhất của mỗi nguồn
                top_entry = feed.entries[0]
                news_items.append({
                    "source": source_name,
                    "title": top_entry.title,
                    "link": top_entry.link
                })
        except Exception as e:
            print(f"Error parsing {source_name}: {e}")
    return news_items


def broadcast_news():
    print(f"[{datetime.now()}] 📡 Maria đang tổng hợp bản tin...")
    try:
        bot.send_message(
            GROUP_ID,
            f"🌆 *BẢN TIN CÔNG NGHỆ TỔNG HỢP* — {datetime.now().strftime('%d/%m/%Y')}\n_Đang thu thập và phân tích dữ liệu, anh yêu đợi em chút nhé..._",
            message_thread_id=TOPIC_ID,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Lỗi gửi tin nhắn mở đầu: {e}")
        return

    # 1. GitHub Trending
    gh_repo = get_github_trending()
    if gh_repo:
        prompt = f"Viết 1 bài giới thiệu ngắn gọn về repo GitHub đang trending này (sử dụng format Markdown):\nTên: {gh_repo['title']}\nMô tả: {gh_repo['desc']}\n(KHÔNG chèn link vào bài viết, chỉ viết nội dung)"
        text = call_gemini(prompt)
        final_msg = f"🐙 *Nguồn: GitHub Trending*\n\n{text}\n\n🔗 [Xem Repository tại đây]({gh_repo['link']})"
        try:
            bot.send_message(GROUP_ID, final_msg, message_thread_id=TOPIC_ID, parse_mode="Markdown")
        except Exception:
            bot.send_message(GROUP_ID, final_msg, message_thread_id=TOPIC_ID)
        time.sleep(3)

    # 2. RSS News
    rss_news = get_rss_news()
    for item in rss_news:
        prompt = f"Tóm tắt tin tức sau từ {item['source']}:\nTiêu đề: {item['title']}\nLink: {item['link']}\n(Lưu ý: tự động tìm kiếm thêm nội dung để tóm tắt chi tiết. KHÔNG chèn link vào bài viết, tôi sẽ tự chèn)"
        text = call_gemini(prompt)
        final_msg = f"📰 *Nguồn: {item['source']}*\n\n{text}\n\n🔗 [Đọc bài viết gốc tại đây]({item['link']})"
        try:
            bot.send_message(GROUP_ID, final_msg, message_thread_id=TOPIC_ID, parse_mode="Markdown")
        except Exception:
            bot.send_message(GROUP_ID, final_msg, message_thread_id=TOPIC_ID)
        time.sleep(3)

    print(f"[{datetime.now()}] ✅ Đã gửi toàn bộ bản tin thành công!")


@bot.message_handler(commands=['news'])
def handle_news_command(message):
    try:
        topic = message.text.replace("/news", "").strip()
        if not topic:
            topic = "Công nghệ, AI, Crypto"

        bot.send_message(
            message.chat.id,
            f"🔍 Đang tìm kiếm 2 tin tức hot nhất về chủ đề: *{topic}*...",
            message_thread_id=message.message_thread_id,
            parse_mode="Markdown"
        )

        import urllib.parse
        import requests
        encoded_topic = urllib.parse.quote(topic)
        rss_url = f"https://news.google.com/rss/search?q={encoded_topic}&hl=vi&gl=VN&ceid=VN:vi"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        resp = requests.get(rss_url, headers=headers, timeout=15)
        resp.raise_for_status()
        
        feed = feedparser.parse(resp.content)

        if not feed.entries:
            bot.send_message(message.chat.id, f"❌ Xin lỗi anh yêu, em không tìm thấy tin tức nào về chủ đề '{topic}'.", message_thread_id=message.message_thread_id)
            return

        for entry in feed.entries[:2]:
            prompt = f"Tóm tắt ngắn gọn tin tức này bằng tiếng Việt:\nTiêu đề: {entry.title}\nLink: {entry.link}\n(KHÔNG chèn thêm link vào bài viết, không dùng lời chào hỏi thừa thãi)"
            text = call_gemini(prompt)
            final_msg = f"📰 *Chủ đề: {topic}*\n\n{text}\n\n🔗 [Đọc bài viết gốc tại đây]({entry.link})"
            try:
                bot.send_message(message.chat.id, final_msg, message_thread_id=message.message_thread_id, parse_mode="Markdown")
            except Exception:
                bot.send_message(message.chat.id, final_msg, message_thread_id=message.message_thread_id)
            time.sleep(2)
    except Exception as e:
        print(f"❌ Lỗi lệnh /news: {e}")
        try:
            bot.send_message(
                message.chat.id,
                f"❌ Maria gặp lỗi rồi anh ơi: `{e}`",
                message_thread_id=message.message_thread_id,
                parse_mode="Markdown"
            )
        except:
            bot.send_message(message.chat.id, f"❌ Lỗi: {e}", message_thread_id=message.message_thread_id)




def run_scheduler():
    schedule.every().day.at("19:00").do(broadcast_news)
    print("⏰ Scheduler đã khởi động — bản tin tự động lúc 19:00 hàng ngày")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    print("🤖 Maria Tokuda v6.0 (Separate Messages & Playwright Edition) đã sẵn sàng!")
    
    if os.getenv("RUN_ONCE") == "true":
        print("🚀 Chế độ RUN_ONCE: Cập nhật tin tức một lần rồi thoát (dành cho Github Actions)")
        broadcast_news()
        import sys
        sys.exit(0)
        
    Thread(target=run_scheduler, daemon=True).start()

    while True:
        try:
            print("🔄 Đang kết nối Telegram...")
            bot.polling(
                none_stop=True,
                interval=3,
                timeout=60,
                long_polling_timeout=60,
            )
        except Exception as e:
            print(f"⚠️ Polling lỗi: {e}")
            print("⏳ Thử lại sau 15 giây...")
            time.sleep(15)