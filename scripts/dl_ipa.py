#!/usr/bin/env python3
import asyncio, sys, os, json, re
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

        # 注入 XHR 拦截器到所有页面
        await context.add_init_script("""
            window.__xhrLog = [];
            const _origOpen = XMLHttpRequest.prototype.open;
            const _origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function(method, url) {
                this.__xhrUrl = url;
                this.__xhrMethod = method;
                return _origOpen.apply(this, arguments);
            };
            XMLHttpRequest.prototype.send = function(body) {
                const xhr = this;
                const url = xhr.__xhrUrl;
                const origOnLoad = xhr.onload;
                const origOnReadyStateChange = xhr.onreadystatechange;
                
                function captureResp() {
                    if (xhr.readyState === 4) {
                        window.__xhrLog.push({
                            url: url,
                            status: xhr.status,
                            resp: xhr.responseText ? xhr.responseText.substring(0, 2000) : ''
                        });
                    }
                }
                
                xhr.addEventListener('readystatechange', captureResp);
                return _origSend.apply(this, arguments);
            };
        """)

        page = await context.new_page()

        print(f"goto {TARGET}")
        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"goto: {e}")

        # 等待 XHR 完成
        print("waiting 20s for XHR...")
        await asyncio.sleep(20)

        # 读取所有 XHR 日志
        xhr_log = await page.evaluate("() => window.__xhrLog || []")
        print(f"\n=== XHR LOG ({len(xhr_log)}) ===")
        download_key = None
        for entry in xhr_log:
            print(f"[{entry.get('status')}] {entry.get('url')}")
            resp_text = entry.get('resp', '')
            if resp_text:
                print(f"  {resp_text[:300]}")
            if 'getinfo' in str(entry.get('url', '')) and 'downloadKey' in resp_text:
                try:
                    data = json.loads(resp_text)
                    download_key = data['data']['downloadKey']
                    print(f"  => downloadKey: {download_key}")
                except:
                    pass

        if not download_key:
            print("[!] 未找到 downloadKey")
            sys.exit(1)

        # 在页面中直接调用下载 API
        print(f"\n[*] 尝试下载 APIs with downloadKey={download_key}")

        apis = [
            ("POST", f"{BASE}/clientapi/app/install",
             json.dumps({"appid": APPID, "downloadKey": download_key, "lang": "zh_CN"})),
            ("GET", f"{BASE}/clientapi/app/install?appid={APPID}&downloadKey={download_key}", ""),
            ("POST", f"{BASE}/clientapi/app/getdownload",
             json.dumps({"appid": APPID, "downloadKey": download_key})),
            ("GET", f"{BASE}/clientapi/app/getdownload?appid={APPID}&downloadKey={download_key}", ""),
            ("GET", f"{BASE}/clientapi/app/plist?appid={APPID}&downloadKey={download_key}", ""),
            ("POST", f"{BASE}/clientapi/app/download",
             json.dumps({"appid": APPID, "downloadKey": download_key})),
        ]

        for method, url, body in apis:
            try:
                js = f"""
                async () => {{
                    const opts = {{method: '{method}', headers: {{'Content-Type': 'application/json'}}}};
                    {'opts.body = JSON.stringify(' + json.dumps(json.loads(body)) + ');' if body else ''}
                    const r = await fetch('{url}', opts);
                    return {{status: r.status, body: await r.text()}};
                }}
                """
                result = await page.evaluate(js)
                print(f"  [{result['status']}] {method} {url}")
                if result['body']:
                    print(f"    {result['body'][:300]}")
            except Exception as e:
                print(f"  [ERR] {url}: {e}")

        await browser.close()

asyncio.run(main())
