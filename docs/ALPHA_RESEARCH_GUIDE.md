# Using the alpha research update

Open `TraderX.command` inside `/Users/ivanlopez/Desktop/traderx`, then visit [TraderX](http://localhost:3000). Keep its terminal window open; Ctrl-C stops services started by that launcher. If the app is already running, the launcher recognizes the existing local service. No new keys or subscriptions are required for this update.

Open **Research → Alpha library**, or go directly to [the alpha dashboard](http://localhost:3000/alpha-library). It has nine views: definitions, decay/correlation, factors, pairs, regimes/volatility, original deep-model comparisons, portfolio methods, adaptive/fixed evidence and forward governance. Expand an alpha to inspect its version, horizon, features, evidence and explicit missing fields. “Unavailable” and “insufficient evidence” are intentional states, not zero-valued results.

The ordinary asset view still says BUY, SELL, HOLD, NO TRADE or INSUFFICIENT EVIDENCE and shows independent supporting/opposing groups. A recommendation is not an order. **Portfolio → Experimental Shadow Portfolio** displays the isolated experimental account. **Model Portfolio** retains its separate qualification gate. Manual paper trades remain your explicit action; optional manual exits remain bound to your existing consent. External/live orders stay disabled.

While TraderX and the computer are awake, existing collectors continue and the new alpha worker checks a bounded, frozen 15-symbol forward universe. It does not train an LLM or require paid inference. Completed observations need real market time, valid quotes and sufficient independent dates; entering more keys cannot bypass those requirements. Cash is an expected outcome when evidence or liquidity is inadequate.

Back up the entire local `data/` and `secrets/` directories and `.env` privately. They are excluded from Git; a source-only Git clone does not include your credentials, database or research artifacts. Do not upload them to a public repository. Read the [measured completion report](ALPHA_RESEARCH_REPORT.md), [technical methodology](QUANT_RESEARCH_METHODS.md) and [Git safety guide](GITHUB_SAFETY.md).
