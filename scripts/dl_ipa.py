#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from playwright.async_api import async_playwright

CF_URL = "https://doe29x10dqvat.cloudfront.net/1cfhnSTQ1T3tLpjtE"
REFERER = "https://yjriz.nzctjvr.com/"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
BASE = "https://doe29x10dqvat.cloudfront.net"
APPID = "1cfhnSTQ1T3tLpjtE"

def extract_ipa_url(plist_xml):
    root = ET.fromstring(plist_xml)
    def find(node):
        ch = list(node)
        for i, c in enumerate(ch):
            if c.tag == "key" and c.text == "url": return ch[i+1].text
            r = find(c)
            if r: return r
    return find(root)

async def main():
    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(
            user_agent=UA, viewport={"width": 390, "height": 844},
            extra_http_headers={"Referer": REFERER}
        )
        await context.add_init_script("""
            Object.defineProperty(navigator, 'platform', {get: () => 'iPhone'});
            Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 5});
            window.__xhrLog = [];
            window.__itmsUrl = null;
            // 拦截 location.href 赋值
            const origDesc = Object.getOwnPropertyDescriptor(window.Location.prototype, 'href') ||
                             Object.getOwnPropertyDescriptor(window, 'location');
            const _origAssign = window.location.assign.bind(window.location);
            window.location.assign = function(url) {
                console.log('[assign]', url);
                if (url && url.includes('itms')) { window.__itmsUrl = url; return; }
                return _origAssign(url);
            };
            // 拦截 XHR
            const _o = XMLHttpRequest.prototype.open;
            const _s = XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open = function(m, u) { this._u = u; return _o.apply(this, arguments); };
            XMLHttpRequest.prototype.send = function(b) {
                const s = this;
                s.addEventListener('readystatechange', function() {
                    if (s.readyState === 4) window.__xhrLog.push({url: s._u, status: s.status, resp: (s.responseText||'').slice(0,3000)});
                });
                return _s.apply(this, arguments);
            };
        """)

        page = await context.new_page()
        console_logs = []
        page.on("console", lambda m: console_logs.append(m.text))

        # 拦截导航到 itms-services
        itms_caught = []
        async def handle_route(route):
            url = route.request.url
            if 'itms-services' in url:
                itms_caught.append(url)
                print(f"[ITMS CAUGHT] {url}")
            await route.abort()
        await page.route("**", handle_route)
        await page.unroute("https://**")  # 只拦截非 https

        await page.goto(REFERER, wait_until="commit", timeout=10000)
        await asyncio.sleep(1)

        # 恢复正常路由，只拦截 itms
        await page.unroute("**")
        await page.route("itms-services://**", lambda route: (
            itms_caught.append(route.request.url) or
            asyncio.get_event_loop().create_task(route.abort())
        ))

        print("goto CloudFront...")
        try:
            await page.goto(CF_URL, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"goto: {e}")

        await asyncio.sleep(10)

        # 检查控制台
        print(f"Console logs: {console_logs[:10]}")
        print(f"ITMS caught: {itms_caught}")

        # 简单找 itms
        itms_from_window = await page.evaluate("() => window.__itmsUrl")
        print(f"itms from window: {itms_from_window}")

        # 在 DOM 里找 a[href] 和 canvas
        dom_info = await page.evaluate("""() => ({
            links: Array.from(document.querySelectorAll('a')).map(a => a.href).filter(h => h.length > 0),
            canvases: document.querySelectorAll('canvas').length,
            bodyText: document.body.innerText.slice(0, 200)
        })""")
        print(f"DOM: {json.dumps(dom_info, ensure_ascii=False)}")

        # XHR
        xhr = await page.evaluate("() => window.__xhrLog")
        print(f"XHR ({len(xhr)}):")
        download_key = None
        for e in xhr:
            print(f"  [{e['status']}] {e['url']}")
            if 'downloadKey' in e.get('resp', ''):
                try: download_key = json.loads(e['resp'])['data']['downloadKey']
                except: pass

        if not download_key:
            print("no downloadKey"); sys.exit(1)

        print(f"\ndownloadKey: {download_key}")

        # 尝试从 canvas 数量推断二维码，然后在页面内找 itms URL
        # 通过 window.__reactFiber 快速找
        itms_from_react = await page.evaluate("""() => {
            try {
                const root = document.getElementById('root');
                if (!root) return 'no root';
                const k = Object.keys(root).find(k => k.startsWith('__react'));
                if (!k) return 'no react key';
                // 简单的 BFS 找 itms
                const queue = [root[k]];
                let count = 0;
                while (queue.length && count < 500) {
                    count++;
                    const node = queue.shift();
                    if (!node) continue;
                    if (node.memoizedProps) {
                        const v = JSON.stringify(node.memoizedProps);
                        if (v && v.includes('itms-services')) {
                            return v.match(/itms-services:\/\/[^"'\s\\]+/)?.[0] || 'found but no match';
                        }
                    }
                    if (node.child) queue.push(node.child);
                    if (node.sibling) queue.push(node.sibling);
                }
                return 'not found in ' + count + ' nodes';
            } catch(e) { return 'err: ' + e.message; }
        }""")
        print(f"itms from React: {itms_from_react}")

        await browser.close()

asyncio.run(main())
