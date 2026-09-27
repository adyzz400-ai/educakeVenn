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

    try:
        # 1. Navigate with a longer timeout
        print("[DeepHat] Navigating to Educake...")
        page.goto("https://my.educake.co.uk/login", wait_until="domcontentloaded", timeout=60000)
        
        # 2. Wait for Cloudflare to potentially resolve
        if detect_cloudflare(page):
            print("[DeepHat] Cloudflare detected. Waiting for bypass...")
            page.wait_for_timeout(10000) # Increase wait to 10s

        # 3. Robust Selector Strategy
        # We don't just look for one thing; we look for anything that looks like a login field
        print("[DeepHat] Searching for login fields...")
        
        # Try to find the username box with multiple attempts
        username_selectors = [
            "input[name='username']", 
            "input[name='email']", 
            "input[type='text']", 
            "input[id*='email']"
        ]
        
        username_box = None
        for selector in username_selectors:
            try:
                # Check if element exists and is visible
                loc = page.locator(selector).first
                if loc.is_visible(timeout=5000):
                    username_box = loc
                    break
            except:
                continue

        if not username_box:
            # If still not found, take a screenshot for debugging (if you can see logs)
            # page.screenshot(path="debug_login_error.png") 
            raise EducakeLoginError("Could not find the Educake username field. Page might be blocked.")

        # 4. Password Box
        password_selector = "input[name='password'], input[type='password']"
        page.wait_for_selector(password_selector, timeout=10000)
        password_box = page.locator(password_selector).first

        # 5. Human-like Typing (Crucial for bypassing detection)
        print("[DeepHat] Typing credentials...")
        human_delay(1, 2)
        human_type(page, username_selector, username) # Use the first successful selector
        human_delay(0.5, 1.5)
        human_type(page, password_selector, password)
        human_delay(1, 2)

        # 6. Click Login
        login_button_selectors = ["button:has-text('Log in')", "button:has-text('Login')", "input[type='submit']"]
        login_button = None
        for selector in login_button_selectors:
            try:
                loc = page.locator(selector).first
                if loc.is_visible(timeout=5000):
                    login_button = loc
                    break
            except: continue

        if not login_button:
            raise EducakeLoginError("Could not find the login button.")

        login_button.click()
        
        # 7. Final check
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(5000) # Wait for redirection

        if detect_cloudflare(page):
            raise CloudflareChallenge("Cloudflare blocked the login after submission.")

        return pw, browser, context, page

    except Exception as e:
        print(f"[DeepHat] Login Error: {e}")
        browser.close()
        pw.stop()
        raise e
