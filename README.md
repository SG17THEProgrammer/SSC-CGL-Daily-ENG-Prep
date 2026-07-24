# Competitive Exam English AI Coach

A Telegram bot that sends competitive exam level English MCQs twice a day, tracks
your accuracy per topic, adapts how many questions each topic gets based on
your weak spots, and re-tests wrong answers on a spaced-repetition schedule.
Runs entirely on GitHub Actions -- ₹0/month, nothing to host or keep running
on your own machine.

## How it works

- **`database.db`** is a plain SQLite file committed to this repo. GitHub
  Actions checks it out, updates it, and pushes it back after every run.
  That's what makes progress persist for free, without any external database
  service.
- **Morning quiz** (8:00 AM IST): synonyms, antonyms, vocabulary, one-word
  substitution.
- **Evening quiz** (4:00 PM IST): idioms, spelling, homonyms, pronunciation.
- **Answer collector** runs every ~50 minutes to fetch your poll answers from
  Telegram (this can't happen instantly since nothing runs continuously) and
  record them.
- **Weekly summary** every Sunday: overall + per-topic accuracy, strongest /
  weakest topic, sent as a Telegram message.
- New questions are generated via the Groq API (free tier) and checked
  against everything already in the database to avoid duplicates.

## One-time setup

### 1. Create your Telegram bot
1. Message **@BotFather** on Telegram -> `/newbot` -> follow the prompts.
2. Save the bot token it gives you.
3. Send your new bot any message, then visit
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser and
   find `"chat":{"id": ...}` in the response -- that number is your chat ID.

### 2. Get a free Groq API key
1. Sign up at https://console.groq.com
2. Create an API key.
3. Check https://console.groq.com/docs/models for the current free model
   list -- `config.py` defaults to `llama-3.3-70b-versatile`, but update the
   `GROQ_MODEL` secret/env var if that model is renamed or retired.

### 3. Push this repo to GitHub (public, as you specified)

### 4. Add GitHub Actions secrets
Repo -> Settings -> Secrets and variables -> Actions -> New repository secret:
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `GROQ_API_KEY`

Since the repo is public, these secrets are still safe -- GitHub Secrets are
encrypted and never exposed in logs or to forks by default.

### 5. Enable Actions and test manually
Go to the **Actions** tab, select each workflow, and click **Run workflow**
to trigger it manually the first time (don't wait for the cron schedule):
- `Morning Quiz` and `Evening Quiz` -- should send you Telegram quiz polls.
- Answer one in Telegram, then manually run `Collect Quiz Answers` -- check
  the Action logs to confirm it recorded your response.
- `Weekly Summary` -- should message you a stats summary (will say "no
  questions answered" until you've built up history).

Once confirmed, the cron schedules take over automatically.

## Local development (optional)

You don't need to run anything locally, but if you want to test changes
before pushing:

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=xxx
export TELEGRAM_CHAT_ID=xxx
export GROQ_API_KEY=xxx
python send_quiz.py morning
python collect_answers.py
python weekly_summary.py
```

## Adding a new topic later

1. Add a new prompt file in `prompts/<topic_name>.txt` describing the
   question style you want.
2. Add `"<topic_name>"` to `MORNING_TOPICS` or `EVENING_TOPICS` in
   `config.py`.

No other code changes needed -- `send_quiz.py` loops over whatever topics
are configured.

## Notes on the ₹0/month design

- **No external database** -- SQLite file lives in the repo itself.
- **No paid hosting** -- everything runs on GitHub Actions' free minutes
  (public repos get unlimited free minutes; this job's runtime is seconds).
- **Groq free tier** for question generation -- watch for rate limits if you
  later add more topics/questions per day.
- One tradeoff to know about: committing `database.db` on every run means
  the git history grows slowly over time (a new binary blob per commit). For
  this usage pattern (a few runs/day, small DB) that's a non-issue for a long
  time. If it ever becomes annoying, the fix is periodically running
  `git gc`/history squashing, or switching to a `.sql` text dump instead of
  a binary commit -- not something you need to think about on day one.

## Word repetition -- how it's actually prevented

Every focus word ever sent is permanently registered in a `used_words` table
with a **database-level UNIQUE constraint**. This isn't a "please don't
repeat" instruction the LLM can ignore -- if it tries to reuse a word
(regardless of casing), the database insert itself fails, and the system
automatically retries with a different, randomly-nudged starting letter
until it finds something fresh. This check is against your **entire
history**, not a recent window, so words don't quietly become "fair game"
again after a few days.
