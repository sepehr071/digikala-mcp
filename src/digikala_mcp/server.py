"""MCP server entry point: registers every read-only Digikala tool."""

import logging

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from . import __version__, catalog, product, services  # noqa: F401  (imports register the tools)
from .registry import TOOLS

INSTRUCTIONS = """\
Unofficial, read-only access to Digikala (digikala.com), Iran's largest online shop, and its
Fresh supermarket. Nothing here can log in, add to a cart, order or post reviews.

Workflow:
1. Find products: dk_search (by words, with sort and filters; prefer results with match='all'),
   dk_find_cheapest (cheapest real match, accessories dropped), dk_best_for_budget ("best X under
   Y Toman", ranked by a rating weighted by its number of ratings), dk_suggest for vague words,
   dk_categories -> dk_category_products to browse, dk_brand_products, dk_best_sellers, dk_deals
   (Incredible Offers). For features ("Android", "256 GB", a color, Digikala-sold, fast delivery)
   get the ids from dk_filters first and pass them to dk_category_products or dk_search.
2. One product: dk_product (every seller's offer, cheapest first, stock, specs, lowest price of
   the last 30 days), then dk_price_history, dk_reviews, dk_questions, dk_similar (cheaper
   alternatives), dk_compare (2-4 products), dk_installments, dk_seller (seller reputation).
   Several products at once: dk_shortlist (re-price up to 10).
3. Groceries: dk_fresh_search and dk_deals(store='supermarket').
4. Other: dk_plus_plans (free-shipping membership), dk_gold_prices, dk_location.

Conventions: all prices are Toman (the API's Rial divided by 10; gold prices are already Toman).
Ratings are 0-5 like the site (null = not rated); review stars 1-5. Product ids are the number in
'dkp-<id>' URLs, e.g. 20109389. Category and brand codes are English slugs ('mobile-phone',
'samsung'). Persian and English queries both work. Shipping cost is only known at checkout.
Answers are cached for 2 minutes.
"""

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=True)

mcp = MCPServer(
    "digikala-mcp",
    title="Digikala",
    instructions=INSTRUCTIONS,
    version=__version__,
    website_url="https://github.com/sepehr071/digikala-mcp",
)

for fn, title in TOOLS:
    mcp.add_tool(fn, title=title, annotations=READ_ONLY)


def main() -> None:
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one INFO line per request floods client logs
    mcp.run()


if __name__ == "__main__":
    main()
