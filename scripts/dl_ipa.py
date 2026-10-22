#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from playwright.async_api import async_playwright

CF_URL = "https://doe29x10dqvat.cloudfront.net/1cfhnSTQ1T3tLpjtE"
REFERER = "https://yjriz.nzctjvr.com/"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def main():
    itms_url = None

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(
            user_agent=UA, viewport={"width": 390, "height": 844},
            extra_http_headers={"Referer": REFERER}
        )

        # 拦截 itms-services 导航
        await context.route("itms-services://**", lambda route: (
            setattr(sys.modules[__name__], '_itms', route.request.url) or route.abort()
        ))

        # 拦截所有请求记录
        all_reqs = []
        async def on_request(req):
            all_reqs.append(req.url)
            if 'itms' in req.url.lower() or 'plist' in req.url.lower():
                print(f"[REQ] {req.url}")

        page = await context.new_page()
        page.on("request", on_request)

        # 监听页面导航到 itms-services
        async def on_response(resp):
            if 'itms' in resp.url.lower() or 'plist' in resp.url.lower() or '.ipa' in resp.url.lower():
                print(f"[RESP {resp.status}] {resp.url}")

        page.on("response", on_response)

        print("goto...")
        await page.goto(REFERER, wait_until="commit", timeout=10000)
        await asyncio.sleep(1)

        # 捕获所有导航
        nav_urls = []
        async def on_framenavigated(frame):
            nav_urls.append(frame.url)
            print(f"[NAV] {frame.url}")

        page.on("framenavigated", on_framenavigated)

        try:
            await page.goto(CF_URL, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"goto: {e}")

        await asyncio.sleep(10)

        print(f"\nAll nav URLs: {nav_urls}")
        print(f"All reqs with itms/plist/ipa:")
        for u in all_reqs:
            if any(x in u.lower() for x in ['itms', 'plist', '.ipa']):
                print(f"  {u}")

        # 从 window 里找 itms URL
        try:
            result = await page.evaluate("""() => {
                // 找所有 a href 里的 itms-services
                const links = Array.from(document.querySelectorAll('a[href]'));
                return links.map(a => a.href).filter(h => h.includes('itms') || h.includes('plist'));
            }""")
            print(f"itms links in DOM: {result}")
        except Exception as e:
            print(f"eval err: {e}")

        await browser.close()

    # 用全局变量
    itms = getattr(sys.modules[__name__], '_itms', None)
    print(f"\nitms intercepted: {itms}")

asyncio.run(main())
