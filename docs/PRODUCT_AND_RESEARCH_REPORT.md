# TraderX product and expanded research report

Acceptance snapshot: 2026-10-10T22:09:12.604451+00:00. Project: `/Users/ivanlopez/Desktop/traderx`.

## Delivered product

Open `TraderX.command`, then visit http://localhost:3000. Follow [PAPER_TRADING_GUIDE.md](PAPER_TRADING_GUIDE.md). Existing credentials and the six original model cohorts were preserved; your personal account has no development orders and was not reset.

## Universe and historical coverage

| Measure | Before | Final snapshot |
|---|---:|---:|
| Configured assets | 24 | 502 |
| Primary daily bars | 66,680 | 1,280,806 |
| Assets with primary archives | 24 | 501 |
| Form 4 documents | 750 | 2,150 |
| Forward cohorts | 6 | 61 |

Composition: **375 stocks, 124 ETFs, 3 crypto assets**. **486** pass current research filters; **500** have usable eligible observations in the historical panel. DOW remains configured but unavailable because the source returned no historical series. No history was fabricated.

Primary archive coverage is 824–4,099 daily observations per covered asset. The 498 US series extend through October 9, 2026; the three crypto archives through October 8. US backfills begin in 2016 or at their available listing history; the earliest crypto series begins July 20, 2015. Raw and provider-adjusted archives are separate and not double-counted. Immutable vintages and source timestamps remain stored.

The expanded list includes broad-market, size, sector and thematic ETFs and individual stocks beyond the original large technology names. Active/tradable identifiers were checked against the provider catalog. Current and historical company market capitalization are unavailable, so cap buckets remain **unknown** rather than inferred from famous names or prices. This is a retrospective watchlist, not a survivorship-free historical membership database. Delisted observations already stored are retained, but complete delisting returns and historical membership require another legitimate source.

Eligibility requires price ≥ $5, 20-session average dollar volume ≥ $1 million, at least 252 observations, at least 95% expected-session coverage, and average daily volume ≥ 10,000 shares for stocks/ETFs or 100 base units for crypto. Executability additionally requires active/non-halted status, valid fresh bid/ask and depth, spread ≤ 50 bps, and verified sessions. Research eligibility does not assert an executable quote.

## Evidence expansion

Fourteen additional issuers supplied 100 Form 4 documents each: PLTR, JPM, JNJ, CAT, NEE, WMT, SOFI, RKLB, HIMS, FIX, STRL, CALM, INDB and FULT. XOM and OZK returned no indexed documents in this attempt and remain incomplete. Public SEC acceptance timestamps, accession IDs, source documents and amendments are retained. The collection is limited to recent documents per issuer, not full corporate histories.

Insider purchase magnitude, role, repeat buyers, buyer clusters and time since filing remain separately measurable. Recent coverage is insufficient in the earlier training periods, so the insider family is excluded from fitted comparisons rather than backfilled as known evidence. Macro and funding collectors continue. Funding also lacks adequate early training coverage. Verified earnings surprises, usable historical 13F holdings with identifier mapping, historical basis and open interest remain unavailable; none was fabricated.

## Validation and model comparisons

Fixed chronological partitions use 60% fitting, 10% calibration, 15% validation and 15% holdout, with purging and nonoverlapping outcome windows. Boundaries are November 4, 2022, October 27, 2023 and April 16, 2025. There are **224 fitting, 38 calibration, 58 validation and 58 holdout date clusters**. Tens of thousands of cross-asset rows are not independent observations; serial, regime and cross-asset dependence remains. These counts are an upper bound on independent evidence, not an IID sample-size claim.

The frozen research panel has 1,113,687 feature rows. Its Parquet content/file hashes and evidence IDs are stored with the study. Architecture choice uses development results, followed by one release of the fixed snapshot holdout. These historical dates overlap earlier research and are not newly untouched prospective evidence. Only future quarantined observations provide that evidence.

All comparisons use local standardized ridge regression plus logistic classification with separate earlier sigmoid calibration. Cash, buy-and-hold holding-window returns, simple momentum, simple mean reversion, zero/constant target prediction and base-rate probabilities are reported. No neural network or reinforcement learner was added. Linear/logistic baselines remain explicit.

Research uses delayed daily-open return labels with conservative round-trip cost proxies: 110 bps for unknown-cap stocks or average dollar volume below $20 million, 22 bps otherwise. These are diagnostics, not simulated historical executions or authorization to trade arbitrary size.

### Strategy family results

