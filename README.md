# SIMS course timeline

This repository publishes a wide, automatically updated course timeline at:

<https://rogols.github.io/SIMS-timeline/timeline.png>

The image is generated from the public TimeEdit calendar every day at **06:00
Europe/Stockholm** and is also regenerated after pushes to `main` or when the
workflow is started manually.

An interactive, responsive alternative is published at:

<https://rogols.github.io/SIMS-timeline/timeline.html>

`timeline.html` is a self-contained HTML/CSS/JavaScript page. It reads the
public TimeEdit feed directly when opened, marks current course progression,
and explains activity categories through a legend and accessible date markers.

## How it works

1. `.github/workflows/update-timeline.yml` downloads the public calendar.
2. `generate_timeline.py` parses its course events and renders a deterministic
   2400 × 600 PNG with Pillow.
3. The workflow commits `timeline.png` only if its bytes changed.
4. The same workflow deploys `index.html`, `timeline.html`, and `timeline.png`
   to GitHub Pages.

The checked-in `index.html` remains the page shell. Canvas can keep using the
stable direct image URL while the file behind that URL changes.

## Manual run

Open **Actions → Update course timeline → Run workflow**. No repository secrets
are required for the current renderer because the TimeEdit feed is public and
GitHub supplies the short-lived `GITHUB_TOKEN` automatically.

Repository **Settings → Actions → General → Workflow permissions** must allow
read and write access. In **Settings → Pages**, set **Source** to **GitHub
Actions**.

## Local test

```text
python -m pip install -r requirements.txt
python -m unittest -v
set TIMEEDIT_ICS_URL=https://cloud.timeedit.net/...calendar....ics
python generate_timeline.py
```

`--date YYYY-MM-DD` makes a run reproducible for a specific Stockholm date.

## Optional future AI-generated artwork

The current workflow does not call an AI service. A future AI-image variant
would be a separate, optional generation step and would require an API account,
API billing, a repository secret such as `OPENAI_API_KEY`, cost controls, and a
deterministic fallback to the programmatic renderer. A ChatGPT subscription is
not used by GitHub Actions and does not supply API credits.
