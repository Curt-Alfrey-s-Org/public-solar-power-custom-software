# Grok Bot standing tasks

**Read this file.** It is the task list for the Grok Bot cloud computer.
**Master:** alfa-ai `docs/GROK_BOT_TASKS.md`. Sibling repos carry this same file
via `scripts/sync-grok-bot-tasks.sh` in alfa-ai. Edit the master, sync, then
commit each repo.
**Operator policy (alfa-ai only):** `docs/GROK_BOT_FLEET_TASKS.md`.
**Named scripts (alfa-ai only):** `docs/GROK_BOT_SCRIPT_LOOP.md`.

Work only under `/workspace/<repo>` that **already exists**. Do not use Wolf1
or `C:\Users\operator`. Do not read `.env`. Do not clone a missing repo. Do not
open the browser. Do not create a routine.

Official: [files and results](https://docs.x.ai/grok-bot/files-and-results),
[computer and apps](https://docs.x.ai/grok-bot/computer-and-apps),
[skills and routines](https://docs.x.ai/grok-bot/skills-routines-and-automations).

## Standing tasks (every run)

Do these for **this repo**, then for every other git repo already under
`/workspace`. Stop after the handoff. Default is **read-only** (no commit).

1. **Sync.** If `git status` is clean, `git pull --ff-only`. If pull fails,
   record the error and the short SHA. If the tree is dirty, record paths and
   skip pull and fetch.
2. **Report.** Branch, short HEAD, `git status -sb` (ahead/behind), last
   commit subject (`git log -1 --oneline`).
3. **Pin check.** In this repo only, search compose files and Dockerfiles for
   image tags `latest`, `nightly`, `edge`, `:rc`, `:beta`, or a floating
   `main` / `master` tag. List at most 8 `file:line` hits. Do not change them.
4. **Secret names.** If status shows an untracked `.env`, `*.pem`, or a name
   containing `token` or `secret`, list the path only. Do not open the file.
5. **Logs.** If `logs/` exists, read at most two text files under 2MB. Quote
   the first hard error line, or say the folder has no run log.
6. **Cluster.** Do not SSH, docker, or start/stop the pool. If this repo is
   alfa-ai and a check is a named script, reply with one line
   `Propose <action_key> on host <nnn>` and stop. Catalog is
   `docs/GROK_BOT_SCRIPT_LOOP.md` in alfa-ai.
7. **Handoff** (required):

```text
Handoff for Cursor. Bot did not edit Wolf1.
Script: none
Verdict: PASS | FAIL
Pushed: nothing
Facts: (max 8 bullets)
Cursor on : git pull --ff-only origin main in (paths that are behind)
```

`PASS` means every existing `/workspace` repo was reported. `FAIL` means pull
failed, a secret-like path appeared, or a pin hit needs a human.

## On demand only (do not do these unless the paste names them)

| Ask | Why it is not standing |
|-----|------------------------|
| Edit, commit, or push | Operator paste B in alfa-ai `docs/GROK_BOT_FLEET_TASKS.md` |
| Open or close GitHub PRs | Extra connector steps; do it only when the paste says "PRs" |
| Judge a deploy log | Only when the operator pastes an exit code and the last ~80 lines |
| Schedule a routine | After one trusted audit and a second success, per official skills docs |
| Pull a dirty or diverged tree | Fast-forward a clean tree only (task 1) |

## Paste (operator)

```text
In each git repo already under /workspace: git pull --ff-only when the tree
is clean. Read docs/GROK_BOT_TASKS.md in that repo and do only the Standing
tasks. Do not use Wolf1. Do not read .env. Do not edit or push. Reply with
the handoff.
```
