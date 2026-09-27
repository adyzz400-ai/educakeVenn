from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import stealth_sync  # <--- NEW IMPORT
from dataclasses import dataclass
from typing import Optional
import re

# ... (Keep existing imports and classes)

def create_browser():
    pw = sync_playwright().start()

    # We launch with specific args to look more like a real browser
    browser = pw.chromium.launch(
        headless=True, 
        args=[
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-accelerated-2d-canvas",
            "--disable-gpu",
            "--no-drop-target",
            "--window-size=1920,1080",
            "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        ],
    )

    return pw, browser

def login(
    username: str,
    password: str,
    storage_state: Optional[dict] = None,
):
    pw, browser = create_browser()

    context_args = {
        "viewport": {
            "width": 1280,
            "height": 900,
        },
        # Essential: Set a real User-Agent here too
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    if storage_state:
        context_args["storage_state"] = storage_state

    context = browser.new_context(**context_args)
    page = context.new_page()

    # APPLY STEALTH TO THE PAGE
    # This masks the 'webdriver' property and other automation signals
    stealth_sync(page)

    try:
        # Increase timeout slightly to allow for Cloudflare's background checks
        page.goto(
            "https://my.educake.co.uk/",
            wait_until="domcontentloaded",
            timeout=45000,
        )

        # If Cloudflare is detected, we don't immediately crash. 
        # We wait a bit to see if the stealth bypass allows the page to resolve.
        if detect_cloudflare(page):
            # Wait a few seconds to see if the challenge auto-resolves
            page.wait_for_timeout(5000) 
            if detect_cloudflare(page):
                raise CloudflareChallenge(
                    "Educake/Cloudflare presented a browser verification page."
                )

        if is_logged_in(page):
            return pw, browser, context, page

        # ... (Rest of your login logic remains the same)
        # Ensure you wrap the subsequent navigation in the same context
        
        page.goto(
            "https://my.educake.co.uk/login",
            wait_until="domcontentloaded",
            timeout=45000,
        )

        # Apply stealth again if navigating to a new sensitive area
        stealth_sync(page)

        if detect_cloudflare(page):
            raise CloudflareChallenge(
                "Educake/Cloudflare presented a browser verification page."
            )

        # ... (The rest of the function follows your existing logic)