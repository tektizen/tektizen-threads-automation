# Setup Guide

Everything in the code is done. These are the steps only you can do, because they need your accounts and keys. Do them in order. It takes about 30–45 minutes.

> **Never paste API keys into chat, code, issues, or any file in this repo.** Keys go only into GitHub Secrets (step 3).

---

## Step 1: Push the latest code

From the project folder:

```powershell
cd C:\Users\Admin\Desktop\TEKTIZEN\threads-automation
git add .
git commit -m "Build engine, workflows, and dashboard"
git push
```

Then open **https://github.com/tektizen/tektizen-threads-automation/actions** and check that the **CI** workflow turns green (tests + dashboard build).

---

## Step 2: Get your API keys

### OpenRouter (AI)
1. Sign in at https://openrouter.ai → **Keys** → **Create Key** (name it `tektizen-actions`).
2. Copy the key (`sk-or-v1-…`).
3. Under **Settings → Privacy**, allow the data policy that free models require. If generation fails with a "no endpoints found" or privacy error, this setting is the reason.

### Zernio (publishing)
1. Sign in at https://zernio.com.
2. Connect the **@tektizen** Threads account (through its linked Instagram account).
3. Create an **API key** and copy it.
4. Optional: check whether your plan includes **Analytics**. Without it, publishing still works, but the Performance page shows "unavailable".

---

## Step 3: Add the keys to GitHub Secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Name | Value |
|---|---|
| `OPENROUTER_API_KEY` | your OpenRouter key |
| `ZERNIO_API_KEY` | your Zernio key |

Also check **Settings → Actions → General**:
- **Actions permissions:** allow actions.
- **Workflow permissions:** if any workflow later fails at "Commit results" with a 403 error, choose **Read and write permissions** and save.

Branch protection: do **not** require pull requests on `main`. The automation commits data directly.

---

## Step 4: Find your Threads account ID

1. **Actions** tab → **Find Zernio Threads Account ID** → **Run workflow**.
2. Open the finished run → the step "List connected Threads accounts" prints something like:
   ```
   66b2e19d8c3f5a7e9d0b1c2d  @tektizen  active=True  needs_reconnection=False
   ```
3. Copy the ID. You'll paste it into the dashboard in step 7.

---

## Step 5: Deploy the dashboard on Cloudflare Pages

1. https://dash.cloudflare.com → **Workers & Pages** → **Create** → **Pages** → **Connect to Git**.
2. Pick **tektizen/tektizen-threads-automation**.
3. Build settings:

   | Setting | Value |
   |---|---|
   | Framework preset | **Vite** (or None) |
   | Root directory | `web` |
   | Build command | `npm run build` |
   | Build output directory | `dist` |
   | Environment variable | `NODE_VERSION` = `22` |

   No other variables are needed. The dashboard defaults to `tektizen/tektizen-threads-automation` on `main`. Only set `VITE_GITHUB_OWNER`, `VITE_GITHUB_REPO`, or `VITE_GITHUB_BRANCH` if those ever change. **Never add API keys here.**
4. **Save and Deploy.** You get a URL like `https://tektizen-threads-automation.pages.dev`.
5. Recommended: **Settings → Builds → Build watch paths → Include paths:** `web/*`. Automation commits are also tagged `[CF-Pages-Skip]`, so they don't trigger rebuilds either way.

Preview with sample data anytime: add `?demo` to the URL (a yellow "DEMO DATA" banner appears; nothing is sent).

---

## Step 6: Create the dashboard login token

The website is public, but only someone holding this token can approve, edit, or generate.

1. GitHub → your avatar → **Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token**.
2. **Resource owner:** the owner of the repo (`tektizen`). If it's an organisation, the org may need to approve the token.
3. **Repository access:** *Only select repositories* → `tektizen-threads-automation`.
4. **Permissions → Repository permissions:**
   - **Actions:** Read and write
   - **Contents:** Read-only
   - (Metadata: Read-only is added automatically)
5. Expiration: 90 days is a good balance. You'll create a new one when it expires.
6. Open the dashboard → **Settings → GitHub connection** → paste the token → **Connect**.

The token stays in that browser tab only and is cleared when you close it. Keep a copy in a password manager.

---

## Step 7: Configure in the dashboard

**Settings** page:
1. **Publishing → Threads account ID:** paste the ID from step 4 → **Save publishing**.
2. Check **Approval mode** is **OFF** (human approval). Leave it that way until you trust the output.
3. Optional: **AI model**. `openrouter/free` picks any free model, so quality varies. After a few runs, look at **Automation Runs → Models** to see which free models produced good results, then pin one (a model ID ending in `:free`), either as default or just for the **Malay Localizer**.

Each save starts a "Dashboard Command" run. The **Activity** menu (top right) shows its progress, and the page refreshes when it finishes.

---

## Step 8: First run

1. **Actions → Daily Content Generation → Run workflow** (or wait for 08:00 MYT).
2. After about 2–4 minutes, open the dashboard **Approval Center**.
3. Approve, edit, or reject. Approving triggers **Publish Approved Content** automatically.
4. Check @tektizen on Threads.

If something fails, open **Automation Runs** in the dashboard (or the GitHub Actions log). Every step is logged.

---

## Step 9: Make the voice yours (the biggest quality win)

**AI Agents → Shared configuration → Style Examples**: replace the starter examples with 5–10 real posts in the exact tone you want. The Malay Localizer copies this voice more closely than anything else. Approved posts are added to its examples automatically over time.

---

## Schedules (Malaysia time)

| Workflow | When |
|---|---|
| Daily Content Generation | 08:00 daily |
| Publish Approved Content | right after approval, plus a safety sweep every 3 hours |
| Performance Analysis | 22:00 daily |

Change a schedule by editing the `cron:` line in `.github/workflows/*.yml` (cron is in UTC; MYT = UTC+8).

GitHub pauses scheduled workflows in repos with no activity for 60 days. The daily commits normally prevent this, but if schedules stop, re-enable them in the Actions tab.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Dashboard says "rate limit" | Connect your token (raises the limit from 60 to 5,000 requests/hour). |
| "Could not send command" | Token missing, expired, or without **Actions: Read and write**. |
| Generation run fails at OpenRouter | Check the key secret, the OpenRouter privacy setting, and whether the daily free-request limit was hit. |
| Item stuck in "Needs reconciling" | The publish outcome was uncertain. Check Threads, then use **Reconcile** in the Approval Center. It's never retried automatically, to avoid double posting. |
| Publishing blocked | Check the kill switch, the Threads account ID, and the max-posts-per-run setting. The run log names the exact reason. |
| Performance shows "unavailable" | Your Zernio plan lacks the Analytics add-on. |
