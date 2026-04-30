# 🚀 Hướng dẫn Deploy News Bot với Docker

## 📋 Yêu cầu

- Docker & Docker Compose đã cài đặt
- Tailscale đã cài đặt trên server
- Token Telegram Bot
- API Key Gemini

## 🏗️ Các bước deploy

### 1. Chuẩn bị trên Local (hoặc dev machine)

```bash
# Clone hoặc copy project
cd my-news-bot

# Tạo .env file từ template
cp .env.example .env

# Edit .env với credentials thực
nano .env
# Hoặc dùng editor khác:
# TELEGRAM_TOKEN=xxx
# GROUP_CHAT_ID=xxx
# TOPIC_ID=0
# GEMINI_API_KEY=xxx
```

### 2. Build Docker Image

```bash
# Build image locally
docker-compose build

# Hoặc push lên Docker Hub để dễ pull trên server
docker tag news-bot your-dockerhub-username/news-bot:latest
docker push your-dockerhub-username/news-bot:latest
```

### 3. Deploy lên Server qua Tailscale

#### A. SSH vào server qua Tailscale
```bash
# Thay <server-tailscale-ip> bằng IP của server trong Tailscale
ssh user@<server-tailscale-ip>
```

#### B. Clone project hoặc copy files
```bash
# Cách 1: Clone từ Git
git clone <your-repo-url> my-news-bot
cd my-news-bot

# Hoặc cách 2: Copy files (nếu không dùng Git)
scp -r . user@<server-tailscale-ip>:/home/user/my-news-bot
ssh user@<server-tailscale-ip>
cd ~/my-news-bot
```

#### C. Setup .env file trên server
```bash
# Tạo .env
nano .env

# Paste credentials:
TELEGRAM_TOKEN=your_actual_token
GROUP_CHAT_ID=your_actual_chat_id
TOPIC_ID=0
GEMINI_API_KEY=your_actual_key
```

#### D. Chạy Docker Compose
```bash
# Pull & run container
docker-compose up -d

# Hoặc nếu build từ source
docker-compose build
docker-compose up -d

# Kiểm tra logs
docker-compose logs -f news-bot

# Dừng container
docker-compose down
```

### 4. Quản lý trên Server

```bash
# Xem status
docker ps

# Xem logs realtime
docker-compose logs -f

# Restart container
docker-compose restart

# Rebuild sau khi có update
docker-compose up -d --build
```

## 🔧 Cấu hình nâng cao

### Tự động khởi động khi server reboot
```bash
# Thêm supervisor hoặc systemd service
# Tạo file /etc/systemd/system/news-bot.service

[Unit]
Description=News Bot Docker Service
After=docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/home/user/my-news-bot
ExecStart=/usr/bin/docker-compose up
ExecStop=/usr/bin/docker-compose down
Restart=always

[Install]
WantedBy=multi-user.target

# Enable service
sudo systemctl enable news-bot
sudo systemctl start news-bot
```

### Monitoring & Logging
```bash
# Giới hạn size logs
# Trong docker-compose.yml đã cấu hình:
# max-size: 10m, max-file: 3

# Xem logs từ file
cd logs
tail -f news-bot.log
```

## 📊 Monitoring Tailscale

```bash
# Trên server: Kiểm tra IP Tailscale
tailscale ip

# Trên client: Ping server qua Tailscale
ping <tailscale-ip-of-server>

# SSH vào qua Tailscale (dễ hơn cấu hình firewall)
ssh user@<tailscale-ip>
```

## 🐛 Troubleshooting

### Container không chạy
```bash
# Kiểm tra logs
docker-compose logs news-bot

# Kiểm tra environment variables
docker exec news-bot env | grep -E "TELEGRAM|GEMINI"
```

### API rate limit
Bot đã cấu hình retry tự động khi gặp rate limit. Có thể điều chỉnh trong `main.py`

### Container crash
- Kiểm tra GPU/Memory limitations
- Kiểm tra .env variables đúng
- Kiểm tra internet connection từ server

## 📁 Folder Structure

```
my-news-bot/
├── main.py                 # Main bot script
├── check_model.py         # Script kiểm tra models
├── requirements.txt       # Python dependencies
├── Dockerfile            # Docker image definition
├── docker-compose.yml    # Docker Compose config
├── .dockerignore         # Files exclude từ image
├── .env                  # Environment variables (KHÔNG COMMIT!)
├── .env.example          # Template .env
├── logs/                 # Logs (tạo tự động)
└── data/                 # Data folder (tùy chọn)
```

## ⚠️ Bảo mật

- **KHÔNG** commit `.env` file lên Git
- Sử dụng `.env.example` làm template
- Rotate tokens định kỳ
- Sử dụng VPN/Tailscale thay vì expose public
- Giới hạn resource trên container

---

💡 **Tips**: Nếu cần update code mà không downtime, có thể dùng Docker registry private + rolling update strategy!
