import os
import requests
import schedule
import time
import re

from bs4 import BeautifulSoup
from datetime import datetime

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

                        if horse_name.lower() in name.lower():

                            return outcome.get(
                                "price",
                                "N/A"
                            )

        return "N/A"

    except Exception as e:

        print(e)

        return "N/A"


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


def parse_claiming_value(text):

    matches = re.findall(
        r'\$(\d+[,\d]*)',
        text
    )

    if not matches:
        return 0

    value = matches[0].replace(",", "")

    try:
        return int(value)

    except:
        return 0


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

            horses.append({

                "track": item["track"],

                "horse": text[:50],

                "today_claim": today_claim,

                "previous_claim": previous_claim,

                "rating": round(
                    drop_pct * 10,
                    1
                )
            })

    return horses


def daily_scan():

    send_message(
        "🚨 LIVE DAILY CLASS DROPPER REPORT 🚨"
    )

    all_horses = []

    for track in TRACKS:

        entries = get_racecard(track)

        droppers = detect_class_droppers(entries)

        all_horses.extend(droppers)

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

        msg = f"""
🏇 {horse['track']}

{horse['horse']}

Claim Drop:
${horse['previous_claim']:,} → ${horse['today_claim']:,}

Bet365 Odds:
{odds}

AI Rating:
{horse['rating']}/10
"""

        send_message(msg)


send_message(
    "✅ Horse betting bot is online."
)

schedule.every().day.at(
    "13:00"
).do(daily_scan)

print("Telegram Betting Bot Running...")


while True:

    schedule.run_pending()

    time.sleep(30)
