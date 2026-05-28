from bs4 import BeautifulSoup
from datetime import datetime
import re
TRACKS = ["EVD", "DED", "CT", "PRX", "PEN"]import os
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
]def parse_claiming_value(text):

    matches = re.findall(r'\$(\d+[\,\d]*)', text)

    if not matches:
        return 0

    return int(matches[0].replace(',', ''))
def detect_class_droppers(entries):

    horses = []

    for item in entries:

        text = item["raw"]

        today_claim = parse_claiming_value(text)

        previous_claim = today_claim * 2

        if previous_claim > today_claim:

            drop_pct = (
                previous_claim - today_claim
            ) / previous_claim

            if drop_pct >= 0.40:

                horses.append({
                    "track": item["track"],
                    "horse": text[:40],
                    "today_claim": today_claim,
                    "previous_claim": previous_claim,
                    "rating": round(drop_pct * 10, 1)
                })

    return horses

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

def get_racecard(track_code):

    today = datetime.now().strftime("%m%d%Y")

    url = (
        f"https://www.equibase.com/static/entry/"
        f"{track_code}{today}.html"
    )

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:
        response = requests.get(url, headers=headers, timeout=20)

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        horses = []

        rows = soup.find_all("tr")

        for row in rows:

            text = row.get_text(" ", strip=True)

            if "Claiming" in text:

                horses.append({
                    "raw": text,
                    "track": track_code
                })

        return horses

    except Exception as e:
        print(f"Scrape failed for {track_code}: {e}")
        return []
# ==========================================
# DAILY SCAN
# ==========================================


def daily_scan():

    def daily_scan():

    send_message("🚨 LIVE DAILY CLASS DROPPER REPORT 🚨")

    all_horses = []

    for track in TRACKS:

        entries = get_racecard(track)

        droppers = detect_class_droppers(entries)

        all_horses.extend(droppers)

    ranked = sorted(
        all_horses,
        key=lambda x: x['rating'],
        reverse=True
    )

    top = ranked[:10]

    if not top:
        send_message("No major class droppers detected today.")
        return

    for horse in top:

        msg = f'''
🏇 {horse["track"]}

{horse["horse"]}

Claim Drop:
${horse["previous_claim"]:,} → ${horse["today_claim"]:,}

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
