"""
Posts a daily Barca trivia question to the channel as a native Telegram
quiz poll (shows the correct answer automatically once people vote).

Runs once a day via GitHub's own schedule (daily schedules are reliable --
the earlier issues were specific to very frequent schedules like every
few minutes).

Requires:
    TELEGRAM_BOT_TOKEN - your bot's token from BotFather
"""

import json
import os

import requests

# ---- Configuration -------------------------------------------------------

TARGET_CHANNEL = "@barcatimes1"
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
STATE_FILE = "quiz_state.json"

QUESTIONS = [
    {
        "question": "In what year was FC Barcelona founded?",
        "options": ["1899", "1902", "1910", "1925"],
        "correct": 0,
        "explanation": "Barca was founded on 29 November 1899 by Joan Gamper.",
    },
    {
        "question": "What is Barca's home stadium called?",
        "options": ["Santiago Bernabeu", "Camp Nou", "Wanda Metropolitano", "San Siro"],
        "correct": 1,
        "explanation": "Camp Nou has been Barca's home since 1957.",
    },
    {
        "question": "Which player has scored the most goals in Barca's history?",
        "options": ["Ronaldinho", "Messi", "Luis Suarez", "Cesar Rodriguez"],
        "correct": 1,
        "explanation": "Lionel Messi scored over 670 goals for Barca across all competitions.",
    },
    {
        "question": "What does 'Mes que un club' mean, Barca's famous motto?",
        "options": ["The best club", "More than a club", "Always united", "For the fans"],
        "correct": 1,
        "explanation": "It translates to 'More than a club', reflecting Barca's cultural significance.",
    },
    {
        "question": "Which academy is Barca's famous youth system known as?",
        "options": ["La Fabrica", "La Masia", "La Cantera", "El Vivero"],
        "correct": 1,
        "explanation": "La Masia has produced stars like Messi, Xavi, Iniesta, and many more.",
    },
    {
        "question": "How many Champions League titles has Barca won (as of recent years)?",
        "options": ["3", "5", "7", "9"],
        "correct": 1,
        "explanation": "Barca has won the Champions League/European Cup 5 times.",
    },
    {
        "question": "Who is Barca's fiercest domestic rival, in the fixture known as El Clasico?",
        "options": ["Atletico Madrid", "Sevilla", "Real Madrid", "Valencia"],
        "correct": 2,
        "explanation": "El Clasico refers to the Barca vs Real Madrid rivalry.",
    },
    {
        "question": "Which country is FC Barcelona based in?",
        "options": ["Portugal", "Spain", "Italy", "France"],
        "correct": 1,
        "explanation": "Barca is based in Barcelona, in the Catalonia region of Spain.",
    },
    {
        "question": "What color are Barca's iconic home shirt stripes?",
        "options": ["Red and yellow", "Blue and garnet (blaugrana)", "Green and white", "Black and white"],
        "correct": 1,
        "explanation": "Barca's colors are famously known as 'blaugrana' (blue and garnet).",
    },
    {
        "question": "Which Dutch manager led Barca's famous 'Dream Team' in the early 1990s?",
        "options": ["Louis van Gaal", "Johan Cruyff", "Frank Rijkaard", "Ronald Koeman"],
        "correct": 1,
        "explanation": "Johan Cruyff managed Barca's Dream Team, winning the club's first European Cup in 1992.",
    },
]


# ---- State ------------------------------------------------------------------


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def pick_next_question(state):
    used = state.get("used_indices", [])
    remaining = [i for i in range(len(QUESTIONS)) if i not in used]

    if not remaining:
        used = []  # exhausted the bank -- start over
        remaining = list(range(len(QUESTIONS)))

    next_index = remaining[0]
    used.append(next_index)
    state["used_indices"] = used
    return QUESTIONS[next_index], state


# ---- Telegram -----------------------------------------------------------------


def send_quiz(question_data):
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPoll",
        data={
            "chat_id": TARGET_CHANNEL,
            "question": f"⚽ Barca Trivia: {question_data['question']}",
            "options": json.dumps(question_data["options"]),
            "type": "quiz",
            "correct_option_id": question_data["correct"],
            "explanation": question_data["explanation"],
            "is_anonymous": True,  # required for channel polls
        },
        timeout=20,
    )
    resp.raise_for_status()


# ---- Main -------------------------------------------------------------------


def main():
    state = load_state()
    question_data, state = pick_next_question(state)
    send_quiz(question_data)
    save_state(state)
    print(f"Posted quiz: {question_data['question']}")


if __name__ == "__main__":
    main()
