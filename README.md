<!-- mcp-name: io.github.sepehr071/digikala-mcp -->

<div align="center">

<img src="https://raw.githubusercontent.com/sepehr071/digikala-mcp/main/.github/banner.png" alt="digikala-mcp: unofficial Digikala MCP server for Claude, Cursor and Copilot" width="100%">

# digikala-mcp: Digikala MCP server for AI agents

**Let your AI agent shop around on Digikala (دیجی&zwnj;کالا).**<br>
An unofficial, read-only MCP server for Iran's largest online store: search products, compare every seller's offer,<br>
check a product's price history, read reviews and Q&A, and catch today's Incredible Offers, all from Claude, Cursor or Copilot.

[![PyPI](https://img.shields.io/pypi/v/digikala-mcp?color=2563eb)](https://pypi.org/project/digikala-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/digikala-mcp)](https://pypi.org/project/digikala-mcp/)
[![CI](https://github.com/sepehr071/digikala-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/sepehr071/digikala-mcp/actions/workflows/ci.yml)
[![MCP Registry](https://img.shields.io/badge/MCP_Registry-io.github.sepehr071%2Fdigikala--mcp-7c3aed)](https://registry.modelcontextprotocol.io/?q=digikala-mcp)
[![License: MIT](https://img.shields.io/badge/license-MIT-16a34a)](https://github.com/sepehr071/digikala-mcp/blob/main/LICENSE)

[![Install in Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=digikala&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJkaWdpa2FsYS1tY3AiXX0=)
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_digikala--mcp-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://vscode.dev/redirect/mcp/install?name=digikala&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22digikala-mcp%22%5D%7D)

[For AI agents](#for-ai-agents) · [Why](#why) · [What it can do](#what-it-can-do) · [Quick start](#quick-start) · [Tools](#tools) · [How it works](#how-it-works) · [Good to know](#good-to-know) · [FAQ](#faq) · [Configuration](#configuration) · [فارسی](#فارسی) · [Development](#development) · [Related](#related-servers)

</div>

---

## For AI agents

- **What:** unofficial MCP server (model context protocol) for Digikala (digikala.com, Iran) and its Fresh supermarket. Queries in Persian or English, prices in Toman.
- **Install:** `uvx digikala-mcp` or `claude mcp add digikala -- uvx digikala-mcp`. Transport: stdio. Needs [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python 3.10+).
- **Auth:** none, no API key or account. Optional `DIGIKALA_MCP_PROXY` (HTTP proxy, or a comma-separated list, e.g. with an Iranian exit if Digikala blocks yours).
- **Access:** read-only. No login, cart, checkout or payment, so no confirmation is needed before calling any tool.
- **Tools:** 23, all prefixed `dk_`. Start with `dk_find_cheapest`, `dk_search`, `dk_best_for_budget`, `dk_deals`.
  Typical sequence: `dk_find_cheapest` -> `dk_product` -> `dk_price_history`.
- **Use when:** finding, comparing or judging prices of products and sellers on Digikala, including the Fresh supermarket.
- **Do not use when:** the user wants to buy, or needs shipping cost (only calculated at checkout) or anything behind a login.
- **Output:** compact JSON. Prices in Toman, ratings 0-5 (`null` = not rated). Numeric product ids (the `<id>` of `dkp-<id>`) pass between tools.
- **Network:** talks to `api.digikala.com` directly from your machine. On "refused the request (HTTP 403)" for every call, set `DIGIKALA_MCP_PROXY`.
- **Machine-readable:** [`server.json`](https://github.com/sepehr071/digikala-mcp/blob/main/server.json) and the
  [iran-mcp catalog](https://github.com/sepehr071/iran-mcp) (`TOOLS.md`, `servers.json`, `llms.txt`).

## Why

Digikala lists the same phone many times: different colors, memory sizes, bundles and a dozen sellers per
listing, with prices that move every day. Sorting by "cheapest" puts phone cases first. Finding *the real
cheapest offer, and whether today's price is a good one* means a lot of clicking. An agent with
`digikala-mcp` does it in three calls:

> **You:** Cheapest Samsung Galaxy A07 on Digikala, and is now a good time to buy?
>
> **Agent:** *calls* `dk_find_cheapest(query="samsung a07")` → `dk_product(product_id=20109389)` → `dk_price_history(product_id=20109389)`
>
> | Price | Model | Seller |
> |---:|---|---|
> | **42,503,600** | Galaxy A07 64 GB / 4 GB | Digikala (same-day delivery in Tehran) |
> | **44,518,000** | Galaxy A07 64 GB / 4 GB + 25 W charger | Sepahan Hamrah Yaghout |
> | **46,811,800** | Galaxy A07 128 GB / 4 GB | Digikala |
>
> The 64 GB model is cheapest at 42,503,600, sold by Digikala itself; the next seller asks 42,918,000.
> But it's not a great moment: the black one sold for 34,499,000 yesterday and 33,200,000 at its lowest this
> month. Today's best offer is about 23% above yesterday's, so waiting may pay off.

<sub>Real tool output from 2026-10-03; prices change all the time. Prices are in Toman.</sub>

## What it can do

- **Search** the whole catalogue in Persian or English, with price, brand, feature (OS, storage, ...), color, seller and fast-delivery filters; every result says whether its title really matches
- **Find the real cheapest match**, with accessories filtered out, and every seller's offer for a product
- **Best picks for a budget**, ranked by a rating weighted by how many buyers rated it, with the reasoning shown
- **Re-check a shortlist** of up to 10 products in one call: price, cheapest offer, stock, distance from the 30-day low
- **Judge a price** with about 30 days of daily price history and the 30-day low
- **Browse** categories, brands, sellers and best sellers, sorted by price, sales, views, newest or buyers' pick
- **Check quality** with reviews, pros/cons, buyer Q&A and seller reputation
- **Catch deals**: Incredible Offers and supermarket (Digikala Fresh) discounts
- **Extras**: spec comparison, installment plans, Digikala Plus shipping plans, live gold and coin prices
- **Read-only by design**: no login, no cart, no orders, no payment

## Quick start

You need [uv](https://docs.astral.sh/uv/getting-started/installation/). No API key or account.

<details open>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add digikala -- uvx digikala-mcp
```
</details>

<details>
<summary><b>Claude Desktop</b></summary>

Settings → Developer → Edit Config, then add:

```json
{
  "mcpServers": {
    "digikala": { "command": "uvx", "args": ["digikala-mcp"] }
  }
}
```
</details>

<details>
<summary><b>Cursor</b></summary>

Click **Install in Cursor** above, or add the Claude Desktop block to `~/.cursor/mcp.json`.
</details>

<details>
<summary><b>VS Code (Copilot agent mode)</b></summary>

Click **Install in VS Code** above, or add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "digikala": { "type": "stdio", "command": "uvx", "args": ["digikala-mcp"] }
  }
}
```
</details>

<details>
<summary><b>Codex CLI</b></summary>

```bash
codex mcp add digikala -- uvx digikala-mcp
```

Or in `~/.codex/config.toml`:

```toml
[mcp_servers.digikala]
command = "uvx"
args = ["digikala-mcp"]
```
</details>

<details>
<summary><b>Gemini CLI</b></summary>

Add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "digikala": { "command": "uvx", "args": ["digikala-mcp"] }
  }
}
```
</details>

<details>
<summary><b>Windsurf</b></summary>

Add the Claude Desktop block to `~/.codeium/windsurf/mcp_config.json`.
</details>

<details>
<summary><b>Anything else</b></summary>

It's a standard stdio MCP server: run `uvx digikala-mcp`, or `pip install digikala-mcp` and run `digikala-mcp`.
</details>

Then just ask:

- "Cheapest AirPods-style earbuds under 3 million Toman with at least 4 stars?"
- "Compare the Galaxy A07 64 GB and 128 GB. Is the bigger one worth the difference?"
- "Is this seller reliable? CGDG9"
- "What are today's Incredible Offers on headphones, biggest discount first?"
- "Which Android phones with 256 GB sold by Digikala itself are under 20 million Toman?"
- <span dir="rtl">ارزان&zwnj;ترین شیر کم&zwnj;چرب در سوپرمارکت دیجی&zwnj;کالا چند است؟</span>
- <span dir="rtl">ارزان&zwnj;ترین گوشی سامسونگ A07 کدام است و الان وقت خرید است؟</span>
- <span dir="rtl">امروز چه شگفت&zwnj;انگیزی برای هدفون هست؟</span>

## Tools

Product ids are the number in a `digikala.com/product/dkp-<id>/` link. Every list returns compact product cards:
id, title, brand, price, discount, stock, seller, rating, a photo URL (`image`) and the product link.

<details open>
<summary><b>Find products</b> (12)</summary>

| Tool | What it does |
|---|---|
| `dk_search` | Search by words with sort, price, brand, feature, color and seller filters; flags loose title matches |
| `dk_find_cheapest` | Cheapest in-stock real matches for a query, accessories dropped, one list |
| `dk_best_for_budget` | Best-rated real matches under a budget, rating weighted by number of ratings |
| `dk_suggest` | Autocomplete: better keywords, category codes and brand ids |
| `dk_filters` | Filter options of a category or search: features (OS, storage, ...), colors, brands, sellers, price range |
| `dk_categories` | Find category codes and main-category ids |
| `dk_category_products` | Browse a category with sort and the same filters, optionally one brand |
| `dk_brand_products` | Browse a brand's products |
| `dk_seller` | A seller's rating, on-time shipping, cancellations, returns and products |
| `dk_deals` | Incredible Offers or supermarket deals, biggest discount first |
| `dk_best_sellers` | Current best sellers, overall or per main category |
| `dk_fresh_search` | Search or browse Digikala Fresh, the supermarket |
</details>

<details open>
<summary><b>Products</b> (8)</summary>

| Tool | What it does |
|---|---|
| `dk_product` | Price, stock, specs and every seller's offer (color, warranty, shipping), cheapest first |
| `dk_shortlist` | Re-price up to 10 products at once: price, cheapest offer, stock, rating, distance from the 30-day low |
| `dk_price_history` | About 30 days of daily prices per color, with low and high |
| `dk_reviews` | Customer reviews with stars, pros/cons and verified-buyer flag |
| `dk_questions` | Customer questions with their top answers |
| `dk_similar` | Similar products, e.g. cheaper alternatives |
| `dk_compare` | 2-4 products side by side: the specs that differ, plus the shared ones |
| `dk_installments` | Digipay credit-line offers for a product (credit amount, monthly repayment, months) |
</details>

<details open>
<summary><b>Other</b> (3)</summary>

| Tool | What it does |
|---|---|
| `dk_plus_plans` | Digikala Plus membership plans (free shipments) and benefits |
| `dk_gold_prices` | Live 18k gold price per gram (daily and ~3-month change) and gold coin prices |
| `dk_location` | Address → coordinates, or coordinates → address with Digikala city/province ids |
</details>

All 23 tools are annotated `readOnlyHint: true` and return compact structured JSON, so they don't flood the agent's context.

## How it works

```text
  AI agent  (Claude, Cursor, Copilot, ...)
      │
      │  MCP over stdio
      ▼
  digikala-mcp  (runs on your machine)
      │
      │  HTTPS
      └──────▶  api.digikala.com   products, sellers, deals, Fresh supermarket
```

`digikala-mcp` runs locally and calls the same public endpoints the digikala.com web app uses. There's no
hosted server in between, no API key, and nothing about you is sent anywhere else.

## Good to know

- **Prices are in Toman.** The Digikala API answers in Rial; every tool divides by 10 so numbers match the website. Gold and coin prices are already Toman.
- **Ratings are 0–5**, like the site (the API's 0–100 divided by 20); `null` means not rated yet. Review stars are 1–5.
- **Persian and English queries both work** (`گوشی سامسونگ`, `airpods pro`). Category and brand codes are English slugs (`mobile-phone`, `samsung`).
- **`sort=cheapest` on a text search shows accessories first**; that's how Digikala ranks it. Use `dk_find_cheapest` for "cheapest X".
- **Search always returns something**, even for nonsense words (Digikala's search is semantic). `dk_search` marks each result `match: all / some / none` (with the missing words), and `dk_find_cheapest` and `dk_best_for_budget` keep only titles that contain every query word.
- **Filters by feature**: `dk_filters(category_code="mobile-phone")` lists ids like operating system → Android, then `dk_category_products(attributes={2226: [19239]})` filters on them.
- **The 30-day low ignores one-day dips.** `dk_shortlist` compares today's price with the lowest price that held on two days in a row (`low_30d`), because Digikala's own 30-day low (`lowest_one_day_30d`, `dk_product`'s `lowest_price_30d`) can be a single day of one color. `dk_price_history` gives both per color.
- **Photos**: cards carry `image`, `dk_product` an `images` list (max 4), both absolute https URLs taken from the API as-is. They end in `?x-oss-process=image/resize,m_lfit,h_300,w_300/quality,q_80`, so they are 300 px JPEGs; drop that suffix for the original size.
- **Prices move several times an hour** on popular listings with many sellers; re-check right before buying.
- **Answers are cached for 2 minutes**, so an agent repeating a call doesn't hit Digikala again; prices can lag the site by that much. A timeout, 5xx or 429 is retried up to twice with backoff.
- **Groceries** come from the supermarket store: `dk_product` shows its price, which can differ from the main-store price in search results.
- **Shipping cost** is only calculated at checkout (login). `dk_product` shows how each offer ships, and `dk_plus_plans` the free-shipping plans.

## FAQ

<details>
<summary><b>Is there a Digikala API or MCP server for AI agents?</b></summary>

Yes: `digikala-mcp` is an unofficial MCP server with 23 read-only tools for search, seller offers, price history,
reviews and deals. It calls the same public endpoints the digikala.com web app uses; no API key is needed.
</details>

<details>
<summary><b>How do I use Digikala with Claude, Cursor or Copilot?</b></summary>

Add the server with `claude mcp add digikala -- uvx digikala-mcp` (or the matching config in
[Quick start](#quick-start) for Claude Desktop, Cursor and VS Code), then ask in plain language, in Persian or English.
</details>

<details>
<summary><b>Is it official, safe and free?</b></summary>

It is unofficial and not affiliated with Digikala. It is read-only (no login, cart or payment), runs on your machine,
and is free under the MIT license.
</details>

<details>
<summary><b>Do I need an Iranian IP?</b></summary>

Usually not: in testing the API answered from a foreign (Turkish) exit. If every tool fails with
"refused the request (HTTP 403)", set `DIGIKALA_MCP_PROXY` to an HTTP proxy with an Iranian exit. (A 403 from just
one call usually means an unknown category or brand code.) Normal system
proxy variables are ignored on purpose. If Digikala serves a bot-check page, install the optional browser
fallback (`uvx --with patchright==1.63.0 digikala-mcp` or `pip install digikala-mcp[browser]`), then run
`patchright install chromium`.
</details>

<details>
<summary><b>Can it buy something for me?</b></summary>

No, and that's deliberate. It has no login and never calls the cart, checkout, payment, or review/question
posting endpoints; it only reads public data. The agent finds the best option; you tap buy on the site.
</details>

<details>
<summary><b>A product shows <code>in_stock: false</code> and no price</b></summary>

Digikala lists products that are out of stock, coming soon or discontinued. They have no current offer, so there's
no price. Searches use `in_stock_only: true` by default.
</details>

<details>
<summary><b>Does it cover the Digikala Fresh supermarket?</b></summary>

Yes. `dk_fresh_search` searches and browses Digikala Fresh, `dk_deals` takes `store='supermarket'`, and `dk_product`
falls back to the Fresh product API for supermarket ids.
</details>

<details>
<summary><b>Are prices in Rial or Toman?</b></summary>

Toman, like the website. The API answers in Rial and every tool divides by 10; gold and coin prices are already Toman.
</details>

<details>
<summary><b>Why does <code>dk_installments</code> return a note instead of offers?</b></summary>

Since 2026-10-05 Digikala's Digipay credit endpoint answers an empty list for every product (the product page shows no
credit box either), so the tool returns a note instead of offers.
</details>

<details>
<summary><b>Claude Desktop says <code>uvx</code> is not found</b></summary>

Use the full path to `uvx` (`where uvx` on Windows, `which uvx` on macOS/Linux) as `command`.
</details>

<details>
<summary><b>How do I debug what the agent sees?</b></summary>

```bash
npx @modelcontextprotocol/inspector uvx digikala-mcp
```
</details>

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `DIGIKALA_MCP_PROXY` | unset | HTTP proxy for every request, e.g. `http://user:pass@host:port`. A comma-separated list is used one at a time: the next proxy takes over when one is blocked (403/429) or cannot connect |

<a id="فارسی"></a>

## فارسی

<div dir="rtl">

### سرور MCP دیجی&zwnj;کالا برای دستیار هوش مصنوعی

**digikala-mcp** یک سرور MCP غیررسمی و فقط&zwnj;خواندنی برای دیجی&zwnj;کالا، بزرگ&zwnj;ترین فروشگاه اینترنتی ایران، است. این سرور به دستیار هوش مصنوعی شما (Claude، Cursor، Copilot و ...) اجازه می&zwnj;دهد در دیجی&zwnj;کالا جستجو کند،
قیمت همه فروشندگان یک کالا را مقایسه کند، تاریخچه قیمت، نظرات و پرسش&zwnj;وپاسخ&zwnj;ها را بخواند و پیشنهادهای شگفت&zwnj;انگیز را پیدا کند.

**چه کارهایی می&zwnj;کند**

- **جستجو** به فارسی یا انگلیسی، با فیلتر قیمت، برند، ویژگی (سیستم عامل، حافظه و ...)، رنگ، نوع فروشنده و ارسال سریع؛ کنار هر نتیجه می&zwnj;گوید عنوانش واقعاً با جستجو جور است یا نه.
- **ارزان&zwnj;ترین کالای واقعی** را پیدا می&zwnj;کند (لوازم جانبی مثل قاب و کابل را کنار می&zwnj;گذارد) و پیشنهاد همه فروشندگان یک کالا را از ارزان به گران نشان می&zwnj;دهد.
- **بهترین انتخاب با بودجه شما**: کالاها را بر اساس امتیازی رتبه&zwnj;بندی می&zwnj;کند که تعداد امتیازدهنده&zwnj;ها را هم در نظر می&zwnj;گیرد، تا یک کالای ۵ ستاره با ۳ رأی از کالای ۴٫۶ ستاره با ۹۰۰ رأی جلو نزند.
- **تاریخچه قیمت** حدود ۳۰ روز گذشته و کمترین قیمت ماه، برای اینکه بدانید الان وقت خرید است یا نه.
- **بررسی دوباره فهرست منتخب**: قیمت، موجودی و فاصله تا کمترین قیمت ماه تا ۱۰ کالا با یک درخواست.
- **کیفیت**: نظرات خریداران با نقاط قوت و ضعف، پرسش&zwnj;وپاسخ&zwnj;ها، و کارنامه فروشنده (ارسال به&zwnj;موقع، لغو، مرجوعی).
- **تخفیف&zwnj;ها**: شگفت&zwnj;انگیزها، پرفروش&zwnj;ها و تخفیف&zwnj;های سوپرمارکت (دیجی&zwnj;کالا فرش).
- **بیشتر**: مقایسه مشخصات فنی، طرح&zwnj;های دیجی&zwnj;کالا پلاس، قیمت لحظه&zwnj;ای طلا و سکه.

**نکته&zwnj;ها**

- فقط خواندنی است: وارد حساب نمی&zwnj;شود، سبد خرید نمی&zwnj;سازد و سفارش ثبت نمی&zwnj;کند.
- همه قیمت&zwnj;ها به تومان است و امتیازها مثل سایت از ۵.
- روی سیستم خود شما اجرا می&zwnj;شود، کلید API لازم ندارد و به هیچ سرور واسطی داده نمی&zwnj;فرستد.
- پاسخ&zwnj;ها تا ۲ دقیقه نگه داشته می&zwnj;شوند؛ قیمت ممکن است همین&zwnj;قدر از سایت عقب باشد.

**کلیدواژه&zwnj;ها:** دیجی&zwnj;کالا، digikala، سرور MCP دیجی&zwnj;کالا، مقایسه قیمت، ارزان&zwnj;ترین قیمت، تاریخچه قیمت، شگفت&zwnj;انگیز دیجی&zwnj;کالا، دیجی&zwnj;کالا فرش، فروشگاه اینترنتی، خرید آنلاین.

**نصب** (اول [uv](https://docs.astral.sh/uv/getting-started/installation/) را نصب کنید). در Claude Code:

</div>

```bash
claude mcp add digikala -- uvx digikala-mcp
```

<div dir="rtl">

در Claude Desktop، Cursor و بقیه برنامه&zwnj;ها همان تنظیم بخش [Quick start](#quick-start) را بگذارید.

**نمونه پرسش&zwnj;ها**

- «ارزان&zwnj;ترین گوشی سامسونگ A07 کدام است و الان قیمتش خوب است؟»
- «بهترین هدفون بی&zwnj;سیم تا ۳ میلیون تومان چیست؟»
- «گوشی اندرویدی با ۲۵۶ گیگ حافظه که خود دیجی&zwnj;کالا می&zwnj;فروشد، از ارزان به گران.»
- «این سه لپ&zwnj;تاپ را مقایسه کن و بگو کدام ارزش خرید دارد.»
- «امروز چه شگفت&zwnj;انگیزی برای هدفون هست؟»

</div>

## Development

```bash
git clone https://github.com/sepehr071/digikala-mcp && cd digikala-mcp
uv sync
uv run python -m pytest            # offline, against recorded responses
uv run python -m pytest -m live    # real API
uv run ruff check .
```

The live tests can also run on GitHub (Actions → Live → Run workflow). They are not scheduled: from GitHub's US
runners Digikala times out on a few calls each run, while the same tests pass from an Iranian connection.

Tools live in `src/digikala_mcp/catalog.py`, `product.py` and `services.py`; each is a typed async function with a
docstring that tells the agent when to use it. Issues and PRs are welcome, especially new tools and fixes for API changes.

Releases: bump the version in `pyproject.toml` and `server.json`, then push a `v*` tag. GitHub Actions tests,
publishes to PyPI and the [MCP Registry](https://registry.modelcontextprotocol.io), and creates the GitHub Release.

## Related servers

- [Technolife MCP server](https://github.com/sepehr071/technolife-mcp) for electronics prices, with installment prices
- [MasterKala MCP server](https://github.com/sepehr071/masterkala-mcp) for gadgets and phone accessories
- [Torob MCP server](https://github.com/sepehr071/torob-mcp) for price comparison across Iranian shops
- [Okala MCP server](https://github.com/sepehr071/okala-mcp) for online grocery shopping
- [Banimode MCP server](https://github.com/sepehr071/banimode-mcp) for fashion and clothing
- [iran-mcp](https://github.com/sepehr071/iran-mcp): catalog of all Iranian-service MCP servers

## Disclaimer

Unofficial and not affiliated with or endorsed by Digikala. It uses the public endpoints of the digikala.com web
app, which can change without notice. Please keep request rates reasonable.

## Author

<a href="https://www.linkedin.com/in/sepehr-radmard"><img src="https://raw.githubusercontent.com/sepehr071/iran-mcp/main/assets/author-banner.png" alt="Sepehr Radmard: open-source MCP servers for the Iranian web. LinkedIn: linkedin.com/in/sepehr-radmard" width="100%"></a>

Built and maintained by **Sepehr Radmard** (سپهر رادمرد). Connect on [LinkedIn](https://www.linkedin.com/in/sepehr-radmard) or follow [@sepehr071 on GitHub](https://github.com/sepehr071) for more MCP servers for Iranian websites, all listed in [iran-mcp](https://github.com/sepehr071/iran-mcp). If this saves you time, a star on the repo helps other people find it.

## License

[MIT](https://github.com/sepehr071/digikala-mcp/blob/main/LICENSE)

If this saves you clicks, a star helps others find it.
