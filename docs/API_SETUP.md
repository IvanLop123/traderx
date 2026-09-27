# TraderX provider setup

Documentation checked on 2026-09-25 UTC (2026-09-24 in America/Detroit). This is a partial account setup with working free public connections. Read `API_STATUS.md` before relying on any integration.

## Run now

From the permanent `TraderX/` repository root (currently `/Users/ivanlopez/Desktop/TraderX`):

```sh
./check_environment.command
./test_apis.command
```

The equivalent test command is `.venv/bin/python scripts/api_tests/test_all_providers.py`. It writes sanitized evidence to `docs/LAST_TEST_RESULTS.json`. Exit 0 means the configured **required checks** passed, not that every provider is configured. Exit 1 means a required provider did not pass; exit 2 means unsafe settings or invalid arguments. Required defaults are Hyperliquid public, Coinbase public and GS Quant. Kalshi demo availability is optional. Change `REQUIRED_PROVIDERS` to promote a provider once you need it.

To rerun only a provider after adding its key:

```sh
./test_apis.command --only FRED --required FRED
```

Targeted runs write `LAST_TARGETED_RESULTS.json` and preserve the full-suite report. Provider IDs are in `test_all_providers.py` and the status table. The prose status document was refreshed during pre-build cleanup; JSON is the latest run evidence. Optional failures remain visible but do not fail the command. Neither test script changes credentials.

## Exact remaining user steps

Real keys cannot be issued locally for account-based services. Registration, legal terms, email verification and financial account onboarding must be completed by you, as requested. No account was created this session. No existing credentials were overwritten.

