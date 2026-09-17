# Bellwether — Project Context

## What this is
A single-file, offline-capable stock research app: watchlist, portfolio
tracker, screener and trade journal. No backend, no accounts, no secrets in
the repo. Everything a user enters — holdings, journal entries, API keys —
lives in that browser's localStorage and is never sent anywhere except to the
price provider it belongs to.

It shows data and the user's own past reasoning. It does not recommend trades,
and the footer says so.

## Architecture
- `index.html` at the root is **the single source of truth**. A clean file with
  no PWA plumbing, meant to be double-clicked and run from `file://`.
- `python build.py` copies it into `docs/` with the manifest link, Apple meta
  tags and service worker registration injected, and writes
  `manifest.webmanifest`, `sw.js`, `.nojekyll` and the icons.
- Never edit `docs/index.html` directly — edit the root file and rebuild.
- `VERSION` at the top of `build.py` drives the service worker cache name.
  **Bump it with every published change** (+0.1 for features and fixes, next
  whole number for milestones) or browsers will serve the old cached copy.
- Icons are drawn by a pure-Python PNG encoder in `build.py` (no Pillow). They
  are kept between builds; set `BW_ICONS=1` to redraw them.

## Data providers
Both are free tier, both optional, both keyed by the user in Settings.

- **Finnhub** — quotes, company profile, fundamentals, news, symbol search.
  60 calls a minute. The client queue in `Limiter` paces to 55.
- **Twelve Data** — daily price history for the charts. 8 a minute, 800 a day,
  paced to 7. Each symbol's history is cached for a day.

Finnhub's own candle endpoint moved behind a paid plan, which is the only
reason a second provider exists. If that ever changes, charts could come from
Finnhub and Twelve Data could be dropped.

The service worker deliberately does **not** cache provider responses — only
same-origin app files. Stale quotes are worse than no quotes.

## Supabase sync (optional)
Signed out, or with `SUPA` unfilled, none of this runs and every feature still
works — the app is local first and stays that way.

- `schema.sql` creates four tables, all prefixed `bw_` so they can share a
  project with another app's tables. Run it once in the SQL Editor.
- Every table is `primary key (user_id, id)` with row-level security, so the
  public anon key in the page can only ever touch the signed-in user's rows.
- **No Supabase SDK.** Auth and PostgREST are called with plain `fetch`, because
  a CDN dependency would break the offline `file://` copy. Roughly 200 lines in
  the "supabase sync" block of `index.html`.
- Sync is last-write-wins per row on `updated_at`, with `deleted_at` tombstones
  so a delete on one device does not get resurrected by another device's push.
  Local rows carry `updatedAt` and a `_d` dirty flag; `S.tombs` holds pending
  deletes until they are pushed.
- **Every mutation must go through** `addWatch`, `delWatch`, `putLot`, `delLot`,
  `putJournal`, `delJournal` or `touchPrefs`. Writing to `S.watch` / `S.lots` /
  `S.journal` directly and calling `save()` will persist locally but never sync.
- The **API keys are deliberately not synced**. They stay in the browser that
  entered them, so each device is entered once.
- To wire a project up, fill `SUPA.url` and `SUPA.anon` at the top of the
  sync block from Settings -> API, then rebuild.

### Auth
Email and password only, with confirmation switched on. Two things are easy to
break here:

- **`handleAuthRedirect()` must run at boot.** Supabase returns confirmation
  and password-reset links with the session in the URL fragment. Without it the
  reset link is a dead end — the user lands on the app and nothing happens.
  It consumes the fragment, strips it from the address bar, and for a recovery
  link opens `newPasswordModal()`.
- **The redirect allow-list is server-side.** `auth.site_url` and
  `auth.additional_redirect_urls` live in `supabase/config.toml` and are applied
  with `supabase config push`. If a new host is added, add it there or its
  email links will bounce to the wrong origin.

`config push` has no way to push a single key: it pushes the whole managed
config, so always run `supabase config pull` then `supabase config diff` first
and read the change list before pushing. A `config diff` that fails prints a
JSON object with `_tag: "Error"` and no changes, which is easy to mistake for
"nothing to do" — check for that field.

A failed token refresh clears the session and re-renders on purpose, so the app
never sits there looking signed in while every sync quietly fails.

**The built-in mail service is capped at two emails an hour for the whole
project** (`auth.rate_limit.email_sent = 2`). A sign-up confirmation plus one
reset request exhausts it, and the API then returns
`over_email_send_rate_limit`. There is a second, separate throttle per address
that returns "you can only request this after N seconds". These are different
limits and must not be reported with the same message — telling someone to wait
a minute when they are actually capped for the hour sends them into a loop that
cannot succeed. That happened once already.

