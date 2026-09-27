# Your remaining setup

The local app and public market research do not need any new API key.
Open the Dashboard at http://localhost:3000 after double-clicking `TraderX.command`.
Keep AI Off until you choose a model. Keep the kill switch engaged unless you want
explicit internal simulation. No deposit, wallet key or live brokerage access is
needed for the delivered app.

## Optional local AI

1. Install/open LM Studio from https://lmstudio.ai/ (or another compatible local runtime).
2. Load a text model suitable for your Mac's memory. TraderX does not download one.
3. Start the OpenAI-compatible server at `http://localhost:1234/v1`.
4. In TraderX Settings choose Local AI and paste the exact loaded model identifier.
5. Save, then Check connection. A local API key is unnecessary unless server auth is enabled.

Local model compatibility still needs a real test once you load a model. Adapter
behavior has been validated with mocks; no local model was available during this build.
The runtime needs chat completions with JSON object output. No model fine-tuning is
performed. Change model identifier/prompt revision after swapping fine-tuned weights.

## Optional cloud AI

Put an OpenAI project API key into `OPENAI_API_KEY` in the existing
`/Users/ivanlopez/Desktop/TraderX/.env`, then restart. Choose OpenAI or Hybrid in
Settings. The app uses the configured model and requires a pricing entry in
`config/llm_prices.json`. Routine nano pricing is preconfigured; escalation models
are deliberately blank/unpriced. Chat works only when you send a message.
Automated AI and automated cloud use have separate toggles, both off by default.

No OpenAI key is required for Local AI. Never paste a private key into the chatbot
or this conversation. Existing .env contents and private keys were preserved.

## Data providers you may choose to enable

| Provider | What to add locally | What it enables / caveat |
|---|---|---|
| SEC EDGAR | `SEC_USER_AGENT` containing your identifying name and real contact email | Filing reads; no API key needed |
| Alpaca | `ALPACA_API_KEY`, `ALPACA_API_SECRET` from a paper account | Stock quotes/history; retain paper mode and IEX; entitlements may limit options/history |
| Alpha Vantage | `ALPHA_VANTAGE_API_KEY` | News, earnings transcripts and options reads; some endpoints may require a paid entitlement |
| FRED / ALFRED | `FRED_API_KEY` | Vintage-aware macro observations |
| EIA | `EIA_API_KEY` | Electricity/energy observations |
| X | `X_BEARER_TOKEN`, explicit `X_API_ENABLED=true` only after accepting its costs | Optional paid social reads; not needed to run TraderX |
| Kalshi account | Registered demo `KALSHI_API_KEY_ID` and existing protected private-key path | Existing Phase 0 authenticated demo read test; public demo data already works |
| Coinbase account | View-only `COINBASE_API_KEY_NAME` and protected private-key file | Existing Phase 0 account read test; public spot market data already works |

Hyperliquid public data needs no wallet secret. Authorized manual trader CSV import
works without Invo access. TraderX does not scrape Invo or automatically mirror wallets.
GS Quant local calculations need no Goldman credentials.

You can use Earnings, Insiders and Institutions immediately with authorized text
or XML imports. Include reporting-period dates for transcript comparisons; 13F
comparisons additionally need the same manager identifier across filings and
confirmed value units. Historical options summaries appear after an explicit
entitled provider fetch. See EVIDENCE_RESEARCH.md for exact import expectations.

Exact registration links and safe key-file instructions remain in `API_SETUP.md`.
Provider access/paid-plan entitlement is your account decision; development did not
purchase access, enroll accounts or submit any exchange order. Configured Alpaca, SEC, FRED and EIA feeds activate after restart. Alpha Vantage
news runs once every six hours for the configured watchlist; premium transcripts
and options are fetched explicitly. Schedules and symbols are in
`config/ingestion.json`. X remains explicit opt-in. Supplying credentials
does not complete the remaining engineering described in `BUILD_STATUS.md`.

## Start / stop / tests

```sh
cd /Users/ivanlopez/Desktop/TraderX
./TraderX.command
```

Frontend: http://localhost:3000 · Backend: http://localhost:8000 · API docs:
http://localhost:8000/docs. Keep the launch window open. Use Ctrl-C to stop processes
started by that launcher. Run `./test.command` with the app running for the browser
proxy tests. The full backend suite can run independently with `.venv/bin/python -m pytest`.
