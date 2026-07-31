# VisaWatch

VisaWatch watches public Reddit discussions where other applicants report that US
visa appointment slots have opened, and pushes an alert to your phone within
seconds. You then log in yourself and try to book.

**What VisaWatch does not do, ever.** It never contacts usvisascheduling.com or
ustraveldocs.com. It never asks for or stores your username, password, security
answers, passport number or DS-160 number — there is nowhere in this project for
that information to go. It never tries to book, hold or reschedule anything. It
reads five public pages that anyone can open in a browser without logging in, and
it backs off politely when a site says slow down. The alert contains a plain link
to the booking site; clicking it opens the normal login page, exactly as if you
had typed the address yourself.

---

## Part 1 — Get notifications on your phone (5 minutes)

VisaWatch sends alerts through **ntfy** (say "notify"). It's a free app with no
account, no email and no password. You invent a secret word, subscribe to it in
the app, and anything sent to that word appears as a notification.

1. Install **ntfy** on your phone:
   [iPhone](https://apps.apple.com/us/app/ntfy/id1625396347) ·
   [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
2. Open it and tap the **+** button.
3. In "Topic name", type a secret word that nobody would guess. Mix in random
   letters and numbers, for example `visawatch-kx7q2m-slots`.
   **Write this word down.** You'll paste it in Part 2.
   > Anyone who knows this exact word could send you a notification. That is the
   > only reason it needs to be hard to guess. It contains no personal data.
4. Tap **Subscribe**.
5. Still in the app, open your new topic → the **⋮** menu → **Settings**, and turn
   on the option to **allow this topic to override Do Not Disturb** (Android calls
   it "Ignore Do Not Disturb"; on iPhone, go to your phone's
   Settings → Notifications → ntfy → **Time Sensitive Notifications: on**).
   This is what lets a slot alert reach you at 3 AM.

---

## Part 2 — Put VisaWatch online (15 minutes)

VisaWatch runs on **GitHub Actions**. See "Why GitHub Actions" at the bottom for
the reasoning and one important limitation.

### Step 1 — Make a GitHub account

Go to [github.com/signup](https://github.com/signup) and create a free account if
you don't have one. Nothing here costs money.

### Step 2 — Create an empty repository

1. Go to [github.com/new](https://github.com/new).
2. **Repository name:** `visawatch`
3. Select **Public**.
   > This feels wrong, so here's why. GitHub gives public repositories unlimited
   > free automation minutes, but private ones only 2,000 minutes a month.
   > Running every 5 minutes uses roughly 9,000 minutes a month, so on a private
   > repo VisaWatch would stop working about a week into every month — silently.
   > Nothing private goes in this repository: your secret ntfy word is stored
   > separately as a GitHub "secret" (Step 4), which is never visible to anyone
   > else even on a public repo, and VisaWatch holds no personal data of yours by
   > design. What people could see is the keyword list and the code.
4. Tick **Add a README file**.
5. Click **Create repository**.

### Step 3 — Upload the VisaWatch files

1. On your new repository page, click **Add file** → **Upload files**.
2. Drag the entire contents of the `visawatch` folder you were given into the
   upload box — every file and folder, including the one called `.github`.
   > If your computer hides the `.github` folder: on Mac press
   > `Cmd + Shift + .` in Finder to show hidden folders; on Windows, in File
   > Explorer go to View → Show → Hidden items.
3. Scroll down and click **Commit changes**.
4. You should now see `config.ini`, `README.md`, a `visawatch` folder, a `tests`
   folder and a `.github` folder listed.

### Step 4 — Tell VisaWatch your secret ntfy word

1. In your repository, click **Settings** (the tab along the top).
2. In the left sidebar: **Secrets and variables** → **Actions**.
3. Click the green **New repository secret**.
4. **Name:** `NTFY_TOPIC` — typed exactly like that, capitals and underscore.
5. **Secret:** the secret word you invented in Part 1 (just the word, not a web
   address).
6. Click **Add secret**.

### Step 5 — Turn the schedule on

1. Click the **Actions** tab.
2. If you see a green button saying *"I understand my workflows, go ahead and
   enable them"*, click it.
3. You should now see four workflows in the left sidebar: **VisaWatch poll**,
   **VisaWatch daily digest**, **Send test alert** and **Tests**.

### Step 6 — Send yourself a test alert

1. **Actions** tab → click **Send test alert** in the left sidebar.
2. Click **Run workflow** (grey button on the right) → **Run workflow** again.
3. Wait about 30 seconds and refresh. A notification should arrive on your phone
   saying "VisaWatch test alert".

**If nothing arrives:** click into the run and read the red step. The two usual
causes are a typo in the secret name (it must be exactly `NTFY_TOPIC`) or a
mismatch between the word in the GitHub secret and the topic in the ntfy app.

### Step 7 — Check that polling works

**Actions** → **VisaWatch poll** → **Run workflow**. Click into the run and open
the "Poll public feeds" step. You should see a line like
`Polled 4 feeds: 96 items, 96 new, 0 urgent, 0 queued.`

The very first run says *"First run: learned the existing items quietly."* That is
deliberate — the feeds hand over about a hundred older posts at once, and alerting
on all of them would just be noise about slots that are already gone. Real
alerting starts from the second cycle, five minutes later.

After that, `0 urgent` is the normal result for most cycles. It only fires when
someone actually reports slots within the last 15 minutes.

That's it. VisaWatch now checks every 5 minutes on its own, and sends a digest at
9:00 AM India time.

---

## Part 3 — Changing keywords later

Everything you might want to change lives in **`config.ini`**. You never need to
touch any other file.

To edit it:

1. Open your repository on GitHub and click **`config.ini`**.
2. Click the **pencil icon** (top right of the file).
3. Make your change.
4. Scroll down and click **Commit changes** → **Commit changes**.

The next poll (within 5 minutes) uses the new settings.

### What each part of config.ini controls

| Setting | What it does |
|---|---|
| `group_a`, `group_b`, `group_c` | The three keyword groups. An alert needs at least one word from **each** group. Add a city to `group_c` to watch it; delete one to stop. |
| `boost` | Extra words that mark an alert HIGH PRIORITY. |
| `exclude` | Phrases that cancel a match. Add phrases here if you're getting noise. |
| `urgent_max_age_minutes` | How fresh a report must be to push instantly. Default 15. Raise it to catch more, lower it to cut false alarms. |
| `digest_time_ist` | Reminder of the digest time. To actually move it, see below. |
| `quiet_hours` | When digests stay silent. Urgent slot alerts always ignore these. |
| `posts`, `column` | Which consulates and which column of the wait-times table to track. |

**To move the digest time** you also need to edit `.github/workflows/daily.yml`.
The line `- cron: "30 3 * * *"` is in UTC. India is 5 hours 30 minutes ahead, so
subtract 5:30 from your desired IST time. For 8:00 AM IST, that's `"30 2 * * *"`.

**To pause VisaWatch:** Actions tab → **VisaWatch poll** → the **⋯** menu on the
right → **Disable workflow**. Re-enable it the same way.

---

## Part 4 — What an alert looks like

```
HIGH PRIORITY Slot report - Hyderabad

BULK SLOTS just dropped for Hyderabad H-1B, go go go

Matched: what: slots | event: dropped, bulk | where: Hyderabad | boost: H-1B
Age: 3 min old  |  source: reddit_comments

Report: https://www.reddit.com/r/usvisascheduling/comments/.../
Book here yourself: https://www.usvisascheduling.com/en-US/
```

Tapping the notification opens the Reddit report so you can judge whether it's
real before spending your time on the portal.

The **daily digest** at 9:00 AM IST lists matches that were already stale when
VisaWatch found them, plus the current petition-based wait times for the five
Indian consulates. If nothing matched, it says *"Nothing matched today. VisaWatch
is running normally."* — that message is how you know the service is alive.

A **source-down notice** arrives if any feed has failed for more than an hour, so
silence is never ambiguous.

### Where VisaWatch keeps its memory

To avoid alerting you twice about the same post, VisaWatch remembers the IDs of
items it has already seen. That memory lives on a separate branch of your
repository called **`state`**, which is rewritten each cycle and always holds
exactly one commit. You never need to look at it. It contains Reddit item IDs and
timestamps — no usernames, and nothing about you.

---

## Part 5 — Optional: email the digest too

Skip this unless you want it; push notifications work without it.

Add these repository secrets (Settings → Secrets and variables → Actions), using
a Gmail **App Password**, not your normal password
([how to make one](https://support.google.com/accounts/answer/185833)):

| Secret name | Value |
|---|---|
| `EMAIL_TO` | the address you want the digest sent to |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASS` | the 16-character app password |

Only the digest is emailed. Urgent alerts stay on push, because email is too slow
and gets silenced by Do Not Disturb.

---

## Why GitHub Actions — and the one catch

**Chosen:** a scheduled GitHub Actions job.

**Why:** on a public repository it is genuinely free at this volume, there is no
server to keep alive, no credit card, nothing to restart when it crashes, and no
free-tier host that quietly sleeps your app after 15 minutes of inactivity. The
code, the config and the schedule all live in one place you can edit from a
browser on your phone. For something you may run for months, "nothing to
maintain" beats "slightly faster".

**What I rejected and why.** A free always-on host (Render, Fly, Railway and
similar) would give you an exact 5-minute timer instead of a best-effort one. But
every free tier either sleeps idle apps, expires after a trial, or asks for a card
— and each of those failure modes is silent, which is the worst property an alert
service can have. GitHub Actions fails loudly, in a tab you can check.

**The catch you need to know about.** GitHub's scheduled jobs are best-effort, not
guaranteed. They are queued along with everyone else's, and during busy periods
they commonly run **3–10 minutes late**, occasionally more, and very
occasionally a run is skipped entirely.

What that means in practice: the schedule says every 5 minutes, but a report
posted on Reddit may reach your phone anywhere from **1 to about 15 minutes**
later. Since VisaWatch only pushes URGENT for reports under 15 minutes old, a
badly delayed cycle can push a report to the digest instead of your phone.

There are two smaller gaps worth knowing about. Around 9:00 AM IST the daily
digest job holds the lock for a few minutes while it opens a browser, so one or
two poll cycles are skipped. And GitHub switches off scheduled jobs in a
repository that has had no activity for 60 days — VisaWatch saves its memory on
every cycle, which counts as activity, but if you ever get an email saying
"workflows disabled", open the Actions tab and click **Enable**.

Honestly: this affects how often you catch a drop, not whether the service works.
Slots that vanish in seconds are gone before *any* alerting system could help —
what VisaWatch reliably catches are the bulk releases that stay open for minutes
and the pattern of when drops are happening, so you know when to sit at your
laptop. If you later want tighter timing, the same code runs unchanged on a small
always-on host with a real 5-minute timer; the trade is a machine you have to
maintain.

---

## For the curious: running it on your own computer

Not required. Only if you want to test locally.

```bash
pip install requests feedparser playwright
python -m playwright install chromium

export NTFY_TOPIC="your-secret-word"

python -m visawatch test-alert     # send a test notification
python -m visawatch poll           # one polling cycle
python -m visawatch daily          # wait times + digest
python -m pytest -q                # run the tests
```

Add `--dry-run` to any command to print what would be sent without sending it.

### The tests

`python -m pytest -q` covers, among other things, the four behaviours that matter
most: a matching item fires exactly once, the same item never fires twice (even
across restarts), a stale item goes to the digest instead of an urgent push, and a
source that has been failing for over an hour produces a source-down notice. It
also asserts that the visa booking portals can never be contacted — the test
tries, and requires the code to refuse.
