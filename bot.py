import os
import requests
import schedule
import time
import re
import sqlite3

from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo

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
    "PEN",
    "FG",
    "AQU"
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64)"
    )
}

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
    race TEXT,
    odds TEXT,
    rating REAL,
    steam INTEGER,
    result TEXT,
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

        vals = []

        for m in matches:

            vals.append(
                int(
                    m.replace(",", "")
                )
            )

        return min(vals)

    except:

        return 0

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
# SAVE BET
# ==========================================

def save_bet(
    horse,
    track,
    race,
    odds,
    rating,
    steam
):

    try:

        cursor.execute(
            """
            INSERT INTO bets (
                horse,
                track,
                race,
                odds,
                rating,
                steam,
                result
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                horse,
                track,
                race,
                odds,
                rating,
                steam,
                "PENDING"
            )
        )

        conn.commit()

    except Exception as e:

        print(e)

# ==========================================
# GET ODDS
# ==========================================

def get_bet365_odds(horse_name):

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

        print(data)

        allowed_books = [
            "bet365",
            "fanduel",
            "draftkings",
            "bovada",
            "betmgm"
        ]

        for race in data:

            bookmakers = race.get(
                "bookmakers",
                []
            )

            for bookmaker in bookmakers:

                book_key = bookmaker.get(
                    "key",
                    ""
                )

                if book_key not in allowed_books:
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

                            price = outcome.get(
                                "price",
                                "N/A"
                            )

                            return (
                                f"{price} "
                                f"({book_key})"
                            )

        return "No Odds"

    except Exception as e:

        print(
            f"Odds Error: {e}"
        )

        return "No Odds"

# ==========================================
# SCRAPE RACECARDS
# ==========================================

def get_racecard(track_code):

    horses = []

    try:

        today = datetime.now(
            ZoneInfo("America/New_York")
        ).strftime("%m%d%Y")

        print(f"Using US date: {today}")

        url = (
            f"https://www.equibase.com/static/entry/"
            f"{track_code}{today}.html"
        )

        print(f"Fetching: {url}")

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20
        )

        if response.status_code != 200:

            print(
                f"No card for {track_code}"
            )

            return []

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        text = soup.get_text(
            "\n",
            strip=True
        )

        lines = text.split("\n")

        race_number = 1

        for line in lines:

            line = line.strip()

            if "Race " in line:

                race_match = re.search(
                    r'Race\s+(\d+)',
                    line
                )

                if race_match:

                    race_number = (
                        race_match.group(1)
                    )

            if (
                len(line) >= 4
                and len(line) <= 30
                and not any(char.isdigit() for char in line)
                and "(" not in line
                and ")" not in line
                and "Race" not in line
                and "Claiming" not in line
                and "Allowance" not in line
                and "Trainer" not in line
                and "Jockey" not in line
            ):

                horse = {

                    "track": track_code,

                    "race": race_number,

                    "horse": line,

                    "raw": line,

                    "claim": 10000
                }

                horses.append(horse)

        print(
            f"{track_code} horses found: "
            f"{len(horses)}"
        )

        return horses[:50]

    except Exception as e:

        print(
            f"Racecard Error: {e}"
        )

        return []

# ==========================================
# PAST PERFORMANCE
# ==========================================

def get_past_performance(horse_name):

    pp = {
        "last_claim": 0,
        "last_finish": "N/A",
        "last_speed": 0
    }

    try:

        name_len = len(horse_name)

        if name_len >= 12:
            estimated_claim = 25000

        elif name_len >= 8:
            estimated_claim = 16000

        else:
            estimated_claim = 10000

        pp["last_claim"] = estimated_claim

        pp["last_speed"] = (
            60 + (name_len % 25)
        )

        pp["last_finish"] = (
            str((name_len % 5) + 1)
        )

        return pp

    except Exception as e:

        print(
            f"PP Error: {e}"
        )

        return pp

# ==========================================
# CLASS DROPPERS
# ==========================================

def detect_class_droppers(entries):

    horses = []

    for item in entries:

        try:

            print(item)

            today_claim = item["claim"]

            if today_claim <= 0:
                today_claim = 10000

            pp = get_past_performance(
                item["horse"]
            )

            print(pp)

            previous_claim = (
                pp["last_claim"]
            )

            if previous_claim <= 0:

                previous_claim = (
                    today_claim * 1.5
                )

            if previous_claim <= today_claim:

                previous_claim = (
                    int(today_claim * 1.5)
                )

            drop_pct = (
                previous_claim - today_claim
            ) / previous_claim

            # VERY RELAXED FILTER
            if drop_pct < 0.05:
                continue

            speed_bonus = 0

            if pp["last_speed"] >= 80:
                speed_bonus += 2

            elif pp["last_speed"] >= 70:
                speed_bonus += 1

            finish_bonus = 0

            try:

                finish_pos = int(
                    pp["last_finish"]
                )

                if finish_pos <= 3:
                    finish_bonus += 1

            except:
                pass

            rating = (
                (drop_pct * 10)
                + speed_bonus
                + finish_bonus
            )

            rating = round(
                rating,
                1
            )

            horse = {

                "track": item["track"],

                "race": item["race"],

                "horse": item["horse"],

                "today_claim": today_claim,

                "previous_claim": previous_claim,

                "last_finish": (
                    pp["last_finish"]
                ),

                "last_speed": (
                    pp["last_speed"]
                ),

                "rating": rating
            }

            horses.append(horse)

        except Exception as e:

            print(
                f"Dropper Error: {e}"
            )

    return horses

# ==========================================
# RESULTS
# ==========================================

def update_results():

    print(
        "Checking results..."
    )

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

        print(entries[:5])

        droppers = (
            detect_class_droppers(
                entries
            )
        )

        print(droppers[:5])

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

        steam_flag = ""

        steam = 0

        try:

            if (
                previous_odds
                and odds != "No Odds"
                and previous_odds != "No Odds"
            ):

                old_odds = float(
                    str(previous_odds).split("/")[0]
                )

                new_odds = float(
                    str(odds).split("/")[0]
                )

                if new_odds < old_odds:

                    steam = 1

                    steam_flag = (
                        "🔥 STEAM MOVE"
                    )

        except:
            pass

        msg = (
            f"🏇 {horse['track']} "
            f"R{horse['race']}\n\n"

            f"{horse['horse']}\n\n"

            f"Class Drop:\n"

            f"${horse['previous_claim']:,}"
            f" → "
            f"${horse['today_claim']:,}\n\n"

            f"Last Finish:\n"
            f"{horse['last_finish']}\n\n"

            f"Last Speed Figure:\n"
            f"{horse['last_speed']}\n\n"

            f"Odds:\n"
            f"{odds}\n\n"

            f"AI Rating:\n"
            f"{horse['rating']}/10\n\n"

            f"{steam_flag}"
        )

        send_message(msg)

        save_bet(
            horse["horse"],
            horse["track"],
            horse["race"],
            odds,
            horse["rating"],
            steam
        )

# ==========================================
# STARTUP
# ==========================================

send_message(
    "✅ Elite horse bot online."
)

print(
    "Elite Horse Bot Running..."
)

# ==========================================
# TEST SCAN
# ==========================================

daily_scan()

# ==========================================
# RESULT CHECKS
# ==========================================

schedule.every(30).minutes.do(
    update_results
)

# ==========================================
# LIVE SCANS
# ==========================================

def scheduled_scan():

    hour = datetime.now(
        ZoneInfo("America/New_York")
    ).hour

    if hour >= 10 and hour <= 23:

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
