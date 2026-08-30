# ShopAlert

> English (default) · [繁體中文](README.zh-TW.md)

ShopAlert is a Flask web application for creating a searchable, evidence-led community record of shops involved in reported controversies. Users can register, search by keyword or proximity, and publish a report with shop details and at least one supporting image or video.

Important: reports are community-submitted allegations. A production deployment should add a moderation workflow, reporting/appeal tools, retention rules, and legal/privacy review appropriate to its jurisdiction.

## Features

- Sign-up with a unique username and email, login with either identifier, remembered sessions, and logout
- Persistent failed-login throttling scoped to an account-identity/client-IP pair
- Optional Cloudflare Turnstile checks on both login and sign-up, with mandatory server validation when configured
- Search across shop name, address, hashtags, and report text
- Nearby search using browser geolocation and a selectable 2–100 km radius
- Manual shop name/address entry
- Online-shop reports that do not require a physical address and are excluded from nearby results
- Optional Google Place Autocomplete that follows the selected interface language and fills editable name, localized address, coordinates, and Place ID fields
- Required multi-file evidence upload with image and video support; repeated chooser and drag-and-drop selections append to the current list, render responsive pre-publish thumbnails, and let each file be rotated before publishing
- Cached WebP thumbnails generated on first request and served to report cards and gallery rails, so listings load a fraction of the original upload size
- Report cards whose excerpt always occupies the same three lines, regardless of how long or short the report is, so every card in a row lines up
- Up to 10 optional, searchable hashtags per report, with Enter/comma-to-label input, removable chips, popular tags, and locale-specific starter suggestions
- Debounced similar-report detection while entering a shop name or location, with a live count in the checker icon and in-page modal previews that preserve the draft
- Up to 10 optional controversy/source URLs per report, with SSRF checks, optional Cloudflare URL Scanner verdicts, a cached server screenshot, and confirmation before leaving ShopAlert
- Up to 10 optional related shops per report, either linked to an existing ShopAlert report through a debounced search or typed manually for shops that are not on ShopAlert
- Stable GUID identifiers in every public report URL, with redirects for legacy numeric links
- A private “My reports” page where each user can review and edit only their own submissions
- A profile page for changing the profile picture and password and reviewing the account’s reports
- An administrator dashboard for archiving/restoring or permanently deleting reports, resetting passwords, and banning/restoring users, with destructive controls clearly marked and the administrator's own account protected from banning
- Optional environment-managed administrator credentials that create the account at startup and keep its username and password in sync with the configured values
- Published timestamps plus last-updated timestamps shown only after a report is edited and localized to the visitor's timezone
- Evidence editing that supports additions and removals while always retaining at least one proof file
- Editable evidence filenames for new and existing media while preserving the real file type and randomized storage name
- Persistent media reordering with up/down buttons or drag-and-drop for new reports and edits, including a single order across existing and newly added evidence
- A report-specific administrator contact modal and protected review inbox
- Optional Facebook, Instagram, Threads, TikTok, and other official profile links
- Responsive, accessible UI with clear allegation and responsible-reporting notices, plus a scroll-aware progress indicator on the report form
- Branded ShopAlert favicon, multi-size browser icon, Apple touch icon, and installable web-app icons
- English (en-US) and Traditional Chinese (zh-TW) interface selector, with an IP-country default when no preference has been saved
- Separate language, appearance, and color selectors in the profile and footer, offering English/Traditional Chinese, light/dark/system, and coral/yellow/purple
- Public bilingual introduction, update-history, and license/attribution pages
- Public bilingual privacy policy describing data collection, public submissions, location search, browser storage, third-party services, retention, and user choices
- CSRF protection, password hashing, safe redirect checks, randomized upload names, and upload type/size checks

## Technology

- Python 3.10+
- Flask, Flask-SQLAlchemy, Flask-Login, and Flask-WTF
- SQLite by default; another SQLAlchemy database URL can be supplied
- Server-rendered Jinja templates and vanilla CSS/JavaScript
- Pillow for cached listing thumbnails
- FFmpeg for rotating uploaded videos

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp .env.example .env
python run.py
```

Install FFmpeg through your operating system's package manager to enable video rotation. The Docker image includes it automatically.

Open `http://127.0.0.1:5000`. The database and uploaded files are created under `instance/`.

Generate a strong secret before any shared or production deployment:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Then put the result in `.env` as `SECRET_KEY`. Never commit `.env`.

## Run with Docker Compose

