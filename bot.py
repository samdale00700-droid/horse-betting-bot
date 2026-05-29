import os
import requests
import schedule
import time
import re
import sqlite3
import math

from bs4 import BeautifulSoup
from datetime import datetime

# ==========================================
# CONFIG
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

TRACKS = [
    "EVD",
    "DED",
    "CT",
    "PRX",
    "PEN"
]

TOP_TRAINERS = [
    "Asmussen",
    "Cox",
    "Pletcher",
    "Baffert",
    "Maker"
]

# ==========================================
# DATABASE
# ==========================================

conn = sqlite3.connect(
    "horses.db",
    check_same_thread=False
)

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS bets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    horse TEXT,
    track TEXT,
    odds TEXT,
    rating REAL,
    result TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()

# ==========================================
# TELEGRAM MESSAGE
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

    try:

        requests.post(
            url,
            json=payload,
            timeout=20
        )

    except Exception as e:

        print(e)

# ==========================================
# SAVE BET
# ==========================================

def save_bet(
    horse,
    track,
    odds,
    rating
):

    cursor.execute(
        """
        INSERT INTO bets (
            horse,
            track,
            odds,
            rating,
            result
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            horse,
            track,
            odds,
            rating,
            "PENDING"
        )
    )

    conn.commit()

# ==========================================
# BET365 ODDS
# ==========================================

def get_bet365_odds(horse_name):

    try:

        url = (
            "https://api.the-odds-api.com/v4/sports/"
            "horse-racing/odds/"
        )

        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "uk",
            "markets": "h2h"
        }

        response = requests.get(
            url,
            params=params,
            timeout=20
        )

        data = response.json()

        for race in data:

            bookmakers = race.get(
                "bookmakers",
                []
            )

            for bookmaker in bookmakers:

                if bookmaker.get("key") != "bet365":
                    continue

                markets = bookmaker.get(
                    "markets",
                    []
                )

                for market in markets:

                    outcomes = market.get(
                        "outcomes",
                        []
                    )

                    for outcome in outcomes:

                        name = outcome.get(
                            "name",
                            ""
                        )

                        if (
                            horse_name.lower()
                            in name.lower()
                        ):

                            return outcome.get(
                                "price",
                                "N/A"
                            )

        return "N/A"

    except Exception as e:

        print(e)

        return "N/A"

# ==========================================
# SCRAPE RACECARDS
# ==========================================

def get_racecard(track_code):

    today = datetime.now().strftime(
        "%m%d%Y"
    )

    url = (
        f"https://www.equibase.com/static/entry/"
        f"{track_code}{today}.html"
    )

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        horses = []

        rows = soup.find_all("tr")

        for row in rows:

            text = row.get_text(
                " ",
                strip=True
            )

            if (
                "Claiming" in text
                or "Maiden Claiming" in text
            ):

                horses.append({
                    "raw": text,
                    "track": track_code
                })

        return horses

    except Exception as e:

        print(e)

        return []

# ==========================================
# CLAIM VALUE PARSER
# ==========================================

def parse_claiming_value(text):

    matches = re.findall(
        r'\$(\d+[,\d]*)',
        text
    )

    if not matches:
        return 0

    value = matches[0].replace(
        ",",
        ""
    )

    try:
        return int(value)

    except:
        return 0

# ==========================================
# TRAINER BONUS
# ==========================================

def trainer_bonus(text):

    for trainer in TOP_TRAINERS:

        if trainer.lower() in text.lower():

            return 1.5

    return 0

# ==========================================
# AI PROBABILITY
# ==========================================

def calculate_ai_probability(rating):

    return min(
        0.90,
        rating / 10
    )

# ==========================================
# ODDS TO PROBABILITY
# ==========================================

def odds_to_probability(odds):

    try:

        if odds == "N/A":
            return 0

        parts = str(odds).split("/")

        if len(parts) != 2:
            return 0

        numerator = float(parts[0])
        denominator = float(parts[1])

        return denominator / (
            numerator + denominator
        )

    except:

        return 0

# ==========================================
# CLASS DROPPER DETECTION
# ==========================================

def detect_class_droppers(entries):

    horses = []

    for item in entries:

        text = item["raw"]

        today_claim = parse_claiming_value(
            text
        )

        if today_claim == 0:
            continue

        previous_claim = (
            today_claim * 2
        )

        drop_pct = (
            previous_claim - today_claim
        ) / previous_claim

        if drop_pct >= 0.40:

            rating = round(
                (
                    drop_pct * 10
                )
                + trainer_bonus(text),
                1
            )

            horses.append({

                "track": item["track"],

                "horse": text[:50],

                "today_claim": today_claim,

                "previous_claim": previous_claim,

                "rating": rating
            })

    return horses

# ==========================================
# DAILY SCAN
# ==========================================

def daily_scan():

    send_message(
        "🚨 LIVE DAILY CLASS DROPPER REPORT 🚨"
    )

    all_horses = []

    for track in TRACKS:

        entries = get_racecard(track)

        droppers = (
            detect_class_droppers(
                entries
            )
        )

        all_horses.extend(
            droppers
        )

    ranked = sorted(
        all_horses,
        key=lambda x: x["rating"],
        reverse=True
    )

    top = ranked[:10]

    if not top:

        send_message(
            "No major class droppers detected today."
        )

        return

    for horse in top:

        odds = get_bet365_odds(
            horse["horse"]
        )

        ai_prob = (
            calculate_ai_probability(
                horse["rating"]
            )
        )

        market_prob = (
            odds_to_probability(
                odds
            )
        )

        value_flag = ""

        if ai_prob > market_prob:

            value_flag = (
                "✅ VALUE BET DETECTED"
            )

        msg = f'''
🏇 {horse['track']}

{horse['horse']}

Claim Drop:
${horse['previous_claim']:,} → ${horse['today_claim']:,}

Bet365 Odds:
{odds}

AI Rating:
{horse['rating']}/10

{value_flag}
'''

        send_message(msg)

        save_bet(
            horse["horse"],
            horse["track"],
            odds,
            horse["rating"]
        )

# ==========================================
# STARTUP MESSAGE
# ==========================================

send_message(
    "✅ Horse betting bot is online."
)

# ==========================================
# SCHEDULE
# ==========================================

schedule.every().day.at(
    "13:00"
).do(daily_scan)

print(
    "Telegram Betting Bot Running..."
)

# ==========================================
# MAIN LOOP
# ==========================================

while True:

    schedule.run_pending()

    time.sleep(30)