To get a user in while the cap is hit, mint a link with the admin API instead,
which does not send email and does not touch the quota:
```
POST /auth/v1/admin/generate_link   (service_role key)
{"type":"recovery","email":"…","options":{"redirect_to":"https://bellwether-5uj.pages.dev/"}}
```
The long-term fix is connecting a real SMTP sender, which removes the cap.

Password reset is two screens, both separate from the sign-in form:
`resetRequestModal()` asks for the address, and the emailed link opens
`newPasswordModal()`. The "if that address has an account" wording is
deliberate — naming which addresses exist would let anyone test emails against
the project.

**Field styling is keyed to input types by name.** The base input rule lists
`text`, `number`, `date`, `password`, `email`, `search`, `tel` and `url`. A new
input type that is not in that list silently falls back to the browser default,
which is a white box on this dark theme. That is exactly how the email fields
broke once already.

## Design
**Obsidian and platinum.** Near-black neutral base (`#0a0a0b`) with a single
platinum accent (`#e8e8ec`). Chosen over four alternatives for "clean, modern,
premium", and deliberately unlike the other four projects, so do not drift it
back towards the usual blue, purple or orange house palette.

The treatment matters as much as the palette, and an earlier glassmorphism pass
was removed to get here. Hold the line on:

- **Flat surfaces.** No backdrop blur, no frosted panels, no noise overlay, no
  colour washes. One barely-there radial lift at the top of the page is the
  only gradient in the app.
- **Hairline borders** (`--line`, white at 7.5%) and tight radii (12px cards,
  9px controls). Depth comes from a 1px shadow at most.
- **Colour is spent only where it carries meaning.** Green and red belong to
  gains and losses and nothing else; the platinum accent marks what is
  actionable. Everything else is a neutral, and hierarchy is carried by weight
  and space.
- Because the theme is near-monochrome, two greys cannot be told apart in a
  chart. The 200 day average is **dashed** for that reason — pattern, not
  brightness. Do not "fix" this by tinting it.

### Motion
Durations and easings are tokens (`--dur-fast`, `--dur`, `--dur-slow`,
`--ease`, `--ease-out`). Everything animates `transform` and `opacity` only, so
nothing in the app triggers layout while moving. `prefers-reduced-motion` is
honoured globally and the chart's draw-in checks it in JS as well.

Three things here are load-bearing and easy to undo by accident:

- `html { scrollbar-gutter: stable }`. Opening a modal sets `body` overflow to
  hidden; without the reserved gutter the entire page jolts sideways as the
  scrollbar vanishes. That was the single worst piece of jank.
- **`render(animate)` only animates when passed `true`, and only `go()` does
  that.** `render()` is called on every save, so animating unconditionally
  turns ordinary edits into a light show.
- The chart's draw-in needs `void pl.getBoundingClientRect()` between setting
  the start offset and the end offset. The path is created in the same frame,
  so without forcing that style flush the browser has no start value and snaps
  straight to the end — it silently does nothing rather than erroring.

The tab underline is one travelling element (`#tabInk`), positioned by
`moveTabInk()` on tab change, at boot and on resize. Its `init` class suppresses
the transition for the first placement so it does not fly in from the left.

All chart and sparkline colours are read from the CSS variables via `CSSV()`,
so a palette change is a token change and never a hunt through drawing code.
The icon in `build.py` carries the same palette and must be regenerated with
`BW_ICONS=1` if the tokens move.

## Hosting
No secrets, no backend — safe as a public repo.

- **Primary: Cloudflare Pages** → https://bellwether-5uj.pages.dev/ (project
  `bellwether`, production branch `main`). The plain `bellwether.pages.dev`
  was already taken globally, hence the suffix. Deployed by **direct upload**
  of `docs/` via wrangler, which is already OAuth-authenticated locally.
- **Mirror: GitHub Pages** → https://arzzerry.github.io/bellwether/ (serves
  `/docs` on `main`, auto-updates on push).

Publish a change, updating both hosts:
```
python build.py
git add -A && git commit -m "..." && git push
wrangler pages deploy docs --project-name bellwether --branch main --commit-dirty true
```

## Local development
A dev server config lives in the parent folder at `.claude/launch.json`
(`python -m http.server 8811 --directory bellwether`). Serving over http
matters: opened as a `data:` URL, localStorage is blocked by the browser and
nothing saves.

## Things worth knowing
- The portfolio models each purchase as a **lot** with its own sell history, so
  partial sales and realised profit and loss work per lot rather than per
  symbol. Fees are folded into the per-share cost basis.
- The screener runs over a bundled list of about 140 large companies plus the
  user's own names. There is no free full-market screening API; this limit is
  stated in the app rather than hidden.
- Currency is a cosmetic symbol only. There is no conversion, so mixing markets
  in one portfolio mixes their currencies too.
