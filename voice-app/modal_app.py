import modal

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi", "httpx")
    .add_local_dir("./voice-app/public", remote_path="/app/public")
)

app = modal.App("voice-shopping")

usage_stats = modal.Dict.from_name("voice-usage-stats", create_if_missing=True)

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
    "superstore": {
        "name": "Real Canadian Superstore",
        "cart_url": "https://www.realcanadiansuperstore.ca/en/cartReview",
    },
    "nofrills": {"name": "No Frills", "cart_url": "https://www.nofrills.ca/en/cartReview"},
    "loblaw": {"name": "Loblaws", "cart_url": "https://www.loblaws.ca/en/cartReview"},
    "independent": {
        "name": "Your Independent Grocer",
        "cart_url": "https://www.yourindependentgrocer.ca/en/cartReview",
    },
    "zehrs": {"name": "Zehrs", "cart_url": "https://www.zehrs.ca/en/cartReview"},
    "fortinos": {"name": "Fortinos", "cart_url": "https://www.fortinos.ca/en/cartReview"},
    "maxi": {"name": "Maxi", "cart_url": "https://www.maxi.ca/en/cartReview"},
    "provigo": {"name": "Provigo", "cart_url": "https://www.provigo.ca/en/cartReview"},
    "dominion": {"name": "Dominion", "cart_url": "https://www.dominion.ca/en/cartReview"},
    "wholesaleclub": {"name": "Wholesale Club", "cart_url": "https://www.wholesaleclub.ca/en/cartReview"},
    "valumart": {"name": "Valu-Mart", "cart_url": "https://www.valumart.ca/en/cartReview"},
    "extrafoods": {"name": "Extra Foods", "cart_url": "https://www.extrafoods.ca/en/cartReview"},
}


def pcx_headers(banner: str = "superstore") -> dict:
    return {**PCX_BASE_HEADERS, "basesiteid": banner, "site-banner": banner}


SYSTEM_PROMPT = """\
# Role & Objective

You are a friendly, efficient voice shopping assistant for PC Express. You help users build grocery orders through natural conversation.

# Personality & Tone

- Warm and conversational, like a helpful friend who knows the grocery store well.
- Keep responses to 2–3 sentences per turn. This is a voice conversation — be concise.
- Vary your phrasing naturally. Do NOT repeat the same transition phrases.
- Deliver responses quickly but do not sound rushed.
- Omit unnecessary details like store provinces, postal codes, and product codes.

# Greeting

- Introduce yourself briefly: you can help with recipe ideas or adding items straight to their PC Express cart.
- Let the user know they can interrupt you anytime.
- IF the user immediately starts listing items, skip pleasantries and ask for their location so you can find a store.

# Finding a Store

1. Ask where the user is located — they can say an address, neighbourhood, city, or postal code.
2. Call `find_nearest_stores` with whatever they give you.
3. Present the top 3 results by name, banner, street name and distance only. Example: "There's a No Frills 1.2 km away on 123 Main St, a Superstore at 3.5 km on 456 Main St, and a Loblaws at 4 km on 789 Main St. Which one works?"
4. IF the user names a specific store or banner, match it from the results.
5. Once they pick a store, remember its `storeId` and `banner` from the results. Confirm: "Great, you're shopping at [store name]. What do you need?"
6. ALWAYS pass `store_id` and `banner` when calling `search_products`.

# Shopping Modes:

## Recipe Mode
- The user wants to brainstorm meal ideas before shopping.
- Suggest 2–3 simple recipe ideas based on what they mention (cuisine, ingredients on hand, dietary needs).
- Once they pick a recipe, list ONLY the non-staple ingredients they'd need to buy. Assume they have basics like salt, pepper, oil, butter, sugar, flour, and common spices.
- Confirm the list, then search and add all items in one batch.

## List Mode
- The user knows what they want and starts naming items.
- Do NOT slow them down with confirmations for each item. Immediately search for each item and add the best match.
- Batch multiple items into a single `add_to_cart` call when possible.
- After adding, give a quick summary: "Added chicken, rice, and broccoli. Anything else?"

# IMPORTANT RULES

- IF the user asks about anything unrelated to groceries or food IMMEDIATELY call `finish_shopping` with `reason: "off_topic"`.
- When the user says they're done shopping, call `finish_shopping` and say a quick goodbye.
"""

