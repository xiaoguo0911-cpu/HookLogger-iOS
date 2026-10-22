#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, plistlib
from playwright.async_api import async_playwright

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
BASE = "https://doe29x10dqvat.cloudfront.net"
APPID = "1cfhnSTQ1T3tLpjtE"

async def main():
    itms_urls = []

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(
            user_agent=UA, viewport={"width":390,"height":844},
            extra_http_headers={"Referer":"https://yjriz.nzctjvr.com/"}
        )
        await context.add_init_script("""
            Object.defineProperty(navigator,'platform',{get:()=>'iPhone'});
            Object.defineProperty(navigator,'maxTouchPoints',{get:()=>5});
            window.__log=[];
            window.__itms=[];
            const _o=XMLHttpRequest.prototype.open,_s=XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open=function(m,u){this._u=u;return _o.apply(this,arguments)};
            XMLHttpRequest.prototype.send=function(b){
                const s=this;
                s.addEventListener('readystatechange',function(){
                    if(s.readyState===4) window.__log.push({url:s._u,status:s.status,resp:(s.responseText||'').slice(0,8000)});
                });
                return _s.apply(this,arguments);
            };
            // 最重要: 拦截 window.location.href 赋值
            let _origHref = Object.getOwnPropertyDescriptor(window.Location.prototype, 'href') || 
                            {get: function(){return window.location.href}, set: function(v){window.location.href=v}};
            try {
                Object.defineProperty(window.Location.prototype, 'href', {
                    get: _origHref.get,
                    set: function(v) {
                        console.log('[LOC HREF]', v);
                        window.__itms.push(v);
                        if(!v.includes('itms')) {
                            _origHref.set.call(this, v);
                        }
                    }
                });
            } catch(e) {}
            // 也拦截 document.location
            // 拦截 open() 和 location.assign
            const origAssign = window.location.assign;
            window.location.assign = function(url) {
                console.log('[ASSIGN]', url);
                window.__itms.push(url);
                if(!url.includes('itms')) return origAssign.call(this, url);
            };
            // 拦截 <a> 标签点击
            document.addEventListener('click', function(e) {
                const a = e.target.closest('a');
                if(a && a.href && a.href.includes('itms')) {
                    e.preventDefault();
                    console.log('[A CLICK]', a.href);
                    window.__itms.push(a.href);
                }
            }, true);
        """)

        page = await context.new_page()
        console_logs = []
        page.on("console", lambda m: console_logs.append(m.text))

        # 拦截 itms 请求
        async def on_itms(route):
            itms_urls.append(route.request.url)
            print(f"[ROUTE ITMS] {route.request.url}")
            await route.abort()
        await page.route("itms-services://**", on_itms)

        print("loading page...")
        await page.goto(BASE+"/"+APPID, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(20)

        # 读取
        console_itms = [m for m in console_logs if 'itms' in m.lower() or 'ASSIGN' in m or 'LOC HREF' in m]
        print(f"console itms: {console_itms}")

        window_itms = await page.evaluate("()=>window.__itms||[]")
        print(f"window.__itms: {window_itms}")

        # 找所有 a[href] 包含 itms
        links = await page.evaluate("""()=>{
            return Array.from(document.querySelectorAll('a')).map(a=>a.href).filter(h=>h.includes('itms'));
        }""")
        print(f"itms links: {links}")

        # 查看 DOM 状态
        body = await page.evaluate("()=>document.body.innerHTML.slice(0,2000)")
        print(f"body: {body[:500]}")

        # 查看所有 XHR 里的 inhouse 响应
        xhr = await page.evaluate("()=>window.__log||[]")
        for e in xhr:
            print(f"XHR [{e['status']}] {e['url']}")

        await browser.close()

    all_itms = itms_urls + window_itms + links
    print(f"\nAll itms: {all_itms}")

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
                    with open("/tmp/downloaded.ipa","wb") as f:
                        while True:
                            c = r2.read(65536)
                            if not c: break
                            f.write(c)
                    print(f"Done: {os.path.getsize('/tmp/downloaded.ipa'):,} bytes")
    else:
        print("no itms found"); sys.exit(1)

asyncio.run(main())
