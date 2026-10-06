<!-- mcp-name: io.github.sepehr071/digikala-mcp -->

<div align="center">

<img src="https://raw.githubusercontent.com/sepehr071/digikala-mcp/main/.github/banner.png" alt="digikala-mcp: let your AI agent compare every seller on Digikala" width="100%">

# 🛍️ digikala-mcp

**Let your AI agent shop around on Digikala.**<br>
Search Iran's largest online store, compare every seller's offer, check a product's price history,<br>
read reviews and Q&A, and catch today's Incredible Offers, all from Claude, Cursor or Copilot.

[![PyPI](https://img.shields.io/pypi/v/digikala-mcp?color=2563eb)](https://pypi.org/project/digikala-mcp/)
[![Python](https://img.shields.io/pypi/pyversions/digikala-mcp)](https://pypi.org/project/digikala-mcp/)
[![CI](https://github.com/sepehr071/digikala-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/sepehr071/digikala-mcp/actions/workflows/ci.yml)
[![MCP Registry](https://img.shields.io/badge/MCP_Registry-io.github.sepehr071%2Fdigikala--mcp-7c3aed)](https://registry.modelcontextprotocol.io/?q=digikala-mcp)
[![License: MIT](https://img.shields.io/badge/license-MIT-16a34a)](https://github.com/sepehr071/digikala-mcp/blob/main/LICENSE)

[![Install in Cursor](https://cursor.com/deeplink/mcp-install-dark.svg)](https://cursor.com/en/install-mcp?name=digikala&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyJkaWdpa2FsYS1tY3AiXX0=)
[![Install in VS Code](https://img.shields.io/badge/VS_Code-Install_digikala--mcp-0098FF?style=flat-square&logo=visualstudiocode&logoColor=white)](https://vscode.dev/redirect/mcp/install?name=digikala&config=%7B%22command%22%3A%22uvx%22%2C%22args%22%3A%5B%22digikala-mcp%22%5D%7D)

[Quick start](#quick-start) · [What it can do](#what-it-can-do) · [Tools](#tools) · [FAQ](#faq) · [فارسی](#فارسی)

</div>

---

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

- 🔎 **Search** the whole catalogue in Persian or English, with price, brand, feature (OS, storage, ...), color, seller and fast-delivery filters; every result says whether its title really matches
- 💸 **Find the real cheapest match**, with accessories filtered out, and every seller's offer for a product
- 🏆 **Best picks for a budget**, ranked by a rating weighted by how many buyers rated it, with the reasoning shown
- 📋 **Re-check a shortlist** of up to 10 products in one call: price, cheapest offer, stock, distance from the 30-day low
- 📈 **Judge a price** with about 30 days of daily price history and the 30-day low
- 🗂️ **Browse** categories, brands, sellers and best sellers, sorted by price, sales, views, newest or buyers' pick
- ⭐ **Check quality** with reviews, pros/cons, buyer Q&A and seller reputation
- ⚡ **Catch deals**: Incredible Offers and supermarket (Digikala Fresh) discounts
- 🧾 **Extras**: spec comparison, installment plans, Digikala Plus shipping plans, live gold and coin prices
- 🔒 **Read-only by design**: no login, no cart, no orders, no payment

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
<summary><b>Anything else</b></summary>

It's a standard stdio MCP server: run `uvx digikala-mcp`, or `pip install digikala-mcp` and run `digikala-mcp`.
</details>

Then just ask:

- "Cheapest AirPods-style earbuds under 3 million Toman with at least 4 stars?"
- "Compare the Galaxy A07 64 GB and 128 GB. Is the bigger one worth the difference?"
- "Is this seller reliable? CGDG9"
- <span dir="rtl">ارزان&zwnj;ترین شیر کم&zwnj;چرب در سوپرمارکت دیجی&zwnj;کالا چند است؟</span>

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

## Tools

Product ids are the number in a `digikala.com/product/dkp-<id>/` link. Every list returns compact product cards:
id, title, brand, price, discount, stock, seller, rating and the product link.

<details open>
<summary><b>🔎 Find products</b> (12)</summary>

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
<summary><b>📦 Products</b> (8)</summary>

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
<summary><b>🧾 Other</b> (3)</summary>

| Tool | What it does |
|---|---|
| `dk_plus_plans` | Digikala Plus membership plans (free shipments) and benefits |
| `dk_gold_prices` | Live 18k gold price per gram (daily and ~3-month change) and gold coin prices |
| `dk_location` | Address → coordinates, or coordinates → address with Digikala city/province ids |
</details>

All 23 tools are annotated `readOnlyHint: true` and return compact structured JSON, so they don't flood the agent's context.

## Good to know

- **Prices are in Toman.** The Digikala API answers in Rial; every tool divides by 10 so numbers match the website. Gold and coin prices are already Toman.
- **Ratings are 0–5**, like the site (the API's 0–100 divided by 20); `null` means not rated yet. Review stars are 1–5.
- **Persian and English queries both work** (`گوشی سامسونگ`, `airpods pro`). Category and brand codes are English slugs (`mobile-phone`, `samsung`).
- **`sort=cheapest` on a text search shows accessories first**; that's how Digikala ranks it. Use `dk_find_cheapest` for "cheapest X".
- **Search always returns something**, even for nonsense words (Digikala's search is semantic). `dk_search` marks each result `match: all / some / none` (with the missing words), and `dk_find_cheapest` and `dk_best_for_budget` keep only titles that contain every query word.
- **Filters by feature**: `dk_filters(category_code="mobile-phone")` lists ids like operating system → Android, then `dk_category_products(attributes={2226: [19239]})` filters on them.
- **The 30-day low ignores one-day dips.** `dk_shortlist` compares today's price with the lowest price that held on two days in a row (`low_30d`), because Digikala's own 30-day low (`lowest_one_day_30d`, `dk_product`'s `lowest_price_30d`) can be a single day of one color. `dk_price_history` gives both per color.
- **Prices move several times an hour** on popular listings with many sellers; re-check right before buying.
- **Answers are cached for 2 minutes**, so an agent repeating a call doesn't hit Digikala again; prices can lag the site by that much.
- **Groceries** come from the supermarket store: `dk_product` shows its price, which can differ from the main-store price in search results.
- **Shipping cost** is only calculated at checkout (login). `dk_product` shows how each offer ships, and `dk_plus_plans` the free-shipping plans.

## FAQ

<details>
<summary><b>Do I need an Iranian IP?</b></summary>

Usually not: in testing the API answered from a foreign (Turkish) exit. If every tool fails with
"refused the request (HTTP 403)", set `DIGIKALA_MCP_PROXY` to an HTTP proxy with an Iranian exit. (A 403 from just
one call usually means an unknown category or brand code.) Normal system
proxy variables are ignored on purpose.
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
| `DIGIKALA_MCP_PROXY` | unset | HTTP proxy for every request, e.g. `http://user:pass@host:port` |

## فارسی

<div dir="rtl">

**digikala-mcp** به دستیار هوش مصنوعی شما (Claude، Cursor، Copilot و ...) اجازه می&zwnj;دهد در دیجی&zwnj;کالا جستجو کند،
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
uv run pytest            # offline, against recorded responses
uv run pytest -m live    # real API
uv run ruff check .
```

The live tests can also run on GitHub (Actions → Live → Run workflow). They are not scheduled: from GitHub's US
runners Digikala times out on a few calls each run, while the same tests pass from an Iranian connection.

Tools live in `src/digikala_mcp/catalog.py`, `product.py` and `services.py`; each is a typed async function with a
docstring that tells the agent when to use it. Issues and PRs are welcome, especially new tools and fixes for API changes.

Releases: bump the version in `pyproject.toml` and `server.json`, then push a `v*` tag. GitHub Actions tests,
publishes to PyPI and the [MCP Registry](https://registry.modelcontextprotocol.io), and creates the GitHub Release.

## Disclaimer

Unofficial and not affiliated with or endorsed by Digikala. It uses the public endpoints of the digikala.com web
app, which can change without notice. Please keep request rates reasonable.

## License

[MIT](https://github.com/sepehr071/digikala-mcp/blob/main/LICENSE)