Each cell below is mean net strategy return per nonoverlapping holding window, including cash observations, in percent. It is not annualized or compounded account performance. Regime cells use that regime’s observations. “Unavailable” means no fitted comparison.

| Family | Class | Holdout % | Trade rows | Downtrend % | Range % | Uptrend % | Development improved? |
|---|---|---:|---:|---:|---:|---:|---|
| momentum | stock | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| momentum | etf | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| momentum | crypto | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| trend_following | stock | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| trend_following | etf | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| trend_following | crypto | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| mean_reversion | stock | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| mean_reversion | etf | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| mean_reversion | crypto | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| breakout | stock | -0.0039 | 11 | -0.0112 | 0.0000 | 0.0000 | No |
| breakout | etf | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| breakout | crypto | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| volatility | stock | -0.0037 | 151 | -0.0355 | 0.0032 | 0.0044 | No |
| volatility | etf | 0.0002 | 41 | 0.0040 | -0.0038 | -0.0251 | No |
| volatility | crypto | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| relative_strength | stock | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| relative_strength | etf | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| relative_strength | crypto | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| cross_sectional_ranking | stock | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| cross_sectional_ranking | etf | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| cross_sectional_ranking | crypto | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| insider_event | stock | Unavailable | — | — | — | — | No |
| insider_event | etf | Unavailable | — | — | — | — | No |
| insider_event | crypto | Unavailable | — | — | — | — | No |
| macro_regime | stock | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| macro_regime | etf | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| macro_regime | crypto | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| crypto_funding | stock | Unavailable | — | — | — | — | No |
| crypto_funding | etf | Unavailable | — | — | — | — | No |
| crypto_funding | crypto | Unavailable | — | — | — | — | No |
| pairs_relative_value | stock | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| pairs_relative_value | etf | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |
| pairs_relative_value | crypto | 0.0000 | 0 | 0.0000 | 0.0000 | 0.0000 | No |

All 33 family/class trials are retained for audit; 27 have fitted comparisons and six are ineligible. Pairs research uses predefined relative-value features, not validated cointegration or an executable two-leg system. Earnings/13F are unavailable, not extra completed strategy families.

### Benchmarks

The following is the momentum family’s shared asset-class cohort; pairs use a smaller subset and have separate benchmark values in the saved results. Values are mean holding-window percent returns. Buy-and-hold is the gross market-return comparator; momentum and mean reversion include the cost proxy. Cash earns zero in this study.

| Class | Buy-and-hold % | Simple momentum after costs % | Mean reversion after costs % | Cash % |
|---|---:|---:|---:|---:|
| stock | 0.6038 | -0.3767 | -0.0606 | 0.0000 |
| etf | 0.4854 | -0.0379 | 0.0033 | 0.0000 |
| crypto | 0.6787 | 0.3481 | 0.0939 | 0.0000 |

### Cross-sectional approaches

Relative return and future percentile rank are measured within asset class. Excess return after costs uses SPY as benchmark. The paired classifiers estimate positive relative return or positive excess return, respectively. All three approaches for a given target use the same development-qualified assets and dates. Ratios below 1 improve squared-error or probability calibration against their stated baseline. Top-rank returns are descriptive diagnostics and cannot authorize absolute BUY decisions.

| Target | Approach | Common assets | Holdout rows / dates | MSE / baseline | Brier / base rate | Top-rank net % | Selected on development |
|---|---|---:|---|---:|---:|---:|---|
| relative_return | per_asset | 450 | 25,736 / 58 | 1.00852 | 1.02597 | 2.4936 | No |
| relative_return | asset_class | 450 | 25,736 / 58 | 0.99803 | 1.00331 | -1.9254 | Yes |
| relative_return | cross_sectional_ranking | 450 | 25,736 / 58 | 0.99819 | 1.00248 | -2.9356 | No |
| future_rank | per_asset | 450 | 25,736 / 58 | 1.01176 | 1.02597 | -0.7702 | No |
| future_rank | asset_class | 450 | 25,736 / 58 | 0.99997 | 1.00331 | -1.2452 | No |
| future_rank | cross_sectional_ranking | 450 | 25,736 / 58 | 1.00019 | 1.00248 | -0.9254 | Yes |
| excess_after_cost | per_asset | 446 | 25,504 / 58 | 0.98000 | 1.01405 | 1.6039 | No |
| excess_after_cost | asset_class | 446 | 25,504 / 58 | 0.96837 | 0.99211 | -0.6738 | Yes |
| excess_after_cost | cross_sectional_ranking | 446 | 25,504 / 58 | 0.97264 | 0.99422 | -1.7936 | No |

