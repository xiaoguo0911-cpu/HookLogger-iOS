#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, plistlib
from playwright.async_api import async_playwright

TARGET = os.environ.get("TARGET_URL","")
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
BASE = "https://doe29x10dqvat.cloudfront.net"

async def main():
    itms_caught = []
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
            // 拦截 XHR
            const _o=XMLHttpRequest.prototype.open,_s=XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open=function(m,u){this._u=u;return _o.apply(this,arguments)};
            XMLHttpRequest.prototype.send=function(b){
                const s=this;
                s.addEventListener('readystatechange',function(){
                    if(s.readyState===4) window.__log.push({url:s._u,status:s.status,resp:(s.responseText||'').slice(0,3000)});
                });
                return _s.apply(this,arguments);
            };
            // 拦截 location 跳转
            const _loc=Object.getOwnPropertyDescriptor(window,'location');
            window.__itms=null;
            Object.defineProperty(window,'location',{
                get(){return _loc?_loc.get.call(this):window._fakeLocation||window.location;},
                set(v){
                    console.log('[location=]',v);
                    if(v&&v.toString().includes('itms-services')){window.__itms=v.toString();}
                    else if(_loc&&_loc.set){_loc.set.call(this,v);}
                }
            });
        """)
        page = await context.new_page()
        console_msgs = []
        page.on("console", lambda m: console_msgs.append(m.text))
        async def on_itms(route):
            itms_caught.append(route.request.url)
            print(f"[ITMS ROUTE] {route.request.url}")
            await route.abort()
        await page.route("itms-services://**", on_itms)
        print(f"goto CF...")
        await page.goto(BASE+"/1cfhnSTQ1T3tLpjtE", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(15)
        # 检查控制台
        for m in console_msgs:
            if 'itms' in m.lower() or 'location' in m.lower():
                print(f"console: {m}")
        # 检查 window.__itms
        itms_from_window = await page.evaluate("()=>window.__itms")
        print(f"window.__itms: {itms_from_window}")
        print(f"route captured: {itms_caught}")
        # 检查 XHR
        xhr = await page.evaluate("()=>window.__log||[]")
        dk = None
        for e in xhr:
            if 'downloadKey' in e.get('resp',''):
                try: dk = json.loads(e['resp'])['data']['downloadKey']
                except: pass
        print(f"downloadKey: {dk}")
        # 把 XHR 日志里的 URL 都收集起来
        for e in xhr:
            print(f"XHR [{e['status']}] {e['url']}")
        # 如果没有 itms，尝试用 downloadKey 和已知格式猜 plist URL
        itms = (itms_caught + [itms_from_window] + [None])[0]
        await browser.close()
    # 提取 plist URL 并下载
    if itms:
        print(f"itms: {itms}")
        m = re.search(r'url=([^&\s]+)', itms)
        if m:
            plist_url = urllib.parse.unquote(m.group(1))
            print(f"plist: {plist_url}")
            r = urllib.request.urlopen(urllib.request.Request(plist_url,headers={"User-Agent":UA}),timeout=15)
            p = plistlib.loads(r.read())
            for a in p.get('items',[{}])[0].get('assets',[]):
                if a.get('kind')=='software-package':
                    ipa = a['url']
                    print(f"IPA: {ipa}")
                    r2=urllib.request.urlopen(urllib.request.Request(ipa,headers={"User-Agent":UA}),timeout=300)
                    with open("/tmp/downloaded.ipa","wb") as f:
                        done=0
                        while True:
                            c=r2.read(65536);
                            if not c: break
                            f.write(c);done+=len(c)
                            print(f"{done//1024}KB",end="\r",flush=True)
                    print(f"\nDone: {os.path.getsize('/tmp/downloaded.ipa'):,} bytes")
                    break
    elif dk:
        # 直接尝试所有可能的 plist URL
        for path in [
            f"/clientapi/app/ios5helper.plist?a=1cfhnSTQ1T3tLpjtE&k={dk}",
            f"/clientapi/ios5helper.plist?a=1cfhnSTQ1T3tLpjtE&k={dk}",
            f"/clientapi/app/manifest.plist?a=1cfhnSTQ1T3tLpjtE&k={dk}",
            f"/clientapi/download?appid=1cfhnSTQ1T3tLpjtE&downloadKey={dk}",
        ]:
            url = BASE + path
            try:
                r = urllib.request.urlopen(urllib.request.Request(url,headers={"User-Agent":UA,"Referer":BASE+"/1cfhnSTQ1T3tLpjtE"}),timeout=10)
                body = r.read()
                print(f"[{r.status}] {path}: {body[:200]}")
                if b'software-package' in body or b'plist' in body or len(body) > 1000:
                    open('/tmp/manifest.raw','wb').write(body)
                    print(f"saved {len(body)} bytes")
            except Exception as e:
                print(f"[ERR] {path}: {e}")
    else:
        print("No itms or downloadKey found"); sys.exit(1)

asyncio.run(main())
