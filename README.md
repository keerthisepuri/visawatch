# VisaWatch

VisaWatch does two things for you.

1. **It tells you when a slot release is likely**, a few minutes before it starts,
   so you can already be logged in and refreshing. This is the part that actually
   wins slots.
2. **It pushes an alert to your phone** when someone on Reddit reports that slots
   have opened. Useful, but always second-hand and therefore always a little late.

Both land as notifications on your phone. You do the booking yourself.

**What VisaWatch never does.** It never contacts usvisascheduling.com or
ustraveldocs.com. It never asks for or stores your username, password, security
answers, passport number or DS-160 number — there is nowhere in this project for
that information to go. It never tries to book, hold or reschedule anything. It
reads four public Reddit feeds that anyone can open without logging in, and it
backs off politely when a site says slow down. The alert contains a plain link to
the booking site; tapping it opens the normal login page, exactly as if you had
typed the address yourself.

---

## Read this first: why the heads-up matters more than the alert

VisaWatch is structurally too slow to win a race against a slot release, and no
tool that refuses to log into the portal on your behalf can be otherwise. The
chain is: a slot opens → a human notices → that human writes a Reddit post →
Reddit publishes it → VisaWatch reads it → your phone buzzes. Bulk releases are
reported to fill within minutes. By the time an alert reaches you, the good ones
are often gone.

What is *not* a race is knowing **when to be sitting at your laptop**. On
4 Aug 2026 I measured 346 slot-drop posts across a year against 1,200 ordinary
posts from the same subreddits — the comparison matters, because otherwise you
just rediscover when people are awake. Two hours stood out:

| Hour (IST) | How much likelier than normal | In Phoenix |
|---|---|---|
| **06:00** | **3.7×** (the strongest signal by far) | 17:30 the previous day |
| 22:00 | 1.5× | 09:30 |

06:00 IST is one of the *quietest* hours on those subreddits — 1.1% of all posts —
yet it carries 4.0% of the slot-drop posts. Nobody is casually browsing at 6am.
They are posting because something happened.

I also checked the obvious objection: *isn't that just when Indians are awake?*
r/h1b is a US-based crowd whose activity is the mirror image of the India-based
subs, and the same two hours show up there too, each measured against its own
baseline. So it is a real release pattern, anchored to India time because the
consulates run on India time — not an artifact of who is online.

**What the data does not support:** day of the week. The popular "Wednesday
midnight" and "Friday batch" folklore is not visible in a year of data, so
VisaWatch makes no weekday claim.

So VisaWatch pings you **20 minutes before** each window. That ping is the
important notification. Everything else is a bonus.

**A tendency, not a schedule.** Some days nothing drops. This tells you when the
odds are better, not when a slot is guaranteed.

---

## Part 1 — Getting notifications on your phone

VisaWatch sends alerts through **ntfy** (say "notify"). It's free, with no
account, no email and no password. You invent a secret word, subscribe to it in
the app, and anything sent to that word appears as a notification.

