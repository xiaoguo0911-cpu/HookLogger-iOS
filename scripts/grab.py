#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, plistlib
from playwright.async_api import async_playwright

TARGET = "https://yjriz.nzctjvr.com/2VHkkYFEvf/vxwmS1ivH7eZWQKy"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def main():
    itms_urls = []

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(
            user_agent=UA, viewport={"width":390,"height":844},
        )
        await context.add_init_script("""
            Object.defineProperty(navigator,'platform',{get:()=>'iPhone'});
            Object.defineProperty(navigator,'maxTouchPoints',{get:()=>5});
            window.__log=[];
            const _o=XMLHttpRequest.prototype.open,_s=XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open=function(m,u){this._u=u;return _o.apply(this,arguments)};
            XMLHttpRequest.prototype.send=function(b){
                const s=this;
                s.addEventListener('readystatechange',function(){
                    if(s.readyState===4) window.__log.push({url:s._u,status:s.status,resp:(s.responseText||'').slice(0,8000)});
                });
                return _s.apply(this,arguments);
            };
            // 捕获所有字符串赋值给 location.href
            window.__locHref = [];
            const _locDesc = Object.getOwnPropertyDescriptor(window.Location.prototype, 'href');
            if (_locDesc) {
                Object.defineProperty(window.Location.prototype, 'href', {
                    get: _locDesc.get,
                    set: function(v) {
                        if (typeof v === 'string') window.__locHref.push(v);
                        if (!v || !v.toString().includes('itms')) {
                            _locDesc.set.call(this, v);
                        }
                    },
                    configurable: true
                });
            }
        """)
        page = await context.new_page()

        async def on_itms(route):
            itms_urls.append(route.request.url)
            print(f"[ITMS] {route.request.url}")
            await route.abort()
        await page.route("itms-services://**", on_itms)

        print(f"goto {TARGET}")
        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"goto: {e}")

        await asyncio.sleep(25)  # 多等一会

        final_url = page.url
        print(f"final: {final_url}")

        xhr = await page.evaluate("()=>window.__log||[]")
        dk = None
        enc_data = None
        for e in xhr:
            print(f"XHR [{e['status']}] {e['url']}")
            if 'getinfo' in e['url']:
                try: dk = json.loads(e['resp'])['data']['downloadKey']
                except: pass
            if 'inhouse' in e['url']:
                try: enc_data = json.loads(e['resp']).get('data','')
                except: pass

        loc_hrefs = await page.evaluate("()=>window.__locHref||[]")
        print(f"loc hrefs: {loc_hrefs}")
        print(f"itms: {itms_urls}")
        print(f"dk: {dk}")

        # 找所有以 itms 开头的字符串（从任何变量）
        all_itms = await page.evaluate("""() => {
            const found = [];
            function check(v) {
                if (typeof v === 'string' && v.includes('itms-services')) found.push(v.slice(0,500));
            }
            // 检查 localStorage, sessionStorage
            try { for(let i=0;i<localStorage.length;i++) check(localStorage.getItem(localStorage.key(i))); } catch(e) {}
            try { for(let i=0;i<sessionStorage.length;i++) check(sessionStorage.getItem(sessionStorage.key(i))); } catch(e) {}
            // 检查所有全局 string 变量
            for (const k of Object.keys(window)) {
                try { check(window[k]); } catch(e) {}
            }
            return found;
        }""")
        print(f"all itms strings: {all_itms}")

        if not (itms_urls or all_itms or loc_hrefs):
            # 最后手段：取得所有 a 元素的 href 
            links = await page.evaluate("""() => 
                Array.from(document.querySelectorAll('a,canvas,[href]')).map(e => ({
                    tag:e.tagName, href:e.href||'', text:e.innerText||''
                })).filter(e => e.href || e.text)
            """)
            print(f"links: {links[:10]}")

        await browser.close()

    # 处理找到的 itms URL
    found = itms_urls + all_itms + loc_hrefs
    found = [u for u in found if 'itms-services' in str(u)]
    print(f"\nfound itms: {found}")

    if found:
        itms = found[0]
        m = re.search(r'url=([^&\s"]+)', itms)
        if m:
            plist_url = urllib.parse.unquote(m.group(1))
            print(f"plist: {plist_url}")
            r = urllib.request.urlopen(urllib.request.Request(plist_url, headers={"User-Agent": UA}), timeout=15)
            p = plistlib.loads(r.read())
            for a in p.get('items',[{}])[0].get('assets',[]):
                if a.get('kind')=='software-package':
                    ipa_url = a['url']
                    print(f"IPA URL: {ipa_url}")
                    r2 = urllib.request.urlopen(urllib.request.Request(ipa_url, headers={"User-Agent": UA}), timeout=300)
                    total = int(r2.headers.get("Content-Length",0))
                    done = 0
                    with open("/tmp/downloaded.ipa","wb") as f:
                        while True:
                            c = r2.read(65536)
                            if not c: break
                            f.write(c); done += len(c)
                            if total: print(f"{done*100//total}%", end="\r", flush=True)
                    print(f"\nDone: {os.path.getsize('/tmp/downloaded.ipa'):,} bytes")
    else:
        print("no itms found"); sys.exit(1)

asyncio.run(main())
