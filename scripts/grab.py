#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, plistlib
from playwright.async_api import async_playwright

TARGET = "https://yjriz.nzctjvr.com/2VHkkYFEvf/vxwmS1ivH7eZWQKy"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def main():
    itms_urls = []

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(user_agent=UA, viewport={"width":390,"height":844})
        await context.add_init_script("""
            Object.defineProperty(navigator,'platform',{get:()=>'iPhone'});
            Object.defineProperty(navigator,'maxTouchPoints',{get:()=>5});
            window.__log=[];
            window.__navLog=[];
            const _o=XMLHttpRequest.prototype.open,_s=XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open=function(m,u){this._u=u;return _o.apply(this,arguments)};
            XMLHttpRequest.prototype.send=function(b){
                const s=this;
                s.addEventListener('readystatechange',function(){
                    if(s.readyState===4) window.__log.push({url:s._u,status:s.status,resp:(s.responseText||'').slice(0,8000)});
                });
                return _s.apply(this,arguments);
            };
            const _oa=window.location.assign.bind(window.location);
            window.location.assign=function(u){window.__navLog.push({t:'assign',u});return _oa(u);};
            window.open=function(u){window.__navLog.push({t:'open',u});return null;};
        """)
        page = await context.new_page()

        async def on_itms(route):
            itms_urls.append(route.request.url)
            print(f"[ITMS] {route.request.url}")
            await route.abort()
        await page.route("itms-services://**", on_itms)

        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except: pass
        await asyncio.sleep(20)

        # 找并点击"安装"按钮
        btns = await page.query_selector_all("button")
        print(f"buttons: {len(btns)}")
        for btn in btns:
            txt = await btn.inner_text()
            print(f"  btn: '{txt}'")
            if '安装' in txt and '前' not in txt and '后' not in txt:
                print(f"  >> CLICKING: '{txt}'")
                await btn.click()
                await asyncio.sleep(5)
                break

        # 等待 itms 导航
        await asyncio.sleep(5)

        nav_log = await page.evaluate("()=>window.__navLog||[]")
        xhr = await page.evaluate("()=>window.__log||[]")
        print(f"navLog: {nav_log}")
        print(f"itms: {itms_urls}")

        # 新增 XHR
        for e in xhr:
            if 'inhouse' in e['url'] or 'download' in e['url'].lower():
                print(f"XHR [{e['status']}] {e['url']}")
                print(f"  {e['resp'][:200]}")

        await browser.close()

    all_itms = itms_urls + [n['u'] for n in nav_log if 'itms' in str(n.get('u',''))]
    print(f"all itms: {all_itms}")

    if all_itms:
        itms = all_itms[0]
        m = re.search(r'url=([^&\s"]+)', itms)
        if m:
            plist_url = urllib.parse.unquote(m.group(1))
            print(f"plist: {plist_url}")
            r = urllib.request.urlopen(urllib.request.Request(plist_url, headers={"User-Agent": UA}), timeout=15)
            p = plistlib.loads(r.read())
            for a in p.get('items',[{}])[0].get('assets',[]):
                if a.get('kind')=='software-package':
                    ipa_url = a['url']
                    print(f"IPA: {ipa_url}")
                    r2 = urllib.request.urlopen(urllib.request.Request(ipa_url, headers={"User-Agent": UA}), timeout=300)
                    total = int(r2.headers.get("Content-Length",0))
                    done = 0
                    with open("/tmp/downloaded.ipa","wb") as f:
                        while True:
                            c=r2.read(65536);
                            if not c: break
                            f.write(c); done+=len(c)
                            if total: print(f"{done*100//total}%",end="\r",flush=True)
                    print(f"\nDone: {os.path.getsize('/tmp/downloaded.ipa'):,} bytes")
                    sys.exit(0)
    print("no itms"); sys.exit(1)

asyncio.run(main())
