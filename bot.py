import os
import re
import time
import sqlite3
import requests
import schedule

from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo

# ==========================================
# CONFIG
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
ODDS_API_KEY = os.getenv("ODDS_API_KEY")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64)"
    )
}

TRACK_SLUGS = [
    "churchill-downs",
    "belmont-at-aqueduct",
    "fair-grounds",
    "parx-racing",
    "penn-national",
    "charles-town"
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
CREATE TABLE IF NOT EXISTS runners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    horse TEXT,
    track TEXT,
    race TEXT,
    odds TEXT,
    trainer TEXT,
    jockey TEXT,
    rating REAL,
    steam INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS odds_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    horse TEXT,
    odds TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

conn.commit()

# ==========================================
# TELEGRAM
# ==========================================

def send_message(message):

    if not BOT_TOKEN or not CHAT_ID:
        print("Telegram not configured")
        return

    try:

        url = (
            f"https://api.telegram.org/bot"
            f"{BOT_TOKEN}/sendMessage"
        )

        payload = {
            "chat_id": CHAT_ID,
            "text": str(message)
        }

        requests.post(
            url,
            json=payload,
            timeout=20
        )

    except Exception as e:

        print(f"Telegram Error: {e}")

# ==========================================
# CLEAN NAMES
# ==========================================

def clean_name(name):

    name = name.lower()

    name = re.sub(
        r'[^a-z0-9 ]',
        '',
        name
    )

    return name.strip()

# ==========================================
# SAVE ODDS HISTORY
# ==========================================

def save_odds_history(
    horse,
    odds
):

    try:

        cursor.execute(
            """
            INSERT INTO odds_history (
                horse,
                odds
            )
            VALUES (?, ?)
            """,
            (
                horse,
                str(odds)
            )
        )

        conn.commit()

    except Exception as e:

        print(e)

# ==========================================
# PREVIOUS ODDS
# ==========================================

def get_previous_odds(horse):

    try:

        cursor.execute(
            """
            SELECT odds
            FROM odds_history
            WHERE horse = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (horse,)
        )

        row = cursor.fetchone()

        if row:
            return row[0]

    except Exception as e:

        print(e)

    return None

# ==========================================
# SAVE RUNNER
# ==========================================

def save_runner(
    horse,
    track,
    race,
    odds,
    trainer,
    jockey,
    rating,
    steam
):

    try:

        cursor.execute(
            """
            INSERT INTO runners (
                horse,
                track,
                race,
                odds,
                trainer,
                jockey,
                rating,
                steam
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                horse,
                track,
                race,
                odds,
                trainer,
                jockey,
                rating,
                steam
            )
        )

        conn.commit()

    except Exception as e:

        print(e)

# ==========================================
# ODDS LOOKUP
# ==========================================

def get_live_odds(horse_name):

    if not ODDS_API_KEY:
        return "No API Key"

    try:

        url = (
            "https://api.the-odds-api.com/v4/sports/"
            "horse-racing/odds/"
        )

        params = {
            "apiKey": ODDS_API_KEY,
            "regions": "us,uk",
            "markets": "h2h"
        }

        response = requests.get(
            url,
            params=params,
            timeout=20
        )

        data = response.json()

        allowed_books = [
            "bet365",
            "fanduel",
            "draftkings",
            "betmgm"
        ]

        for race in data:

            bookmakers = race.get(
                "bookmakers",
                []
            )

            for bookmaker in bookmakers:

                key = bookmaker.get(
                    "key",
                    ""
                )

                if key not in allowed_books:
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
                            clean_name(horse_name)
                            in clean_name(name)
                        ):

                            return (
                                f"{outcome.get('price')} "
                                f"({key})"
                            )

        return "No Odds"

    except Exception as e:

        print(f"Odds Error: {e}")

        return "No Odds"

# ==========================================
# TWINSPIRES SCRAPER
# ==========================================

