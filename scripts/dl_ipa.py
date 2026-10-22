#!/usr/bin/env python3
import asyncio, sys, os, re
from playwright.async_api import async_playwright

TARGET = os.environ.get("TARGET_URL", "")
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def main():
    all_reqs = []

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(user_agent=UA)
        page = await context.new_page()

        async def on_request(req):
            all_reqs.append(req.url)
            print(f"REQ {req.method} {req.url}")

        async def on_response(resp):
            try:
                body = await resp.text()
                if len(body) < 3000 and resp.status != 200 or "download" in resp.url.lower() or "plist" in resp.url.lower() or "ipa" in resp.url.lower():
                    print(f"RESP {resp.status} {resp.url}")
                    print(f"  {body[:400]}")
            except:
                pass

        page.on("request", on_request)
        page.on("response", on_response)

        print(f"goto {TARGET}")
        try:
            await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"goto err: {e}")

        await asyncio.sleep(5)

        body_text = await page.inner_text("body")
        print(f"PAGE TEXT: {body_text[:1000]}")

        elements = await page.query_selector_all("button, a, div[class*=btn], div[class*=download], div[class*=install]")
        print(f"ELEMENTS: {len(elements)}")
        for el in elements:
            try:
                tag = await el.evaluate("e => e.tagName")
                txt = await el.inner_text()
                print(f"  {tag}: {txt[:40]}")
            except:
                pass

        print(f"ALL REQS ({len(all_reqs)}):")
        for u in all_reqs:
            print(f"  {u}")

        content = await page.content()
        itms = re.findall(r'itms-services://[^\s\'"<>]+', content)
        ipas = re.findall(r'https?://[^\s\'"<>]+\.ipa[^\s\'"<>]*', content)
        print(f"itms: {itms}")
        print(f"ipa_urls: {ipas}")

        await browser.close()

asyncio.run(main())
