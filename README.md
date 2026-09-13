# @BarcaTimes → Telegram forwarder

Forwards new tweets from **@BarcaTimes** to the Telegram channel
**@footbal_2325** as plain text + image, with no visible X/Twitter link
(so no link-preview card gets generated).

## How it works

- Runs on a schedule via **GitHub Actions** (free, no server needed).
- Every 10 minutes it checks X's public "syndication" endpoint for the
  latest tweets from the account (no official X API / developer key needed).
- Any tweet newer than the last one it posted gets sent to the Telegram
  channel via your bot.
- It remembers the last tweet it posted in `last_tweet_id.txt`, committed
  back to the repo, so it never double-posts.

⚠️ The syndication endpoint is **unofficial** (X could change or block it
without notice). If posts suddenly stop, that's the first thing to check —
message me and I can help patch it.

## Setup (one-time)

1. **Create a GitHub repo** and upload these files (keep the folder
   structure, especially `.github/workflows/forward.yml`).

2. **Add your bot token as a secret** (never put it directly in the code):
   - Go to your repo → **Settings** → **Secrets and variables** → **Actions**
   - Click **New repository secret**
   - Name: `TELEGRAM_BOT_TOKEN`
   - Value: the token @BotFather gave you for `@barcatime1_bot`

3. **Make sure your bot is an admin** of `@footbal_2325` with "Post
   Messages" permission (you've already done this ✅).

4. **Enable Actions** on the repo if prompted (Settings → Actions →
   allow workflows to run), and make sure the workflow has permission to
   push commits (Settings → Actions → General → Workflow permissions →
   "Read and write permissions").

5. **First run:** go to the **Actions** tab → select "Forward tweets to
   Telegram" → **Run workflow** to trigger it manually once. The first run
   just records the current latest tweet as the starting point and won't
   post anything (this avoids dumping the whole recent history into your
   channel). From then on, it checks every 10 minutes and posts anything new.

## Adjusting things later

- **Different account:** change `TWITTER_HANDLE` in `check_tweets.py`.
- **Different channel:** change `TELEGRAM_CHANNEL` in `check_tweets.py`.
- **Check more/less often:** edit the cron schedule in
  `.github/workflows/forward.yml` (`*/10 * * * *` = every 10 minutes).
- **Post more tweets per run if there's a backlog:** raise
  `MAX_TWEETS_PER_RUN` in `check_tweets.py`.