TOOLS = [
    {
        "type": "function",
        "name": "find_nearest_stores",
        "description": "Find the nearest PC Express pickup locations by address, neighbourhood, city, or postal code",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The user's location - can be a street address, neighbourhood, city, or postal code (e.g. '100 Main St, Calgary', 'Kensington Calgary', 'T2N 1A1')",
                },
            },
            "required": ["location"],
        },
    },
    {
        "type": "function",
        "name": "search_products",
        "description": "Search for products at a store. Pass the store_id and banner from find_nearest_stores results. Only returns in-stock products.",
        "parameters": {
            "type": "object",
            "properties": {
                "store_id": {"type": "string", "description": "The storeId from find_nearest_stores results"},
                "banner": {
                    "type": "string",
                    "description": "The banner from find_nearest_stores results (e.g. superstore, nofrills, loblaw)",
                },
                "term": {"type": "string", "description": "Search term for the product"},
            },
            "required": ["store_id", "banner", "term"],
        },
    },
    {
        "type": "function",
        "name": "add_to_cart",
        "description": "Add items to the shopping cart. Returns added_items (successfully added) and failed_items (with reason). Check failed_items and inform the user.",
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_code": {"type": "string"},
                            "quantity": {"type": "number"},
                        },
                        "required": ["product_code", "quantity"],
                    },
                    "description": "Items to add with product code and quantity",
                },
            },
            "required": ["items"],
        },
    },
    {
        "type": "function",
        "name": "remove_from_cart",
        "description": "Remove items from the shopping cart. Returns removed_items (successfully removed) and failed_items (with reason).",
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_code": {"type": "string"},
                        },
                        "required": ["product_code"],
                    },
                    "description": "Items to remove by product code",
                },
            },
            "required": ["items"],
        },
    },
    {
        "type": "function",
        "name": "finish_shopping",
        "description": "Signal that the user is done shopping or that the session should end. Set reason to 'off_topic' when ending due to repeated off-topic messages.",
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "enum": ["done", "off_topic"],
                    "description": "Why the session is ending: 'done' if the user finished shopping, 'off_topic' if the user repeatedly went off-topic",
                },
            },
        },
    },
]


