"""
Forwards new tweets from an X (Twitter) account to a Telegram channel,
posting just the text + image (no twitter.com/x.com link, so Telegram
won't generate a link-preview card).

Uses twikit, which logs into a real X account to fetch tweets (the
free "no login" syndication endpoint for profile timelines has been
discontinued by X as of late 2026).

Requires these environment variables to be set on this machine:
    TWITTER_USERNAME  - the bot account's @handle (no @)
    TWITTER_EMAIL      - the bot account's email
    TWITTER_PASSWORD   - the bot account's password
    TELEGRAM_BOT_TOKEN - your Telegram bot's token from BotFather

Safety notes (to avoid the bot account getting flagged):
    - Cookies are cached to cookies.json so it logs in fresh only once,
      not on every run.
    - Don't drop the polling interval below ~10 minutes.
"""

import asyncio
import html
import os
import re

import requests
from twikit import Client

# ---- Configuration -------------------------------------------------------

TWITTER_HANDLE = "BarcaTimes"          # no @
TELEGRAM_TARGETS = ["@footbal_2325", "@fcbarcelonachatgroup"]  # channel + group
STATE_FILE = "last_tweet_id.txt"
COOKIES_FILE = "cookies.json"
MAX_TWEETS_PER_RUN = 5                 # safety cap so a big backlog can't spam the channel

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

client = Client("en-US")

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


# ---- Login (reuses cached cookies when possible) ---------------------------


async def ensure_logged_in():
    # X retired the old username/password login flow (now requires
    # JS-obfuscated tokens and supports passkeys, which a plain script
    # can't drive). Authentication now works only via cookies exported
    # from a real logged-in browser session -- see cookies.json setup.
    if not os.path.exists(COOKIES_FILE):
        raise RuntimeError(
            f"No {COOKIES_FILE} found. Log into the bot's X account in your "
            "browser, export its cookies, convert them with convert_cookies.py, "
            f"and place the result at {COOKIES_FILE} in this folder."
        )

    client.load_cookies(COOKIES_FILE)
    try:
        await client.user_id()  # cheap call to confirm the session is valid
    except Exception as e:
        raise RuntimeError(
            f"{COOKIES_FILE} exists but the session is invalid or expired. "
            "Log into the account again in your browser and re-export cookies."
        ) from e


# ---- Fetching tweets -------------------------------------------------------


async def fetch_latest_tweets(handle):
    user = await client.get_user_by_screen_name(handle)
    tweets = await client.get_user_tweets(user.id, "Tweets", count=MAX_TWEETS_PER_RUN + 5)
    tweets = [t for t in tweets if not is_retweet(t)]
    return tweets


def is_retweet(tweet):
    text = getattr(tweet, "full_text", None) or getattr(tweet, "text", "") or ""
    return bool(getattr(tweet, "retweeted_tweet", None)) or text.startswith("RT @")


def extract_text_and_image(tweet):
    text = html.unescape(getattr(tweet, "full_text", None) or getattr(tweet, "text", "") or "")

    # Twitter appends a t.co link at the end of the text when there's media
    # attached -- strip it since we're sending the image separately.
    text = re.sub(r"\s*https://t\.co/\w+\s*$", "", text).strip()

    image_url = None
    media_list = getattr(tweet, "media", None) or []
    if media_list:
        first = media_list[0]
        # Different twikit media types expose the URL under slightly
        # different attribute names -- try the common ones.
        image_url = (
            getattr(first, "media_url", None)
            or getattr(first, "media_url_https", None)
            or getattr(first, "url", None)
            or getattr(first, "thumbnail_url", None)
        )

    return text, image_url


# ---- Sending to Telegram ----------------------------------------------------


def send_to_telegram(text, image_url):
    any_success = False
    for target in TELEGRAM_TARGETS:
        try:
            if image_url:
                api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                payload = {
                    "chat_id": target,
                    "caption": text[:1024],  # Telegram caption limit
                    "photo": image_url,
                }
            else:
                api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": target,
                    "text": text[:4096],  # Telegram message limit
                }

            resp = requests.post(api_url, data=payload, timeout=20)
            resp.raise_for_status()
            any_success = True
        except requests.RequestException as e:
            # Don't let one broken destination (e.g. bot not yet added to a
            # group) block sending to the others, or block saving progress.
            print(f"WARNING: failed to send to {target}: {e}")

    return any_success


# ---- Main -------------------------------------------------------------------


async def main():
    await ensure_logged_in()

    last_id = get_last_tweet_id()
    tweets = await fetch_latest_tweets(TWITTER_HANDLE)

    if not tweets:
        print("No tweets found.")
        return

    tweets.sort(key=lambda t: int(t.id))

    if last_id is None:
        # First ever run: don't spam the channel with the whole recent
        # history, just remember the newest tweet and start from there.
        save_last_tweet_id(tweets[-1].id)
        print(f"Initialized. Latest tweet id: {tweets[-1].id}. No messages sent.")
        return

    new_tweets = [t for t in tweets if int(t.id) > int(last_id)]
    new_tweets = new_tweets[-MAX_TWEETS_PER_RUN:]

    if not new_tweets:
        print("No new tweets.")
        return

    for tweet in new_tweets:
        text, image_url = extract_text_and_image(tweet)
        send_to_telegram(text, image_url)
        save_last_tweet_id(tweet.id)
        print(f"Posted tweet {tweet.id}")


if __name__ == "__main__":
    asyncio.run(main())
