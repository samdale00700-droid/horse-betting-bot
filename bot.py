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

cursor.execute(
    """
    CREATE TABLE IF NOT EXISTS bets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        horse TEXT,
        track TEXT,
        odds TEXT,
        rating REAL,
        result TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """
)

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
# BET365 ODDS
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

                        clean_horse = (
                            horse_name
                            .lower()
                            .strip()
                        )

                        clean_name = (
                            name
                            .lower()
                            .strip()
                        )

                        if clean_horse == clean_name:

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
# TRAINER BONUS
# ==========================================

def trainer_bonus(text):

    try:

        for trainer in TOP_TRAINERS:

            if (
                trainer.lower()
                in text.lower()
            ):

                return 1.5

    except:
        pass

    return 0

# ==========================================
# AI PROBABILITY
# ==========================================

def calculate_ai_probability(rating):

    try:

        return min(
            0.90,
            rating / 10
        )

    except:

        return 0

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
# GET RACECARD
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

        rows = soup.find_all("tr")

        for row in rows:

            text = row.get_text(
                " ",
                strip=True
            )

            if len(text) < 20:
                continue

            claim_value = (
                parse_claiming_value(text)
            )

            horse_data = {
                "track": track_code,
                "horse": text[:50],
                "raw": text,
                "claim": claim_value
            }

            horses.append(horse_data)

        return horses

    except Exception as e:

        print(e)

        return []

# ==========================================
# DETECT CLASS DROPPERS
# ==========================================

def detect_class_droppers(entries):

    horses = []

    try:

        for item in entries:

            text = item["raw"]

            today_claim = item["claim"]

            if today_claim <= 0:
                continue

            previous_claim = (
                today_claim * 2
            )

            if previous_claim <= today_claim:
                continue

            drop_pct = (
                previous_claim - today_claim
            ) / previous_claim

            if drop_pct < 0.40:
                continue

            rating = round(
                (
                    drop_pct * 10
                )
                + trainer_bonus(text),
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
# DAILY SCAN
# ==========================================

def daily_scan():

    send_message(
        "🚨 DAILY CLASS DROPPER REPORT 🚨"
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

    if len(top) == 0:

        send_message(
            "No major class droppers found."
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
                "✅ VALUE BET"
            )

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
            f"{value_flag}"
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
    "✅ Horse betting bot is online."
)

print(
    "Telegram Betting Bot Running..."
)

# ==========================================
# STARTUP TEST SCAN
# ==========================================

daily_scan()

# ==========================================
# RUN EVERY MINUTE
# BETWEEN 13:00 AND 16:59
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

    if len(text) > 20:

    print(text)

    horses.append({
        "raw": text,
        "track": track_code
    })

        return horses

    except Exception as e:

        print(e)

        return []

# ==========================================
# PARSE CLAIMING VALUE
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

        today_claim = parse_claiming_value(text)

        if today_claim == 0:
            continue

        previous_claim = today_claim * 2

        drop_pct = (
            previous_claim - today_claim
        ) / previous_claim

        if drop_pct >= 0.40:

            rating = round(
                (drop_pct * 10)
                + trainer_bonus(text),
                1
            )

            horse_data = {
                "track": item["track"],
                "horse": text[:60],
                "today_claim": today_claim,
                "previous_claim": previous_claim,
                "rating": rating
            }

            horses.append(horse_data)

    return horses

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
# GET BET365 ODDS
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
# PARSE CLAIMING VALUE
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

        send_message(
            f"Scanning {track}"
        )

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
# TELEGRAM
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
# TWIN SPIRES SCRAPER
# ==========================================

def get_twinspires_data(track_code):

    try:

        today = datetime.now().strftime(
            "%Y-%m-%d"
        )

        url = (
            f"https://www.twinspires.com/"
        )

        headers = {
            "User-Agent": "Mozilla/5.0"
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=20
        )

        soup = BeautifulSoup(
            response.text,
            "html.parser"
        )

        page_text = soup.get_text(
            " ",
            strip=True
        )

        return page_text[:5000]

    except Exception as e:

        print(e)

        return ""

# ==========================================
# EQUibase RACECARDS
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

            if len(text) > 20:

                print(text)

                horses.append({
                    "raw": text,
                    "track": track_code
                })

        return horses

    except Exception as e:

        print(e)

        return []

# ==========================================
# CLAIM VALUE
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
# CLASS DROPPERS
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

                "horse": text[:60],

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

        send_message(
            f"🔍 Scanning {track}"
        )

        twinspires_data = get_twinspires_data(
            track
        )

        print(
            twinspires_data[:1000]
        )

        entries = get_racecard(track)

        send_message(
            f"{track} rows found: {len(entries)}"
        )

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
# GET BET365 ODDS
# ==========================================

def get_bet365_odds(horse_name):
