"""Voice shopping backend (FastAPI on Modal).

Serves the WebRTC voice frontend, mints OpenAI Realtime ephemeral keys, and
proxies every shopping tool call to the superstore MCP server — all PC Express
and Mapbox logic (including the residential-proxy WAF workaround) lives there.
"""

import modal

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi", "httpx", "fastmcp>=2.3")
    .add_local_dir("./voice-app/public", remote_path="/app/public")
)

app = modal.App("voice-shopping")

usage_stats = modal.Dict.from_name("voice-usage-stats", create_if_missing=True)

DEFAULT_MCP_URL = "https://dbandrews--superstore-mcp-mcp-server.modal.run/mcp"


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

- Before calling any tool, say a very short filler phrase first (e.g. "One sec — checking.", "Let me look that up.") so the user never hears dead air while the tool runs. Vary the phrasing.
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
    import os
    import uuid
    from datetime import datetime, timezone

    import httpx
    from fastapi import FastAPI, Request
    from fastapi.responses import HTMLResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from fastmcp import Client
    from starlette.middleware.base import BaseHTTPMiddleware

    web_app = FastAPI()

    MCP_URL = os.environ.get("SUPERSTORE_MCP_URL", DEFAULT_MCP_URL)
    MCP_TIMEOUT_S = 90.0

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

    def _tool_payload(res) -> dict:
        """Extract a tool's dict payload across fastmcp client versions."""
        data = getattr(res, "data", None)
        if isinstance(data, dict):
            return data
        structured = getattr(res, "structured_content", None)
        if isinstance(structured, dict):
            return structured.get("result", structured)
        blocks = res if isinstance(res, list) else getattr(res, "content", None) or []
        for block in blocks:
            text = getattr(block, "text", None)
            if text:
                try:
                    return json.loads(text)
                except ValueError:
                    return {"text": text}
        return {}

    async def call_mcp(tool: str, args: dict) -> dict:
        async with Client(MCP_URL, timeout=MCP_TIMEOUT_S) as client:
            result = await client.call_tool(tool, args)
        return _tool_payload(result)

    def _mcp_error(tool: str, exc: Exception) -> JSONResponse:
        _log("mcp_error", tool=tool, error=str(exc)[:300])
        return JSONResponse(status_code=502, content={"error": f"{tool} failed: {exc}"})

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
        body = await request.json()
        location = body.get("location") or body.get("postal_code") or ""
        _log("find_stores", query=f'"{location}"')
        _inc("store_lookups")
        try:
            result = await call_mcp("superstore_find_nearest_stores", {"location": location})
        except Exception as exc:
            return _mcp_error("find_nearest_stores", exc)
        if result.get("error"):
            return JSONResponse(status_code=400, content={"error": result["error"]})
        for s in result.get("stores", []):
            print(
                f"[find-stores]   #{s.get('storeId')} [{s.get('banner')}] {s.get('name')}"
                f" — {s.get('distance_km')}km — {s.get('address')}"
            )
        return result

    @web_app.post("/api/create-cart")
    async def create_cart(request: Request):
        body = await request.json()
        store_id = body.get("store_id")
        banner = body.get("banner", "superstore")
        _log("create_cart", store_id=store_id, banner=banner)
        try:
            result = await call_mcp(
                "superstore_create_cart", {"store_id": store_id, "banner": banner}
            )
        except Exception as exc:
            return _mcp_error("create_cart", exc)
        # The MCP tool returns cart_url with ?forceCartId baked in; the frontend
        # appends forceCartId itself, so hand it the base review URL.
        if result.get("cart_url"):
            result["cart_url"] = result["cart_url"].split("?")[0]
        _log("create_cart_done", cart_id=result.get("cart_id"))
        return result

    @web_app.post("/api/search-products")
    async def search_products(request: Request):
        body = await request.json()
        term = body.get("term")
        store_id = body.get("store_id")
        banner = body.get("banner", "superstore")
        _log("search", term=f'"{term}"', store_id=store_id, banner=banner)
        _inc("searches")
        try:
            result = await call_mcp(
                "superstore_search_products",
                {
                    "store_id": store_id,
                    "banner": banner,
                    "term": term,
                    "cart_id": body.get("cart_id") or "",
                },
            )
        except Exception as exc:
            return _mcp_error("search_products", exc)
        products = result.get("products", [])
        print(f"[search] {len(products)} shoppable products for {term!r}")
        return result

    @web_app.post("/api/add-to-cart")
    async def add_to_cart(request: Request):
        body = await request.json()
        cart_id = body.get("cart_id")
        store_id = body.get("store_id")
        banner = body.get("banner", "superstore")
        # Normalize into the MCP tool's discriminated-union item shapes so a
        # missing count/kg from the model degrades gracefully instead of
        # failing schema validation.
        items = []
        for it in body.get("items", []):
            if it.get("sold_by") == "weight":
                items.append(
                    {
                        "product_code": it.get("product_code"),
                        "sold_by": "weight",
                        "kg": float(it.get("kg") or 0.1),
                    }
                )
            else:
                items.append(
                    {
                        "product_code": it.get("product_code"),
                        "sold_by": "each",
                        "count": int(it.get("count") or it.get("quantity") or 1),
                    }
                )
        _log("add_to_cart", items=len(items), cart_id=cart_id, store_id=store_id, banner=banner)
        _inc("items_added", len(items))
        try:
            result = await call_mcp(
                "superstore_add_to_cart",
                {"cart_id": cart_id, "store_id": store_id, "banner": banner, "items": items},
            )
        except Exception as exc:
            return _mcp_error("add_to_cart", exc)
        result.setdefault("added_items", [])
        result.setdefault("failed_items", [])
        result["success"] = len(result["added_items"]) > 0
        print(
            f"[add-to-cart] {len(result['added_items'])} added, "
            f"{len(result['failed_items'])} failed"
        )
        return result

    @web_app.post("/api/remove-from-cart")
    async def remove_from_cart(request: Request):
        body = await request.json()
        cart_id = body.get("cart_id")
        store_id = body.get("store_id")
        banner = body.get("banner", "superstore")
        codes = body.get("product_codes") or [
            it.get("product_code") for it in body.get("items", [])
        ]
        _log("remove_from_cart", items=len(codes), cart_id=cart_id, banner=banner)
        try:
            result = await call_mcp(
                "superstore_remove_from_cart",
                {
                    "cart_id": cart_id,
                    "store_id": store_id,
                    "banner": banner,
                    "product_codes": codes,
                },
            )
        except Exception as exc:
            return _mcp_error("remove_from_cart", exc)
        result.setdefault("removed_items", [])
        result.setdefault("failed_items", [])
        result["success"] = len(result["removed_items"]) > 0
        print(
            f"[remove-from-cart] {len(result['removed_items'])} removed, "
            f"{len(result['failed_items'])} failed"
        )
        return result

    @web_app.post("/api/finish-shopping")
    async def finish_shopping(request: Request):
        body = await request.json()
        cart_id = body.get("cart_id")
        banner = body.get("banner", "superstore")
        _log("finish_shopping", cart_id=cart_id, banner=banner)
        _inc("completed_sessions")
        if not cart_id:
            # e.g. off_topic exit before a store was ever picked
            return {"success": True, "message": "Shopping session complete", "cart_url": None}
        try:
            result = await call_mcp(
                "superstore_finish_shopping", {"cart_id": cart_id, "banner": banner}
            )
        except Exception as exc:
            return _mcp_error("finish_shopping", exc)
        return {
            "success": True,
            "message": "Shopping session complete",
            "cart_url": result.get("cart_url"),
        }

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
        modal.Secret.from_name("pc-express-voice-app-token"),
    ],
    timeout=3600,
    cpu=0.25,
    memory=256,
)
@modal.asgi_app()
def ui():
    return create_web_app()
