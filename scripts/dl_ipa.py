#!/usr/bin/env python3
import asyncio, sys, os, json
import urllib.request
from playwright.async_api import async_playwright

TARGET = "https://yjriz.nzctjvr.com/2VHkkYFEvf/vxwmS1ivH7eZWQKy"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
BASE = "https://doe29x10dqvat.cloudfront.net"
APPID = "1cfhnSTQ1T3tLpjtE"

async def main():
    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(user_agent=UA)

        await context.add_init_script("""
            window.__xhrLog = [];
            const _origOpen = XMLHttpRequest.prototype.open;
            const _origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function(method, url) {
                this.__xhrUrl = url;
                return _origOpen.apply(this, arguments);
            };
            XMLHttpRequest.prototype.send = function(body) {
                const self = this;
                this.addEventListener('readystatechange', function() {
                    if (self.readyState === 4) {
                        window.__xhrLog.push({
                            url: self.__xhrUrl || '',
                            status: self.status,
                            resp: self.responseText ? self.responseText.substring(0, 3000) : ''
                        });
                    }
                });
                return _origSend.apply(this, arguments);
            };
        """)

        page = await context.new_page()

        print(f"goto {TARGET}")
        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"  goto: {e}")

        # 等待重定向到 CloudFront
        print(f"current url: {page.url}")
        try:
            await page.wait_for_url("*cloudfront*", timeout=15000)
            print(f"redirected to: {page.url}")
        except Exception as e:
            print(f"  wait_for_url: {e}")
            print(f"  current url: {page.url}")

        # 等待 API 调用完成
        print("waiting 15s...")
        await asyncio.sleep(15)

        current_url = page.url
        print(f"final url: {current_url}")

        # 读 XHR log
        xhr_log = await page.evaluate("() => window.__xhrLog || []")
        print(f"\n=== XHR LOG ({len(xhr_log)}) ===")
        download_key = None
        for entry in xhr_log:
            print(f"[{entry.get('status')}] {entry.get('url')}")
            resp = entry.get('resp', '')
            print(f"  {resp[:200]}")
            if 'downloadKey' in resp:
                try:
                    d = json.loads(resp)
                    download_key = d['data']['downloadKey']
                    print(f"  => downloadKey: {download_key}")
                except:
                    pass

        if not download_key:
            print("[!] 未找到 downloadKey，退出")
            sys.exit(1)

        # 用页面内 fetch 试各种 API
        print(f"\n[*] 尝试下载 APIs...")
        for method, path, body in [
            ("POST", "/clientapi/app/install", json.dumps({"appid": APPID, "downloadKey": download_key, "lang": "zh_CN"})),
            ("GET", f"/clientapi/app/install?appid={APPID}&downloadKey={download_key}", ""),
            ("POST", "/clientapi/app/getdownloadurl", json.dumps({"appid": APPID, "downloadKey": download_key})),
            ("GET", f"/clientapi/app/getdownloadurl?appid={APPID}&downloadKey={download_key}", ""),
            ("GET", f"/clientapi/app/plist?appid={APPID}&downloadKey={download_key}", ""),
            ("POST", "/clientapi/app/download", json.dumps({"appid": APPID, "downloadKey": download_key})),
            ("GET", f"/clientapi/app/download?appid={APPID}&downloadKey={download_key}", ""),
        ]:
            url = BASE + path
            try:
                js_body = f"opts.body = {repr(body)};" if body else ""
                result = await page.evaluate(f"""
                    async () => {{
                        const opts = {{method: '{method}', headers: {{'Content-Type':'application/json'}}}};
                        {js_body}
                        const r = await fetch('{url}', opts);
                        return {{status: r.status, body: (await r.text()).substring(0, 400)}};
                    }}
                """)
                print(f"  [{result['status']}] {method} {path}")
                if result['body']:
                    print(f"    {result['body']}")
            except Exception as e:
                print(f"  [ERR] {path}: {e}")

        await browser.close()

asyncio.run(main())
