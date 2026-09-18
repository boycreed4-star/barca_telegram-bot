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
        "question": "Along with Barca, which two Spanish clubs have never been relegated from La Liga?",
        "options": ["Real Madrid & Athletic Bilbao", "Sevilla & Valencia", "Atletico Madrid & Espanyol", "Villarreal & Real Betis"],
        "correct": 0,
        "explanation": "Barca, Real Madrid, and Athletic Bilbao are the only three clubs never relegated from La Liga.",
    },
    {
        "question": "What does the nickname for Barca fans, 'cules', originally refer to?",
        "options": ["A local Catalan dance", "Fans' backsides visible from outside the old stadium wall", "The street where the club was founded", "Their traditional chant"],
        "correct": 1,
        "explanation": "At the old Camp de la Industria stadium, fans sat on a wall with their backsides ('cul' in Catalan) visible to people outside.",
    },
    {
        "question": "Which player holds the record for most official appearances for Barca, with 767?",
        "options": ["Lionel Messi", "Xavi Hernandez", "Andres Iniesta", "Carles Puyol"],
        "correct": 1,
        "explanation": "Xavi made 767 official appearances for Barca between 1998 and 2015.",
    },
    {
        "question": "Who was the first FC Barcelona player to win the Ballon d'Or, in 1960?",
        "options": ["Johan Cruyff", "Luis Suarez Miro", "Lionel Messi", "Ladislao Kubala"],
        "correct": 1,
        "explanation": "Luis Suarez Miro (a Spanish midfielder, not the Uruguayan striker of the same name) won it in 1960.",
    },
    {
        "question": "Founder Joan Gamper was forced to resign as club president in 1925 after fans did what during a match?",
        "options": ["Boycotted the match", "Jeered the Spanish Royal March", "Threw objects at the referee", "Invaded the pitch"],
        "correct": 1,
        "explanation": "Fans jeered the Royal March in protest against Primo de Rivera's dictatorship, leading to the stadium's closure and Gamper's forced resignation.",
    },
    {
        "question": "In which match did Messi become the first player to score 5 goals in a single Champions League game (2012)?",
        "options": ["vs Real Madrid", "vs Bayer Leverkusen", "vs Arsenal", "vs Bayern Munich"],
        "correct": 1,
        "explanation": "Messi scored 5 times in a 7-1 win over Bayer Leverkusen on 7 March 2012.",
    },
    {
        "question": "Which goalkeeper holds Barca's record for most consecutive minutes without conceding a goal (896 minutes, 2011-12 season)?",
        "options": ["Marc-Andre ter Stegen", "Claudio Bravo", "Victor Valdes", "Antoni Ramallets"],
        "correct": 2,
        "explanation": "Victor Valdes went 896 minutes without conceding across all competitions in the 2011-12 season.",
    },
    {
        "question": "When Johan Cruyff joined Barca from Ajax in 1973, his transfer fee set a world record. Roughly how much was it?",
        "options": ["$500,000", "$1.2 million", "$5 million", "$10 million"],
        "correct": 1,
        "explanation": "Cruyff's transfer was around $1.2 million, a world record fee at the time.",
    },
    {
        "question": "Under Franco's dictatorship, the club's name was changed in 1939 to remove Catalan influence. What was it renamed to?",
        "options": ["Real Club Barcelona", "Club de Futbol Barcelona", "Sociedad Deportiva Barcelona", "Club Atletico Barcelona"],
        "correct": 1,
        "explanation": "The Catalan 'Futbol Club Barcelona' was reordered to the Spanish 'Club de Futbol Barcelona', and the Catalan flag was removed from the crest.",
    },
    {
        "question": "Which academy is Barca's famous youth system known as?",
        "options": ["La Fabrica", "La Masia", "La Cantera", "El Vivero"],
        "correct": 1,
        "explanation": "La Masia has produced stars like Messi, Xavi, Iniesta, and many more.",
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
