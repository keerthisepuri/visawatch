# VisaWatch

VisaWatch is a **metronome and a checklist**, not a slot finder.

1. **It keeps time.** It pings you a few minutes before every :00 and :30 during
   your chosen hours, because cancelled appointments are reported to return to
   the pool then. You want to be already on the calendar when that happens.
2. **It watches Reddit** and pushes an alert if someone reports a drop. This is
   a genuinely weak signal — see "What VisaWatch cannot do" — and it is kept
   because it costs nothing, not because it will win you a slot.

**What VisaWatch never does.** It never contacts usvisascheduling.com or
ustraveldocs.com. It never asks for or stores your username, password, security
answers, passport number or DS-160 number — there is nowhere in this project for
that information to go. It never tries to book, hold or reschedule anything. It
reads four public Reddit feeds that anyone can open without logging in, and it
backs off politely when a site says slow down. The alert contains a plain link to
the booking site; tapping it opens the normal login page, exactly as if you had
typed the address yourself.

---

## A correction, because it changes what this tool does

VisaWatch used to claim it had **measured** two daily release windows in IST
(05:30–07:30 and 22:00–23:00), the stronger one supposedly 3.7× baseline. That
claim has been withdrawn. Re-run on a fresh year of posts on 6 Aug 2026, it did
not replicate — chi-square 30.3 on 23 df where 35.2 was needed for p<0.05. Two
things were wrong with the original analysis:

- **It was measuring the wrong thing.** Of 131 posts in a year whose titles
  matched "slot" plus an availability word, 57 were questions and 63 were
  narrative. Only a handful were live reports. So the hourly pattern was a
  pattern in *when people ask about slots and complain*, not in when slots open.
- **There is a confound that survives the controls I ran.** The portal's daily
  calendar-refresh budget resets on the IST day boundary, which gives every
  applicant on earth — in India or abroad — a reason to check hardest in the
  Indian morning. That would produce exactly the observed spike with no
  underlying release pattern, and it replicates across US-based and India-based
  subreddits alike, which is why my cross-audience check did not catch it.

The windows are gone. What replaced them is timekeeping against the one cadence
the community documents as repeating, described next.

---

## How slots actually appear

Two different things, and they need different responses.

| | Bulk releases | Cancellations |
|---|---|---|
| How often | Rare — maybe once every 2–4 weeks | Continuous |
| When | Reported as unpredictable | Around **minute :00 and :30** of every hour |
| What to do | Cannot be planned for. This is what the Reddit alerts are for, weak as they are. | **Be on the calendar at :55 and :25.** This is what VisaWatch's pings are for. |

The :00/:30 cadence is the useful one because it repeats. It is also **portal
behaviour rather than crowd behaviour**, which is why it is worth setting your
day by — a pattern in how the booking system returns cancelled appointments is a
much better thing to bet on than a pattern in when people post to Reddit.

**Honesty about where this comes from.** It is community knowledge, from
applicants who watch the portal directly. VisaWatch cannot verify it, because
verifying would mean polling the booking portal, which your rules forbid and
which this project will not do. I tested it against Reddit timing anyway and the
test came out inconclusive — slot posts sat 1.17× above chance in the :00/:30
±4 min band, the right direction but nowhere near significance at n=57. Reddit
is simply the wrong instrument: a post is written minutes after the fact, which
smears minute-of-hour into noise. Treat the cadence as a well-sourced tip, not as
something this tool proved.

---

## The rules of the portal

These come from applicants who use the system daily, not from VisaWatch. They
matter more than any alerting tool, because **the scarce resource is not your
time — it is your daily page-load budget.**

**You get 20 full calendar page loads per day.** Not 20 logins; logins are
unlimited. It is the calendar page specifically. Every load and reload counts. A
Cloudflare "are you human" check counts. When you hit the limit you cannot see
the calendar at all until the counter resets.

**The counter resets at midnight IST — 11:30 in the morning for you in
Phoenix.** VisaWatch tells you this in the first ping of each day.

**The trick that makes the budget last: don't reload.** Stay on the calendar
page and change the location in the dropdown, then change it back. That
re-queries availability without a page load, so it does not count. You can do
this many more than 20 times.

**You get logged out after 15 minutes of inactivity** — but changing the
location counts as activity, so the dropdown trick keeps you alive too.

**Slow down.** The 1015 rate limit is caused by an *accumulated* burst of
clicks, not by any single one. The cruel part is that it usually bites on the
last click of a sequence — the one where you finally found a slot and hit
submit. Roughly 5–8 seconds between checks is reported as safe. Test it
yourself, gently.

**"No slots available" is the normal state.** Slots are reported to disappear in
1–3 seconds. Seeing nothing after an alert almost never means the alert was
fake; it means somebody was a few seconds ahead of you.

### If you are booking in India: OFC + Consular

Two appointments are required — OFC (fingerprinting) and Consular (the
interview). Once you book the OFC you have **about 45 minutes** to book a
Consular, or the OFC is cancelled automatically and you start over.

