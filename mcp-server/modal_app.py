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


# Static fallback when pickup-locations API is unavailable (e.g. 503)
# Format: (storeId, latitude, longitude, city, street_name)
_FALLBACK_STORES: dict[str, list[tuple]] = {
    "superstore": [
        ("1502", 53.5647, -113.5213, "Edmonton", "Kingsway Avenue"),
        ("1503", 49.5429, -96.6910, "Steinbach", "Steinbach"),
        ("1504", 48.4097, -89.2500, "Thunder Bay", "Carrick St"),
        ("1505", 49.9487, -97.1546, "Winnipeg", "Mcphillips Street"),
        ("1506", 49.8944, -97.0663, "Winnipeg", "Regent Avenue"),
        ("1508", 49.8828, -97.2884, "Winnipeg", "Portage Avenue"),
        ("1509", 49.8001, -97.1639, "Winnipeg", "Bison Drive"),
        ("1510", 49.1862, -97.9319, "Winkler", "Cargill Road"),
        ("1511", 49.8992, -97.1989, "Winnipeg", "Sargent Avenue"),
        ("1512", 49.9282, -97.0703, "Winnipeg", "Gateway Road"),
        ("1514", 49.8573, -97.1043, "Winnipeg", "St Anne's Road"),
        ("1515", 49.8416, -99.9507, "Brandon", "Victoria Avenue"),
        ("1516", 49.8564, -97.2037, "Winnipeg", "Kenaston Blvd"),
        ("1517", 49.2091, -123.1001, "Vancouver", "Marine Drive"),
        ("1518", 49.2275, -123.0013, "Burnaby", "Eaton Center and Kingsway"),
        ("1519", 49.2356, -122.8561, "Coquitlam", "South Coquitlam Lougheed"),
        ("1520", 49.2590, -123.0367, "Vancouver", "Grandview Highway"),
        ("1521", 49.1397, -122.8453, "Surrey", "King George Highway"),
        ("1522", 50.6683, -120.3544, "Kamloops", "Columbia Street"),
        ("1523", 49.1479, -121.9465, "Chilliwack", "Luckakuck Way"),
        ("1524", 50.0341, -125.2484, "Campbell River", "Island Highway"),
        ("1525", 49.2303, -124.0459, "Nanaimo", "Metral Drive"),
        ("1526", 49.2748, -122.7949, "Coquitlam", "North Coquitlam Lougheed"),
        ("1527", 48.4407, -123.5043, "Victoria", "Langford Parkway"),
        ("1528", 49.6972, -124.9861, "Courtenay", "Ryan Road"),
        ("1530", 60.7278, -135.0623, "Whitehorse", "2nd Avenue"),
        ("1531", 50.2841, -119.2717, "Vernon", "Anderson Way"),
        ("1532", 49.4736, -119.5808, "Penticton", "Penticton Main"),
        ("1533", 50.4169, -104.6199, "Regina", "Albert Street"),
        ("1535", 52.1157, -106.6136, "Saskatoon", "8th Street"),
        ("1536", 52.1326, -106.7256, "Saskatoon", "Confederation Drive"),
        ("1537", 53.4083, -113.5370, "Edmonton", "26 Avenue"),
        ("1538", 53.4373, -113.6177, "Edmonton", "Windermere Way"),
        ("1539", 50.9865, -114.0419, "Calgary", "Heritage Meadows Way"),
        ("1540", 51.3008, -114.0106, "Airdrie", "Veterans Blvd NE"),
        ("1541", 49.6591, -112.7891, "Lethbridge", "Mayor MaGrath Drive"),
        ("1542", 51.1098, -113.9718, "Calgary", "Westwinds Drive"),
        ("1543", 51.1621, -114.0695, "Calgary", "Country Village Road"),
        ("1544", 55.1909, -118.7908, "Grande Prairie", "99th Street"),
        ("1545", 51.1158, -114.0692, "Calgary", "4th Street"),
        ("1546", 50.9335, -113.9668, "Calgary", "130th Avenue"),
        ("1547", 53.0161, -112.8641, "Camrose", "48th Avenue"),
        ("1548", 56.7233, -111.3765, "Fort McMurray", "Fort McMurray"),
        ("1549", 53.4522, -113.4809, "Edmonton", "23rd Avenue"),
        ("1550", 50.0041, -110.6524, "Medicine Hat", "Trans Canada Way"),
        ("1551", 49.0433, -122.7758, "Surrey", "160th Street"),
        ("1552", 49.8357, -119.6214, "Westbank", "Westbank"),
        ("1553", 49.5292, -115.7521, "Cranbrook", "17th Street"),
        ("1554", 49.1516, -122.8916, "Delta", "120 Street"),
        ("1555", 49.2213, -122.6717, "Pitt Meadows", "Pitt Meadows Lougheed"),
        ("1556", 49.1910, -122.8160, "Surrey", "104th Avenue"),
        ("1557", 49.1793, -123.1385, "Richmond", "No 3 Road"),
        ("1558", 49.0540, -122.3176, "Abbotsford", "Gladwin Road"),
        ("1559", 49.1312, -122.3337, "Mission", "Mission Lougheed"),
        ("1560", 49.3114, -123.0238, "North Vancouver", "Seymour Boulevard"),
        ("1561", 49.1184, -122.6734, "Langley", "Willowbrook Drive"),
        ("1562", 53.8873, -122.7693, "Prince George", "Ferry Avenue"),
        ("1563", 48.7744, -123.7040, "Duncan", "Cowichan Way"),
        ("1564", 49.8810, -119.4317, "Kelowna", "Baron Road"),
        ("1565", 53.5437, -113.9345, "Spruce Grove", "Jennifer Heil Way"),
        ("1566", 53.5993, -113.4116, "Edmonton", "137 Avenue"),
        ("1567", 53.5422, -113.2932, "Sherwood Park", "Baseline Road"),
        ("1568", 53.6208, -113.6038, "St. Albert", "St Albert Trail"),
        ("1569", 53.4807, -113.3743, "Edmonton", "17 Street"),
        ("1570", 53.4860, -113.4934, "Edmonton", "Calgary Trail"),
        ("1571", 53.2761, -110.0084, "Lloydminster", "44th Street"),
        ("1572", 53.6015, -113.5372, "Edmonton", "137th Avenue"),
        ("1573", 53.5400, -113.6211, "Edmonton", "Stony Plain Road"),
        ("1574", 50.9620, -114.0746, "Calgary", "Southport Road"),
        ("1575", 51.1381, -114.1626, "Calgary", "Country Hills Boulevard"),
        ("1576", 51.0699, -113.9838, "Calgary", "20th Avenue"),
        ("1577", 51.0212, -114.1679, "Calgary", "Signal Hill Center"),
        ("1578", 50.9093, -114.0673, "Calgary", "Macleod Trail"),
        ("1579", 52.2698, -113.8178, "Red Deer", "51 Avenue"),
        ("1581", 53.1981, -105.7389, "Prince Albert", "15th Street"),
        ("1582", 51.2083, -102.4510, "Yorkton", "Broadway Street"),
        ("1583", 50.4124, -105.5285, "Moose Jaw", "Thatcher Drive"),
        ("1584", 50.4464, -104.5287, "Regina", "Prince Of Wales Drive"),
        ("1585", 50.4983, -104.6442, "Regina", "Rochdale Boulevard"),
        ("1586", 50.8796, -113.9566, "Calgary", "Seton Way"),
        ("1590", 51.0475, -114.0540, "Calgary", "Calgary 6th Ave"),
        ("2800", 43.7081, -79.5332, "Toronto", "Weston Road"),
        ("2803", 46.5203, -80.9407, "Sudbury", "Lasalle Boulevard"),
        ("2806", 43.2043, -79.5912, "Grimsby", "South Service Road"),
        ("2809", 43.7780, -79.2631, "Toronto", "Brimley Road"),
        ("2810", 43.5254, -79.8663, "Milton", "Milton Main"),
        ("2811", 43.6504, -79.9064, "Georgetown", "Guelph Street"),
        ("2812", 42.9761, -81.3228, "London", "Oxford Street - Oakridge"),
        ("2813", 45.2829, -75.8667, "Kanata", "Eagleson Road"),
        ("2818", 42.8485, -80.2939, "Simcoe", "Queensway East"),
        ("2822", 43.4293, -80.5262, "Kitchener", "Highland Road"),
        ("2823", 42.9673, -81.6339, "Strathroy", "Victoria Street"),
        ("2826", 42.9775, -82.3655, "Sarnia", "Murphy Road"),
        ("2827", 42.2890, -83.0222, "Windsor", "Dougall Avenue"),
        ("2831", 44.2813, -78.3331, "Peterborough", "Borden Avenue"),
        ("2841", 43.5677, -79.6335, "Mississauga", "Mavis Road"),
        ("2842", 43.8852, -78.8781, "Oshawa", "Gibb Street"),
    ],
}


