# ForgeMind v3.0 — Slack Integration + Daily Standup Plan

**Status:** PLANNED (not implemented) — read this before starting the next work session.

**Context:** The user wants a messaging platform (Slack) for two purposes:
1. Notifications — ForgeMind posts analysis results, status updates, alerts to Slack
2. Human review — humans approve/reject paused workflows from Slack (buttons or slash commands)
3. Daily standup — a bot posts a daily summary of what ForgeMind did in the last 24h

**Existing baseline:** `SUBMISSION/ARCHITECTURE.md` already lists Slack as an external event
source in the mermaid diagram (line 10), but no actual integration exists yet.

## Real PR Context (as of this plan's save)

Verified via GitHub API: the repo `asifdotpy/forge-mind` currently has **no open PRs**.

The user mentioned working with a real PR with meaningful changes — that PR appears to
live in `asifdotpy/forge-mind-v3-prod` (a separate repo), not in `asifdotpy/forge-mind`.

**Before the next work session**, confirm:
- Which repo the real PR is in (likely `forge-mind-v3-prod`)
- The PR number, title, and changed files
- Whether the webhook is already pointing at the Cloud Run `/api/v1/adk/webhook` endpoint
- Whether the `GITHUB_TOKEN` on Cloud Run has write access to that repo

**Action item:** If the demo will use a real PR, open one in `asifdotpy/forge-mind` (the
public demo repo) OR point the webhook at the PR in `forge-mind-v3-prod` and ensure the
token is scoped correctly. Don't leave this ambiguous — the demo needs a real PR URL the
judges can see.

---

## 1. Slack as External Event Source (Incoming)

**What it does:** Slack events flow INTO the ForgeMind DAG the same way GitHub webhooks do.

**How it works:**
- Slack app with an incoming webhook (or Events API subscription) pointing to a new route: `POST /api/v1/slack/events`
- Slack can send: channel messages, thread replies, slash command invocations, button clicks from interactive messages
- The route normalizes the Slack payload into the same `Event` shape the DAG expects (event_id, situation_id, payload, provenance)
- The DAG processes it: acquire → supervisor → workers → validator → reducer → action gate

**Use cases this enables:**
- A developer posts "hey forge, scan this PR" in Slack → ForgeMind analyzes
- A monitoring alert comes in as a Slack message → ForgeMind triages
- A thread discussion about an incident → ForgeMind correlates and proposes actions

**What's needed:**
- Slack app (new or existing) with appropriate scopes/bot token
- New route `POST /api/v1/slack/events` in `adk_routes.py` (mirrors webhook pattern)
- Payload-to-Event normalization function (similar to `_webhook_changed_files` but for Slack)
- Slack signature verification middleware (standard — verify `X-Slack-Signature` header)

---

## 2. Slack as Notification Channel (Outgoing)

**What it does:** ForgeMind sends messages OUT to Slack — analysis results, status updates, alerts, escalation notifications.

**How it works:**
- Slack app with an outgoing webhook or bot that can post to channels
- After the DAG produces a terminal outcome, the route (or a post-processing step) sends a summary to a Slack channel
- Two channels suggested:
  - **#forgemind-analysis** — every analysis result (comment + verdict)
  - **#forgemind-escalations** — human-review requests and escalations (higher signal)

**Message content (example):**
```
🔍 ForgeMind Analysis — PR #42 (asifdotpy/forge-mind)
Status: paused (human review required)
Confidence: 0.88 | Risk: medium
Causality: unsupported (single domain — code)
Verdict: Hold for human review before acting
Decide here: https://forgemind-n3nupsii5a-uc.a.run.app/approvals/<token>
```

**What's needed:**
- Slack bot token with `chat:write` scope
- Slack channel IDs configured (env vars: `SLACK_ANALYSIS_CHANNEL`, `SLACK_ESCALATION_CHANNEL`)
- Notification function: takes the DAG result, formats a Slack message, posts it
- Hook it into the route after `_execute_github_actions` — send notification regardless of whether GitHub actions succeeded

---

## 3. Human Review via Slack (Interactive)

**What it does:** Instead of (or in addition to) the web dashboard, a human can approve/reject a paused workflow directly from Slack.

**How it works:**

**Option A — Slack button in message (interactive):**
- The escalation/notification message includes two buttons: "Approve" and "Reject"
- Slack sends an `interactivity` callback to `POST /api/v1/slack/interactive`
- The callback includes the `pending_approval.token` and the user's decision
- ForgeMind calls `resume_adk_pipeline(token, decision)` and posts the result back to Slack

**Option B — Slash command:**
- `/forge-approve <token>` and `/forge-reject <token>` as Slack slash commands
- Simpler to build, less interactive polish

**Recommended:** Option A (buttons) for the demo — it's the most visible "agent asks human, human clicks approve" moment.

**What's needed:**
- Slack interactive message signing/verification
- New route `POST /api/v1/slack/interactive`
- Button payload format: `{"token": "***", "decision": "approve"}`
- After decision: resume pipeline, post result message to the originating Slack thread
- Thread-aware replies (use `thread_ts` from the original message so the conversation stays threaded)

---

## 4. Daily Standup Bot (Scheduled)

**What it does:** Every day (e.g., 9:00 AM UTC), a bot posts a standup summary to a Slack channel summarizing what ForgeMind did in the last 24 hours.

**Why it matters for the hackathon:** It's a visible "agent that operates autonomously on a schedule" — shows the system isn't just reactive, it also proactively reports.

