# KC 13 Run Pool — Barbets.com

Static website for the O'Fallon 13 Run Pool. Results update automatically once a day.

## How it works
- `config.json` — everything you edit: season dates, payout, players, rotation seed, notices, social links.
- `scripts/build.py` — fetches every 13-run game this season from sportsdatabase.com, computes
  team assignments and payouts (same math as the old Excel workbook), writes `data.json`.
- `index.html` — the page. Reads `data.json`. Print button prints standings + weekly grid.
- `.github/workflows/update.yml` — runs `build.py` every morning and commits the new `data.json`.

## Posting a notice
Edit `config.json` on GitHub (pencil icon), add an entry under `"notices"`, commit. Example:
```json
{ "date": "2026-10-15", "title": "Steak dinner", "text": "Sat Nov 7, 6pm at ..." }
```
Remove the entry (or leave `"notices": []`) to clear it. The page updates within a minute or two.

## New season checklist (once a year)
In `config.json`:
1. Change `season`, `opening_date`, `last_date`, `payout_per_week`, `entry_fee`.
2. Replace the `players` list (order matters: in week 1, player 1 gets the first team
   alphabetically, player 2 the second, and so on; each week everyone moves down one team).
3. Delete the `"rotation_seed": 21,` line. It only exists to keep the 2026 assignments as they were.
Then go to Actions → "Update 13 Run Pool results" → Run workflow.

The finished season is frozen automatically in `history.json` and shows under "Past Seasons".
`history.json` can also be edited by hand (names, totals) if an old year needs a correction.

## Running locally
`python scripts/build.py` (live) or `python scripts/build.py --from saved_page.html`.
