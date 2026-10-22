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
            r = find(c); 
            if r: return r
    return find(root)

async def main():
    itms_caught = []

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

        # 拦截 itms-services 协议
        async def handle_itms(route):
            url = route.request.url
            itms_caught.append(url)
            print(f"[ITMS] {url}")
            await route.abort()

        await page.route("itms-services://**", handle_itms)

        console_logs = []
        page.on("console", lambda m: console_logs.append(m.text))

        print("goto REFERER...")
        await page.goto(REFERER, wait_until="commit", timeout=10000)
        await asyncio.sleep(1)

        print("goto CF...")
        try:
            await page.goto(CF_URL, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(f"goto: {e}")

        await asyncio.sleep(10)

        print(f"ITMS: {itms_caught}")
        print(f"Console: {console_logs[:5]}")

        xhr = await page.evaluate("() => window.__xhrLog")
        download_key = None
        for e in xhr:
            print(f"XHR [{e['status']}] {e['url']}")
            if 'downloadKey' in e.get('resp', ''):
                try: download_key = json.loads(e['resp'])['data']['downloadKey']
                except: pass

        if not download_key:
            print("no DK"); sys.exit(1)

        print(f"DK: {download_key}")

        # React fiber BFS 找 itms URL
        itms_react = await page.evaluate("""() => {
            try {
                const root = document.getElementById('root');
                if (!root) return 'no #root';
                const k = Object.keys(root).find(k => k.startsWith('__react'));
                if (!k) return 'no react key, keys=' + Object.keys(root).slice(0,5).join(',');
                const queue = [root[k]];
                let i = 0;
                while (queue.length && i < 2000) {
                    i++;
                    const n = queue.shift();
                    if (!n) continue;
                    if (n.memoizedState) {
                        const s = n.memoizedState;
                        // 找 queue 里的 itms
                        if (s.queue && s.queue.dispatch) {
                            // skip
                        }
                        if (s.memoizedState && typeof s.memoizedState === 'string' && s.memoizedState.includes('itms')) {
                            return s.memoizedState;
                        }
                    }
                    if (n.memoizedProps) {
                        const p = n.memoizedProps;
                        for (const pk of Object.keys(p)) {
                            const v = p[pk];
                            if (typeof v === 'string' && v.includes('itms-services')) return v;
                        }
                    }
                    if (n.child) queue.push(n.child);
                    if (n.sibling) queue.push(n.sibling);
                }
                return 'searched ' + i + ' nodes, not found';
            } catch(e) { return 'err: '+e.message; }
        }""")
        print(f"React itms: {itms_react}")

        # 在 DOM 找 a 链接和 canvas
        links = await page.evaluate("""() => ({
            a: Array.from(document.querySelectorAll('a')).map(x=>x.href),
            canvas: document.querySelectorAll('canvas').length,
            txt: document.body.innerText.slice(0,300)
        })""")
        print(f"Links: {links['a']}")
        print(f"Canvas: {links['canvas']}")
        print(f"Text: {links['txt']}")

        # 拿 itms 或 plist
        itms_url = itms_caught[0] if itms_caught else None
        if not itms_url and isinstance(itms_react, str) and itms_react.startswith('itms'):
            itms_url = itms_react

        if not itms_url:
            print("[!] no itms URL found"); sys.exit(1)

        print(f"\nitms URL: {itms_url}")
        plist_url = re.search(r'url=([^&]+)', itms_url)
        if plist_url:
            plist_url = urllib.parse.unquote(plist_url.group(1))
            print(f"plist URL: {plist_url}")
            r = urllib.request.urlopen(urllib.request.Request(plist_url, headers={"User-Agent": UA}), timeout=15)
            plist_xml = r.read().decode()
            ipa_url = extract_ipa_url(plist_xml)
            print(f"IPA URL: {ipa_url}")
            if ipa_url:
                out = "/tmp/downloaded.ipa"
                r2 = urllib.request.urlopen(urllib.request.Request(ipa_url, headers={"User-Agent": UA}), timeout=300)
                total = int(r2.headers.get("Content-Length", 0))
                done = 0
                with open(out, "wb") as f:
                    while True:
                        chunk = r2.read(65536)
                        if not chunk: break
                        f.write(chunk); done += len(chunk)
                        if total: print(f"{done*100//total}%", end="\r", flush=True)
                print(f"\nDone! {os.path.getsize(out):,} bytes")

        await browser.close()

asyncio.run(main())