**Standup content (example):**
```
📋 ForgeMind Daily Standup — 2026-08-28

✅ 3 events processed
   · PR #42 (asifdotpy/forge-mind) — human_review, comment posted
   · PR #41 — safe_autonomous, comment + status check passed
   · PR #39 — escalated (security file touched)

⏸ 1 awaiting human decision
   · PR #42 — token 9885bf27... — decision_required

🏁 Autonomy breakdown:
   · safe_autonomous: 1 (33%)
   · human_review: 1 (33%)
   · escalated: 1 (33%)

🔗 Dashboard: https://forgemind-n3nupsii5a-uc.a.run.app
```

**How it works:**
- A scheduled runner (cron job, Cloud Scheduler, or GitHub Actions scheduled workflow) fires daily
- It queries the system for yesterday's events — either:
  - **Option A:** Read from the in-memory pause store + recent DAG results (simple but volatile)
  - **Option B:** Query a lightweight store (SQLite file, or a Cloud Run endpoint that exposes a `/api/v1/standup` summary endpoint)
  - **Option C:** Log events to a file/DB as they happen, read them back for the standup
- Format the summary, post to Slack via bot token

**Recommended for the hackathon:** Option B — add a lightweight `GET /api/v1/standup` endpoint that returns the last 24h summary (counts by autonomy class, pending decisions, recent actions). The scheduled runner just HTTP-gets that endpoint and posts the result to Slack. No new database — the endpoint aggregates from in-memory state + a small ring buffer of recent results.

**What's needed:**
- New endpoint `GET /api/v1/standup` — returns 24h summary (event counts, autonomy breakdown, pending decisions, recent actions with PR links)
- Ring buffer or small in-memory store of recent results (append-only list, bounded size, survives until process restart — fine for demo)
- Scheduled runner: simplest is a GitHub Actions scheduled workflow or a local cron that curls the endpoint and posts to Slack
- Slack bot token with `chat:write` for the standup channel

**Scheduling options (pick one):**
- **GitHub Actions scheduled workflow** — `schedule: cron: '0 9 * * *'` (9 AM UTC), posts to Slack via a step that calls the Slack API with the bot token (stored as a repo secret)
- **Cloud Scheduler → Cloud Run endpoint** — Cloud Scheduler hits a new `POST /api/v1/standup/run` endpoint that triggers the standup (self-hosted scheduler inside the service)
- **Local cron** — simplest, runs on the dev machine, curls the endpoint and posts to Slack

**Recommended:** GitHub Actions scheduled workflow — no extra GCP service needed, fits the "GitHub-centric" story.

---

## 5. What Changes Where (Code Map — For Later Implementation)

| Component | File(s) | Change |
|-----------|---------|--------|
| Slack incoming route | `adk_routes.py` | New `POST /api/v1/slack/events` — normalizes Slack payload to Event, delegates to `run_adk_pipeline` |
| Slack signature verify | new helper in `adk_routes.py` or `tools/slack_utils.py` | Verify `X-Slack-Signature` using bot signing secret |
| Slack interactive route | `adk_routes.py` | New `POST /api/v1/slack/interactive` — decodes button payload, calls `resume_adk_pipeline`, posts result |
| Slack outgoing notify | `adk_routes.py` (after actions) or new `notifications.py` | Posts analysis/escalation summary to Slack channels after DAG completes |
| Slack bot utils | new `tools/slack_client.py` | Wraps Slack Web API (post message, add buttons, thread replies) — mirrors `github_client.py` pattern |
| Standup endpoint | `adk_routes.py` | New `GET /api/v1/standup` — returns 24h summary from recent results ring buffer |
| Standup scheduler | `deploy/standup.yml` (GitHub Actions) or new route | Scheduled job that curls `/api/v1/standup` and posts to Slack |
| Recent results store | new `recent_results.py` or in `adk_runtime.py` | Bounded ring buffer of recent DAG outcomes (for standup + human review history) |
| Env vars | `.env` + Cloud Run | `SLACK_BOT_TOKEN`, `SLACK_SIGNING_SECRET`, `SLACK_ANALYSIS_CHANNEL`, `SLACK_ESCALATION_CHANNEL`, `SLACK_STANDUP_CHANNEL` |
| Architecture diagram | `SUBMISSION/ARCHITECTURE.md` | Update mermaid to show Slack bidirectional (in + out), standup scheduler box |
| Submission checklist | `SUBMISSION/CHECKLIST.md` | Add Slack integration + standup as completed items |
| Demo script | `SUBMISSION/DEMO_SCRIPT.md` | Add Slack notification + human-review-via-button + standup to demo flow |

---

## 6. Demo Story With Slack

The demo gets stronger with Slack because it shows the full loop in a channel people use every day:

1. **Open a PR** (or use the existing open PR)
2. **Show the Slack notification** — ForgeMind posts the analysis to #forgemind-analysis
3. **If human_review:** show the message with Approve/Reject buttons, click Approve, show the result posted back to the thread
4. **Show the GitHub comment** appearing on the PR (parallel action)
5. **Show the dashboard** updating
6. **Show tomorrow's standup** (or simulate it) — the bot posts the daily summary to the standup channel

This is a stronger demo than just the dashboard alone — it shows the agent in the tools people actually use (GitHub + Slack), asking for human input when needed, and reporting on a schedule.

---

## 7. Implementation Order (When You Code This)

1. **Slack outgoing notifications** — easiest win, shows the agent "talking"
2. **Slack human review buttons** — the most visible "agent asks human" moment
3. **Slack incoming events** — makes Slack a first-class input source
4. **Daily standup endpoint + scheduler** — shows scheduled autonomy + daily reporting

Do them in that order because each one is independently demoable and they layer naturally.
