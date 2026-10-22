#!/usr/bin/env python3
import asyncio, sys, os, re, json
from playwright.async_api import async_playwright

TARGET = os.environ.get("TARGET_URL", "")
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def main():
    all_responses = {}

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(user_agent=UA)
        page = await context.new_page()

        async def on_response(resp):
            try:
                body = await resp.text()
                all_responses[resp.url] = body
                if 'clientapi' in resp.url or resp.status >= 300:
                    print(f"RESP {resp.status} {resp.url}")
                    print(f"  {body[:300]}")
            except:
                pass

        page.on("response", on_response)

        print(f"goto {TARGET}")
        try:
            await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"goto: {e}")

        # 等待页面 JS 完全执行
        print("waiting 20s...")
        await asyncio.sleep(20)

        # 打印完整 HTML
        content = await page.content()
        print(f"HTML len={len(content)}")
        print(content[:3000])

        # 找所有可点击元素
        print("\n=== CLICKABLE ===")
        for sel in ["button", "a", "[onclick]", "div", "span"]:
            els = await page.query_selector_all(sel)
            for el in els:
                try:
                    box = await el.bounding_box()
                    if box and box['width'] > 10 and box['height'] > 10:
                        txt = await el.inner_text()
                        if txt.strip():
                            print(f"  {sel}: '{txt[:40]}' @ {box}")
                except:
                    pass

        # 尝试通过 JS 直接调用下载
        print("\n=== JS EVAL ===")
        try:
            result = await page.evaluate("""
                () => {
                    const keys = Object.keys(window).filter(k => {
                        try {
                            const v = window[k];
                            return typeof v === 'object' && v !== null && JSON.stringify(v).includes('downloadKey');
                        } catch(e) { return false; }
                    });
                    return keys.slice(0,5).map(k => ({k, v: JSON.stringify(window[k]).slice(0,200)}));
                }
            """)
            print("downloadKey in window:", result)
        except Exception as e:
            print(f"eval err: {e}")

        await browser.close()

asyncio.run(main())
