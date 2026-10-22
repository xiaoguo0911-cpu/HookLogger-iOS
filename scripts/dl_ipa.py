#!/usr/bin/env python3
import asyncio, sys, os, json, re
import urllib.request, urllib.parse
from playwright.async_api import async_playwright

TARGET = "https://yjriz.nzctjvr.com/2VHkkYFEvf/vxwmS1ivH7eZWQKy"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def main():
    all_resp = {}
    download_key = None

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(user_agent=UA)
        page = await context.new_page()

        # 拦截所有响应
        async def on_response(resp):
            try:
                body = await resp.text()
                all_resp[resp.url] = body
                if 'clientapi' in resp.url:
                    print(f"API {resp.status} {resp.url}")
                    print(f"  {body[:300]}")
            except:
                pass

        page.on("response", on_response)

        # 注入 XHR 拦截器
        await context.add_init_script("""
            const _origOpen = XMLHttpRequest.prototype.open;
            const _origSend = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function(method, url) {
                this._url = url;
                this._method = method;
                console.log('[XHR open]', method, url);
                return _origOpen.apply(this, arguments);
            };
            XMLHttpRequest.prototype.send = function(body) {
                console.log('[XHR send]', this._url, body ? body.slice(0,200) : '');
                this.addEventListener('load', function() {
                    console.log('[XHR resp]', this._url, this.status, this.responseText ? this.responseText.slice(0,300) : '');
                });
                return _origSend.apply(this, arguments);
            };
            const _origFetch = window.fetch;
            window.fetch = function(url, opts) {
                console.log('[fetch]', url, JSON.stringify(opts||{}).slice(0,200));
                return _origFetch.apply(this, arguments).then(r => {
                    r.clone().text().then(t => console.log('[fetch resp]', url, r.status, t.slice(0,300)));
                    return r;
                });
            };
        """)

        print(f"goto {TARGET}")
        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"goto: {e}")

        # 等待页面并监控控制台
        logs = []
        page.on("console", lambda m: logs.append(m.text))

        await asyncio.sleep(15)

        print("\n=== CONSOLE LOGS ===")
        for log in logs:
            print(f"  {log}")

        # 从 getinfo 提取 downloadKey
        for url, body in all_resp.items():
            if 'getinfo' in url:
                try:
                    data = json.loads(body)
                    download_key = data['data']['downloadKey']
                    print(f"\n[downloadKey] {download_key}")
                except:
                    pass

        if not download_key:
            # 从 cookie 或响应中找
            cookies = await context.cookies()
            print(f"[cookies] {[c['name']+':'+c['value'][:20] for c in cookies]}")
            print("[!] 未找到 downloadKey，退出")
            sys.exit(1)

        # 尝试在页面里直接触发下载
        print("\n[*] 尝试通过 JS 触发下载...")
        try:
            result = await page.evaluate(f"""
                async () => {{
                    const r = await fetch('/clientapi/app/install', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{appid: '1cfhnSTQ1T3tLpjtE', downloadKey: '{download_key}', lang: 'zh_CN'}})
                    }});
                    return await r.text();
                }}
            """)
            print(f"  install result: {result[:300]}")
        except Exception as e:
            print(f"  install err: {e}")

        await browser.close()

asyncio.run(main())