After booking the OFC you are taken to a screen that looks almost identical.
Check the heading: the OFC screen says OFC, the Consular screen does not. An
`SGA10` error means your 45 minutes expired — go back to Home and click
"schedule application" again.

### Rescheduling

Booking a new slot replaces your old appointment. You do not cancel first.
Attempts are limited (1–4 depending on post and visa type), so save them for a
meaningful jump rather than a few days. Many people book a "good enough" date to
lock something in, then keep hunting for an earlier one — with OFC+Consular, if
you find a new OFC but no matching Consular, you keep your original pair.

---

## Part 1 — Getting notifications on your phone

VisaWatch sends alerts through **ntfy** (say "notify"). Free, no account, no
password. You invent a secret word, subscribe to it in the app, and anything
sent to that word appears as a notification.

1. Install **ntfy**:
   [iPhone](https://apps.apple.com/us/app/ntfy/id1625396347) ·
   [Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy)
2. Open it, tap **+**, and enter your secret topic word. **Write it down.**
   Anyone who knows that exact word could send you a notification — that is the
   only reason it needs to be hard to guess. It contains no personal data.
3. Tap **Subscribe**.
4. Open the topic → **⋮** → **Settings**, and allow it to **override Do Not
   Disturb**. On iPhone: phone Settings → Notifications → ntfy → **Time
   Sensitive Notifications: on**.

Check pings arrive at priority 4 and slot reports at priority 5, so you can tell
them apart without reading them.

---

## Part 2 — The one file you edit

Everything lives in **`config.ini`** at the top of the repository. Open it on
GitHub → click the **pencil icon** → change it → **Commit changes**. The next
cycle picks it up.

| Setting | What it does |
|---|---|
| `[you] timezone` | **Your** timezone, e.g. `America/Phoenix`. Everything below is on your clock. |
| `[checking] active_hours` | When you can be at a screen. Default `09:00-21:00`. Outside these, silence. |
| `[checking] ticks` | Minutes past the hour to ping for. Default `00, 30`. Every extra entry doubles the pings. |
| `[checking] lead_minutes` | How far ahead to ping. Default 5, so pings land at :55 and :25. |
| `[checking] days` | Drop `sat, sun` if weekends aren't worth the interruption. |
| `[checking] enabled` | Set to `no` to stop the pings entirely. |
| `group_a`, `group_b`, `group_c` | The three keyword groups for Reddit alerts. A match needs one word from **each**. |
| `boost` | Words that mark an alert HIGH PRIORITY (H1B, H4, petition…). |
| `exclude` | Phrases that cancel a match. Add to this when you get noise. |
| `[quiet_hours]` | When digests stay silent. **Your local time.** Slot alerts always ignore these. |

**Current setting: 09:00–21:00, every :00 and :30 — 25 pings a day.** That is
deliberate and it is a lot. If it becomes wallpaper you will start ignoring it,
which is worse than not having it. Narrow `active_hours` the moment that starts
happening.

---

## Part 3 — How it runs, honestly

VisaWatch runs on **GitHub Actions**: free on a public repository, no server, no
credit card, nothing to restart.

**GitHub's schedule is a request, not a promise.** Measured on this repository:
over three days a `*/5` cron that should have fired ~860 times fired **46**.
Median gap 74 minutes, worst 227. That was the cause of the early "a source has
not been read" complaints — the service mostly wasn't running.

The fix: **each run polls in an internal loop for 55 minutes, every 5 minutes**,
so the schedule only has to succeed once an hour. Cadence is now real.

**What that means for the pings.** A ping fires if a polling cycle lands in the
7-minute band around its tick. Simulated against a schedule with 45-minute
holes, about **60% of pings get through** — roughly 15 of 25 on a typical day.
That is fine here, unlike the old window design where a missed ping meant a
missed day: there are 25 chances a day and you also have a clock.

**One feed per cycle.** Reddit rate-limits data-centre IPs hard — measured live,
the second request in a cycle gets HTTP 429 even six seconds later. So VisaWatch
makes exactly one request per cycle. The megathread comments feed gets three
cycles out of four; the others rotate through the fourth. This is why the log
reads `Read 1 of 4 feeds this cycle`, and why a feed that has not been read for
a while is **not** an outage — a "source is down" notice requires three
consecutive failures over the threshold.

**The wait-times table is off.** `travel.state.gov` answers HTTP 403 to GitHub's
runners because it blocks data-centre IPs. VisaWatch backs off rather than
disguising itself, so it is switched off rather than left to fail daily.

---

## Part 4 — Running it by hand

**Actions** → **VisaWatch** → **Run workflow**:

| Mode | What it does |
|---|---|
| `test-alert` | Sends a test notification. Proves the phone side works. |
| `poll` | Starts a 55-minute polling loop now. |
| `daily` | Sends the daily digest now. |

**To pause:** Actions → **VisaWatch** → **⋯** → **Disable workflow**.

---

## Part 5 — What the notifications look like

**The check ping — the one that matters. First of the day carries the protocol:**

```
Check the calendar - :00 in 5 min

Cancellations go back into the pool around 09:00 MST (21:30 IST).

Do NOT reload the page. Change the location in the dropdown and
change it back - that re-queries availability and costs you none
of your 20 daily calendar loads.

First check of the day. Your 20 calendar page
loads reset at 11:30 MST (midnight IST).

Slow down between clicks - a burst of them is what triggers the
1015 rate limit, and it will hit you on the click that matters.

Reported cadence, not something VisaWatch can verify - it never
touches the portal.

Log in here: https://www.usvisascheduling.com/en-US/
```

Every later ping that day is the short version — three lines and the link.

**A Reddit slot report:**

```
HIGH PRIORITY Slot report - Hyderabad

BULK SLOTS just dropped for Hyderabad H-1B, go go go

Matched: what: slots | event: dropped, bulk | where: Hyderabad | boost: H-1B
Age: 3 min old  |  source: reddit_comments

Report: https://www.reddit.com/r/usvisascheduling/comments/.../
Book here yourself: https://www.usvisascheduling.com/en-US/
```

**The daily digest**, 09:00 IST (20:30 the previous evening in Phoenix), lists
matches too stale to alert on. If nothing matched it says *"Nothing matched
today. VisaWatch is running normally."* — that message is how you know the
service is alive.

### Why so few Reddit alerts

Because there is very little to alert on. In a year, the biggest slot subreddit
produced 131 posts matching "slot" + an availability word, and only a handful
were live drop reports. The rest were questions, complaints, and write-ups.
VisaWatch requires the three keyword groups to appear **within 20 words of each
other**, drops anything reading as a question, and applies the `exclude` list —
and it still finds mostly noise, because mostly noise is what is there.

If you were expecting a stream of alerts, that expectation was wrong, and it was
wrong before this tool existed.

### Where VisaWatch keeps its memory

On a separate branch called **`state`**, rewritten each cycle, always one
commit. Reddit item IDs and timestamps — no usernames, nothing about you.

---

## Part 6 — Optional: email the digest

Add these repository secrets (Settings → Secrets and variables → Actions), using
a Gmail **App Password**
([how](https://support.google.com/accounts/answer/185833)):

| Secret | Value |
|---|---|
| `EMAIL_TO` | where to send it |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASS` | the 16-character app password |

Only the digest is emailed. Urgent alerts stay on push.

---

## What VisaWatch cannot do for you

- **Alerts are structurally too late.** Time yourself: notification → unlock
  phone → read → log in → reach the calendar. Call it 30 seconds. Slots go in
  1–3. Anyone already sitting on the calendar beat you before you picked up the
  phone. This is true of every alert service, paid ones included — someone has
  to see the slot before you can be told about it.
- **The paid crowdsourced services are faster but not different in kind.** They
  get data from users running extensions against their own logged-in portal
  sessions. There is no credential-free way to see the portal's real inventory,
  which is why VisaWatch reads Reddit. That is a deliberate trade made because
  your rules forbid touching the portal, and it costs real speed.
- **Free public Telegram slot channels are deliberately delayed** (typically 30
  minutes) and post images rather than text.
- **Agents have no special access.** They cannot reserve, transfer or resell
  appointments — bookings are tied to your passport, specifically to prevent a
  resale market. What you would be buying is somebody's time and attention.
  Never pay upfront; anyone promising a guaranteed slot in 1–2 days is lying.
  The common scam is to take your login, change the security questions (which
  needs no email confirmation), fake a screenshot and demand payment. If it
  happens, do not pay — tell the embassy you forgot your security questions, or
  open a new account with a new email and ask them to transfer your profile.
- **Emergency/expedited appointment requests are the biggest under-used lever**
  if your travel is genuinely urgent. Worth more than any alerting tool.
- Interview waiver / "dropbox" has been closed to H-1B since 1 Oct 2025, and
  third-country appointments closed in Sept 2025. Many law-firm blog posts
  saying otherwise are stale.

**The uncomfortable summary:** slots go to whoever is checking most
consistently. This tool exists to make your checking disciplined and to stop you
wasting page loads — not to find slots for you.

---

## For the curious: running it locally

```bash
pip install requests feedparser
export NTFY_TOPIC="your-secret-word"

python -m visawatch test-alert     # send a test notification
python -m visawatch poll           # one polling cycle
python -m visawatch daily          # digest
python -m pytest -q                # 79 tests
```

Add `--dry-run` to any command to print instead of sending.

### The tests

Among other things: a matching item fires exactly once, the same item never
fires twice (even across restarts), a stale item goes to the digest instead of
an urgent push, and a genuinely failing source produces a source-down notice.
They also assert that the booking portals can never be contacted — the test
tries, and requires the code to refuse — that quiet hours are evaluated on your
clock rather than India's, and that a full day of check pings comes to exactly
25 rather than silently drifting upward into your pocket.