No strategy family met the development improvement test. Stock breakout and volatility lost money under the fixed trade rule; ETF volatility’s tiny positive result is insufficient. The pooled excess-return model improves held-out MSE and Brier against its baselines, but its selected top-rank return is negative. Positive diagnostics in unselected per-asset alternatives do not justify switching after seeing the holdout. Insider/funding data added coverage but cannot yet demonstrate incremental predictive value. No family is declared valuable from these results, and no model qualifies for promotion.

Full metrics by model, symbol, family, regime, liquidity and unknown market-cap bucket are available in Strategies and `data/product_phase/strategy_results.json`. Missing market-cap data prevents a meaningful cap-stratified conclusion. No historical winner was promoted or blended into a black box.

## Forward paper evaluation

There are **61 independent books**: six preserved originals and 55 new books across strategies, asset classes and representative niche assets. Each new book starts with its own $10,000 hypothetical budget; these balances are not a single portfolio. The worker rotates 24 books per pass, with a configured ceiling of 500. Current scalability is bounded local operation, not a thousands-of-books load-test claim.

At this snapshot there are **3 actual forward decisions**, **1 cash/no-trade decision**, **2 pending execution decisions**, **0 fills**, and **0 completed outcomes/no-fill outcomes**. The original AAPL/NVDA decisions are awaiting their execution windows; MSFT chose cash. The 55 newly enrolled books await post-enrollment feature observations. Zero completed outcomes is insufficient evidence, not proof of profitability.

Every new decision records fixed model/version, features and their availability, family, asset, regime, predicted return, probability/uncertainty, reasons, intended position, entry/exit rule and policy. Quote observations, partial/no fills, costs, actual subsequent marks, realized P&L and observed-quote excursions are linked as they occur. NO_TRADE, NO_FILL and INSUFFICIENT_LIQUIDITY remain valid results. Original decisions and policies are not rewritten.

Completed results remain quarantined. A later release requires cohort retirement, at least 90 days of aging for all completed observations, and an explicit audited request. Release creates a manifest for future training, not immediate recycling. Current forecasts are filtered to elapsed feature-availability times; future-dated records remain excluded. The 486 displayed current forecasts are dated experimental predictions selected from development performance; they are not promoted recommendations.

## Personal paper execution and browser acceptance

Manual tickets use the shared quote-validation rules with a separate account. The simulator includes spread, adverse slippage, five-second delay, five-bps fees per side, cash/share reservations, verified market hours, limit conditions, partial fills and expiry. Stock/ETF quantities are whole shares; crypto has eight decimal places. Quote age is bounded to 30 seconds. Orders are limited to 0.01% of observed average daily dollar volume. Small/unknown-cap stocks or limited-liquidity assets use 25-bps adverse slippage and 2% displayed-depth participation; others use five bps and 5%. Missing/stale/crossed quotes, halts, removed/inactive instruments and inadequate depth do not produce fictional fills.

Desktop and 390×844 mobile browser journeys completed: Overview → search → asset → BUY → review/confirm → simulated fill → Portfolio → position → SELL → completed history. A PLTR limit order was placed and its remainder canceled; watchlist controls were verified. These ran in an explicitly isolated acceptance database with labeled synthetic quotes, not production orders or model evaluation. Four fills completed two round trips, with realistic fixture losses of $0.2094 and $0.1047 from costs. This proves application/accounting behavior, not access to executable real-market liquidity.

Your production personal account remains uninitialized with its displayed $10,000 default, no manual orders, and no reset. The final production UI was separately checked against real collected data.

## Verification and preservation

- 218 backend tests plus eight subtests passed, including PostgreSQL acceptance, concurrency, duplicate confirmation, reserves, partial fills, limit/expiry, reset archival, halts/removal, invalid quotes, corporate actions and chronological model checks.
- 49 frontend/API checks passed; production build and TypeScript checks passed.
- Environment and required read-only provider checks passed. Unsupported or unentitled optional data remains explicitly unavailable.
- Credential-file hashes match the pre-change snapshot; the original six enrollment records match exactly. Existing data and studies were preserved.
- AI Off; zero language-model calls/tokens/cost in the usage ledger. Live trading and all external submission remain disabled and halted. No Git push was made.

## Remaining limits and owner steps

Provider semantics referenced: [Alpaca quotes](https://docs.alpaca.markets/us/reference/stockquotes-1), [Alpaca historical stock data](https://docs.alpaca.markets/us/v1.1/docs/historical-stock-data-1), and [SEC automated-access guidance](https://www.sec.gov/files/about/webmaster-faq.htm).
