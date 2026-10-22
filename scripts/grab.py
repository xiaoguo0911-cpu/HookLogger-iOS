#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, plistlib, xml.etree.ElementTree as ET
from playwright.async_api import async_playwright

TARGET = "https://yjriz.nzctjvr.com/2VHkkYFEvf/vxwmS1ivH7eZWQKy"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def main():
    cf_base = [None]

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, viewport={"width":390,"height":844})
        await ctx.add_init_script("""
            Object.defineProperty(navigator,'platform',{get:function(){return 'iPhone'}});
            Object.defineProperty(navigator,'maxTouchPoints',{get:function(){return 5}});
            window.open=function(url){return null;};
        """)
        page = await ctx.new_page()
        async def on_resp(r):
            if 'cloudfront' in r.url and cf_base[0] is None:
                m = re.match(r'(https://[^/]+cloudfront\.net)', r.url)
                if m: cf_base[0] = m.group(1)
        page.on("response", on_resp)

        try: await page.goto(TARGET, wait_until="load", timeout=30000)
        except: pass
        await asyncio.sleep(15)
        print(f"CF={cf_base[0]}")
        if not cf_base[0]: sys.exit(1)

        # 直接在页面里调 getinfo 和 ts15helper.plist
        result = await page.evaluate("""async (cf) => {
            try {
                const gi = await fetch(cf + '/clientapi/app/getinfo?appid=1cfhnSTQ1T3tLpjtE&android=false');
                const giData = await gi.json();
                const dk = giData.data.downloadKey;
                console.log('DK:', dk);
                const purl = cf + '/clientapi/app/ts15helper.plist?appid=1cfhnSTQ1T3tLpjtE&k=' + dk;
                const pr = await fetch(purl, {headers:{'Referer': cf+'/1cfhnSTQ1T3tLpjtE'}});
                return {dk, plist_status: pr.status, plist_body: (await pr.text()).slice(0,500)};
            } catch(e) { return {error: e.message}; }
        }""", cf_base[0])
        print(f"Result: {result}")

        if result.get('plist_status') == 200:
            body = result['plist_body']
            root = ET.fromstring(body)
            def find_url(n):
                ch=list(n)
                for i,c in enumerate(ch):
                    if c.tag=='key' and c.text=='url': return ch[i+1].text
                    rv=find_url(c)
                    if rv: return rv
            ipa_url = find_url(root)
            print(f"IPA URL: {ipa_url}")
            if ipa_url:
                r2 = urllib.request.urlopen(urllib.request.Request(ipa_url,headers={"User-Agent":UA}),timeout=300)
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

        await browser.close()
    sys.exit(1)

asyncio.run(main())
