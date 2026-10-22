#!/usr/bin/env python3
import asyncio, sys, os, json, base64
import urllib.request
from playwright.async_api import async_playwright

CF_URL = "https://doe29x10dqvat.cloudfront.net/1cfhnSTQ1T3tLpjtE"
REFERER = "https://yjriz.nzctjvr.com/"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
BASE = "https://doe29x10dqvat.cloudfront.net"
APPID = "1cfhnSTQ1T3tLpjtE"

async def main():
    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(
            user_agent=UA,
            viewport={"width": 390, "height": 844},
            extra_http_headers={"Referer": REFERER}
        )

        all_xhr = []
        await context.add_init_script("""
            window.__xhrLog = [];
            const _orig_open = XMLHttpRequest.prototype.open;
            const _orig_send = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function(m, u) {
                this._u = u; return _orig_open.apply(this, arguments);
            };
            XMLHttpRequest.prototype.send = function(b) {
                const s = this;
                s.addEventListener('readystatechange', function() {
                    if (s.readyState === 4) {
                        window.__xhrLog.push({url: s._u, status: s.status, resp: (s.responseText||'').slice(0,3000)});
                    }
                });
                return _orig_send.apply(this, arguments);
            };
        """)

        page = await context.new_page()
        await page.goto(REFERER, wait_until="commit", timeout=10000)
        await asyncio.sleep(1)
        await page.goto(CF_URL, wait_until="networkidle", timeout=45000)
        await asyncio.sleep(8)

        # 截图保存
        await page.screenshot(path="/tmp/screen1.png", full_page=True)
        print("screenshot saved")

        # 检查 DOM
        body_html = await page.evaluate("() => document.body.innerHTML")
        print(f"body innerHTML len={len(body_html)}")
        print(f"body innerHTML: {body_html[:1000]}")

        # 检查 shadow DOM 和 iframe
        frames = page.frames
        print(f"\nframes: {len(frames)}")
        for i, frame in enumerate(frames):
            print(f"  frame[{i}] url={frame.url} name={frame.name}")
            try:
                txt = await frame.evaluate("() => document.body ? document.body.innerHTML : 'no body'")
                if txt and len(txt) > 10:
                    print(f"    innerHTML len={len(txt)}: {txt[:200]}")
            except:
                pass

        # 拿 downloadKey
        xhr_log = await page.evaluate("() => window.__xhrLog || []")
        download_key = None
        for e in xhr_log:
            if 'downloadKey' in e.get('resp', ''):
                try:
                    download_key = json.loads(e['resp'])['data']['downloadKey']
                    print(f"\ndownloadKey: {download_key}")
                except:
                    pass

        if not download_key:
            print("no downloadKey")
            sys.exit(1)

        # 尝试点击屏幕中心，看是否触发更多 XHR
        print("\nclicking center...")
        await page.mouse.click(195, 422)
        await asyncio.sleep(5)
        await page.screenshot(path="/tmp/screen2.png", full_page=True)

        xhr_log2 = await page.evaluate("() => window.__xhrLog || []")
        print(f"\nXHR after click ({len(xhr_log2)}):")
        for e in xhr_log2:
            print(f"  [{e['status']}] {e['url']}")
            if e['url'] != '/clientapi/app/getinfo?appid=1cfhnSTQ1T3tLpjtE&android=false':
                print(f"    {e['resp'][:300]}")

        # 上传截图到 artifact
        import shutil
        shutil.copy("/tmp/screen1.png", "/tmp/screen.png")

        await browser.close()

asyncio.run(main())