def _expand_fallback(banner: str) -> list[dict]:
    banner_name = BANNERS.get(banner, banner)
    return [
        {
            "storeId": sid,
            "storeBannerId": banner,
            "storeBannerName": banner_name,
            "name": f"{banner_name} {street}",
            "geoPoint": {"latitude": lat, "longitude": lon},
            "address": {"formattedAddress": city},
        }
        for sid, lat, lon, city, street in _FALLBACK_STORES.get(banner, [])
    ]


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
            "2. Call superstore_find_nearest_stores to get nearby pickup locations.\n"
            "3. Present the stores and let the user pick one.\n"
            "4. Call superstore_create_cart with the chosen store_id and banner.\n"
            "5. For each item the user wants, call superstore_search_products, then superstore_add_to_cart.\n"
            "6. Share the cart_url so the user can review and checkout."
        ),
    )

    @mcp.tool()
    async def superstore_find_nearest_stores(location: str) -> dict:
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
                    return _expand_fallback(banner)
                data = resp.json()
                locs = data if isinstance(data, list) else data.get("pickupLocations", [])
                return locs if locs else _expand_fallback(banner)
            except Exception:
                return _expand_fallback(banner)

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
    async def superstore_create_cart(store_id: str, banner: str) -> dict:
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
    async def superstore_search_products(
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
    async def superstore_add_to_cart(
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
    async def superstore_finish_shopping(cart_id: str, banner: str) -> dict:
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
