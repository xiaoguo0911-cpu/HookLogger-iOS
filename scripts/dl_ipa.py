#!/usr/bin/env python3
import asyncio, sys, os, json
import urllib.request
from playwright.async_api import async_playwright

CF_URL = "https://doe29x10dqvat.cloudfront.net/1cfhnSTQ1T3tLpjtE"
REFERER = "https://yjriz.nzctjvr.com/2VHkkYFEvf/vxwmS1ivH7eZWQKy"
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

        # 先访问原始页面设置 referer cookie
        print(f"step1: goto original page")
        try:
            await page.goto(REFERER, wait_until="commit", timeout=10000)
        except:
            pass
        await asyncio.sleep(1)

        # 再跳到 CloudFront，模拟正常用户流程
        print(f"step2: goto CloudFront")
        try:
            await page.goto(CF_URL, wait_until="networkidle", timeout=45000)
        except Exception as e:
            print(f"  goto: {e}")

        print(f"current url: {page.url}")
        await asyncio.sleep(15)

        # 读 XHR
        xhr_log = await page.evaluate("() => window.__xhrLog || []")
        print(f"\n=== XHR ({len(xhr_log)}) ===")
        download_key = None
        for entry in xhr_log:
            print(f"[{entry['status']}] {entry['url']}")
            if entry['resp']:
                print(f"  {entry['resp'][:200]}")
                if 'downloadKey' in entry['resp']:
                    try:
                        d = json.loads(entry['resp'])
                        download_key = d['data']['downloadKey']
                        print(f"  => DK: {download_key}")
                    except:
                        pass

        if not download_key:
            print("[!] no downloadKey")
            sys.exit(1)

        # 试各种下载 API
        print(f"\n[*] try download APIs (downloadKey={download_key})")
        tests = [
            ("POST", "/clientapi/app/install",
             {"appid": APPID, "downloadKey": download_key, "lang": "zh_CN"}),
            ("GET", f"/clientapi/app/install?appid={APPID}&downloadKey={download_key}", None),
            ("POST", "/clientapi/app/getdownloadurl",
             {"appid": APPID, "downloadKey": download_key}),
            ("GET", f"/clientapi/app/getdownloadurl?appid={APPID}&downloadKey={download_key}", None),
            ("POST", "/clientapi/app/plist",
             {"appid": APPID, "downloadKey": download_key}),
            ("GET", f"/clientapi/app/plist?appid={APPID}&downloadKey={download_key}", None),
        ]
        for method, path, body_dict in tests:
            url = BASE + path
            body_js = f"opts.body = JSON.stringify({json.dumps(body_dict)});" if body_dict else ""
            try:
                r = await page.evaluate(f"""async () => {{
                    const opts = {{method:'{method}',headers:{{'Content-Type':'application/json'}}}};
                    {body_js}
                    const res = await fetch('{url}', opts);
                    return {{s: res.status, b: (await res.text()).slice(0,500)}};
                }}""")
                print(f"  [{r['s']}] {method} {path}")
                if r['b']:
                    print(f"    {r['b']}")
            except Exception as e:
                print(f"  [ERR] {path}: {e}")

        await browser.close()

asyncio.run(main())