The production-style image uses `tiangolo/uwsgi-nginx-flask:python3.12`, includes Playwright Chromium, and is named `shopalert-holey-cc:local` by Compose.

```bash
cp .env.example .env
docker compose up --build -d
docker compose ps
docker compose logs -f app
```

Open `http://127.0.0.1:8080`. SQLite data, uploads, and link-preview artifacts are persisted in the named volume `shop-alert-data` under `/instance`. The container exposes an HTTP health check against port 8080.

```bash
docker compose down
```

`docker compose down` does not remove the named volume unless `--volumes` is explicitly supplied. Back up the volume before migration or removal. Local operational helpers, deployment scripts, and database backups belong under the `private/` directory, which is excluded from both Git and the Docker build context, and are not required for the repository setup above.

## Environment variables

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `SECRET_KEY` | Production | Development-only value | Signs sessions and CSRF tokens |
| `DATABASE_URL` | No | `sqlite:///shop_alert.db` | SQLAlchemy database URL |
| `HOME_RECENT_REPORTS_COUNT` | No | `9` | Reports per home-page batch: the first batch rendered with the page and each further batch loaded while scrolling |
| `GOOGLE_MAPS_API_KEY` | No | Empty | Enables Google Place Autocomplete |
| `ADMIN_EMAIL` | Recommended | Empty | Account granted the report moderation, user management, and contact-inbox dashboard |
| `ADMIN_PASSWORD` | No | Empty | With `ADMIN_EMAIL`, creates the admin account at startup if missing and keeps its login password in sync (min 8 characters) |
| `ADMIN_USERNAME` | No | Empty | With `ADMIN_EMAIL`, forces the admin account's unique login username (3–30 letters, numbers, or underscores) |
| `LOGIN_MAX_ATTEMPTS` | No | `5` | Failed attempts allowed within the retry window |
| `LOGIN_ATTEMPT_WINDOW_MINUTES` | No | `15` | Window used to count failed login attempts |
| `LOGIN_LOCKOUT_MINUTES` | No | `15` | Time an account-identity/client-IP pair must wait after reaching the limit |
| `TURNSTILE_SITE_KEY` | Production | Empty | Public Cloudflare Turnstile widget key |
| `TURNSTILE_SECRET_KEY` | Production | Empty | Private key used only for server-side Turnstile validation |
| `TURNSTILE_EXPECTED_HOSTNAME` | Recommended | Empty | Hostname required in successful Turnstile responses |
| `LINK_PREVIEW_TIMEOUT_SECONDS` | No | `15` | Browser timeout for generating an external-link screenshot |
| `LINK_PREVIEW_SETTLE_MS` | No | `1500` | Additional page-rendering time before capture |
| `LINK_PREVIEW_CACHE_HOURS` | No | `24` | How long a generated screenshot remains fresh |
| `CLOUDFLARE_URL_SCANNER_ACCOUNT_ID` | Recommended | Empty | Cloudflare account that owns the URL Scanner token |
| `CLOUDFLARE_URL_SCANNER_API_TOKEN` | Recommended | Empty | Secret API token with Account → URL Scanner → Edit permission |
| `CLOUDFLARE_URL_SCANNER_REQUEST_TIMEOUT_SECONDS` | No | `10` | Timeout for each Cloudflare API request |
| `CLOUDFLARE_URL_SCANNER_RESULT_TIMEOUT_SECONDS` | No | `40` | Maximum time to wait for a scan result |
| `CLOUDFLARE_URL_SCANNER_POLL_INTERVAL_SECONDS` | No | `10` | Delay between result checks; Cloudflare recommends 10–30 seconds |
| `CLOUDFLARE_URL_SCANNER_CACHE_HOURS` | No | `24` | How long a Cloudflare verdict is reused |
| `MAX_CONTENT_LENGTH_MB` | No | `50` | Maximum total request/upload size in MB |

### IP-based localization and timezones

When no language preference has been saved, ShopAlert reads Cloudflare's `CF-IPCountry` header. Visitors from Taiwan, Hong Kong, or Macau default to Traditional Chinese; all other and unknown locations default to English. A visitor's explicit language selection is stored in the signed session and always takes priority.

