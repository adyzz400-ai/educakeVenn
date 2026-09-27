import time
import random
import re
from dataclasses import dataclass
from typing import Optional
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

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

# --- HUMAN SIMULATION ---
def human_delay(min_s=1, max_s=3):
    time.sleep(random.uniform(min_s, max_s))

def human_type(page, selector, text):
    try:
        page.focus(selector)
        for char in text:
            page.type(selector, char, delay=random.randint(70, 160))
            time.sleep(random.uniform(0.05, 0.1))
    except: pass

def detect_cloudflare(page):
    try:
        title = (page.title() or "").lower()
        indicators = ["just a moment", "checking your browser", "verify you are human", "cloudflare"]
        return any(x in title for x in indicators)
    except: return False

def create_browser():
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=True,
        args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
            "--window-size=1920,1080",
        ],
    )
    return pw, browser

def login(username: str, password: str, storage_state: Optional[dict] = None):
    pw, browser = create_browser()
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    
    context_args = {"viewport": {"width": 1280, "height": 900}, "user_agent": user_agent}
    if storage_state: context_args["storage_state"] = storage_state

    context = browser.new_context(**context_args)
    page = context.new_page()

    try:
        page.goto("https://my.educake.co.uk/login", wait_until="domcontentloaded", timeout=45000)
        if detect_cloudflare(page):
            page.wait_for_timeout(7000) # Wait for stealth bypass

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

        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(4000)

        if detect_cloudflare(page):
            raise CloudflareChallenge("Cloudflare detected.")

        return pw, browser, context, page
    except Exception as e:
        browser.close()
        pw.stop()
        raise e

def is_logged_in(page):
    try:
        text = page.locator("body").inner_text(timeout=5000).lower()
        return any(ind in text for ind in ["my educake", "my account", "log out"])
    except: return False

def get_login_error(page):
    try:
        locator = page.locator(".error, .alert, [role='alert']").first
        return locator.inner_text() if locator.count() else None
    except: return None

def save_storage_state(context): return context.storage_state()

def fetch_assignments(page):
    assignments = []
    # Simplified fetcher for stability
    try:
        page.wait_for_selector("body", timeout=10000)
        # This is a placeholder for your actual scraping logic
        # Re-insert your specific selectors here
        return assignments 
    except: return []

def open_assignment(page, assignment):
    page.goto(assignment.url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    return page

def extract_questions(page):
    # Placeholder: Insert your actual question extraction logic here
    return [] 
