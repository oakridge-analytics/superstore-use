"""Smoke test the voice app backend → MCP server → PC Express chain.

Drives the same /api/* endpoints the voice frontend calls, in order:
find-stores → create-cart → search-products → add-to-cart →
remove-from-cart → finish-shopping. Fails fast on any non-200 or
empty/failed result.

Usage:
    uv run python scripts/voice_smoke_api.py                    # deployed app
    uv run python scripts/voice_smoke_api.py --url http://...   # other deployment
    uv run python scripts/voice_smoke_api.py --location "V5K 0A1" --term milk
"""

import argparse
import sys

import httpx

DEFAULT_URL = "https://dbandrews--voice-shopping-ui.modal.run"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help="Voice app base URL")
    parser.add_argument("--location", default="T2N 1A1", help="Location to search stores near")
    parser.add_argument("--term", default="bananas", help="Product search term")
    args = parser.parse_args()

    client = httpx.Client(base_url=args.url, timeout=120.0)

    def post(endpoint: str, body: dict) -> dict:
        resp = client.post(endpoint, json=body)
        if resp.status_code != 200:
            print(f"FAIL {endpoint}: HTTP {resp.status_code}: {resp.text[:500]}")
            sys.exit(1)
        return resp.json()

    print(f"Target: {args.url}")

    print(f"[1/6] find-stores: {args.location!r}")
    stores = post("/api/find-stores", {"location": args.location}).get("stores", [])
    if not stores:
        print("FAIL: no stores returned")
        return 1
    store = stores[0]
    print(
        f"      -> {len(stores)} stores; using #{store['storeId']} "
        f"[{store['banner']}] {store['name']} ({store['distance_km']} km)"
    )

    print(f"[2/6] create-cart at store {store['storeId']}")
    cart = post("/api/create-cart", {"store_id": store["storeId"], "banner": store["banner"]})
    cart_id = cart.get("cart_id")
    if not cart_id:
        print(f"FAIL: no cart_id in {cart}")
        return 1
    print(f"      -> cart_id={cart_id}")

    ctx = {"cart_id": cart_id, "store_id": store["storeId"], "banner": store["banner"]}

    print(f"[3/6] search-products: {args.term!r}")
    products = post("/api/search-products", {**ctx, "term": args.term}).get("products", [])
    if not products:
        print("FAIL: no products returned")
        return 1
    product = products[0]
    print(f"      -> {len(products)} products; using {product['code']} {product['name']!r} sold_by={product['sold_by']}")

    if product["sold_by"] == "weight":
        item = {
            "product_code": product["code"],
            "sold_by": "weight",
            "kg": max(product.get("min_kg") or 0.1, 0.5),
        }
    else:
        item = {"product_code": product["code"], "sold_by": "each", "count": 1}

    print(f"[4/6] add-to-cart: {item}")
    added = post("/api/add-to-cart", {**ctx, "items": [item]})
    added_codes = [i["product_code"] for i in added.get("added_items", [])]
    if product["code"] not in added_codes:
        print(f"FAIL: item not added: {added}")
        return 1
    print(f"      -> added {added['added_items']}")
    if added.get("failed_items"):
        print(f"      !! failed_items: {added['failed_items']}")

    print(f"[5/6] remove-from-cart: {product['code']}")
    removed = post("/api/remove-from-cart", {**ctx, "items": [{"product_code": product["code"]}]})
    removed_codes = [i["product_code"] for i in removed.get("removed_items", [])]
    if product["code"] not in removed_codes:
        print(f"FAIL: item not removed: {removed}")
        return 1
    print(f"      -> removed {removed_codes}")

    print("[6/6] finish-shopping")
    finish = post("/api/finish-shopping", {"cart_id": cart_id, "banner": store["banner"]})
    cart_url = finish.get("cart_url") or ""
    if "forceCartId" not in cart_url:
        print(f"FAIL: bad cart_url: {finish}")
        return 1
    print(f"      -> {cart_url}")

    print("\nPASS: full voice-backend → MCP → PC Express chain works")
    return 0


if __name__ == "__main__":
    sys.exit(main())
