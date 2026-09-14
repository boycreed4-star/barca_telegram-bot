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
import difflib
import html
import json
import os
import re

import requests
from twikit import Client

# ---- Configuration -------------------------------------------------------

TWITTER_HANDLES = ["BarcaTimes", "BarcaUniversal"]  # no @, add more here later
TELEGRAM_TARGETS = ["@footbal_2325", "@fcbarcelonachatgroup"]  # channel + group
COOKIES_FILE = "cookies.json"
MAX_TWEETS_PER_RUN = 5                 # safety cap so a big backlog can't spam the channel

RECENT_POSTS_FILE = "recent_posts.json"
RECENT_POSTS_TO_KEEP = 40       # how many past posts to compare new ones against
DUPLICATE_SIMILARITY_THRESHOLD = 0.6  # 0-1, higher = stricter match required

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

client = Client("en-US")

# ---- State (avoids re-posting the same tweet) -----------------------------


def state_file_for(handle):
    return f"last_tweet_id_{handle}.txt"


def get_last_tweet_id(handle):
    path = state_file_for(handle)
    if os.path.exists(path):
        with open(path, "r") as f:
            content = f.read().strip()
            return content or None
    return None


def save_last_tweet_id(handle, tweet_id):
    with open(state_file_for(handle), "w") as f:
        f.write(str(tweet_id))


# ---- Cross-account duplicate detection -------------------------------------


def normalize_text(text):
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)  # strip punctuation
    text = re.sub(r"\s+", " ", text).strip()
    return text


def load_recent_posts():
    if os.path.exists(RECENT_POSTS_FILE):
        with open(RECENT_POSTS_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def save_recent_posts(posts):
    posts = posts[-RECENT_POSTS_TO_KEEP:]
    with open(RECENT_POSTS_FILE, "w", encoding="utf-8") as f:
        json.dump(posts, f)


def is_duplicate_content(text, recent_posts):
    if not text:
        return False
    normalized = normalize_text(text)
    for prior in recent_posts:
        ratio = difflib.SequenceMatcher(None, normalized, prior).ratio()
        if ratio >= DUPLICATE_SIMILARITY_THRESHOLD:
            return True
    return False


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


def extract_text_and_media(tweet):
    text = html.unescape(getattr(tweet, "full_text", None) or getattr(tweet, "text", "") or "")

    # Twitter appends a t.co link at the end of the text when there's media
    # attached -- strip it since we're sending the media separately.
    text = re.sub(r"\s*https://t\.co/\w+\s*$", "", text).strip()

    media_type = None
    media_url = None

    media_list = getattr(tweet, "media", None) or []
    if media_list:
        first = media_list[0]
        kind = (getattr(first, "type", None) or type(first).__name__).lower()

        if "video" in kind or "gif" in kind:
            media_type = "video"
            streams = getattr(first, "streams", None) or []
            best = None
            best_bitrate = -1
            for s in streams:
                content_type = getattr(s, "content_type", "") or ""
                bitrate = getattr(s, "bitrate", 0) or 0
                if "mp4" in content_type and bitrate >= best_bitrate:
                    best = s
                    best_bitrate = bitrate
            if best is not None:
                media_url = getattr(best, "url", None)
        else:
            media_type = "photo"
            media_url = (
                getattr(first, "media_url", None)
                or getattr(first, "media_url_https", None)
                or getattr(first, "url", None)
                or getattr(first, "thumbnail_url", None)
            )

    return text, media_type, media_url


# ---- Sending to Telegram ----------------------------------------------------


def send_to_telegram(text, media_type, media_url):
    any_success = False
    for target in TELEGRAM_TARGETS:
        try:
            if media_type == "video" and media_url:
                api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
                payload = {
                    "chat_id": target,
                    "caption": text[:1024],
                    "video": media_url,
                }
            elif media_type == "photo" and media_url:
                api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                payload = {
                    "chat_id": target,
                    "caption": text[:1024],
                    "photo": media_url,
                }
            else:
                api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                payload = {
                    "chat_id": target,
                    "text": text[:4096],
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
    recent_posts = load_recent_posts()

    for handle in TWITTER_HANDLES:
        print(f"--- Checking @{handle} ---")
        recent_posts = await check_account(handle, recent_posts)

    save_recent_posts(recent_posts)


async def check_account(handle, recent_posts):
    last_id = get_last_tweet_id(handle)
    tweets = await fetch_latest_tweets(handle)

    if not tweets:
        print(f"No tweets found for @{handle}.")
        return recent_posts

    tweets.sort(key=lambda t: int(t.id))

    if last_id is None:
        # First ever run for this account: don't spam the channel with the
        # whole recent history, just remember the newest tweet.
        save_last_tweet_id(handle, tweets[-1].id)
        print(f"Initialized @{handle}. Latest tweet id: {tweets[-1].id}. No messages sent.")
        return recent_posts

    new_tweets = [t for t in tweets if int(t.id) > int(last_id)]
    new_tweets = new_tweets[-MAX_TWEETS_PER_RUN:]

    if not new_tweets:
        print(f"No new tweets for @{handle}.")
        return recent_posts

    for tweet in new_tweets:
        text, media_type, media_url = extract_text_and_media(tweet)

        if is_duplicate_content(text, recent_posts):
            print(f"Skipped tweet {tweet.id} from @{handle} (duplicate of a recent post)")
        else:
            send_to_telegram(text, media_type, media_url)
            recent_posts.append(normalize_text(text))
            print(f"Posted tweet {tweet.id} from @{handle}")

        save_last_tweet_id(handle, tweet.id)

    return recent_posts


if __name__ == "__main__":
    asyncio.run(main())
