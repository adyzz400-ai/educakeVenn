import time
import random
from dataclasses import dataclass
from typing import Optional
import re

# SAFE IMPORT PATTERN
try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    from playwright_stealth import stealth
except Exception as e:
    print(f"[DeepHat] CRITICAL IMPORT ERROR: {e}")
    # Fallback to prevent bot crash during boot
    stealth = None

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

# --- HUMAN SIMULATION UTILITIES ---

def human_delay(min_s=1, max_s=3):
    time.sleep(random.uniform(min_s, max_s))

def human_type(page, selector, text):
    """Types text with randomized delays to mimic a human."""
    try:
        page.focus(selector)
        for char in text:
            page.type(selector, char, delay=random.randint(60, 160))
            time.sleep(random.uniform(0.05, 0.1))
    except Exception:
        pass

# --- CORE LOGIC ---

def detect_cloudflare(page):
    try:
        title = (page.title() or "").lower()
        url = page.url.lower()
        indicators = ["just a moment", "checking your browser", "verify you are human", "cloudflare"]
        return any(x in title for x in indicators) or "challenge-platform" in url
    except:
        return False

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

    context_args = {
        "viewport": {"width": 1280, "height": 900},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    if storage_state:
        context_args["storage_state"] = storage_state

    context = browser.new_context(**context_args)
    page = context.new_page()
    
    # Apply Stealth safely
    if stealth:
        try:
            stealth(page)
        except Exception as e:
            print(f"[DeepHat] Stealth application failed: {e}")

    try:
        page.goto("https://my.educake.co.uk/login", wait_until="domcontentloaded", timeout=45000)
        
        if detect_cloudflare(page):
            page.wait_for_timeout(7000) # Wait for bypass

        # Login Field Selectors
        username_selector = "input[name='username'], input[name='email'], input[type='text']"
        password_selector = "input[name='password'], input[type='password']"

        page.wait_for_selector(username_selector, timeout=15000)
        
        # Human-like delay and typing
        human_delay(1, 2)
        human_type(page, username_selector, username)
        human_delay(0.5, 1.5)
        human_type(page, password_selector, password)
        human_delay(1, 2)

        login_button = page.locator("button:has-text('Log in'), button:has-text('Login'), input[type='submit']").first
        login_button.click()

        # Wait for login to settle
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(4000)

        if detect_cloudflare(page):
            raise CloudflareChallenge("Cloudflare detected after login attempt.")

        if not is_logged_in(page):
            error_msg = get_login_error(page)
            raise EducakeLoginError(error_msg if error_msg else "Login failed.")

        return pw, browser, context, page

    except Exception as e:
        browser.close()
        pw.stop()
        raise e

def is_logged_in(page):
    url = page.url.lower()
    if "/login" not in url: return True
    indicators = ["my educake", "my account", "view all your quizzes", "log out"]
    try:
        text = page.locator("body").inner_text(timeout=5000).lower()
        return any(ind in text for ind in indicators)
    except:
        return False

def get_login_error(page):
    selectors = [".error", ".alert", ".alert-danger", "[role='alert']"]
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count():
                text = locator.inner_text().strip()
                if text: return text[:500]
        except: pass
    return None

def save_storage_state(context):
    return context.storage_state()

def fetch_assignments(page):
    if detect_cloudflare(page):
        raise CloudflareChallenge("Cloudflare detected during assignment fetch.")

    assignments = []
    selectors = ["a", "button", "[role='link']"]
    elements = []

    for selector in selectors:
        try:
            elements.extend(page.locator(selector).all())
        except: pass

    seen = set()
    for element in elements:
        try:
            text = " ".join(element.inner_text().split())
            if not text or len(text) < 3: continue
            
            href = element.get_attribute("href") or ""
            combined = (text + " " + href).lower()
            if not any(k in combined for k in ["quiz", "homework", "assignment"]): continue
            if text in seen: continue
            seen.add(text)

            # Extracting details
            parent_text = ""
            try: parent_text = element.locator("xpath=..").inner_text(timeout=1000)
            except: pass

            subject = extract_subject(parent_text)
            teacher = extract_teacher(parent_text)
            due = extract_due_date(parent_text)

            if href.startswith("/"):
                href = "https://my.educake.co.uk" + href

            assignments.append(EducakeAssignment(
                title=text[:100], subject=subject, teacher=teacher, due=due, url=href
            ))
        except: continue

    return deduplicate_assignments(assignments)

def extract_subject(text):
    match = re.search(r"subject\s*[:\-]\s*(.+)", text, re.I)
    return match.group(1).split("\n")[0][:80] if match else "Unknown"

def extract_teacher(text):
    match = re.search(r"teacher\s*[:\-]\s*(.+)", text, re.I)
    return match.group(1).split("\n")[0][:80] if match else "Unknown"

def extract_due_date(text):
    match = re.search(r"due\s*(?:date)?\s*[:\-]\s*(.+)", text, re.I)
    return match.group(1).split("\n")[0][:80] if match else "No due date"

def deduplicate_assignments(assignments):
    result, seen = [], set()
    for a in assignments:
        key = (a.title.lower(), a.url)
        if key not in seen:
            seen.add(key)
            result.append(a)
    return result

def open_assignment(page, assignment):
    if detect_cloudflare(page):
        page.wait_for_timeout(5000)
    if not assignment.url: raise EducakeError("No assignment URL.")
    page.goto(assignment.url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)
    return page

def extract_questions(page):
    candidates = []
    selectors = ["[data-question]", "fieldset", "article", ".question", "[class*='question']"]
    for selector in selectors:
        try:
            loc = page.locator(selector)
            for i in range(min(loc.count(), 10)): # Limit to 10 to prevent massive loops
                text = " ".join(loc.nth(i).inner_text().split())
                if len(text) >= 10: candidates.append(text)
        except: pass
    return list(set(candidates))
