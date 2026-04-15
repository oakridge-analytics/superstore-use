import modal

image = modal.Image.debian_slim(python_version="3.12").pip_install("fastmcp>=2.3", "httpx")

app = modal.App("superstore-mcp")

PCX_BASE = "https://api.pcexpress.ca/pcx-bff/api/v1"
PCX_BASE_HEADERS = {
    "x-apikey": "C1xujSegT5j3ap3yexJjqhOfELwGKYvz",
    "x-loblaw-tenant-id": "ONLINE_GROCERIES",
    "x-channel": "web",
    "x-application-type": "web",
    "business-user-agent": "PCXWEB",
    "accept-language": "en",
    "content-type": "application/json",
}

BANNERS = {
    "superstore": "Real Canadian Superstore",
    "nofrills": "No Frills",
    "loblaw": "Loblaws",
    "independent": "Your Independent Grocer",
    "zehrs": "Zehrs",
    "fortinos": "Fortinos",
    "maxi": "Maxi",
    "provigo": "Provigo",
    "dominion": "Dominion",
    "wholesaleclub": "Wholesale Club",
    "valumart": "Valu-Mart",
    "extrafoods": "Extra Foods",
}

CART_URLS = {
    "superstore": "https://www.realcanadiansuperstore.ca/en/cartReview",
    "nofrills": "https://www.nofrills.ca/en/cartReview",
    "loblaw": "https://www.loblaws.ca/en/cartReview",
    "independent": "https://www.yourindependentgrocer.ca/en/cartReview",
    "zehrs": "https://www.zehrs.ca/en/cartReview",
    "fortinos": "https://www.fortinos.ca/en/cartReview",
    "maxi": "https://www.maxi.ca/en/cartReview",
    "provigo": "https://www.provigo.ca/en/cartReview",
    "dominion": "https://www.dominion.ca/en/cartReview",
    "wholesaleclub": "https://www.wholesaleclub.ca/en/cartReview",
    "valumart": "https://www.valumart.ca/en/cartReview",
    "extrafoods": "https://www.extrafoods.ca/en/cartReview",
}


def pcx_headers(banner: str) -> dict:
    return {**PCX_BASE_HEADERS, "basesiteid": banner, "site-banner": banner}


