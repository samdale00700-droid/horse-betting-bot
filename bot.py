import os
import requests
import schedule
import time

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")


# ==========================================
# SAMPLE CLASS DROPPER SCAN
# Replace with live race scraping later
# ==========================================

horses = [
    {
        "track": "Evangeline",
        "race": 5,
        "horse": "THISONEISFORYOU",
        "drop": "$10k → $5k",
        "rating": 9.1
    },
    {
        "track": "Evangeline",
        "race": 7,
        "horse": "DYNAMITE TONIGHT",
        "drop": "$12.5k → $4k",
        "rating": 8.7
    }
]


# ==========================================
# SEND TELEGRAM MESSAGE
# ==========================================


def send_message(message):

    url = (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(url, json=payload)


# ==========================================
# DAILY SCAN
# ==========================================


def daily_scan():

    send_message("🚨 DAILY CLASS DROPPER REPORT 🚨")

    for horse in horses:

        msg = f'''
🏇 {horse["track"]} R{horse["race"]}

{horse["horse"]}

Class Drop:
{horse["drop"]}

AI Rating:
{horse["rating"]}/10
'''

        send_message(msg)


# ==========================================
# SCHEDULE
# ==========================================

schedule.every().day.at("13:00").do(daily_scan)

print("Telegram Betting Bot Running...")

while True:
    schedule.run_pending()
    time.sleep(30)
