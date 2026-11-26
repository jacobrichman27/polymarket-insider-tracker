# Polymarket & data collection primer

This guide introduces the ideas you need to understand this repository: what Polymarket is, how trades show up on the internet and on the blockchain, and what kinds of data the project uses.

The detailed field list for long-running collection lives in [`Data.md`](../Data.md). How we sequence landing that archive in this repo is in [`research-archive-roadmap.md`](research-archive-roadmap.md). The existing monitoring product is summarized in [`README.md`](../README.md).

**Scope reminder:** this project is for **research and monitoring** of public activity. It does not place trades. Suspicious-looking patterns are clues for investigation, not proof that anyone broke a law.

---

## 1. What Polymarket is

[Polymarket](https://polymarket.com) is a **prediction market**. People buy and sell shares tied to real-world questions, for example:

- “Will candidate X win the election?”
- “Will Bitcoin be up over the next five minutes?”

### Prices and payoffs

- Share prices usually sit between **$0 and $1**.
- A price of **$0.30** roughly means “the market thinks there is about a 30% chance.”
- When the market **resolves** (the real-world answer is decided):
  - winning shares pay about **$1** each,
  - losing shares pay about **$0**,
  - some special cases pay **$0.50** (e.g. a void / 50-50 settlement).

So buying shares is like betting on an outcome; selling is like betting against it (or closing a position).

### Events, markets, and outcomes

Polymarket groups things roughly like this:

```text
Event          e.g. “Israeli election”
  └── Market   e.g. “Will Likud win the most seats?”   ← one tradable question
        └── Outcomes / tokens   e.g. Yes and No
```

You do not trade “the news.” You trade **shares of a specific outcome** of a specific market.

---

## 2. Crypto building blocks (short glossary in context)

Polymarket runs on a blockchain called **Polygon**. You do not need deep crypto expertise, but a few terms show up everywhere.

### Blockchain, transaction, block

| Term | Meaning |
| ---- | ------- |
| **Blockchain** | A shared public ledger of transactions, updated in batches |
| **Transaction** | One recorded action (e.g. “settle this trade”); identified by a long `transaction_hash` |
| **Block** | A batch of transactions with a time and a `block_number` |
| **Wallet / address** | An account id on the chain, written as `0x` plus 40 hex characters |

Anyone can read public chain data. Writing (sending a transaction) normally requires keys and fees; **this project only reads**.

### Tokens (ERC-20 and ERC-1155)

A **token** is a digital asset recorded by a smart contract (a program on the blockchain).

**ERC-20** is the common standard for **fungible** tokens — every unit is interchangeable, like dollars in a bank balance. Examples on Polymarket’s stack:

- **USDC** / **USDC.e** — dollar-pegged stablecoins used as trading collateral (cash-like).
- **pUSD** — another collateral token used on newer Polymarket markets.

When someone “deposits dollars onto Polymarket,” what usually happens under the hood is an **ERC-20 transfer** of USDC (or similar) into their Polymarket trading account.

**ERC-1155** is a standard for contracts that can manage **many token types** in one place. Polymarket outcome shares use this pattern: each outcome (Yes, No, “Lakers”, “Up”, …) has its own **`token_id`**, but they live in the same token system.

| Standard | Rough analogy | On Polymarket |
| -------- | ------------- | ------------- |
| ERC-20 | Bank balance of one currency | Collateral (USDC / pUSD) |
| ERC-1155 | Many coupon types in one drawer | Outcome shares (Yes/No/…) |

### Smart contracts and “the exchange”

A **smart contract** is code deployed at an address on the chain. Polymarket’s **exchange contracts** settle matched trades: they move collateral and outcome shares according to the fill.

When a fill settles, the contract emits an **event** (a structured log), often named **`OrderFilled`**. Those logs are how on-chain tools know a trade happened.

### RPC

An **RPC** (remote procedure call) endpoint is an HTTP/WebSocket API talking to a Polygon node — e.g. “give me the receipt for transaction `0xabc…`.”  
Providers include public endpoints and paid ones (Alchemy, QuickNode, etc.). Continuous enrichment needs something reliable enough to keep up with trade volume.

---

## 3. Who is trading? Proxies vs owners

On Polymarket, the address on the public trade feed is usually a **proxy wallet**: a trading account the platform created for the user (often a Gnosis Safe or Magic-style wallet). It holds positions and shows up as `proxy_wallet`.

Behind that sits an **owner** — the controller of the proxy — which **does not** appear on every trade row.

| Term | Meaning |
| ---- | ------- |
| **Proxy wallet** | Trading account address on the trade feed |
| **Owner** | Address that controls the proxy |
| **First funder** | Who first sent collateral into that proxy |
| **Funding route** | Direct transfer from some wallet vs through a shared Polymarket deposit/bridge address |

**Why it matters:** one person can use many proxies. If several proxies share the same owner or the same uncommon funding source, they may be linked. If they were only funded through a busy Polymarket deposit address used by thousands of users, that funding edge alone is much weaker.

**What we can *observe* vs what is *true*.** Alice might really control several trading accounts. Our tables only see public clues (Dune owner, first funder, fill counterparties). Same person in reality ≠ always clusterable in data. The three bullets below are **separate evidence patterns**, not steps in one story:

- **Strong (same owner).** Dune lists the same **owner** for proxies `0xA` and `0xB` → treat them as one cluster. This is the clean “Alice’s accounts” case when the lookup hits.
- **Useful (same obscure funder).** Dune owner is missing, but `0xA` and `0xB` were each first funded by the same rare wallet `0xFUND` (not a mass bridge/deposit address) → still a useful link; someone likely controlled both funding paths.
- **Weak (shared deposit only).** Proxy `0xC`’s first funding came only from Polymarket’s **shared deposit address** used by thousands of users. Even if Alice *in fact* owns `0xC`, that funding edge alone does **not** let us verify it—millions of unrelated wallets share that same funder. Do not cluster `0xC` with Alice on that edge alone.

So “Alice controls `0xC`” (ground truth) and “we can prove Alice owns `0xC`” (verifiable in our cache) can diverge. Collection records what the cache supports (`hit` / `miss`, funder quality), not omniscient ownership.

---

## 4. How a trade goes from click to data

Simplified lifecycle:

1. **Order** — A user places a limit order (resting on the book) or takes liquidity (hits resting orders).
2. **Match** — Polymarket’s **CLOB** (central limit order book) matches buyers and sellers. Think “exchange matching engine,” mostly off-chain.
3. **Settlement** — A Polygon transaction hits the exchange contract; balances update; **`OrderFilled`** (and related) logs are emitted.
4. **Publication** — Polymarket’s **Data API** publishes easy-to-read trade rows (wallet, market, price, size, time, `transaction_hash`, …).

So every fill has at least two useful views:

| View | What it is | Strength |
| ---- | ---------- | -------- |
| **API trade row** | Denormalized “tape” record | Easy to poll and store |
| **On-chain receipt** | Full transaction result + event logs | Better for role, fees, counterparties, economic direction |

### Maker and taker

- **Maker** — Had a resting order; provided liquidity.  
- **Taker** — Crossed the book; took liquidity.

One taker order can fill against several makers in a single transaction (hitting multiple price levels). That produces multiple fills / logs sharing one `transaction_hash`.

### Buy/sell labels

The API provides a **`side`** (`BUY` / `SELL`) for each row.  
Separately, the **`OrderFilled`** log implies an **on-chain direction** from which assets moved (collateral in vs shares in, etc.).

Those two can **disagree**. One study found API `side` matching on-chain economics only about **59%** of the time. Systems that care about true exposure usually **keep both** and treat on-chain direction as closer to economic truth.

**Example.** The API says `side=BUY` on Yes shares at $0.40. The receipt shows the wallet **received USDC and gave Yes tokens** → economically a **sell** of Yes (reducing Yes exposure). If you scored “bought Yes cheap and later Yes won” using only the API label, you would mis-label the trade. Store API `side` for feed fidelity; prefer `onchain_direction` for exposure, win/loss, and PnL-if-held when the receipt mapping is clear.

**Caveat.** The ~59% figure is from one study. Much apparent disagreement may be Yes/No complement pricing or mint/merge matching, not a broken API label. Treat the example above as one failure mode, not proof that receipts always win. Validate match rates and disagreement classes on ~1,000 of your own decoded receipts before leaning hard on either field.

### Units on a fill

| Field | Meaning | Tiny example |
| ----- | ------- | ------------ |
| **Price** | Collateral per share (about 0–1) | $0.40 |
| **Size** | Number of shares | 10,000 |
| **Notional** | ≈ price × size (dollar-ish size of the fill) | $4,000 |
| **Timestamp** | Usually the block time of settlement | Unix seconds of the Polygon block |

---

## 5. Identifiers you will see in code and schemas

| Identifier | What it points to |
| ---------- | ----------------- |
| `condition_id` | The market on-chain |
| `token_id` | One outcome’s share token |
| `proxy_wallet` | The trading account on the fill |
| `transaction_hash` | The settling Polygon transaction |
| `log_index` | Which event log inside that transaction (from the receipt; not always on the API row) |
| `outcome` / `outcome_index` | Human label and index of the outcome — sometimes missing on the API |

**Sentinel:** `outcome_index = 999` on the Data API means “could not label the outcome,” not “outcome number 999.” The trade can still be valid; metadata has to be repaired from `token_id` via market APIs when possible.

**Example.** API row: `token_id=123…`, `outcome=""`, `outcome_index=999`. Gamma says that token is outcome index `0` named `"Yes"`. You keep the raw API fields, set `outcome_repaired="Yes"`, `outcome_index_repaired=0`, `outcome_repair_status=ok`. Never invent an outcome if the token cannot be mapped.

---

## 6. Data sources used around this project

Different systems see different slices of the same activity.

### Data API v2 (`data-api.polymarket.com`)

Public HTTP API (no key) for trades, portfolios, resolutions, and more.

**`GET /v2/trades`** is the main near-real-time fill feed:

- Keyset / cursor pagination.
- Fields such as proxy wallet, condition/token ids, side, price, size, timestamp, title/slug, `transaction_hash`.
- `taker_only=false` includes **maker and taker** observations (fuller coverage than taker-only).

Good for: building a continuous archive of fills.  
Weak alone for: maker/taker role, counterparties, fees, block/log indexes, complete outcome labels.

### Gamma API (`gamma-api.polymarket.com`)

Polymarket’s **market metadata** API: questions, descriptions, dates, resolution sources, event groupings, outcome token lists, tags.

**Tags** (Sports, Politics, Economy, team names, …) are requested with `include_tag=true`. A dedicated `category` field on markets is often empty; tags are usually the practical way to classify markets.

Good for: joining human-readable context onto `condition_id` / `token_id`.

### Polygon (via RPC)

Reading **transaction receipts** and decoding exchange events (`OrderFilled`, …) yields:

- maker / taker,
- counterparties in the same transaction,
- fees,
- on-chain direction,
- `block_number` / `log_index`.

Good for: enriching fills the API under-specifies.  
Requires: a dependable RPC and a small service that fetches receipts as new `transaction_hash` values appear.

### Dune

[Dune](https://dune.com) is an analytics platform with **curated tables** built from chain data. For Polymarket, tables under `polymarket_polygon` include market trades, market metadata, and **`users_address_lookup`** (proxy → owner, wallet type, creation, first funding).

Curated tables are typically refreshed on the order of **about an hour**, and the SQL API is meant for analytical queries—not for calling once per live trade.

A common production pattern is: **periodically sync** a Dune table into your own Postgres, then **join locally** when trades arrive.

For this project the sync is a **scheduled bulk** (or watermark-incremental) pull of `users_address_lookup` into local `proxy_funding`—not one Dune request per seen proxy. At ~70 requests/minute, per-proxy lookups are the wrong cost model; hot-path misses use Transfer logs and wait for the next sync. Details live in [`Data.md`](../Data.md) (Proxy, owner, and funding).

### This project’s own database

Anything like “size versus the market’s last 24 hours of volume” or “how this wallet has traded before” is computed from **rows you already stored**. If small trades were never saved, those market-wide statistics are skewed.

---

## 7. How collection fits together (big picture)

```text
  Polymarket Data API          Gamma metadata           Polygon RPC
  (/v2/trades, …)              (markets, tags)          (tx receipts)
         │                            │                        │
         └──────────────┬─────────────┴────────────┬───────────┘
                        ▼                          ▼
                 Store fills +              Optional: Dune sync
                 enrichments                (proxy / funding cache)
                        │
                        ▼
              Derived features & research tables
              (see Data.md)
                        │
                        ▼
         Later: market resolution & after-trade labels
```

**Near-real-time** in this repo means polling and enrichment on the order of **seconds to minutes** after a fill is visible—not the latency of the matching engine itself.

Related ideas when running for a long time:

- **Archive broadly, score selectively** — keep enough small fills for honest market statistics; you may only alert or heavily enrich large trades.
- **Cold start** — a new collector has no history; wallet history can be backfilled per address, while market-wide windows need time to fill.
- **As-of features vs later labels** — trailing volume at trade time is fair game for a live score; “did they win at resolution?” is known only later and should not leak into that trade’s score.

Details and field-level decisions: [`Data.md`](../Data.md).

---

## 8. Concepts that often confuse newcomers

### CLOB vs CTF vs “the exchange”

Three different layers, often mixed up in conversation:

| Layer | Job | Analogy |
| ----- | --- | ------- |
| **CLOB** | Match buyers and sellers (order book) | The matching engine at an exchange |
| **CTF** (Conditional Token Framework) | Define and hold **outcome share** tokens | The warehouse of Yes/No coupons |
| **Exchange contracts** | Settle a matched trade on Polygon; emit `OrderFilled` | The cash register + receipt printer |

**Walkthrough.** You click “buy Yes at $0.35.” The **CLOB** matches you with a resting seller. A Polygon transaction hits an **exchange contract**, which moves USDC and Yes **CTF** tokens and emits **`OrderFilled`**. Your collector usually sees the Data API row first, then optionally fetches the receipt to decode that log.

### Neg risk

Some multi-outcome events (often politics: “Who wins the nomination?” with many candidates) use **neg-risk** contracts so related outcomes stay economically consistent (you should not be able to invent free money by buying mutually exclusive Yeses carelessly).

For most analysis you still see ordinary fills with price/size/wallet. You may also see a `neg_risk` flag from Gamma or from which contract settled the trade. Treat it as plumbing metadata unless you are studying multi-outcome arbitrage.

### Wash-like activity

**Wash-like** trading inflates volume without genuine disagreement about the outcome—price and size alone rarely prove it.

**Examples that look wash-like (need more evidence):**

- Wallet `0xA` buys $20k of Yes, then minutes later sells the same size back; net exposure ≈ 0, volume looks huge.
- `0xA` “buys” from `0xB`, and funding data says both proxies share the same owner → possible self-trade / circular volume.

**Not automatically wash:** two unrelated wallets trading large size at the same price—that can just be a liquid market. Detection usually needs **counterparties from the receipt** and/or **funding/owner links**, not only notional.

### Clusters

A **cluster** is a group of proxy wallets that look related—typically same **owner**, or same **uncommon first funder**.

**Example.** Five proxies all first-funded by `0xFUND` (not a mass deposit address) each buy Yes in the same geopolitical market within an hour. Individually each trade might look ordinary; as a cluster they look coordinated. That is a research signal, **not** automatic proof of misconduct.

This collection pass builds clusters from the **Dune funding cache + fill counterparties**. It does **not** (for now) follow every off-book share transfer between wallets.

### Bursts

A **burst** is many **distinct** wallets trading the **same outcome** in a short window (e.g. 3+ wallets within 2 hours—exact rule in `Data.md`).

**Example.** At 14:00, wallet `0xLEAD` buys $15k of “ceasefire by Friday” Yes. By 15:30, eight other wallets have also bought Yes. `0xLEAD` is the **originator** of that burst; the others are **followers**. Follower volume after a trade is a *later label* (section 8 in `Data.md`), useful for evaluation—not something you knew at 14:00 for scoring that first fill.

### As-of features vs later labels

This split is easy to get wrong and it breaks backtests if you mix them.

| Kind | When known | Example | May it enter *this* trade’s live score? |
| ---- | ---------- | ------- | --------------------------------------- |
| **As-of feature** | At or before `trade_ts` | Market volume in the prior 24h; wallet age; funding as of last cache sync | Yes |
| **Later label** | After the trade | Did Yes win? Did price jump 1h later? Did the wallet go dormant? | **No** for this trade’s score |

**Example.** Scoring a 10:00 trade with “price +40 points by 11:00” uses the future. Fair game: “price drift over the hour *before* 10:00.” Win/loss and “followed by a burst” can still be stored to evaluate the score later, and to build `prior_*` features for the *next* trade by that wallet.

### Archive broadly, score selectively

If you only store trades ≥ $5,000, then “this fill is 3× the market’s median” is computed against a biased median (only other whales). The design is: **archive small fills** for honest denominators; **score / heavily enrich** large ones. Do **not** put `filter_type=CASH&filter_amount=5000` (or any size filter) on the archive ingest query—that is scoring-only. Hot storage can keep full detail for a short window; warm storage keeps compact fact rows longer.

### Dune cache lag (funding)

Dune’s curated Polymarket tables refresh on the order of **~1 hour**, and we **bulk-sync** (or watermark-increment) `users_address_lookup` into local `proxy_funding` on a schedule. At trade time we join that cache—we do **not** call Dune once per fill or once per newly seen proxy.

**Example.** A brand-new proxy trades $20k two minutes after creation. Your cache may still say `funding_lookup_status=miss` until the next sync. That miss is expected; record it. Do not later overwrite the historical row with a perfect backfill and pretend the live scorer knew the owner at trade time—or live vs backtest diverge.

### Could an insider already know? (knowability)

Not every market allows privileged private knowledge before the public finds out. The archive classifies each market’s **information structure** once (not once per trade). Authoritative rules live in [`Data.md`](../Data.md); summary:

| Regime | Meaning |
| ------ | ------- |
| **`no_private_edge`** | No meaningful non-public informational edge on the settlement fact before it is public |
| **`private_edge_possible`** | Some party can hold privileged, non-public knowledge of the settlement fact before it is public |
| **`unknown`** | Listing does not clearly establish whether a privileged non-public edge exists |

Binary lock: timing of when privileged knowledge might appear does **not** create a third class. If a privileged channel can exist before public resolution → `private_edge_possible`. There is no live `knowable_from` onset under `knowability.v3`.

**Do not ask an LLM for every sports game.** Recurring shapes reuse a cache: Gamma `seriesSlug` when present, else exact question-text cache, else (when enabled) a normalized question template. Call a cheap decision model only on cache miss. See `Data.md` Knowability.

---

## 9. Where this repo fits

| Doc / area | Role |
| ---------- | ---- |
| [`README.md`](../README.md) | What the current **insider-style monitor** does (ingest → profile → score → optional alerts) |
| [`Data.md`](../Data.md) | Spec for a **rich multi-month trade + feature archive** |
| [`research-archive-roadmap.md`](research-archive-roadmap.md) | How we **sequence** landing that archive (phases, wiring, access) |
| **This primer** | Shared vocabulary for both |

You can run or extend the monitor without memorizing every crypto standard—but reading trades, receipts, and wallet links will make much more sense with the vocabulary above.

---

## 10. Quick reference glossary

| Term | One-line meaning |
| ---- | ---------------- |
| **Polygon** | Blockchain network Polymarket settles on |
| **Address / wallet** | `0x…` account id on that chain |
| **Proxy wallet** | Polymarket trading account on the tape |
| **Owner** | Controller of a proxy |
| **ERC-20** | Standard for fungible tokens (e.g. USDC) |
| **ERC-1155** | Standard used for many outcome share ids |
| **Stablecoin** | Token designed to track $1 (USDC, etc.) |
| **Collateral** | The cash-like token used to buy/sell shares |
| **CLOB** | Central limit order book |
| **CTF** | Conditional token (outcome share) framework |
| **Smart contract** | Program on the blockchain |
| **Event / log** | Data a contract emits when something happens |
| **OrderFilled** | Typical fill event from the exchange |
| **Receipt** | Full result of one transaction, including logs |
| **RPC** | API to query a blockchain node |
| **condition_id** | On-chain market id |
| **token_id** | On-chain outcome share id |
| **Notional** | ≈ price × shares |
| **Gamma** | Polymarket market metadata API |
| **Data API** | Polymarket public trades / portfolio API |
| **Dune** | Analytics platform with curated chain tables |
| **Neg risk** | Multi-outcome settlement plumbing so related markets stay consistent |
| **Wash-like** | Volume without real economic disagreement (needs counterparties / links) |
| **Cluster** | Proxies linked by owner or uncommon funder |
| **Burst** | Many wallets hitting the same outcome in a short window |
| **Knowability regime** | Information structure: `no_private_edge` / `private_edge_possible` / `unknown` (featuring gate = `private_edge_possible`) |
| **As-of feature** | Value knowable at trade time (fair for live scoring) |
| **Later label** | Value known only after the trade (evaluation / next-trade features) |