Enable Cloudflare **IP Geolocation** so the origin receives `CF-IPCountry`. Enabling the **Add visitor location headers** Managed Transform also supplies `CF-Timezone`, which ShopAlert uses for its server-rendered timestamp fallback. JavaScript then formats timestamps in the browser's actual timezone, which handles travel, VPNs, and device settings more accurately. If neither signal is available, timestamps remain in UTC. See Cloudflare's [IP geolocation guide](https://developers.cloudflare.com/network/ip-geolocation/) and [Managed Transforms reference](https://developers.cloudflare.com/rules/transform/managed-transforms/reference/).

### Controversy-link screenshots

ShopAlert uses Playwright Chromium to generate a screenshot when a visitor first previews a controversy link. Screenshots are cached under `instance/link_previews/`; subsequent visitors receive the cached PNG until `LINK_PREVIEW_CACHE_HOURS` expires. The external site is contacted by the ShopAlert server, not embedded in the visitor's browser, so sites such as Threads that reject iframes can still be previewed.

When both `CLOUDFLARE_URL_SCANNER_ACCOUNT_ID` and `CLOUDFLARE_URL_SCANNER_API_TOKEN` are set, ShopAlert first submits an **unlisted** scan, polls for its result, and checks `verdicts.overall.malicious`. A malicious result is blocked before Playwright starts. An API error, timeout, failed scan, or inconclusive response also fails closed, so the visitor cannot continue through the preview dialog. Clean and malicious verdicts are cached in `instance/link_previews/*.scan.json`; the UI deliberately says “no known threat detected,” not “safe,” because a scanner verdict is not a guarantee.

Create a custom Cloudflare API token with **Account → URL Scanner → Edit**, copy the account ID and token into `.env`, and restart the app. Configure both values or neither; partial configuration stops application startup. With both empty, local development retains the existing public-network/SSRF validation and screenshot flow but clearly labels the Cloudflare check as not configured. See Cloudflare's official [URL Scanner guide](https://developers.cloudflare.com/radar/investigate/url-scanner/) and [Create URL Scan API](https://developers.cloudflare.com/api/resources/url_scanner/subresources/scans/methods/create/).

The full submitted URL is sent to Cloudflare. Do not put private tokens, session IDs, or other secrets in controversy-link URLs. Cloudflare documents a 12-month retention period for successful scans and 30 days for failed scans; “unlisted” keeps a scan out of public recent/search results, but anyone who knows its scan ID can access it.

The worker accepts only HTTP(S) on ports 80/443, rejects URL credentials, and checks every resolved address so local, private, loopback, link-local, reserved, and otherwise non-public networks are blocked. Browser requests are intercepted and service workers are disabled. Production deployments should additionally apply an outbound firewall that prevents the application/browser process from accessing internal networks; application-level DNS checks cannot replace network-level egress controls against every DNS-rebinding scenario. At larger scale, move screenshot generation to a resource-limited background worker instead of a web request.

After installing Python dependencies, install the matching browser build:

```bash
playwright install chromium
```

Linux containers may also need Playwright's documented system packages, installed during image construction with `playwright install --with-deps chromium`.

### Login protection and Cloudflare Turnstile

Failed login state is stored in the database as a SHA-256 key derived from the normalized account identity and `request.remote_addr`; a recognized username is canonicalized to its account email so switching between username and email does not create a second retry allowance. The raw identifier/IP pair is not stored in the throttle table. ShopAlert returns HTTP `429` with a `Retry-After` header while the pair is locked. Configure your reverse proxy and Flask proxy handling carefully so `request.remote_addr` represents the intended client—ShopAlert deliberately does not trust `X-Forwarded-For` by default.

Create a Turnstile widget in Cloudflare, then set both `TURNSTILE_SITE_KEY` and `TURNSTILE_SECRET_KEY`. Setting only one causes startup to fail instead of silently running without CAPTCHA protection. `TURNSTILE_EXPECTED_HOSTNAME` should match the production hostname (for example, `shopalert.example`). With both keys empty, Turnstile is disabled for local development. The login and sign-up forms send tokens to Cloudflare's Siteverify endpoint; the backend requires a successful result and the matching `login` or `signup` action before processing credentials.

Cloudflare provides public test keys for automated/local integration testing. See the official [Turnstile testing guide](https://developers.cloudflare.com/turnstile/troubleshooting/testing/) and [server-side validation documentation](https://developers.cloudflare.com/turnstile/get-started/server-side-validation/).

### Google Place Autocomplete

Manual entry always works. To enable autocomplete:

1. Create a Google Cloud project with billing enabled.
2. Enable **Maps JavaScript API** and **Places API (New)**.
3. Create a browser API key and restrict it to the site’s HTTP referrers and the required APIs.
4. Set `GOOGLE_MAPS_API_KEY` in `.env` and restart Flask.

Autocomplete suggestions follow ShopAlert's current `en-US` or `zh-TW` language. Selecting a Google Place stores both localized formatted addresses, so report cards, details, and edit forms switch addresses with the interface language. Manually entered addresses remain user-controlled text and use the same text in both interfaces.

The implementation uses the current `PlaceAutocompleteElement` and dynamic Places library import. Google Maps Platform usage may incur charges and is governed by Google's terms.

### Hashtags and similar-report checks

Typing a hashtag and pressing Enter—or typing a comma—converts it into a removable label. Reports accept up to 10 unique hashtags, each containing 1–30 letters, numbers, or underscores. Starter suggestions follow the current interface language (`en-US` or `zh-TW`); popular hashtags preserve the text originally submitted by users.

On report creation and editing, the shop-name/address fields trigger a 450-millisecond debounced request to the authenticated `/api/reports/similar` endpoint. Matching considers fuzzy shop names, the original and localized addresses, exact Google Place IDs, and nearby coordinates. The circular checker icon displays the current result count. Clicking the checker opens up to five ranked matches in an in-page dialog; selecting one loads its detail page in a sandboxed same-origin preview without opening a tab or discarding the draft. Edit forms exclude the report currently being edited.

Similarity is an advisory prompt, not a uniqueness guarantee. A zero count means no report passed the current matching threshold; it does not prove that no related report exists under substantially different data.

### Related shops

The optional related-shops section accepts up to 10 entries per report. Typing at least two characters queries the authenticated `/api/reports/search` endpoint, which matches shop names and both localized addresses and returns up to eight non-archived reports; selecting one stores its GUID so the detail page always shows the linked report's current name and address. Shops that are not on ShopAlert can be typed in as a name (2–180 characters) and an optional address or public link (up to 500 characters).

Entries are stored on the report itself, so a linked report that is later archived or deleted simply stops appearing instead of leaving a broken link. A report cannot list itself, and edit forms exclude the report being edited from search results.

## Tests

```bash
pytest
```

The test suite covers authentication throttling, Turnstile enforcement, access control, validation, report creation with evidence, hashtag behavior, related-shop linking, similar-report ranking, detail/media delivery, keyword search, and nearby filtering. It also covers the Cloudflare URL Scanner client and the Docker deployment configuration.

## Information and administration pages

- `/updates` — bilingual product and security update timeline
- `/introduction` — bilingual introduction, workflow, and responsible-use guidance; linked from the footer
- `/privacy` — bilingual description of data collection, public content, external services, retention, and user choices
- `/licenses` — third-party licenses, service terms, and development acknowledgments
- `/profile` — signed-in user’s profile picture, password, and report management page
- `/admin` — report and user management dashboard for the account matching `ADMIN_EMAIL`
- `/admin/report-contacts` — protected inbox for the account matching `ADMIN_EMAIL`

To activate administration, set `ADMIN_EMAIL`, then sign up or log in with that exact email address. Alternatively, also set `ADMIN_PASSWORD`: at startup the admin account is created if it does not exist, and its login password is reset to the configured value whenever they differ — so a password changed through the profile page reverts on the next restart while `ADMIN_PASSWORD` remains set. `ADMIN_USERNAME` works the same way for the admin account's username, letting the administrator log in with either the configured username or the email address; startup fails if another account already uses that username. Anyone who can read `.env` can log in as the administrator; protect the file accordingly. The configured administrator account cannot ban itself. Password resets take effect immediately; deliver replacement passwords to users through a separate trusted channel.

## Production checklist

- Run behind a production WSGI server and HTTPS reverse proxy (the provided Docker image already uses uWSGI behind nginx).
- Isolate the screenshot browser and enforce outbound firewall rules that deny internal/private networks.
- Use PostgreSQL or another managed database, object storage for uploads, backups, and malware scanning.
- Set a strong `SECRET_KEY`, secure cookie settings, trusted proxy configuration, and strict upload/storage permissions.
- Add email verification, rate limiting, account recovery, moderation queues, takedown/appeal paths, audit logs, and abuse monitoring.
- Add terms, privacy policy, consent and media retention rules; avoid exposing personal data or unverified claims without review.
- Consider server-side media signature inspection and transcoding instead of relying only on file extensions and MIME types.

## License

ShopAlert is released under the [MIT License](LICENSE). Third-party assets and services remain subject to their own licenses and terms; see the in-app `/licenses` page.
