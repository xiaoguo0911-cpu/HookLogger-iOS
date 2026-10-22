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
            // 拦截所有导航
            const origOpen = window.open;
            window.open = function(url) {
                window.__navLog.push({type:'open', url});
                if(url&&url.includes('itms')) { console.log('[OPEN ITMS]', url); return null; }
                return origOpen.apply(this, arguments);
            };
            const origAssign = window.location.assign.bind(window.location);
            window.location.assign = function(url) {
                window.__navLog.push({type:'assign', url});
                if(url&&url.includes('itms')) { console.log('[ASSIGN ITMS]', url); return; }
                return origAssign(url);
            };
            const origReplace = window.location.replace.bind(window.location);
            window.location.replace = function(url) {
                window.__navLog.push({type:'replace', url});
                if(url&&url.includes('itms')) { console.log('[REPLACE ITMS]', url); return; }
                return origReplace(url);
            };
            // 监听所有 a 元素点击
            document.addEventListener('click', function(e) {
                const a = e.target.closest('a');
                if(a) { window.__navLog.push({type:'click', href:a.href, text:a.innerText}); }
            }, true);
            // 拦截 createElement('a') 的 click
            const origCreate = document.createElement.bind(document);
            document.createElement = function(tag) {
                const el = origCreate(tag);
                if(tag.toLowerCase() === 'a') {
                    const origClick = el.click.bind(el);
                    el.click = function() {
                        if(el.href) { window.__navLog.push({type:'a.click', href:el.href}); }
                        if(el.href && el.href.includes('itms')) { console.log('[A.CLICK ITMS]', el.href); return; }
                        return origClick();
                    };
                }
                return el;
            };
        """)

        page = await context.new_page()
        console_msgs = []
        page.on("console", lambda m: console_msgs.append(m.text))

        async def on_itms(route):
            itms_urls.append(route.request.url)
            print(f"[ITMS ROUTE] {route.request.url}")
            await route.abort()
        await page.route("itms-services://**", on_itms)

        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except Exception as e:
            print(f"goto: {e}")

        await asyncio.sleep(25)

        nav_log = await page.evaluate("()=>window.__navLog||[]")
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

        print(f"\nnavLog: {nav_log[:10]}")
        print(f"console: {[m for m in console_msgs if 'itms' in m.lower() or 'ITMS' in m][:5]}")
        print(f"route itms: {itms_urls}")
        print(f"dk: {dk}")

        # 检查 document 全内容（包括 portal）
        full_html = await page.evaluate("()=>document.documentElement.outerHTML")
        print(f"full HTML len={len(full_html)}")
        if 'itms' in full_html:
            matches = re.findall(r'itms-services://[^\s"\'<>]+', full_html)
            print(f"itms in HTML: {matches}")

        # 检查 <body> 下所有元素（包括 portal）
        all_els = await page.evaluate("""()=>{
            const all = document.querySelectorAll('a[href]');
            return Array.from(all).map(a => a.href).filter(h => h.includes('itms'));
        }""")
        print(f"itms hrefs: {all_els}")

        await browser.close()

    all = itms_urls + [n.get('url','') or n.get('href','') for n in nav_log if 'itms' in str(n)]
    print(f"\nAll itms: {all}")
    if not all:
        print("no itms"); sys.exit(1)

asyncio.run(main())
