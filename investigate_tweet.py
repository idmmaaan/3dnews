import asyncio
import json
from app.services.x_scraper import fetch_recent_tweets, _scrape_profile, settings
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        await context.add_cookies([
            {"name": "auth_token", "value": settings.X_AUTH_TOKEN, "domain": ".x.com", "path": "/", "httpOnly": True, "secure": True},
            {"name": "ct0", "value": settings.X_CT0, "domain": ".x.com", "path": "/", "secure": True},
        ])
        
        captured_data = []
        page = await context.new_page()
        
        async def handle_response(response):
            if "UserTweets" in response.url and response.status == 200:
                body = await response.json()
                captured_data.append(body)

        page.on("response", handle_response)
        await page.goto("https://x.com/CNN", wait_until="domcontentloaded", timeout=20000)
        await asyncio.sleep(6)
        
        with open("/tmp/dump.json", "w") as f:
            json.dump(captured_data, f, indent=2)
            
        print(f"Dumped {len(captured_data)} responses to /tmp/dump.json")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
