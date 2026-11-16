"""
Forwards new tweets from an X (Twitter) account to a Telegram channel,
posting just the text + image (no twitter.com/x.com link, so Telegram
won't generate a link-preview card).

Also writes each posted tweet to wa_queue.json so the phone bot can
forward it to a WhatsApp Channel.
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

TWITTER_HANDLES = ["BarcaTimes"]
TELEGRAM_TARGETS = ["@barcatimes1", "@fcbarcelonachatgroup"]
COOKIES_FILE = "cookies.json"
MAX_TWEETS_PER_RUN = 5

RECENT_POSTS_FILE = "recent_posts.json"
RECENT_POSTS_TO_KEEP = 40
DUPLICATE_SIMILARITY_THRESHOLD = 0.6

WA_QUEUE_FILE = "wa_queue.json"
WA_QUEUE_TO_KEEP = 30

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


# ---- Duplicate detection ---------------------------------------------------

def normalize_text(text):
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
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


# ---- WhatsApp queue --------------------------------------------------------

def load_wa_queue():
    if os.path.exists(WA_QUEUE_FILE):
        with open(WA_QUEUE_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return []
    return []


def save_wa_queue(queue):
    queue = queue[-WA_QUEUE_TO_KEEP:]
    with open(WA_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f)


def add_to_wa_queue(tweet_id, text, media_type, media_url):
    queue = load_wa_queue()
    queue.append({
        "id": str(tweet_id),
        "text": text,
        "media_type": media_type,
        "media_url": media_url,
    })
    save_wa_queue(queue)


# ---- Login -----------------------------------------------------------------

async def ensure_logged_in():
    if not os.path.exists(COOKIES_FILE):
        raise RuntimeError("No cookies.json found.")

    client.load_cookies(COOKIES_FILE)
    try:
        await client.user_id()
    except Exception as e:
        raise RuntimeError(
            "cookies.json exists but the session is invalid or expired. "
            "Log into the account again in your browser and re-export cookies."
        ) from e


# ---- Fetching tweets -------------------------------------------------------

def is_retweet(tweet):
    text = getattr(tweet, "full_text", None) or getattr(tweet, "text", "") or ""
    return bool(getattr(tweet, "retweeted_tweet", None)) or text.startswith("RT @")


async def fetch_latest_tweets(handle):
    user = await client.get_user_by_screen_name(handle)
    tweets = await client.get_user_tweets(user.id, "Tweets", count=MAX_TWEETS_PER_RUN + 5)
    tweets = [t for t in tweets if not is_retweet(t)]
    return tweets


def pick_video_url(media):
    streams = getattr(media, "streams", None) or []
    best_url = None
    best_bitrate = -1
    for s in streams:
        content_type = getattr(s, "content_type", "") or ""
        bitrate = getattr(s, "bitrate", 0) or 0
        if "mp4" in content_type and bitrate >= best_bitrate:
            best_url = getattr(s, "url", None)
            best_bitrate = bitrate
    return best_url


def pick_photo_url(media):
    return (
        getattr(media, "media_url", None)
        or getattr(media, "media_url_https", None)
        or getattr(media, "url", None)
        or getattr(media, "thumbnail_url", None)
    )


def extract_text_and_media(tweet):
    raw = getattr(tweet, "full_text", None) or getattr(tweet, "text", "") or ""
    text = html.unescape(raw)
    text = re.sub(r"\s*https://t\.co/\w+\s*$", "", text).strip()

    media_type = None
    media_url = None

    media_list = getattr(tweet, "media", None) or []
    if media_list:
        first = media_list[0]
        kind = (getattr(first, "type", None) or type(first).__name__).lower()
        if "video" in kind or "gif" in kind:
            media_type = "video"
            media_url = pick_video_url(first)
        else:
            media_type = "photo"
            media_url = pick_photo_url(first)

    return text, media_type, media_url


# ---- Sending to Telegram ---------------------------------------------------

def build_telegram_request(target, text, media_type, media_url):
    base = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    if media_type == "video" and media_url:
        return base + "/sendVideo", {
            "chat_id": target,
            "caption": text[:1024],
            "video": media_url,
        }
    if media_type == "photo" and media_url:
        return base + "/sendPhoto", {
            "chat_id": target,
            "caption": text[:1024],
            "photo": media_url,
        }
    return base + "/sendMessage", {
        "chat_id": target,
        "text": text[:4096],
    }


def send_one(target, text, media_type, media_url):
    api_url, payload = build_telegram_request(target, text, media_type, media_url)
    resp = requests.post(api_url, data=payload, timeout=20)
    resp.raise_for_status()


def send_to_telegram(text, media_type, media_url):
    any_success = False
    for target in TELEGRAM_TARGETS:
        try:
            send_one(target, text, media_type, media_url)
            any_success = True
        except requests.RequestException as e:
            print(f"WARNING: failed to send to {target}: {e}")
    return any_success


# ---- Main ------------------------------------------------------------------

async def main():
    await ensure_logged_in()
    recent_posts = load_recent_posts()

    try:
        for handle in TWITTER_HANDLES:
            print(f"--- Checking @{handle} ---")
            recent_posts = await check_account(handle, recent_posts)
    finally:
        save_recent_posts(recent_posts)
        save_wa_queue(load_wa_queue())


def handle_one_tweet(tweet, handle, recent_posts):
    text, media_type, media_url = extract_text_and_media(tweet)

    if is_duplicate_content(text, recent_posts):
        print(f"Skipped tweet {tweet.id} from @{handle} (duplicate of a recent post)")
        save_last_tweet_id(handle, tweet.id)
        return

    send_to_telegram(text, media_type, media_url)

    # Save progress IMMEDIATELY after sending, so a later crash
    # can never cause this tweet to be sent again.
    save_last_tweet_id(handle, tweet.id)

    add_to_wa_queue(tweet.id, text, media_type, media_url)
    recent_posts.append(normalize_text(text))
    save_recent_posts(recent_posts)
    print(f"Posted tweet {tweet.id} from @{handle}")


async def check_account(handle, recent_posts):
    last_id = get_last_tweet_id(handle)
    tweets = await fetch_latest_tweets(handle)

    if not tweets:
        print(f"No tweets found for @{handle}.")
        return recent_posts

    tweets.sort(key=lambda t: int(t.id))
    print("last_id:", last_id, "| fetched:", [t.id for t in tweets])

    if last_id is None:
        save_last_tweet_id(handle, tweets[-1].id)
        print(f"Initialized @{handle}. No messages sent.")
        return recent_posts

    new_tweets = [t for t in tweets if int(t.id) > int(last_id)]
    new_tweets = new_tweets[-MAX_TWEETS_PER_RUN:]

    if not new_tweets:
        print(f"No new tweets for @{handle}.")
        return recent_posts

    for tweet in new_tweets:
        try:
            handle_one_tweet(tweet, handle, recent_posts)
        except Exception as e:
            print(f"ERROR on tweet {tweet.id} from @{handle}: {e}")
            save_last_tweet_id(handle, tweet.id)

    return recent_posts


if __name__ == "__main__":
    asyncio.run(main())
