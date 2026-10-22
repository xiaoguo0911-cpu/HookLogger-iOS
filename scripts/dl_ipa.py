#!/usr/bin/env python3
import asyncio, sys, os, json, re
import urllib.request, urllib.parse
from playwright.async_api import async_playwright

TARGET_CF = "https://doe29x10dqvat.cloudfront.net/1cfhnSTQ1T3tLpjtE"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
APPID = "1cfhnSTQ1T3tLpjtE"
BASE = "https://doe29x10dqvat.cloudfront.net"

async def main():
    all_resp = {}

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(user_agent=UA)
        page = await context.new_page()

        async def on_response(resp):
            try:
                body = await resp.text()
                all_resp[resp.url] = body
            except:
                pass

        page.on("response", on_response)

        # 直接到 CloudFront 页面（跳过跳转）
        print(f"goto {TARGET_CF}")
        try:
            await page.goto(TARGET_CF, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"goto: {e}")

        # 等待内容渲染
        for i in range(15):
            await asyncio.sleep(2)
            cnt = await page.content()
            txt = await page.evaluate("() => document.body.innerText || ''")
            if txt.strip():
                print(f"[{i*2}s] 页面有内容! 长度={len(txt)}")
                break
            els = await page.query_selector_all("button, a")
            if els:
                print(f"[{i*2}s] 找到 {len(els)} 个按钮/链接")
                break
            print(f"[{i*2}s] 空页面...")

        html = await page.content()
        print(f"HTML: {html[:1000]}")

        txt = await page.evaluate("() => document.body.innerText || ''")
        print(f"BODY TEXT: {txt[:500]}")

        # 找所有元素
        els = await page.query_selector_all("*[class]")
        print(f"元素数: {len(els)}")
        for el in els[:20]:
            try:
                cls = await el.get_attribute("class")
                txt2 = await el.inner_text()
                if txt2.strip():
                    print(f"  class={cls[:40]} text={txt2[:40]}")
            except:
                pass

        await browser.close()

    # 从 getinfo 提取 downloadKey
    download_key = None
    for url, body in all_resp.items():
        if 'getinfo' in url:
            try:
                data = json.loads(body)
                download_key = data['data']['downloadKey']
                app_name = data['data']['name']
                print(f"\n[getinfo] name={app_name} downloadKey={download_key}")
            except:
                pass

    if not download_key:
        print("[!] 未找到 downloadKey")
        sys.exit(1)

    # 尝试常见的下载 API 模式
    print("\n[*] 尝试下载 API...")
    api_patterns = [
        f"{BASE}/clientapi/app/getdownloadurl?appid={APPID}&downloadKey={download_key}",
        f"{BASE}/clientapi/app/install?appid={APPID}&downloadKey={download_key}",
        f"{BASE}/clientapi/app/download?appid={APPID}&downloadKey={download_key}",
        f"{BASE}/clientapi/ipa?appid={APPID}&downloadKey={download_key}",
        f"{BASE}/clientapi/app/plist?appid={APPID}&downloadKey={download_key}",
        f"{BASE}/publicres/plist/{download_key}.plist",
        f"{BASE}/app/{APPID}/plist?downloadKey={download_key}",
    ]
    for api in api_patterns:
        try:
            req = urllib.request.Request(api, headers={"User-Agent": UA, "Referer": TARGET_CF})
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read()
                print(f"  [OK {r.status}] {api}")
                print(f"    {body[:200]}")
        except urllib.error.HTTPError as e:
            print(f"  [{e.code}] {api}")
        except Exception as e:
            print(f"  [ERR] {api}: {e}")

asyncio.run(main())