def create_web_app():
    import hashlib
    import json
    import math
    import os
    import re
    import uuid
    from datetime import datetime, timezone
    from urllib.parse import quote

    import httpx
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from starlette.middleware.base import BaseHTTPMiddleware

    web_app = FastAPI()

    def _hash_ip(ip: str) -> str:
        """One-way hash so we can count unique users without storing raw IPs."""
        return hashlib.sha256(ip.encode()).hexdigest()[:12]

    def _log(event: str, **kw):
        if "ip" in kw:
            kw["ip"] = _hash_ip(str(kw["ip"]))
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        parts = " ".join(f"{k}={v}" for k, v in kw.items())
        print(f"[{ts}] [{event}] {parts}")

    def _inc(counter: str, amount: int = 1):
        """Increment a persistent usage counter (keyed by date + event)."""
        date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        key = f"{date_key}:{counter}"
        try:
            usage_stats[key] = usage_stats.get(key, 0) + amount
        except Exception:
            pass  # Never let stats tracking break the app

    class NoCacheMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-cache"
            return response

    web_app.add_middleware(NoCacheMiddleware)

    # Rate limiting: max 3 token requests per IP per 60s window
    TOKEN_RATE_LIMIT = 3
    TOKEN_RATE_WINDOW = 60  # seconds
    token_requests: dict[str, list[float]] = {}

    def _get_client_ip(request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _is_rate_limited(ip: str) -> bool:
        import time

        now = time.time()
        timestamps = token_requests.get(ip, [])
        # Prune old entries
        timestamps = [t for t in timestamps if now - t < TOKEN_RATE_WINDOW]
        token_requests[ip] = timestamps
        if len(timestamps) >= TOKEN_RATE_LIMIT:
            return True
        timestamps.append(now)
        return False

    @web_app.get("/token")
    async def get_token(request: Request):
        expected = os.environ.get("VOICE_APP_TOKEN", "")
        auth = request.headers.get("Authorization", "")
        if not expected or not auth.startswith("Bearer ") or auth[7:] != expected:
            return JSONResponse(status_code=401, content={"error": "Unauthorized"})
        ip = _get_client_ip(request)
        if _is_rate_limited(ip):
            _log("session_blocked", reason="rate_limit", ip=ip)
            return JSONResponse(status_code=429, content={"error": "Too many requests. Try again later."})

        session_id = uuid.uuid4().hex[:12]
        user_agent = request.headers.get("user-agent", "")[:100]
        _log("session_start", session_id=session_id, ip=ip, ua=f'"{user_agent}"')
        _inc("sessions")

        api_key = os.environ["OPENAI_API_KEY"]
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/realtime/sessions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-realtime-mini",
                    "voice": "cedar",
                    "instructions": SYSTEM_PROMPT,
                    "tools": TOOLS,
                    "max_response_output_tokens": 1024,
                    "input_audio_transcription": {
                        "model": "gpt-4o-mini-transcribe-2025-12-15",
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.75,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500,
                    },
                    "input_audio_noise_reduction": {
                        "type": "near_field",
                    },
                },
            )
        data = resp.json()
        _log("session_ready", session_id=session_id, model=data.get("model", "?"))
        return data

    @web_app.get("/api/stats")
    async def get_stats(request: Request):
        """Return usage counters for the last 30 days. Requires the same auth token."""
        expected = os.environ.get("VOICE_APP_TOKEN", "")
        auth = request.headers.get("Authorization", "")
        if not expected or not auth.startswith("Bearer ") or auth[7:] != expected:
            return JSONResponse(status_code=401, content={"error": "Unauthorized"})

        from datetime import timedelta

        counters = ["sessions", "store_lookups", "searches", "items_added", "completed_sessions"]
        today = datetime.now(timezone.utc).date()
        results = {}
        for day_offset in range(30):
            date_str = (today - timedelta(days=day_offset)).isoformat()
            day_data = {}
            for counter in counters:
                val = usage_stats.get(f"{date_str}:{counter}", 0)
                if val:
                    day_data[counter] = val
            if day_data:
                results[date_str] = day_data
        return results

    @web_app.post("/api/find-stores")
    async def find_stores(request: Request):
        import asyncio

        body = await request.json()
        query = body.get("location") or body.get("postal_code") or ""
        _log("find_stores", query=f'"{query}"')
        _inc("store_lookups")

        # Canadian postal code: A1A 1A1 (letter-digit-letter space? digit-letter-digit)
        CA_POSTAL_RE = re.compile(r"^([A-Za-z]\d[A-Za-z])\s*(\d[A-Za-z]\d)$")

        def normalize_postal(raw: str) -> str | None:
            """If *raw* looks like a Canadian postal code, return it as 'A1A 1A1' (uppercase, single space)."""
            m = CA_POSTAL_RE.match(raw.strip())
            if not m:
                return None
            return f"{m.group(1).upper()} {m.group(2).upper()}"

        def normalize_address(addr: str) -> str:
            """Shorten verbose directionals for better geocoding matches."""
            replacements = {
                r"\bNorthwest\b": "NW",
                r"\bNortheast\b": "NE",
                r"\bSouthwest\b": "SW",
                r"\bSoutheast\b": "SE",
            }
            for pattern, abbr in replacements.items():
                addr = re.sub(pattern, abbr, addr, flags=re.IGNORECASE)
            return addr

        async def geocode(q: str, client: httpx.AsyncClient):
            mapbox_token = os.environ.get("MAPBOX_API_KEY", "")
            url = (
                f"https://api.mapbox.com/search/geocode/v6/forward"
                f"?q={quote(q)}&country=ca&limit=1&access_token={mapbox_token}"
            )
            print(f'[find-stores] Mapbox geocode request: "{q}"')
            resp = await client.get(url)
            print(f"[find-stores] Mapbox HTTP {resp.status_code}, body length={len(resp.text)}")
            if resp.status_code != 200:
                print(f"[find-stores] Mapbox error response: {resp.text[:500]}")
                return None
            data = resp.json()
            features = data.get("features", [])
            if not features:
                print(f'[find-stores] Mapbox returned no features for "{q}"')
                return None
            feat = features[0]
            coords = feat["geometry"]["coordinates"]  # [lon, lat]
            display = feat.get("properties", {}).get("full_address") or feat.get("properties", {}).get("name", "")
            hit = {"lat": str(coords[1]), "lon": str(coords[0]), "display_name": display}
            print(f'[find-stores] Geocoded "{q}" -> {hit["lat"]}, {hit["lon"]} ({hit["display_name"]})')
            return hit

        async def fetch_banner_locations(banner: str, client: httpx.AsyncClient):
            try:
                resp = await client.get(
                    f"{PCX_BASE}/pickup-locations?bannerIds={banner}",
                    headers=pcx_headers(banner),
                )
                if resp.status_code != 200 or not resp.text.strip():
                    print(
                        f"[find-stores] {banner}: HTTP {resp.status_code}, empty={not resp.text.strip()}, body={resp.text[:200]}"
                    )
                    return []
                data = resp.json()
                locs = data if isinstance(data, list) else data.get("pickupLocations", [])
                print(f"[find-stores] {banner}: {len(locs)} locations")
                return locs
            except Exception as e:
                print(f"[find-stores] {banner}: error fetching locations: {e}")
                return []

        async with httpx.AsyncClient() as client:
            # Normalize Canadian postal codes (e.g. "t2k 0a5" -> "T2K 0A5")
            postal = normalize_postal(query)
            if postal and postal != query:
                print(f'[find-stores] Normalized postal code: "{query}" -> "{postal}"')
                query = postal

            geo_hit = await geocode(query, client)
            if not geo_hit:
                normalized = normalize_address(query)
                if normalized != query:
                    print(f'[find-stores] Retrying with normalized address: "{normalized}"')
                    geo_hit = await geocode(normalized, client)
            if not geo_hit:
                print(f'[find-stores] FAILED to geocode "{query}"')
                return JSONResponse(
                    status_code=400,
                    content={"error": f'Could not find location: "{query}"'},
                )
            lat = float(geo_hit["lat"])
            lng = float(geo_hit["lon"])

            # Query all banners in parallel
            banner_tasks = {banner: fetch_banner_locations(banner, client) for banner in BANNERS}
            results = await asyncio.gather(*banner_tasks.values())
            all_locations = []
            for locs in results:
                all_locations.extend(locs)
            print(f"[find-stores] Total locations across all banners: {len(all_locations)}")

        def distance(loc):
            gp = loc.get("geoPoint", {})
            d_lat = (gp.get("latitude", 0) - lat) * math.pi / 180
            d_lng = (gp.get("longitude", 0) - lng) * math.pi / 180
            a = (
                math.sin(d_lat / 2) ** 2
                + math.cos(lat * math.pi / 180)
                * math.cos(gp.get("latitude", 0) * math.pi / 180)
                * math.sin(d_lng / 2) ** 2
            )
            return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        sorted_locs = sorted(all_locations, key=distance)
        top3 = [
            {
                "storeId": loc.get("storeId"),
                "name": loc.get("name"),
                "banner": loc.get("storeBannerId", "superstore"),
                "bannerName": loc.get("storeBannerName", ""),
                "address": (loc.get("address") or {}).get("formattedAddress", ""),
                "distance_km": round(distance(loc) * 10) / 10,
            }
            for loc in sorted_locs[:3]
        ]
        for s in top3:
            print(
                f"[find-stores]   #{s['storeId']} [{s['banner']}] {s['name']} — {s['distance_km']}km — {s['address']}"
            )
        return {"stores": top3}

    @web_app.post("/api/create-cart")
    async def create_cart(request: Request):
        body = await request.json()
        store_id = body.get("store_id")
        banner = body.get("banner", "superstore")
        _log("create_cart", store_id=store_id, banner=banner)
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{PCX_BASE}/carts",
                headers=pcx_headers(banner),
                json={"bannerId": banner, "language": "en", "storeId": store_id},
            )
        data = resp.json()
        cart_id = data.get("cartId") or data.get("id")
        cart_url = BANNERS.get(banner, BANNERS["superstore"])["cart_url"]
        _log("create_cart_done", cart_id=cart_id, status=resp.status_code)
        if resp.status_code != 200:
            print(f"[create-cart] Error response: {json.dumps(data, indent=2)}")
        return {"cart_id": cart_id, "store_id": store_id, "banner": banner, "cart_url": cart_url}

    @web_app.post("/api/search-products")
    async def search_products(request: Request):
        body = await request.json()
        term = body.get("term")
        store_id = body.get("store_id")
        banner = body.get("banner", "superstore")
        _log("search", term=f'"{term}"', store_id=store_id, banner=banner)
        _inc("searches")
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{PCX_BASE}/products/search",
                headers=pcx_headers(banner),
                json={
                    "term": term,
                    "banner": banner,
                    "storeId": store_id,
                    "lang": "en",
                    "cartId": body.get("cart_id"),
                    "pagination": {"from": 0, "size": 10},
                },
            )
        data = resp.json()
        total_results = data.get("pagination", {}).get("totalResults", "?")
        all_results = data.get("results", [])
        print(f"[search] HTTP {resp.status_code}, {total_results} total results, {len(all_results)} returned")
        if resp.status_code != 200:
            print(f"[search] Error response: {json.dumps(data, indent=2)}")
        results = []
        for p in all_results:
            shoppable = p.get("shoppable", True)
            stock = p.get("stockStatus", "OK")
            if not shoppable or stock != "OK":
                print(f"[search]   SKIP {p.get('code')} {p.get('name')!r} (shoppable={shoppable}, stock={stock})")
                continue
            prices = p.get("prices", {})
            price_obj = prices.get("price", {}) or {}
            product_price = price_obj.get("value") or p.get("price")

            # Calculate package size from comparison prices (same approach as eval cart_checker)
            comp_prices = prices.get("comparisonPrices", [])
            package_size = None
            package_unit = None
            if comp_prices and product_price is not None:
                comp = comp_prices[0]
                try:
                    size_value = (product_price / comp["price"]) * comp["quantity"]
                    size_rounded = round(size_value) if size_value >= 10 else round(size_value, 1)
                    package_size = size_rounded
                    package_unit = comp.get("unit", "")
                except (ZeroDivisionError, KeyError, TypeError):
                    pass

            item = {
                "code": p.get("code"),
                "name": p.get("name"),
                "brand": p.get("brand"),
                "price": product_price,
                "unit": price_obj.get("unit", ""),
                "packageSize": package_size,
                "packageUnit": package_unit,
            }
            print(
                f"[search]   {item['code']} {item['brand'] or ''} {item['name']!r} ${item['price']} / {item['unit']} ({package_size} {package_unit})"
            )
            results.append(item)
        return {"products": results}

    @web_app.post("/api/add-to-cart")
    async def add_to_cart(request: Request):
        body = await request.json()
        cart_id = body.get("cart_id")
        store_id = body.get("store_id")
        banner = body.get("banner", "superstore")
        items = body.get("items", [])

        _log("add_to_cart", items=len(items), cart_id=cart_id, store_id=store_id, banner=banner)
        _inc("items_added", len(items))
        for item in items:
            print(f"[add-to-cart]   {item['product_code']} x{item['quantity']}")

        entries = {}
        for item in items:
            entries[item["product_code"]] = {
                "quantity": item["quantity"],
                "fulfillmentMethod": "pickup",
                "sellerId": store_id,
            }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{PCX_BASE}/carts/{cart_id}",
                headers=pcx_headers(banner),
                json={"entries": entries},
            )
        data = resp.json()
        print(f"[add-to-cart] HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"[add-to-cart] Error response: {json.dumps(data, indent=2)}")

        # Parse which items actually made it into the cart
        requested_codes = {item["product_code"] for item in items}
        added_codes = set()
        added_items = []
        cart_obj = data.get("cart", data)  # response may nest under "cart" or be top-level
        for order in cart_obj.get("orders", []):
            for entry in order.get("entries", []):
                product = entry.get("offer", {}).get("product", {})
                code = product.get("code") or product.get("id", "")
                if code in requested_codes:
                    added_codes.add(code)
                    name = entry.get("offer", {}).get("product", {}).get("name", "")
                    qty = entry.get("quantity", 0)
                    added_items.append(
                        {
                            "product_code": code,
                            "name": name,
                            "quantity": qty,
                        }
                    )
                    print(f"[add-to-cart]   OK {code} {name!r} x{qty}")

        # Build failed items from API errors + codes not found in cart
        failed_items = []
        for err in data.get("errors", []):
            reason = err.get("message", "Unknown error")
            pc = err.get("productCode", "")
            failed_items.append({"product_code": pc, "reason": reason})
            print(f"[add-to-cart]   FAIL {pc}: {reason}")
        failed_codes = {f["product_code"] for f in failed_items}
        for item in items:
            code = item["product_code"]
            if code not in added_codes and code not in failed_codes:
                reason = "Item not found in cart after adding — may be unavailable"
                failed_items.append({"product_code": code, "reason": reason})
                print(f"[add-to-cart]   MISSING {code}: {reason}")

        success = len(added_items) > 0
        print(f"[add-to-cart] Result: {len(added_items)} added, {len(failed_items)} failed")
        return {
            "success": success,
            "added_items": added_items,
            "failed_items": failed_items,
        }

    @web_app.post("/api/remove-from-cart")
    async def remove_from_cart(request: Request):
        body = await request.json()
        cart_id = body.get("cart_id")
        store_id = body.get("store_id")
        banner = body.get("banner", "superstore")
        items = body.get("items", [])

        _log("remove_from_cart", items=len(items), cart_id=cart_id, banner=banner)
        for item in items:
            print(f"[remove-from-cart]   {item['product_code']}")

        # Setting quantity to 0 removes the item (SAP Hybris CartService behavior)
        entries = {}
        for item in items:
            entries[item["product_code"]] = {
                "quantity": 0,
                "fulfillmentMethod": "pickup",
                "sellerId": store_id,
            }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{PCX_BASE}/carts/{cart_id}",
                headers=pcx_headers(banner),
                json={"entries": entries},
            )
        data = resp.json()
        print(f"[remove-from-cart] HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"[remove-from-cart] Error response: {json.dumps(data, indent=2)}")

        # Check which items are still in the cart after removal
        remaining_codes = set()
        cart_obj = data.get("cart", data)
        for order in cart_obj.get("orders", []):
            for entry in order.get("entries", []):
                product = entry.get("offer", {}).get("product", {})
                code = product.get("code") or product.get("id", "")
                remaining_codes.add(code)

        requested_codes = {item["product_code"] for item in items}
        removed_items = []
        failed_items = []
        for item in items:
            code = item["product_code"]
            if code not in remaining_codes:
                removed_items.append({"product_code": code})
                print(f"[remove-from-cart]   OK removed {code}")
            else:
                failed_items.append({"product_code": code, "reason": "Item still in cart after removal attempt"})
                print(f"[remove-from-cart]   FAIL {code}: still in cart")

        # Also include any API-level errors
        for err in data.get("errors", []):
            reason = err.get("message", "Unknown error")
            pc = err.get("productCode", "")
            if pc and pc not in {f["product_code"] for f in failed_items}:
                failed_items.append({"product_code": pc, "reason": reason})
                print(f"[remove-from-cart]   FAIL {pc}: {reason}")

        success = len(removed_items) > 0
        print(f"[remove-from-cart] Result: {len(removed_items)} removed, {len(failed_items)} failed")
        return {
            "success": success,
            "removed_items": removed_items,
            "failed_items": failed_items,
        }

    @web_app.post("/api/finish-shopping")
    async def finish_shopping(request: Request):
        body = await request.json()
        cart_id = body.get("cart_id")
        banner = body.get("banner", "superstore")
        base_url = BANNERS.get(banner, BANNERS["superstore"])["cart_url"]
        cart_url = f"{base_url}?forceCartId={cart_id}" if cart_id else None
        _log("finish_shopping", cart_id=cart_id, banner=banner)
        _inc("completed_sessions")
        return {"success": True, "message": "Shopping session complete", "cart_url": cart_url}

    @web_app.get("/")
    async def index():
        # Inject the voice app token into the HTML so the frontend can
        # authenticate against /token without exposing the OpenAI key.
        import html as html_mod

        token = html_mod.escape(os.environ.get("VOICE_APP_TOKEN", ""))
        with open("/app/public/index.html") as f:
            content = f.read()
        content = content.replace(
            "</head>",
            f'  <meta name="voice-token" content="{token}">\n</head>',
        )
        return HTMLResponse(content)

    web_app.mount("/", StaticFiles(directory="/app/public"), name="static")

    return web_app


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("pc-express-voice-openai"),
        modal.Secret.from_name("mapbox-api-key"),
        modal.Secret.from_name("pc-express-voice-app-token"),
    ],
    timeout=3600,
    cpu=0.25,
    memory=256,
)
@modal.asgi_app()
def ui():
    return create_web_app()
