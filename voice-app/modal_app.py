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

# Understanding sold_by Types

Each search result has a `sold_by` field:
- `sold_by='each'` → packaged item or loose produce priced by weight at checkout (e.g. bags of rice, loose apples). Order with `count` (number of units/pieces).
- `sold_by='weight'` → true bulk produce sold from a bin (e.g. bulk mushrooms, deli meat by the gram). Order with `kg` (kilograms, e.g. 0.5 for 500g).

When the user says "2 kg of chicken breast" and it's sold_by='each', add count=1 (one package). When they say "500g of mushrooms" and it's sold_by='weight', add kg=0.5.

Do NOT guess the sold_by type from the product name or code — always use the value from search results.

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
        "description": "Search for products at a store. Each result has a 'sold_by' field: 'each' (packaged or loose priced-by-weight — order with count) or 'weight' (true bulk produce — order with kg). Always use sold_by to decide how to add to cart.",
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
        "description": "Add items to the shopping cart. Each item must include sold_by from search_products: use 'each' with count (number of units) or 'weight' with kg (kilograms). Returns added_items and failed_items.",
        "parameters": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "product_code": {"type": "string"},
                            "sold_by": {
                                "type": "string",
                                "enum": ["each", "weight"],
                                "description": "Must match the sold_by from search_products",
                            },
                            "count": {
                                "type": "integer",
                                "description": "Number of units/packages (required when sold_by='each')",
                            },
                            "kg": {
                                "type": "number",
                                "description": "Weight in kilograms, e.g. 0.5 for 500g (required when sold_by='weight')",
                            },
                        },
                        "required": ["product_code", "sold_by"],
                    },
                    "description": "Items to add. Use {product_code, sold_by:'each', count:N} or {product_code, sold_by:'weight', kg:N}",
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

    def _pcx_proxy() -> str | None:
        """Build the Oxylabs proxy URL for PCX/Mapbox calls.

        PC Express's WAF returns 403 to Modal's datacenter egress IPs, which
        silently forces the static fallback store list and breaks carts.
        Routing through the residential proxy restores live API access.
        Returns None if proxy creds aren't configured (callers go direct).
        """
        server = os.environ.get("PROXY_SERVER")
        user = os.environ.get("PROXY_USERNAME")
        pw = os.environ.get("PROXY_PASSWORD")
        if not all([server, user, pw]):
            print("[proxy] oxy-proxy creds missing — PCX/Mapbox calls will likely 403")
            return None
        hostport = re.sub(r"^https?://", "", server).rstrip("/")
        return f"http://{quote(user, safe='')}:{quote(pw, safe='')}@{hostport}"

    def _client() -> httpx.AsyncClient:
        """httpx client routed through the residential proxy for PCX/Mapbox.

        Use for every api.pcexpress.ca / api.mapbox.com call. OpenAI calls
        must stay direct (they'd break through a residential exit).
        """
        return httpx.AsyncClient(proxy=_pcx_proxy(), timeout=30.0)

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
        # GA Realtime API: mint an ephemeral key via /client_secrets. The beta
        # POST /v1/realtime/sessions endpoint was removed (returns 404), which
        # silently broke every session. Session config lives under `session`;
        # audio settings (transcription, VAD, noise reduction, voice) nest under
        # session.audio.input/output. The ephemeral secret is the top-level
        # `value` in the response (beta returned it under client_secret.value).
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/realtime/client_secrets",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "session": {
                        "type": "realtime",
                        "model": "gpt-realtime",
                        "instructions": SYSTEM_PROMPT,
                        "tools": TOOLS,
                        "output_modalities": ["audio"],
                        "max_output_tokens": 1024,
                        "audio": {
                            "input": {
                                "transcription": {
                                    "model": "gpt-4o-mini-transcribe-2025-12-15",
                                },
                                "turn_detection": {
                                    "type": "server_vad",
                                    "threshold": 0.75,
                                    "prefix_padding_ms": 300,
                                    "silence_duration_ms": 500,
                                },
                                "noise_reduction": {
                                    "type": "near_field",
                                },
                            },
                            "output": {
                                "voice": "cedar",
                            },
                        },
                    },
                },
            )
        data = resp.json()
        if resp.status_code != 200 or "value" not in data:
            _log(
                "session_error",
                session_id=session_id,
                status=resp.status_code,
                detail=str(data.get("error", data))[:300],
            )
            return JSONResponse(
                status_code=502,
                content={"error": "Failed to create realtime session"},
            )
        _log(
            "session_ready",
            session_id=session_id,
            model=data.get("session", {}).get("model", "?"),
        )
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

        async with _client() as client:
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
        async with _client() as client:
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
        async with _client() as client:
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
            comp_prices = prices.get("comparisonPrices", [])
            pu = p.get("pricingUnits") or {}

            is_weighted = pu.get("type") == "SOLD_BY_WEIGHT" or pu.get("weighted") is True

            item: dict = {
                "code": p.get("code"),
                "name": p.get("name"),
                "brand": p.get("brand"),
            }
            if is_weighted:
                kg_comp = next(
                    (c for c in comp_prices if (c.get("unit") or "").lower() == "kg"),
                    None,
                )
                pu_unit = (pu.get("unit") or "g").lower()
                to_kg = (lambda x: x / 1000) if pu_unit == "g" else (lambda x: float(x))
                step_kg = round(to_kg(pu.get("interval") or 100), 3)
                min_kg = round(to_kg(pu.get("minOrderQuantity") or 100), 3)
                max_q = pu.get("maxOrderQuantity")
                max_kg = round(to_kg(max_q), 3) if max_q else None
                item.update({
                    "sold_by": "weight",
                    "price_per_kg": kg_comp.get("value") if kg_comp else None,
                    "step_kg": step_kg,
                    "min_kg": min_kg,
                    "max_kg": max_kg,
                })
                print(
                    f"[search]   {item['code']} {item['brand'] or ''} {item['name']!r} sold_by=weight ${item['price_per_kg']}/kg"
                )
            else:
                max_count = pu.get("maxOrderQuantity")
                item.update({
                    "sold_by": "each",
                    "price": product_price,
                    "package_size": p.get("packageSize") or None,
                    "max_count": int(max_count) if max_count else None,
                })
                print(
                    f"[search]   {item['code']} {item['brand'] or ''} {item['name']!r} sold_by=each ${product_price}"
                )
            results.append(item)
        return {"products": results}

    WEIGHT_INCREMENT_G = 100

    @web_app.post("/api/add-to-cart")
    async def add_to_cart(request: Request):
        body = await request.json()
        cart_id = body.get("cart_id")
        store_id = body.get("store_id")
        banner = body.get("banner", "superstore")
        items = body.get("items", [])

        _log("add_to_cart", items=len(items), cart_id=cart_id, store_id=store_id, banner=banner)
        _inc("items_added", len(items))

        entries = {}
        item_sold_by = {}
        for item in items:
            code = item["product_code"]
            sold_by = item.get("sold_by", "each")
            item_sold_by[code] = sold_by
            if sold_by == "weight":
                kg = float(item.get("kg", 0))
                grams = round(kg * 1000 / WEIGHT_INCREMENT_G) * WEIGHT_INCREMENT_G
                grams = max(WEIGHT_INCREMENT_G, grams)
                entries[code] = {
                    "quantity": grams,
                    "fulfillmentMethod": "pickup",
                    "sellerId": store_id,
                }
                print(f"[add-to-cart]   {code} sold_by=weight kg={kg} -> {grams}g")
            else:
                count = int(item.get("count", item.get("quantity", 1)))
                entries[code] = {
                    "quantity": count,
                    "fulfillmentMethod": "pickup",
                    "sellerId": store_id,
                }
                print(f"[add-to-cart]   {code} sold_by=each count={count}")

        async with _client() as client:
            resp = await client.post(
                f"{PCX_BASE}/carts/{cart_id}",
                headers=pcx_headers(banner),
                json={"entries": entries},
            )
        data = resp.json()
        print(f"[add-to-cart] HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"[add-to-cart] Error response: {json.dumps(data, indent=2)}")

        requested_codes = set(entries.keys())
        added_codes = set()
        added_items = []
        cart_obj = data.get("cart", data)
        for order in cart_obj.get("orders", []):
            for entry in order.get("entries", []):
                offer = entry.get("offer", {})
                product = offer.get("product", {})
                code = product.get("code") or offer.get("id", "")
                if code not in requested_codes:
                    continue
                added_codes.add(code)
                raw_qty = entry.get("quantity", 0)
                if offer.get("sellingType") == "SOLD_BY_WEIGHT" or item_sold_by.get(code) == "weight":
                    selling_unit = (offer.get("sellingUnit") or "").upper()
                    kg = raw_qty if selling_unit == "KG" else raw_qty / 1000
                    natural = {"kg": round(kg, 3)}
                else:
                    natural = {"count": int(raw_qty)}
                added_items.append(
                    {"product_code": code, "name": product.get("name", ""), **natural}
                )
                print(f"[add-to-cart]   OK {code} {product.get('name', '')!r} {natural}")

        failed_items = []
        for err in data.get("errors", []):
            reason = err.get("message", "Unknown error")
            pc = err.get("productCode", "")
            if "exceeds maximum" in reason.lower():
                reason += " Check max_kg or max_count from search results and reduce quantity."
            failed_items.append({"product_code": pc, "reason": reason})
            print(f"[add-to-cart]   FAIL {pc}: {reason}")
        failed_codes = {f["product_code"] for f in failed_items}
        for code in requested_codes:
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

        async with _client() as client:
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
        modal.Secret.from_name("oxy-proxy"),
    ],
    timeout=3600,
    cpu=0.25,
    memory=256,
)
@modal.asgi_app()
def ui():
    return create_web_app()
