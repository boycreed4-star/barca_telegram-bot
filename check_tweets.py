"""
Forwards new tweets from an X (Twitter) account to a Telegram channel,
posting just the text + image (no twitter.com/x.com link, so Telegram
won't generate a link-preview card).

Uses X's public "syndication" endpoint (the same one X uses to render
embedded tweets on other websites). This is unofficial and undocumented,
so it can change or break without notice -- if that happens, this is the
first place to look.
"""

import html
import json
import os
import re

import requests

# ---- Configuration -------------------------------------------------------

TWITTER_HANDLE = "BarcaTimes"          # no @
TELEGRAM_CHANNEL = "@footbal_2325"     # public channel username
STATE_FILE = "last_tweet_id.txt"
MAX_TWEETS_PER_RUN = 5                 # safety cap so a big backlog can't spam the channel

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# ---- State (avoids re-posting the same tweet) -----------------------------


def get_last_tweet_id():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            content = f.read().strip()
            return content or None
    return None


def save_last_tweet_id(tweet_id):
    with open(STATE_FILE, "w") as f:
        f.write(str(tweet_id))


# ---- Fetching tweets -------------------------------------------------------


def fetch_latest_tweets(handle):
    """Fetch the latest tweets from a public profile via X's syndication endpoint."""
    url = f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{handle}"
    params = {"showReplies": "false"}
    resp = requests.get(url, params=params, headers=HEADERS, timeout=20)
    resp.raise_for_status()

    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        resp.text,
        re.DOTALL,
    )
    if not match:
        raise RuntimeError(
            "Could not find tweet data in the page. X may have changed the "
            "syndication endpoint's format."
        )

    data = json.loads(match.group(1))
    timeline = (
        data.get("props", {})
        .get("pageProps", {})
        .get("timeline", {})
        .get("entries", [])
    )

    tweets = []
    for entry in timeline:
        tweet = entry.get("content", {}).get("tweet")
        if tweet:
            tweets.append(tweet)
    return tweets


def extract_text_and_image(tweet):
    text = html.unescape(tweet.get("text") or tweet.get("full_text") or "")

    # Twitter appends a t.co link at the end of the text when there's media
    # attached -- strip it since we're sending the image separately.
    text = re.sub(r"\s*https://t\.co/\w+\s*$", "", text).strip()

    image_url = None
    media_details = tweet.get("mediaDetails") or []
    if media_details:
        image_url = media_details[0].get("media_url_https")

    return text, image_url


# ---- Sending to Telegram ----------------------------------------------------


def send_to_telegram(text, image_url):
    if image_url:
        api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": TELEGRAM_CHANNEL,
            "caption": text[:1024],  # Telegram caption limit
            "photo": image_url,
        }
    else:
        api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHANNEL,
            "text": text[:4096],  # Telegram message limit
        }

    resp = requests.post(api_url, data=payload, timeout=20)
    resp.raise_for_status()


# ---- Main -------------------------------------------------------------------


def main():
    last_id = get_last_tweet_id()
    tweets = fetch_latest_tweets(TWITTER_HANDLE)

    if not tweets:
        print("No tweets found.")
        return

    tweets.sort(key=lambda t: int(t["id_str"]))

    if last_id is None:
        # First ever run: don't spam the channel with the whole recent
        # history, just remember the newest tweet and start from there.
        save_last_tweet_id(tweets[-1]["id_str"])
        print(f"Initialized. Latest tweet id: {tweets[-1]['id_str']}. No messages sent.")
        return

    new_tweets = [t for t in tweets if int(t["id_str"]) > int(last_id)]
    new_tweets = new_tweets[-MAX_TWEETS_PER_RUN:]

    if not new_tweets:
        print("No new tweets.")
        return

    for tweet in new_tweets:
        text, image_url = extract_text_and_image(tweet)
        send_to_telegram(text, image_url)
        save_last_tweet_id(tweet["id_str"])
        print(f"Posted tweet {tweet['id_str']}")


if __name__ == "__main__":
    main()