| Provider | Your next step | Save locally |
|---|---|---|
| SEC EDGAR | Supply your identifying name/application and real contact email. No signup or key. | `SEC_USER_AGENT` in `.env`, using an identifying name followed by the contact email. |
| Alpaca | [Sign in or create a paper-only account](https://app.alpaca.markets/). Complete email verification/terms yourself. Select Paper and obtain paper keys; no funding or live brokerage application is needed for this setup. | `ALPACA_API_KEY`, `ALPACA_API_SECRET`. Keep paper URLs and IEX defaults. |
| Alpha Vantage | [Claim a free key](https://www.alphavantage.co/support/#api-key). The actual form asks for your role, organization and email and accepts terms upon submission. | `ALPHA_VANTAGE_API_KEY`. Use your own key, not the shared demo value. |
| FRED | [Request an API key](https://fred.stlouisfed.org/docs/api/api_key.html) after logging in to your FRED account and reviewing the API terms. | `FRED_API_KEY`. |
| EIA | [Register](https://www.eia.gov/opendata/register.php). The actual form requires first/last name, email, category and terms acceptance; the key is emailed. | `EIA_API_KEY`. |
| Kalshi | [Sign in to DEMO](https://demo.kalshi.co/). Register **only the public contents** of `secrets/kalshi_public.pem` under demo API keys, using the documented public-key registration flow. If that flow is not available in your demo UI, leave the generated pair untouched and obtain a demo RSA key through the dashboard instead, saving it under a new file name and updating the path. | The returned `KALSHI_API_KEY_ID`; keep the private key in `secrets/`. Never submit the private PEM as a public key. |
| Coinbase | Optional: log in to CDP and create an ECDSA/ES256 key restricted to **view only**, with trade and transfer disabled. Use the [official instructions](https://docs.cdp.coinbase.com/coinbase-app/authentication-authorization/api-key-authentication). Existing public BTC/USD access needs no account. | `COINBASE_API_KEY_NAME` is the full `organizations/.../apiKeys/...` name. Store the PEM private key in `secrets/coinbase_private.pem`; set mode 600. |
| OpenAI | Optional/paid: supply a project API key only if you already have one. Text generation is deliberately blocked under this task's zero-spend constraint. | `OPENAI_API_KEY`; `OPENAI_MODEL` is configurable and defaults to documented `gpt-5.4-nano`. |
| X | No action needed under a zero-spend budget. [Current access uses purchased credits](https://docs.x.com/x-api/getting-started/pricing). | Keep `X_API_ENABLED=false`; only app bearer-token auth is planned. |
| Hyperliquid / GS Quant | None. | No wallet, signing key, or institutional credential needed. |
| INVO / 393TRADES | Obtain official written API documentation/authorization from the provider if offered later. | No automated integration until then; manual/CSV import remains a future option. |

The Kalshi Ed25519 pair was generated locally using `create_kalshi_demo_key.py`. The script refuses to overwrite existing key files. This is preparatory key material, not authenticated provider access. [Current key algorithms and signing rules](https://docs.kalshi.com/getting_started/api_keys); [demo URLs](https://docs.kalshi.com/getting_started/demo_env).

## Secret handling

`.env` is mode 600, `secrets/` mode 700 and PEM files mode 600. `.gitignore` excludes these paths, alternate environment files and private-key extensions. Git is initialized locally on `main`, with no remote or push. Protected local files remain ignored and untracked. Store future keys only here; never put them in chat or documentation. Do not share or upload this whole folder once keys are added. `.env.example` contains only names and safe defaults.

Values already in `.env` are preserved. Explicit process environment variables take precedence over `.env`; the example supplies only defaults. Expansion of environment-variable expressions is disabled. The checker names missing or malformed fields without showing values. Keep any future credential-import process local.

Every REST request is restricted to specific read paths on official hosts. Redirects are not followed; environment proxies and alternate API origins are disabled. Hyperliquid POST requests go only to allowlisted Info reads. Coinbase private checks reject keys with trading or transfer permissions. The scripts contain no order or transfer calls. OpenAI receives only a fixed test sentence, never financial credentials, account details or files.

Paid tests require both `ALLOW_BILLABLE_TESTS=true` and `--allow-billable-tests`; X additionally requires its enabled flag. These switches are **off** and must remain off for this request. An existing OpenAI key can be checked against model metadata without running a billable response; this is reported as incomplete rather than a successful text-generation test.

## Dependencies and repair

The installed environment is isolated in `.venv/`. Its launchers and activation paths were repaired in place after the move to the permanent root; packages and credentials were preserved. `requirements.txt` pins direct dependencies; `requirements.lock.txt` records the full installed set. Official SDKs: OpenAI, alpaca-py, coinbase-advanced-py and gs-quant. Direct HTTPS is used for the remaining providers to avoid unofficial wrappers. The OpenAI SDK is the [official Python package](https://developers.openai.com/api/docs/libraries).

If you move this folder or use another computer, create a new virtual environment with Python 3.11+ (3.12 is verified), then install the lock file. Virtual environments contain absolute paths and are not portable:

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
.venv/bin/python -m pip check
./check_environment.command
```

Do not recreate `.env` from the example over an existing file. Repair permissions locally with `chmod 600 .env secrets/*.pem` and `chmod 700 secrets` if needed. The checker reports tracked/staged credential paths and configured key values in this Git repository; it does not rewrite history or revoke keys.

Offline safety checks:

```sh
.venv/bin/python scripts/api_tests/test_safety.py
```

401 means rejected credentials; 403 can mean permissions, feed entitlement or network access restrictions; 429 means wait and reduce request frequency. Do not rotate or regenerate a credential merely because a test failed. Raw HTTP bodies, query strings containing keys, account balances and SDK exception text are intentionally omitted from logs.

## Repository readiness

This is the sole project root. Future backend, frontend, config, tests and
infrastructure files should be added here when needed; no empty application
folders or duplicate phase projects were created. See `PRE_BUILD_READINESS.md`.

Run `.venv/bin/python -B scripts/api_setup/check_repository.py` before staging or
sharing. It checks tracked and unignored candidate files plus the Git index for
credential patterns and actual configured values, verifies ignore rules and
checks environment-template separation. Reports contain paths and issue types
only. It is a heuristic local scan, not proof that an externally shared archive
or remote service has never received credentials. The environment checker now
includes this audit. The command launchers use Python's `-B` option to avoid
recreating project bytecode caches.

Direct dependency pins and the full lock serve different purposes and are
consistent. No separate development dependencies are needed for the current
standard-library tests. Optional provider SDKs remain installed so future key
configuration works without reinstalling them.

Run all offline checks with:

```sh
.venv/bin/python -B -m unittest discover -s scripts/api_tests -p 'test_*.py'
```

Use Git rather than whole-folder ZIP files for collaboration. No new archive was
created. Existing archives outside this repository are not working copies and
were not modified or certified safe for sharing.
