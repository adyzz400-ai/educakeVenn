import time
import random
from playwright.sync_api import sync_playwright
from playwright_stealth import stealth
from dataclasses import dataclass
from typing import Optional
import re

@dataclass
class EducakeAssignment:
    title: str
    subject: str = "Unknown"
    teacher: str = "Unknown"
    due: str = "No due date"
    url: str = ""

class EducakeError(Exception): pass
class CloudflareChallenge(EducakeError): pass
class EducakeLoginError(EducakeError): pass

def human_delay(min_s=1, max_s=3):
    time.sleep(random.uniform(min_s, max_s))

def human_type(page, selector, text):
    page.focus(selector)
    for char in text:
        page.type(selector, char, delay=random.randint(60, 160))
        time.sleep(random.uniform(0.05, 0.1))

def detect_cloudflare(page):
    title = (page.title() or "").lower()
    indicators = ["just a moment", "checking your browser", "verify you are human", "cloudflare"]
    return any(x in title for x in indicators)

def create_browser():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu", "--disable-blink-features=AutomationControlled"]
    )
    return pw, browser

def login(username: str, password: str, storage_state: Optional[dict] = None):
    pw, browser = create_browser()
    context_args = {
        "viewport": {"width": 1280, "height": 900},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    if storage_state: context_args["storage_state"] = storage_state

    context = browser.new_context(**context_args)
    page = context.new_page()
    
    try:
        stealth(page)
        page.goto("https://my.educake.co.uk/login", wait_until="domcontentloaded", timeout=45000)
        
        if detect_cloudflare(page):
            page.wait_for_timeout(6000) # Wait for stealth bypass

        # Human-like interaction
        username_selector = "input[name='username'], input[name='email']"
        password_selector = "input[name='password']"
        
        page.wait_for_selector(username_selector, timeout=15000)
        human_delay(1, 2)
        human_type(page, username_selector, username)
        human_delay(0.5, 1.5)
        human_type(page, password_selector, password)
        human_delay(1, 2)

        login_button = page.locator("button:has-text('Log in'), button:has-text('Login'), input[type='submit']").first
        login_button.click()

        # Wait for login to complete
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(4000)

        if detect_cloudflare(page):
            raise CloudflareChallenge("Cloudflare detected after login.")

        return pw, browser, context, page

    except Exception as e:
        browser.close()
        pw.stop()
        raise e

# ... (Keep fetch_assignments, extract_questions, etc. from your original code)