def scrape_twinspires(track_slug):

    runners = []

    try:

        url = (
            f"https://www.twinspires.com/"
            f"racing/racecards/{track_slug}"
        )

        print(f"Fetching: {url}")

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        print(response.status_code)

        if response.status_code != 200:
            return []

        soup = BeautifulSoup(
            response.text,
            "lxml"
        )

        text = soup.get_text(
            "\n",
            strip=True
        )

        lines = text.split("\n")

        race_number = 1

        for line in lines:

            line = line.strip()

            if "Race" in line:

                match = re.search(
                    r'Race\s+(\d+)',
                    line
                )

                if match:
                    race_number = match.group(1)

            if (
                len(line) >= 4
                and len(line) <= 28
                and not any(char.isdigit() for char in line)
                and "Race" not in line
                and "TwinSpires" not in line
                and "Results" not in line
                and "Trainer" not in line
                and "Jockey" not in line
                and "Bet" not in line
                and "Login" not in line
            ):

                horse = {
                    "track": track_slug,
                    "race": race_number,
                    "horse": line,
                    "trainer": "Unknown",
                    "jockey": "Unknown"
                }

                runners.append(horse)

        unique = []
        seen = set()

        for horse in runners:

            key = clean_name(
                horse["horse"]
            )

            if key not in seen:

                seen.add(key)
                unique.append(horse)

        print(
            f"{track_slug}: {len(unique)} horses"
        )

        return unique[:60]

    except Exception as e:

        print(f"Scrape Error: {e}")

        return []

# ==========================================
# AI RATING
# ==========================================

def calculate_rating(horse_name):

    try:

        rating = 5.0

        name_len = len(horse_name)

        # simulated speed figure logic
        speed = 60 + (name_len % 30)

        if speed >= 85:
            rating += 2

        elif speed >= 75:
            rating += 1

        # simulated class drop
        if name_len >= 12:
            rating += 2

        elif name_len >= 8:
            rating += 1

        # finish bonus
        if name_len % 5 <= 2:
            rating += 1

        return round(rating, 1)

    except:

        return 5.0

# ==========================================
# DAILY SCAN
# ==========================================

def daily_scan():

    send_message(
        "🚨 ELITE HORSE BOT SCAN 🚨"
    )

    all_horses = []

    for track in TRACK_SLUGS:

        send_message(
            f"🔍 Scanning {track}"
        )

        runners = scrape_twinspires(track)

        print(runners[:5])

        for horse in runners:

            rating = calculate_rating(
                horse["horse"]
            )

            odds = get_live_odds(
                horse["horse"]
            )

            previous_odds = (
                get_previous_odds(
                    horse["horse"]
                )
            )

            save_odds_history(
                horse["horse"],
                odds
            )

            steam = 0
            steam_flag = ""

            try:

                if (
                    previous_odds
                    and odds != "No Odds"
                    and previous_odds != "No Odds"
                ):

                    old_odds = float(
                        str(previous_odds)
                        .split("/")[0]
                    )

                    new_odds = float(
                        str(odds)
                        .split("/")[0]
                    )

                    if new_odds < old_odds:

                        steam = 1
                        steam_flag = "🔥 STEAM"

            except:
                pass

            horse["rating"] = rating
            horse["odds"] = odds
            horse["steam"] = steam
            horse["steam_flag"] = steam_flag

            all_horses.append(horse)

    ranked = sorted(
        all_horses,
        key=lambda x: x["rating"],
        reverse=True
    )

    top = ranked[:10]

    if not top:

        send_message(
            "No horses found today."
        )

        return

    for horse in top:

        msg = (
            f"🏇 {horse['track']} "
            f"R{horse['race']}\n\n"

            f"{horse['horse']}\n\n"

            f"Odds:\n"
            f"{horse['odds']}\n\n"

            f"AI Rating:\n"
            f"{horse['rating']}/10\n\n"

            f"{horse['steam_flag']}"
        )

        send_message(msg)

        save_runner(
            horse['horse'],
            horse['track'],
            horse['race'],
            horse['odds'],
            horse['trainer'],
            horse['jockey'],
            horse['rating'],
            horse['steam']
        )

# ==========================================
# STARTUP
# ==========================================

send_message(
    "✅ Elite TwinSpires Horse Bot Online"
)

print("Bot Running...")

# ==========================================
# TEST SCAN
# ==========================================

daily_scan()

# ==========================================
# SCHEDULED SCANS
# ==========================================

def scheduled_scan():

    hour = datetime.now(
        ZoneInfo("America/New_York")
    ).hour

    if hour >= 10 and hour <= 23:

        daily_scan()

schedule.every(5).minutes.do(
    scheduled_scan
)

# ==========================================
# MAIN LOOP
# ==========================================

while True:

    schedule.run_pending()

    time.sleep(30)
