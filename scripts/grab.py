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
            window.__decLog=[];  // 解密日志
            const _o=XMLHttpRequest.prototype.open,_s=XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open=function(m,u){this._u=u;return _o.apply(this,arguments)};
            XMLHttpRequest.prototype.send=function(b){
                const s=this;
                s.addEventListener('readystatechange',function(){
                    if(s.readyState===4) window.__log.push({url:s._u,status:s.status,resp:(s.responseText||'').slice(0,8000)});
                });
                return _s.apply(this,arguments);
            };
            // 拦截所有函数调用，找返回 itms URL 的那个
            // 重写 String.prototype.startsWith 来检测
            const _origSW = String.prototype.startsWith;
            String.prototype.startsWith = function(prefix) {
                const result = _origSW.call(this, prefix);
                if(prefix && prefix.includes('itms-services') && this.length > 10) {
                    window.__decLog.push({
                        input: this.slice(0, 300),
                        prefix: prefix,
                        result: result
                    });
                    console.log('[startsWith itms]', this.slice(0, 300), '|', prefix, '|', result);
                }
                return result;
            };
            // 也拦截 includes 检查 itms
            const _origInc = String.prototype.includes;
            String.prototype.includes = function(s) {
                if(s && s.includes('itms') && this.length > 10) {
                    window.__decLog.push({type:'includes', str: this.slice(0,300), search: s});
                }
                return _origInc.call(this, s);
            };
        """)
        page = await context.new_page()

        async def on_itms(route):
            itms_urls.append(route.request.url)
            print(f"[ITMS ROUTE] {route.request.url}")
            await route.abort()
        await page.route("itms-services://**", on_itms)

        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except: pass

        await asyncio.sleep(20)

        # 找安装按钮并点击
        btns = await page.query_selector_all("button")
        for btn in btns:
            txt = await btn.inner_text()
            if '安装' in txt and len(txt) < 5:
                print(f"Clicking: '{txt}'")
                await btn.click()
                break

        await asyncio.sleep(8)

        dec_log = await page.evaluate("()=>window.__decLog||[]")
        xhr = await page.evaluate("()=>window.__log||[]")

        print(f"dec_log: {dec_log[:5]}")
        print(f"itms: {itms_urls}")

        # 从 dec_log 找 itms URL
        for entry in dec_log:
            s = entry.get('input','') or entry.get('str','')
            if 'itms-services' in s:
                itms_url = s
                print(f"FOUND itms: {itms_url}")
                itms_urls.append(itms_url)

        # 也找 inhouse 响应
        for e in xhr:
            if 'inhouse' in e['url']:
                print(f"inhouse resp: {e['resp'][:200]}")

        await browser.close()

    all_itms = [u for u in itms_urls if 'itms-services' in u]
    if all_itms:
        itms = all_itms[0]
        m = re.search(r'url=([^&\s"]+)', itms)
        if m:
            plist_url = urllib.parse.unquote(m.group(1))
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
    print("no itms found"); sys.exit(1)

asyncio.run(main())