1. Install **ntfy**:
   [iPhone](https://apps.apple.com/us/app/ntfy/id1625396347) ·
   [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
2. Open it, tap **+**, and enter your secret topic word.
   **Write it down.** Anyone who knows this exact word could send you a
   notification — that is the only reason it needs to be hard to guess. It
   contains no personal data.
3. Tap **Subscribe**.
4. Open the topic → **⋮** → **Settings**, and allow it to **override Do Not
   Disturb**. On iPhone: phone Settings → Notifications → ntfy → **Time
   Sensitive Notifications: on**. This is what lets an alert reach you at 3 AM.

---

## Part 2 — The one file you edit

Everything you might want to change lives in **`config.ini`** at the top of the
repository. You never need to touch any other file.

To edit it: open the repository on GitHub → click **`config.ini`** → click the
**pencil icon** → make your change → **Commit changes** → **Commit changes**.
The next cycle uses the new settings.

### The settings that matter most

| Setting | What it does |
|---|---|
| `[you] timezone` | **Your** timezone, e.g. `America/Phoenix`. See the note below — this is the one setting people get wrong. |
| `[windows] windows` | The IST hours to warn you about. Default `05:30-07:30, 22:00-23:00`. |
| `[windows] lead_minutes` | How far ahead of a window to ping you. Default 20. |
| `[windows] enabled` | Set to `no` to turn the heads-up off entirely. |
| `group_a`, `group_b`, `group_c` | The three keyword groups. An alert needs at least one word from **each**. Add a city to `group_c` to watch it; delete one to stop. |
| `boost` | Extra words that mark an alert HIGH PRIORITY (H1B, H4, petition…). |
| `exclude` | Phrases that cancel a match. Add phrases here when you get noise. |
| `urgent_max_age_minutes` | How fresh a report must be to push instantly. Default 15. |
| `[quiet_hours]` | When digests stay silent. **Your local time.** Urgent slot alerts always ignore these. |

### Two clocks, and why mixing them up is a real bug

- **Release windows are in IST**, because the consulates and their booking system
  run on India time no matter where you are sitting.
- **Quiet hours are in your local time**, because they are about when you sleep.

VisaWatch used to compare quiet hours against India time. For a Phoenix user that
turned "23:00–07:00" into 10:30–18:30 local — the middle of the working day — so
digests were muted all day and delivered in the middle of the night. Setting
`[you] timezone` correctly is what keeps the two apart. Every window alert quotes
both clocks so you never have to do the arithmetic.

With `America/Phoenix` set, both windows land at civilised hours — pings at
**16:40** and **09:10** — so you get no night-time wake-ups at all.

---

## Part 3 — How it runs, honestly

VisaWatch runs on **GitHub Actions**: free on a public repository, no server to
keep alive, no credit card, and nothing to restart when it crashes.

### The catch, and how it is worked around

GitHub's `*/5 * * * *` schedule is a **request, not a promise**. Measured on this
repository: over three days, a schedule that should have fired ~860 times fired
**46 times**. Median gap 74 minutes; worst gap 227 minutes. That was the cause of
the early "a source has not been read" complaints — the service simply wasn't
running most of the time.

So VisaWatch no longer relies on the schedule for its cadence. **Each run polls
in an internal loop for 55 minutes, every 5 minutes**, and the schedule only has
to succeed once an hour to keep the chain unbroken. Cadence is now real.

### One feed per cycle

Reddit rate-limits data-centre IPs hard — measured live, the *second* request in
a cycle gets HTTP 429 even six seconds later. So VisaWatch makes exactly one
request per cycle. The megathread comments feed carries the live slot reports, so
it gets three cycles out of four (a read every ~7 minutes); the other three feeds
rotate through the fourth cycle, roughly hourly each. That is by design — a whole
post found an hour late belongs in the digest anyway.

This is why the log says `Read 1 of 4 feeds this cycle`, and why a feed that has
not been read for a while is **not** an outage. A "source is down" notice now
requires three consecutive *failures* over the threshold, not merely silence.

### The wait-times table is off

`travel.state.gov` answers HTTP 403 to GitHub's runners because it blocks
data-centre IP ranges. Per your rules VisaWatch backs off rather than trying to
disguise itself, so it cannot be read from here. It is switched off in
`config.ini` rather than left on to fail every day. Check that page yourself in a
browser when you want it.

---

## Part 4 — Running it by hand

**Actions** tab → **VisaWatch** → **Run workflow** → pick from the dropdown:

| Mode | What it does |
|---|---|
| `test-alert` | Sends a test notification. Use this to prove the phone side works. |
| `poll` | Starts a 55-minute polling loop right now. |
| `daily` | Sends the daily digest immediately. |

**To pause VisaWatch:** Actions → **VisaWatch** → the **⋯** menu → **Disable
workflow**. Re-enable the same way.

**If a test alert doesn't arrive:** the two usual causes are a typo in the secret
name (it must be exactly `NTFY_TOPIC`) or a mismatch between the word in the
GitHub secret and the topic in the ntfy app.

---

## Part 5 — What the notifications look like

**The heads-up — the one that matters:**

```
Slot window opening - 05:30-07:30 IST

A likely release window starts at 05:30 IST.
That is 17:00 today your time (MST).

Slot-drop chatter peaks at 06:00 IST - 3.7x the normal rate. It shows up
in both India-based and US-based subreddits, so it is a real release
pattern, not just when people are awake.
A tendency, not a schedule - some days nothing drops.

Batches are reported to fill within minutes, so being logged in and
refreshing beats reacting to any alert.

Log in here: https://www.usvisascheduling.com/en-US/
```

**A live report:**

```
HIGH PRIORITY Slot report - Hyderabad

BULK SLOTS just dropped for Hyderabad H-1B, go go go

Matched: what: slots | event: dropped, bulk | where: Hyderabad | boost: H-1B
Age: 3 min old  |  source: reddit_comments

Report: https://www.reddit.com/r/usvisascheduling/comments/.../
Book here yourself: https://www.usvisascheduling.com/en-US/
```

Tapping it opens the Reddit report so you can judge whether it's real before
spending time on the portal.

**The daily digest**, 09:00 IST (20:30 the previous evening in Phoenix), lists
matches that were already stale when VisaWatch found them. If nothing matched it
says *"Nothing matched today. VisaWatch is running normally."* — that message is
how you know the service is alive.

### Why some obvious-looking posts don't alert

Most Reddit posts containing "slots", "dropped" and "Hyderabad" are people
*asking* about slots or writing up an interview they already attended. VisaWatch
requires the three keyword groups to appear **near each other** (within 20 words),
drops anything that reads as a question, and applies the `exclude` list. Measured
against real queued items, this rejected all seven false positives while keeping
four of five genuine reports. If you start seeing noise, add the offending phrase
to `exclude`.

### Where VisaWatch keeps its memory

To avoid alerting twice about the same post, VisaWatch remembers the IDs of items
it has seen. That memory lives on a separate branch called **`state`**, rewritten
each cycle, always exactly one commit. You never need to look at it. It contains
Reddit item IDs and timestamps — no usernames, and nothing about you.

---

## Part 6 — Optional: email the digest too

Skip this unless you want it; push works without it. Add these repository secrets
(Settings → Secrets and variables → Actions), using a Gmail **App Password**, not
your normal password
([how to make one](https://support.google.com/accounts/answer/185833)):

| Secret | Value |
|---|---|
| `EMAIL_TO` | where to send the digest |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASS` | the 16-character app password |

Only the digest is emailed. Urgent alerts stay on push, because email is too slow
and gets silenced by Do Not Disturb.

---

## What VisaWatch cannot do for you

Worth knowing, so you don't over-trust it:

- **The faster commercial services work differently.** CheckVisaSlots and similar
  get their data from users running browser extensions against their own
  logged-in portal sessions. There is no credential-free way to see the portal's
  actual inventory, which is why VisaWatch reads Reddit instead. That is a
  deliberate trade, made because your rules forbid touching the portal.
- **Free public Telegram slot channels are deliberately delayed** (typically 30
  minutes) and post images rather than text, so they are not a usable source.
- **Emergency/expedited appointment requests are the biggest real lever** most
  applicants under-use, with reportedly favourable approval rates at Mission
  India. If your travel is genuinely urgent, that route is worth more than any
  alerting tool.
- Interview waiver / "dropbox" has been closed to H-1B since 1 Oct 2025, and
  third-country appointments closed in Sept 2025. Many law-firm blog posts saying
  otherwise are stale.

---

## For the curious: running it on your own computer

Not required.

```bash
pip install requests feedparser

export NTFY_TOPIC="your-secret-word"

python -m visawatch test-alert     # send a test notification
python -m visawatch poll           # one polling cycle
python -m visawatch daily          # digest
python -m pytest -q                # 72 tests
```

Add `--dry-run` to any command to print what would be sent without sending it.

### The tests

`python -m pytest -q` covers, among other things, the four behaviours that matter
most: a matching item fires exactly once, the same item never fires twice (even
across restarts), a stale item goes to the digest instead of an urgent push, and a
source that has genuinely been failing for over an hour produces a source-down
notice. It also asserts that the visa booking portals can never be contacted — the
test tries, and requires the code to refuse — and that quiet hours are evaluated
on your clock rather than India's.
