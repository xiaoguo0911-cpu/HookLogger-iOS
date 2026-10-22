#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, plistlib
from playwright.async_api import async_playwright

TARGET = "https://yjriz.nzctjvr.com/2VHkkYFEvf/vxwmS1ivH7eZWQKy"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def main():
    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, viewport={"width":390,"height":844})
        await ctx.add_init_script("""
            Object.defineProperty(navigator,'platform',{get:()=>'iPhone'});
            Object.defineProperty(navigator,'maxTouchPoints',{get:()}>5});
            window.__log=[];
            window.__opened=[];
            const _o=XMLHttpRequest.prototype.open,_s=XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open=function(m,u){this._u=u;return _o.apply(this,arguments)};
            XMLHttpRequest.prototype.send=function(b){
                const s=this;
                s.addEventListener('readystatechange',function(){
                    if(s.readyState===4) window.__log.push({url:s._u,status:s.status,resp:(s.responseText||'').slice(0,500)});
                });
                return _s.apply(this,arguments);
            };
            window.open=function(url){window.__opened.push(url||'');return null;};
        """)
        page = await ctx.new_page()
        async def on_itms(r):
            print(f"ITMS: {r.request.url}"); await r.abort()
        await page.route("itms-services://**", on_itms)

        cf_base = [None]
        dk = [None]
        async def on_resp(r):
            if 'cloudfront' in r.url and cf_base[0] is None:
                m = re.match(r'(https://[^/]+cloudfront\.net)', r.url)
                if m: cf_base[0] = m.group(1)
            if 'getinfo' in r.url:
                try:
                    body = await r.text()
                    dk[0] = json.loads(body)['data']['downloadKey']
                except: pass
        page.on("response", on_resp)

        try: await page.goto(TARGET, wait_until="load", timeout=30000)
        except: pass
        await asyncio.sleep(15)

        print(f"CF={cf_base[0]}, DK={dk[0]}")

        # 用浏览器 session 请求 ts15helper.plist
        if cf_base[0] and dk[0]:
            plist_url = f"{cf_base[0]}/clientapi/app/ts15helper.plist?appid=1cfhnSTQ1T3tLpjtE&k={dk[0]}"
            print(f"Fetching plist: {plist_url}")
            resp = await page.evaluate(f"""async () => {{
                const r = await fetch('{plist_url}', {{
                    headers: {{'Referer': '{cf_base[0]}/1cfhnSTQ1T3tLpjtE'}}
                }});
                return {{status: r.status, body: await r.text()}};
            }}""")
            print(f"plist status: {resp['status']}")
            print(f"plist body: {resp['body'][:300]}")

            if resp['status'] == 200 and 'plist' in resp['body'].lower():
                # 解析 plist
                import xml.etree.ElementTree as ET
                root = ET.fromstring(resp['body'])
                def find_url(n):
                    ch = list(n)
                    for i,c in enumerate(ch):
                        if c.tag=='key' and c.text=='url': return ch[i+1].text
                        r=find_url(c)
                        if r: return r
                ipa_url = find_url(root)
                print(f"IPA URL: {ipa_url}")
                if ipa_url:
                    # 用浏览器 session 下载
                    dl = await page.evaluate(f"""async () => {{
                        const r = await fetch('{ipa_url}');
                        if(!r.ok) return {{err: r.status}};
                        const buf = await r.arrayBuffer();
                        return {{size: buf.byteLength, magic: Array.from(new Uint8Array(buf.slice(0,4)))}};
                    }}""")
                    print(f"IPA download test: {dl}")
                    # 实际下载用 urllib (直接)
                    r2 = urllib.request.urlopen(urllib.request.Request(ipa_url, headers={"User-Agent":UA}), timeout=300)
                    total = int(r2.headers.get("Content-Length",0))
                    done = 0
                    with open("/tmp/downloaded.ipa","wb") as f:
                        while True:
                            c=r2.read(65536)
                            if not c: break
                            f.write(c); done+=len(c)
                            if total: print(f"{done*100//total}%",end="\r",flush=True)
                    print(f"\nDone: {os.path.getsize('/tmp/downloaded.ipa'):,} bytes")
                    sys.exit(0)

        opened = await page.evaluate("()=>window.__opened||[]")
        print(f"opened: {opened}")
        await browser.close()
    sys.exit(1)

asyncio.run(main())