def create_mcp():
    import asyncio
    import math
    import os
    import re
    from urllib.parse import quote

    import httpx
    from fastmcp import FastMCP
    from pydantic import BaseModel

    mcp = FastMCP(
        "Superstore Shopping",
        instructions=(
            "Workflow:\n"
            "1. Ask the user for their location (address, city, or postal code).\n"
            "2. Call find_nearest_stores to get nearby pickup locations.\n"
            "3. Present the stores and let the user pick one.\n"
            "4. Call create_cart with the chosen store_id and banner.\n"
            "5. For each item the user wants, call search_products, then add_to_cart.\n"
            "6. Share the cart_url so the user can review and checkout."
        ),
    )

    @mcp.tool()
    async def find_nearest_stores(location: str) -> dict:
        """Before starting shopping, find the nearest PC Express grocery pickup locations by address, neighbourhood, city, or postal code.

        Returns up to 3 stores sorted by distance. Each store has storeId, banner, name, bannerName,
        address, and distance_km. Pass storeId and banner to create_cart and search_products.
        """
        CA_POSTAL_RE = re.compile(r"^([A-Za-z]\d[A-Za-z])\s*(\d[A-Za-z]\d)$")
        mapbox_token = os.environ.get("MAPBOX_API_KEY", "")

        q = location.strip()
        m = CA_POSTAL_RE.match(q)
        if m:
            q = f"{m.group(1).upper()} {m.group(2).upper()}"

        async def geocode(query: str, client: httpx.AsyncClient):
            url = (
                f"https://api.mapbox.com/search/geocode/v6/forward"
                f"?q={quote(query)}&country=ca&limit=1&access_token={mapbox_token}"
            )
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            features = resp.json().get("features", [])
            if not features:
                return None
            coords = features[0]["geometry"]["coordinates"]  # [lon, lat]
            return {"lat": coords[1], "lon": coords[0]}

        async def fetch_banner_locs(banner: str, client: httpx.AsyncClient) -> list:
            try:
                resp = await client.get(
                    f"{PCX_BASE}/pickup-locations?bannerIds={banner}",
                    headers=pcx_headers(banner),
                )
                if resp.status_code != 200:
                    return []
                data = resp.json()
                return data if isinstance(data, list) else data.get("pickupLocations", [])
            except Exception:
                return []

        async with httpx.AsyncClient() as client:
            geo = await geocode(q, client)
            if not geo:
                return {"error": f"Could not geocode location: {location!r}"}
            lat, lon = geo["lat"], geo["lon"]

            locs_lists = await asyncio.gather(*[fetch_banner_locs(b, client) for b in BANNERS])

        all_locs = [loc for locs in locs_lists for loc in locs]

        def haversine(loc) -> float:
            gp = loc.get("geoPoint", {})
            d_lat = (gp.get("latitude", 0) - lat) * math.pi / 180
            d_lon = (gp.get("longitude", 0) - lon) * math.pi / 180
            a = (
                math.sin(d_lat / 2) ** 2
                + math.cos(lat * math.pi / 180)
                * math.cos(gp.get("latitude", 0) * math.pi / 180)
                * math.sin(d_lon / 2) ** 2
            )
            return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        top3 = sorted(all_locs, key=haversine)[:3]
        return {
            "stores": [
                {
                    "storeId": loc.get("storeId"),
                    "banner": loc.get("storeBannerId", "superstore"),
                    "name": loc.get("name"),
                    "bannerName": loc.get("storeBannerName", ""),
                    "address": (loc.get("address") or {}).get("formattedAddress", ""),
                    "distance_km": round(haversine(loc) * 10) / 10,
                }
                for loc in top3
            ]
        }

    @mcp.tool()
    async def create_cart(store_id: str, banner: str) -> dict:
        """Create a new shopping cart at a PC Express store.

        Call this once after the user picks a store from find_nearest_stores.
        Returns cart_id (required for search_products and add_to_cart), and a cart_url
        the user can visit to review and checkout their cart.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{PCX_BASE}/carts",
                headers=pcx_headers(banner),
                json={"bannerId": banner, "language": "en", "storeId": store_id},
            )
        data = resp.json()
        cart_id = data.get("cartId") or data.get("id")
        base_url = CART_URLS.get(banner, CART_URLS["superstore"])
        cart_url = f"{base_url}?forceCartId={cart_id}" if cart_id else base_url
        return {
            "cart_id": cart_id,
            "store_id": store_id,
            "banner": banner,
            "cart_url": cart_url,
        }

    @mcp.tool()
    async def search_products(
        store_id: str,
        banner: str,
        term: str,
        cart_id: str = "",
    ) -> dict:
        """Search for in-stock products at a PC Express store.

        Returns up to 10 shoppable products with code, name, brand, price, unit,
        packageSize, and packageUnit. Use the product code when calling add_to_cart.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{PCX_BASE}/products/search",
                headers=pcx_headers(banner),
                json={
                    "term": term,
                    "banner": banner,
                    "storeId": store_id,
                    "lang": "en",
                    "cartId": cart_id or None,
                    "pagination": {"from": 0, "size": 10},
                },
            )
        data = resp.json()
        products = []
        for p in data.get("results", []):
            if not p.get("shoppable", True) or p.get("stockStatus", "OK") != "OK":
                continue
            prices = p.get("prices", {})
            price_obj = prices.get("price", {}) or {}
            product_price = price_obj.get("value") or p.get("price")

            package_size = None
            package_unit = None
            comp_prices = prices.get("comparisonPrices", [])
            if comp_prices and product_price is not None:
                try:
                    comp = comp_prices[0]
                    size_value = (product_price / comp["price"]) * comp["quantity"]
                    package_size = round(size_value) if size_value >= 10 else round(size_value, 1)
                    package_unit = comp.get("unit", "")
                except (ZeroDivisionError, KeyError, TypeError):
                    pass

            products.append(
                {
                    "code": p.get("code"),
                    "name": p.get("name"),
                    "brand": p.get("brand"),
                    "price": product_price,
                    "unit": price_obj.get("unit", ""),
                    "packageSize": package_size,
                    "packageUnit": package_unit,
                }
            )
        return {"products": products}

    class CartItem(BaseModel):
        product_code: str
        quantity: int

    @mcp.tool()
    async def add_to_cart(
        cart_id: str,
        store_id: str,
        banner: str,
        items: list[CartItem],
    ) -> dict:
        """Add items to a PC Express shopping cart.

        Returns added_items (successfully added with name and quantity) and
        failed_items (with product_code and reason). Always check failed_items
        and inform the user of any items that could not be added.
        """
        entries = {
            item.product_code: {
                "quantity": item.quantity,
                "fulfillmentMethod": "pickup",
                "sellerId": store_id,
            }
            for item in items
        }
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{PCX_BASE}/carts/{cart_id}",
                headers=pcx_headers(banner),
                json={"entries": entries},
            )
        data = resp.json()

        requested_codes = {item.product_code for item in items}
        added_codes: set[str] = set()
        added_items = []
        cart_obj = data.get("cart", data)
        for order in cart_obj.get("orders", []):
            for entry in order.get("entries", []):
                product = entry.get("offer", {}).get("product", {})
                code = product.get("code") or product.get("id", "")
                if code in requested_codes:
                    added_codes.add(code)
                    added_items.append(
                        {
                            "product_code": code,
                            "name": product.get("name", ""),
                            "quantity": entry.get("quantity", 0),
                        }
                    )

        failed_items = []
        for err in data.get("errors", []):
            failed_items.append(
                {
                    "product_code": err.get("productCode", ""),
                    "reason": err.get("message", "Unknown error"),
                }
            )
        failed_codes = {f["product_code"] for f in failed_items}
        for item in items:
            if item.product_code not in added_codes and item.product_code not in failed_codes:
                failed_items.append(
                    {
                        "product_code": item.product_code,
                        "reason": "Not found in cart after adding — may be unavailable",
                    }
                )

        return {"added_items": added_items, "failed_items": failed_items}

    @mcp.tool()
    async def finish_shopping(cart_id: str, banner: str) -> dict:
        """Get the checkout URL for a cart. The URL forces the cart ID so the user
        can review and complete their order in the browser.

        Call this when the user is done adding items and ready to check out.
        """
        base_url = CART_URLS.get(banner, CART_URLS["superstore"])
        return {"cart_url": f"{base_url}?forceCartId={cart_id}"}

    return mcp.http_app(stateless_http=True)


@app.function(
    image=image,
    secrets=[modal.Secret.from_name("mapbox-api-key")],
    timeout=3600,
    cpu=0.25,
    memory=256,
)
@modal.asgi_app()
def mcp_server():
    return create_mcp()
