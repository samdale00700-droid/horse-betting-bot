import os
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

url = (
    f"https://api.telegram.org/bot"
    f"{BOT_TOKEN}/sendMessage"
)

payload = {
    "chat_id": CHAT_ID,
    "text": "✅ Telegram test successful"
}

response = requests.post(
    url,
    json=payload
)

print(response.text)
