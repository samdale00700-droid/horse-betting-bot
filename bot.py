import os
import requests
import schedule
import time
import re
import sqlite3

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

# ==========================================
# DATABASE
# ==========================================

conn = sqlite3.connect(
    "horses.db",
    check_same_thread=False
)

cursor = conn.cursor()

# Bets table
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

# Odds history table
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

    url = (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": CHAT_ID,
        "text": str(message)
    }

    try:

        requests.post(
            url,
            json=payload,
            timeout=20
        )

    except Exception as e:

        print(f"Telegram Error: {e}")

# ==========================================
# CLEAN HORSE NAME
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
# SAVE BET
# ==========================================

def save_bet(
    horse,
    track,
    odds,
    rating
):

    try:

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

    except Exception as e:

        print(e)

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
# GET PREVIOUS ODDS
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
# GET BET365 ODDS
# ==========================================

def get_bet365_odds(horse_name):

    if not ODDS_API_KEY:
        return "N/A"

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

                        clean_horse = clean_name(
                            horse_name
                        )

                        clean_book = clean_name(
                            name
                        )

                        if clean_horse == clean_book:

                            return outcome.get(
                                "price",
                                "N/A"
                            )

        return "N/A"

    except Exception as e:

        print(e)

        return "N/A"

# ==========================================
# PARSE CLAIM VALUE
# ==========================================

def parse_claiming_value(text):

    try:

        matches = re.findall(
            r'\$(\d[\d,]*)',
            text
        )

        if not matches:
            return 0

        value = matches[0].replace(
            ",",
            ""
        )

        return int(value)

    except:

        return 0

# ==========================================
# STRUCTURED RACECARD PARSER
# ==========================================

def get_racecard(track_code):

    horses = []

    try:

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

        tables = soup.find_all("table")

        for table in tables:

            rows = table.find_all("tr")

            for row in rows:

                cols = row.find_all("td")

                if len(cols) < 5:
                    continue

                try:

                    horse_name = cols[3].get_text(
                        strip=True
                    )

                    row_text = row.get_text(
                        " ",
                        strip=True
                    )

                    claim_value = (
                        parse_claiming_value(
                            row_text
                        )
                    )

                    if not horse_name:
                        continue

                    horse_data = {
                        "track": track_code,
                        "horse": horse_name,
                        "raw": row_text,
                        "claim": claim_value
                    }

                    horses.append(horse_data)

                except:
                    continue

        return horses

    except Exception as e:

        print(f"Racecard Error: {e}")

        return []

# ==========================================
# DETECT CLASS DROPPERS
# ==========================================

def detect_class_droppers(entries):

    horses = []

    for item in entries:

        try:

            today_claim = item["claim"]

            if today_claim <= 0:
                continue

            # Temporary estimate
            previous_claim = (
                today_claim * 2
            )

            drop_pct = (
                previous_claim - today_claim
            ) / previous_claim

            if drop_pct < 0.40:
                continue

            rating = round(
                drop_pct * 10,
                1
            )

            horse_data = {
                "track": item["track"],
                "horse": item["horse"],
                "today_claim": today_claim,
                "previous_claim": previous_claim,
                "rating": rating
            }

            horses.append(horse_data)

        except Exception as e:

            print(e)

    return horses

# ==========================================
# TRACK RESULTS
# ==========================================

def update_results():

    print("Result tracking started")

    try:

        cursor.execute(
            """
            SELECT id, horse
            FROM bets
            WHERE result = 'PENDING'
            """
        )

        bets = cursor.fetchall()

        for bet in bets:

            bet_id = bet[0]

            horse = bet[1]

            # Placeholder
            result = "UNKNOWN"

            cursor.execute(
                """
                UPDATE bets
                SET result = ?
                WHERE id = ?
                """,
                (
                    result,
                    bet_id
                )
            )

        conn.commit()

    except Exception as e:

        print(e)

# ==========================================
# DAILY SCAN
# ==========================================

def daily_scan():

    send_message(
        "🚨 LIVE CLASS DROPPER SCAN 🚨"
    )

    all_horses = []

    for track in TRACKS:

        send_message(
            f"🔍 Scanning {track}"
        )

        entries = get_racecard(track)

        print(
            f"{track} entries: {len(entries)}"
        )

        droppers = (
            detect_class_droppers(entries)
        )

        print(
            f"{track} droppers: {len(droppers)}"
        )

        all_horses.extend(droppers)

    ranked = sorted(
        all_horses,
        key=lambda x: x["rating"],
        reverse=True
    )

    top = ranked[:10]

    if not top:

        send_message(
            "No class droppers found."
        )

        return

    for horse in top:

        odds = get_bet365_odds(
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

        steam = ""

        if (
            previous_odds
            and previous_odds != "N/A"
            and odds != "N/A"
        ):

            try:

                old_num = float(
                    previous_odds.split("/")[0]
                )

                new_num = float(
                    odds.split("/")[0]
                )

                if new_num < old_num:

                    steam = (
                        "🔥 STEAM MOVE"
                    )

            except:
                pass

        msg = (
            f"🏇 {horse['track']}\n\n"
            f"{horse['horse']}\n\n"
            f"Claim Drop:\n"
            f"${horse['previous_claim']:,}"
            f" → "
            f"${horse['today_claim']:,}\n\n"
            f"Bet365 Odds:\n"
            f"{odds}\n\n"
            f"AI Rating:\n"
            f"{horse['rating']}/10\n\n"
            f"{steam}"
        )

        send_message(msg)

        save_bet(
            horse["horse"],
            horse["track"],
            odds,
            horse["rating"]
        )

# ==========================================
# STARTUP
# ==========================================

send_message(
    "✅ Horse betting bot online."
)

print(
    "Horse Bot Running..."
)

# ==========================================
# STARTUP TEST
# ==========================================

daily_scan()

# ==========================================
# UPDATE RESULTS
# ==========================================

schedule.every(30).minutes.do(
    update_results
)

# ==========================================
# RUN EVERY MINUTE
# 13:00 TO 16:59
# ==========================================

def scheduled_scan():

    current_hour = datetime.now().hour

    if (
        current_hour >= 13
        and current_hour <= 16
    ):

        daily_scan()

schedule.every(1).minutes.do(
    scheduled_scan
)

# ==========================================
# MAIN LOOP
# ==========================================

while True:

    schedule.run_pending()

    time.sleep(30)
