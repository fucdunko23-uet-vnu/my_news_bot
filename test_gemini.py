import os
import feedparser
from google import genai
from google.genai import types

def test():
    feed = feedparser.parse('https://news.google.com/rss/search?q=AI%20agent&hl=vi&gl=VN&ceid=VN:vi')
    entry = feed.entries[0]
    prompt = f"Tóm tắt ngắn gọn tin tức này bằng tiếng Việt:\nTiêu đề: {entry.title}\nLink: {entry.link}\n(KHÔNG chèn thêm link vào bài viết, không dùng lời chào hỏi thừa thãi)"
    
    print('Testing Gemini with full prompt...')
    try:
        client = genai.Client(api_key=os.environ['GEMINI_API_KEY'])
        MARIA_SYSTEM_PROMPT = """Bạn là Maria Tokuda, trợ lý công nghệ chuyên nghiệp.
PHONG CÁCH: Chuyên nghiệp, súc tích, tập trung vào giá trị cốt lõi. Xưng hô: 'anh yêu'.
NHIỆM VỤ:
1. Viết bài tóm tắt tin tức ngắn gọn, súc tích, làm nổi bật thông tin chính.
2. Dịch/viết lại bằng tiếng Việt chuẩn, đọc dễ hiểu.
3. LUÔN kèm theo link gốc của bài viết hoặc nguồn báo ở cuối bài.
4. Trình bày đẹp mắt bằng Markdown, dùng emoji phù hợp."""

        response = client.models.generate_content(
            model='gemini-flash-latest',
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                system_instruction=MARIA_SYSTEM_PROMPT,
            )
        )
        print('Gemini OK:', response.text[:100])
    except Exception as e:
        print('Gemini Error:', e)

test()
