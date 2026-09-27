from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from playwright_stealth import stealth_sync
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

class EducakeError(Exception):
    pass

class CloudflareChallenge(EducakeError):
    pass

class EducakeLoginError(EducakeError):
    pass

def detect_cloudflare(page):
    title = (page.title() or "").lower()
    url = page.url.lower()
    text = ""

    try:
        text = page.locator("body").inner_text(timeout=3000).lower()
    except Exception:
        pass

    indicators = [
        "just a moment",
        "checking your browser",
        "verify you are human",
        "security check",
        "cf-chl-",
        "cloudflare",
    ]

    if any(x in title for x in indicators):
        return True

    if any(x in text for x in indicators):
        return True

    if "challenge-platform" in url:
        return True

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
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    if storage_state:
        context_args["storage_state"] = storage_state

    context = browser.new_context(**context_args)
    page = context.new_page()
    
    # Apply stealth to mask automation signals
    stealth_sync(page)

    try:
        page.goto(
            "https://my.educake.co.uk/",
            wait_until="domcontentloaded",
            timeout=45000,
        )

        if detect_cloudflare(page):
            # Brief wait to see if stealth allows auto-resolution
            page.wait_for_timeout(3000)
            if detect_cloudflare(page):
                raise CloudflareChallenge(
                    "Educake/Cloudflare presented a browser verification page."
                )

        if is_logged_in(page):
            return pw, browser, context, page

        page.goto(
            "https://my.educake.co.uk/login",
            wait_until="domcontentloaded",
            timeout=45000,
        )

        if detect_cloudflare(page):
            raise CloudflareChallenge(
                "Educake/Cloudflare presented a browser verification page."
            )

        username_box = page.locator(
            "input[name='username'], "
            "input[name='email'], "
            "input[type='text'], "
            "input[type='email']"
        ).first

        password_box = page.locator(
            "input[name='password'], "
            "input[type='password']"
        ).first

        if not username_box.count():
            raise EducakeLoginError(
                "Could not find the Educake username/email field."
            )

        if not password_box.count():
            raise EducakeLoginError(
                "Could not find the Educake password field."
            )

        username_box.fill(username)
        password_box.fill(password)

        login_button = page.locator(
            "button:has-text('Log in'), "
            "button:has-text('Login'), "
            "input[type='submit']"
        ).first

        if not login_button.count():
            raise EducakeLoginError(
                "Could not find the Educake login button."
            )

        login_button.click()

        page.wait_for_load_state(
            "domcontentloaded",
            timeout=45000,
        )

        page.wait_for_timeout(3000)

        if detect_cloudflare(page):
            raise CloudflareChallenge(
                "Educake/Cloudflare presented a browser verification page."
            )

        if not is_logged_in(page):
            error_text = get_login_error(page)

            if error_text:
                raise EducakeLoginError(error_text)

            raise EducakeLoginError(
                "Educake login did not complete."
            )

        return pw, browser, context, page

    except Exception:
        try:
            browser.close()
        except Exception:
            pass

        try:
            pw.stop()
        except Exception:
            pass

        raise


def is_logged_in(page):
    url = page.url.lower()

    if "/login" not in url:
        return True

    indicators = [
        "my educake",
        "my account",
        "view all your quizzes",
        "track progress",
        "log out",
        "logout",
    ]

    try:
        text = page.locator("body").inner_text(timeout=5000).lower()

        return any(
            indicator in text
            for indicator in indicators
        )

    except Exception:
        return False


def get_login_error(page):
    selectors = [
        ".error",
        ".alert",
        ".alert-danger",
        "[role='alert']",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector).first

            if locator.count():
                text = locator.inner_text().strip()

                if text:
                    return text[:500]

        except Exception:
            pass

    return None


def save_storage_state(context):
    return context.storage_state()


def fetch_assignments(page):
    if detect_cloudflare(page):
        raise CloudflareChallenge(
            "Cloudflare verification detected."
        )

    assignments = []

    selectors = [
        "a",
        "button",
        "[role='link']",
    ]

    elements = []

    for selector in selectors:
        try:
            elements.extend(
                page.locator(selector).all()
            )
        except Exception:
            pass

    seen = set()

    for element in elements:
        try:
            text = " ".join(
                element.inner_text().split()
            )

            if not text:
                continue

            href = element.get_attribute("href") or ""

            combined = (
                text + " " + href
            ).lower()

            keywords = [
                "quiz",
                "homework",
                "assignment",
            ]

            if not any(
                keyword in combined
                for keyword in keywords
            ):
                continue

            if len(text) < 3:
                continue

            if text in seen:
                continue

            seen.add(text)

            parent_text = ""

            try:
                parent_text = element.locator(
                    "xpath=.."
                ).inner_text(timeout=1000)
            except Exception:
                pass

            subject = extract_subject(
                parent_text
            )

            teacher = extract_teacher(
                parent_text
            )

            due = extract_due_date(
                parent_text
            )

            if href.startswith("/"):
                href = (
                    "https://my.educake.co.uk"
                    + href
                )

            assignments.append(
                EducakeAssignment(
                    title=text[:100],
                    subject=subject,
                    teacher=teacher,
                    due=due,
                    url=href,
                )
            )

        except Exception:
            continue

    return deduplicate_assignments(
        assignments
    )


def extract_subject(text):
    match = re.search(
        r"subject\s*[:\-]\s*(.+)",
        text,
        re.I,
    )

    if match:
        return match.group(1).split("\n")[0][:80]

    return "Unknown"


def extract_teacher(text):
    match = re.search(
        r"teacher\s*[:\-]\s*(.+)",
        text,
        re.I,
    )

    if match:
        return match.group(1).split("\n")[0][:80]

    return "Unknown"


def extract_due_date(text):
    match = re.search(
        r"due\s*(?:date)?\s*[:\-]\s*(.+)",
        text,
        re.I,
    )

    if match:
        return match.group(1).split("\n")[0][:80]

    return "No due date"


def deduplicate_assignments(assignments):
    result = []
    seen = set()

    for assignment in assignments:
        key = (
            assignment.title.lower(),
            assignment.url,
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(assignment)

    return result


def open_assignment(page, assignment):
    if detect_cloudflare(page):
        raise CloudflareChallenge(
            "Cloudflare verification detected."
        )

    if not assignment.url:
        raise EducakeError(
            "This assignment does not have a usable URL."
        )

    page.goto(
        assignment.url,
        wait_until="domcontentloaded",
        timeout=30000,
    )

    page.wait_for_timeout(1500)

    if detect_cloudflare(page):
        raise CloudflareChallenge(
            "Cloudflare verification appeared while opening the assignment."
        )

    return page


def extract_questions(page):
    if detect_cloudflare(page):
        raise CloudflareChallenge(
            "Cloudflare verification detected."
        )

    candidates = []

    selectors = [
        "[data-question]",
        "fieldset",
        "article",
        ".question",
        "[class*='question']",
        "[id*='question']",
    ]

    for selector in selectors:
        try:
            loc = page.locator(selector)

            count = min(
                loc.count(),
                100,
            )

            for i in range(count):
                try:
                    text = " ".join(
                        loc.nth(i)
                        .inner_text()
                        .split()
                    )

                    if len(text) >= 10:
                        candidates.append(text)

                except Exception:
                    pass

        except Exception:
            pass

    output = []
    seen = set()

    for question in candidates:
        if question in seen:
            continue

        seen.add(question)

        output.append(question)

    return output