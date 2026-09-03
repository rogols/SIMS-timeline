# SIMS course timeline

This repository publishes a wide course illustration at:

<https://rogols.github.io/SIMS-timeline/timeline.png>

`timeline.png` is a manually managed static illustration.

An interactive, responsive alternative is published at:

<https://rogols.github.io/SIMS-timeline/timeline.html>

`timeline.html` is a self-contained HTML/CSS/JavaScript page. It reads the
public TimeEdit feed directly when opened, marks current course progression,
and explains activity categories through a legend and accessible date markers.

## How it works

1. `timeline.html` reads the public TimeEdit calendar directly in the browser.
2. `timeline.png` provides a static illustrated alternative.
3. `.github/workflows/update-timeline.yml` publishes `index.html`,
   `timeline.html`, and `timeline.png` to GitHub Pages after repository changes
   or when started manually. It does not modify any of those files.

The checked-in `index.html` remains the page shell. Canvas can embed either the
interactive HTML page or the stable direct image URL.

## Manual run

Open **Actions → Publish course timeline → Run workflow**. No repository secrets
are required because the TimeEdit feed is public and the workflow only deploys
the checked-in website files.

In **Settings → Pages**, set **Source** to **GitHub Actions**.
