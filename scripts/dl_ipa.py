#!/usr/bin/env python3
import asyncio, sys, os, json
import urllib.request, urllib.parse
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
            extra_http_headers={"Referer": REFERER}
        )

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
        await asyncio.sleep(10)

        # 拿 downloadKey
        xhr_log = await page.evaluate("() => window.__xhrLog || []")
        download_key = None
        for e in xhr_log:
            if 'downloadKey' in e.get('resp', ''):
                try:
                    download_key = json.loads(e['resp'])['data']['downloadKey']
                except:
                    pass

        print(f"downloadKey: {download_key}")
        if not download_key:
            sys.exit(1)

        # 用 downloadKey 尝试 iOS 分发平台常见的 plist API
        # 从 JS 分析: /clientapi/app/...tget?a=appid&k=downloadKey
        # 以及 /clientapi/.../5helper.plist
        apis = [
            f"/clientapi/app/tget?a={APPID}&k={download_key}",
            f"/clientapi/apptget?a={APPID}&k={download_key}",
            f"/clientapi/app/get?a={APPID}&k={download_key}",
            f"/clientapi/download/tget?a={APPID}&k={download_key}",
            f"/clientapi/app/5helper.plist?a={APPID}&k={download_key}",
            f"/clientapi/ios5helper.plist?a={APPID}&k={download_key}",
            f"/clientapi/app/manifest?appid={APPID}&downloadKey={download_key}",
        ]
        print("\n[*] try APIs:")
        for path in apis:
            url = BASE + path
            try:
                r = await page.evaluate(f"""async () => {{
                    const res = await fetch('{url}');
                    return {{s: res.status, b: (await res.text()).slice(0,500)}};
                }}""")
                print(f"  [{r['s']}] {path}")
                if r['b'] and r['s'] != 404:
                    print(f"    {r['b']}")
            except Exception as e:
                print(f"  [ERR] {path}: {e}")

        # 监控下一个 XHR（在等待期间）
        await asyncio.sleep(5)
        new_log = await page.evaluate("() => window.__xhrLog || []")
        print(f"\n=== ALL XHR ({len(new_log)}) ===")
        for e in new_log:
            print(f"[{e['status']}] {e['url']}")

        await browser.close()

asyncio.run(main())
