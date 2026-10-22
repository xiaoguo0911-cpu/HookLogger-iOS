#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, plistlib
from playwright.async_api import async_playwright

TARGET = "https://yjriz.nzctjvr.com/2VHkkYFEvf/vxwmS1ivH7eZWQKy"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def main():
    itms_urls = []
    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        ctx = await browser.new_context(user_agent=UA, viewport={"width":390,"height":844})
        await ctx.add_init_script("""
            Object.defineProperty(navigator,'platform',{get:()=>'iPhone'});
            Object.defineProperty(navigator,'maxTouchPoints',{get:()=>5});
            window.__log=[];
            window.__opened=[];
            const _o=XMLHttpRequest.prototype.open,_s=XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open=function(m,u){this._u=u;return _o.apply(this,arguments)};
            XMLHttpRequest.prototype.send=function(b){
                const s=this;
                s.addEventListener('readystatechange',function(){
                    if(s.readyState===4) window.__log.push({url:s._u,status:s.status,resp:(s.responseText||'').slice(0,8000)});
                });
                return _s.apply(this,arguments);
            };
            // 拦截 window.open
            const _origOpen = window.open;
            window.open = function(url) {
                console.log('[window.open]', url);
                window.__opened.push(url || '');
                if(url && url.includes('itms-services')) return null;
                return _origOpen ? _origOpen.apply(this, arguments) : null;
            };
        """)
        page = await ctx.new_page()
        console_msgs = []
        page.on("console", lambda m: console_msgs.append(m.text))

        async def on_itms(r):
            itms_urls.append(r.request.url)
            print(f"ITMS ROUTE: {r.request.url}")
            await r.abort()
        await page.route("itms-services://**", on_itms)

        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"goto: {e}")

        await asyncio.sleep(20)
        btns = await page.query_selector_all("button")
        print(f"Buttons: {len(btns)}")
        for btn in btns:
            txt = await btn.inner_text()
            if txt.strip() == "安装":
                print("Clicking install")
                await btn.click()
                break

        await asyncio.sleep(10)

        opened = await page.evaluate("()=>window.__opened||[]")
        xhr = await page.evaluate("()=>window.__log||[]")
        print(f"window.open calls: {opened}")
        print(f"ITMS route: {itms_urls}")
        print(f"console: {[m for m in console_msgs if 'window.open' in m or 'itms' in m.lower()][:5]}")

        for e in xhr:
            if "inhouse" in e["url"]:
                print(f"inhouse: {e['resp'][:100]}")

        await browser.close()

    all_itms = [u for u in (itms_urls + opened) if u and "itms-services" in u]
    print(f"All itms: {all_itms}")
    if all_itms:
        itms = all_itms[0]
        m = re.search(r"url=([^&\s\"]+)", itms)
        if m:
            plist_url = urllib.parse.unquote(m.group(1))
            print(f"plist: {plist_url}")
            r = urllib.request.urlopen(urllib.request.Request(plist_url,headers={"User-Agent":UA}), timeout=15)
            p = plistlib.loads(r.read())
            for a in p.get("items",[{}])[0].get("assets",[]):
                if a.get("kind")=="software-package":
                    ipa_url = a["url"]
                    print(f"IPA: {ipa_url}")
                    r2 = urllib.request.urlopen(urllib.request.Request(ipa_url,headers={"User-Agent":UA}), timeout=300)
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
    print("No itms"); sys.exit(1)

asyncio.run(main())
