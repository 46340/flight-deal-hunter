# Flight Deal Hunter

A personal flight price tracker. You draw circles around airports on a map, pick dates and a price cap, and a scraper checks Google Flights three times a day. Deals at or under your cap show up on a small website you can open on your phone.

Everything runs for free on GitHub: the scraper on GitHub Actions, the website on GitHub Pages, and all data as JSON files in this repository.

> **Everything in this repository is public.** That includes your saved searches (airports, dates, price cap) and all results. Do not put anything private in it. Your GitHub token is never stored in the repository.

## How it works

1. You create a search on the website: origin airports, destination airports, dates, a price cap.
2. Saving commits `config/searches.json` to this repository using your GitHub token.
3. At 05:00, 12:00 and 19:00 UTC, GitHub Actions runs the scraper:
   - **Stage 1:** it looks up the cheapest one-way fare for every origin, destination and date.
   - **Stage 2:** it combines them into trips and re-checks the most promising round trips as a single ticket, which is often cheaper.
4. Results are committed to `data/results/` and the website is republished.

Each trip is shown as either "Single ticket" or "2 separate tickets". Separate tickets are not protected: if the first flight is late and you miss the second, the second airline owes you nothing.

## Setup

These steps assume you have a GitHub account. No programming needed.

### 1. Create the repository

1. Open this repository on GitHub and click **Use this template** or **Fork** (or create a new **public** repository and upload these files).
2. The repository must be **public** for free GitHub Pages and unlimited Actions minutes.

### 2. Turn on GitHub Pages

1. In the repository, go to **Settings > Pages**.
2. Under **Build and deployment > Source**, choose **GitHub Actions**.

### 3. Allow workflows to write

1. Go to **Settings > Actions > General**.
2. Under **Workflow permissions**, choose **Read and write permissions** and click **Save**.

### 4. Publish the site for the first time

1. Go to the **Actions** tab. If asked, click **I understand my workflows, go ahead and enable them**.
2. Click **Publish site** in the list on the left, then **Run workflow > Run workflow**.
3. After a minute or two, your site is at `https://<your-username>.github.io/<repository-name>/`. The link also appears in **Settings > Pages**.

### 5. Create a token so the website can save searches

The website saves your searches by committing a file to this repository. For that it needs a fine-grained personal access token that can only touch this one repository.

1. On GitHub, click your profile picture > **Settings > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token**.
2. **Token name:** for example `flight-deal-hunter`.
3. **Expiration:** your choice (for example 1 year). You will need a new one when it expires.
4. **Repository access:** **Only select repositories**, then pick this repository.
5. **Permissions > Repository permissions > Contents:** **Read and write**. Leave everything else as it is.
6. Click **Generate token** and copy it. It starts with `github_pat_`.
7. Open your site, go to **Settings**, paste the token, check that owner and repository are filled in, and click **Save and test**. You should see "Connected".

The token is stored only in this browser on this device (localStorage). Do this once on each device you use. Use **Forget token** to remove it.

Note: all GitHub Pages sites under your username share the same browser storage. Only publish pages you trust under that username.

### 6. Create your first search

1. Click **New**.
2. Give the search a name.
3. **Origin:** type an airport code or city (or click an airport on the map and choose **Origin center**), then set the radius. Every airport inside the circle is listed with its distance. Untick the ones you do not want.
4. **Destination:** the same.
5. **Trip:** choose return or one-way and fill in:
   - the date window: earliest outbound date and latest return date
   - for return trips, the minimum and maximum stay
   - the price cap and currency
   - how many days to keep tracking
6. Check the **Query budget**. If the search is too big, saving is blocked and the box tells you what to cut (fewer airports or a shorter window).
7. Click **Save search**. It is included in the next run.

### 7. Run it now instead of waiting

1. Go to the **Actions** tab and click **Scrape flights** on the left.
2. Click **Run workflow > Run workflow**.
3. A run takes about 5 seconds per query (the budget box shows the estimate). When it finishes, the site is republished. Open **Searches > Results** to see the deals.

### 8. Optional: paid fallback API

If Google blocks the scraper, it can fall back to a paid fare API. This is **off by default** and capped at a total spend (default $10) tracked in `data/spend.json`.

1. Get an API key from the provider (see `config/settings.json`, `paid_fallback`).
2. In the repository, go to **Settings > Secrets and variables > Actions > New repository secret**. Name it `IGNAV_API_KEY` and paste the key.
3. In `config/settings.json`, set `"enabled": true` under `paid_fallback`.

The fallback is only used when the fallback is enabled **and** Google has blocked the run.

## Day to day

- **Pause, resume, edit or delete** a search from the **Searches** page. Searches stop automatically after their tracking period; use **Edit or renew** to restart one.
- **Per-run cap:** the maximum number of queries per run, for all active searches together. The default is 800, which takes about an hour. Change it under **Settings > Scraper**. Larger runs take longer and are more likely to be blocked.
- **Run log:** every run is listed on a search's results page with status **ok**, **partial** (some queries failed), **blocked** (Google stopped answering, so the run stopped early) or **skipped** (over the per-run cap).
- **When a run is blocked:** nothing is marked "no longer available", and the price chart skips that run.
- **Scheduled runs:** GitHub may start them a few minutes late. GitHub also turns off scheduled workflows in a repository with no activity for 60 days. The scraper's own commits normally count as activity. If runs stop, open the **Actions** tab and re-enable **Scrape flights**.

## Limits

- 1 adult, economy only. No filters for stops, bags, flight duration or self-transfer yet.
- Trips that return to a different airport pair (for example out CPH to JFK, back IAD to HAM) are always priced as 2 separate tickets. Google Flights does not include multi-city results in the page the scraper reads.
- Prices come from Google Flights at the time of the run and can change at any moment.

## For developers

```
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest                    # Python tests
node --test tests/js/*.test.mjs                # JavaScript tests
.venv/bin/python -m scraper.run --dry-run      # planned searches and query count
.venv/bin/python -m scraper.run --mock         # full run with fake prices, no network
.venv/bin/python scripts/serve.py              # preview the site at http://localhost:8000
.venv/bin/python scripts/build_airports.py     # refresh web/data/airports.json from OurAirports
```

- **Running the real scraper from the EU:** Google shows a cookie consent page there. Set `FDH_EU_CONSENT=1` to send its "reject all" choice.
- **Probe Google Flights workflow:** a manual diagnostic. Run it with `probe` mode to check raw Google pages, or with `smoke` mode for a small real pipeline run on `config/searches.smoke.json`.

Code map:

| Path | What it does |
|---|---|
| `scraper/planner.py` | turns searches into one-way legs and estimates query counts |
| `scraper/combine.py` | builds trips and picks which to re-price |
| `scraper/providers/` | Google Flights, mock, and (later) the paid API |
| `scraper/store.py` | result files |
| `scraper/hooks.py` | post-run hook for future notifications |
| `web/` | the static site (plain ES modules, no build step) |
| `.github/workflows/` | scrape, publish, tests, probe |

Airport data: [OurAirports](https://ourairports.com/data/) (public domain). Map tiles: [OpenStreetMap](https://www.openstreetmap.org/copyright).
