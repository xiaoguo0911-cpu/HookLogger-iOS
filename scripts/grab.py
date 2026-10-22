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
            const _o=XMLHttpRequest.prototype.open,_s=XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open=function(m,u){this._u=u;return _o.apply(this,arguments)};
            XMLHttpRequest.prototype.send=function(b){
                const s=this;
                s.addEventListener('readystatechange',function(){
                    if(s.readyState===4) window.__log.push({url:s._u,status:s.status,resp:(s.responseText||'').slice(0,8000)});
                });
                return _s.apply(this,arguments);
            };
        """)
        page = await context.new_page()
        console_logs = []
        page.on("console", lambda m: console_logs.append(m.text))

        async def on_itms(route):
            itms_urls.append(route.request.url)
            print(f"[ITMS] {route.request.url}")
            await route.abort()
        await page.route("itms-services://**", on_itms)

        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except: pass

        await asyncio.sleep(20)

        # 找按钮
        btns = await page.query_selector_all("button")
        print(f"buttons: {len(btns)}")
        install_btn = None
        for btn in btns:
            txt = await btn.inner_text()
            print(f"  btn: {repr(txt)}")
            if txt.strip() == '安装':
                install_btn = btn

        # 拿 downloadKey
        xhr = await page.evaluate("()=>window.__log||[]")
        dk = None
        enc_data = None
        for e in xhr:
            if 'getinfo' in e['url']:
                try: dk = json.loads(e['resp'])['data']['downloadKey']
                except: pass

        print(f"dk: {dk}")

        if install_btn and dk:
            print("Clicking install button...")
            await install_btn.click()
            await asyncio.sleep(10)

            # 再读 XHR
            xhr2 = await page.evaluate("()=>window.__log||[]")
            for e in xhr2:
                if 'inhouse' in e['url']:
                    try: enc_data = json.loads(e['resp']).get('data','')
                    except: pass

            print(f"enc_data after click: {enc_data[:50] if enc_data else None}")

            # 在页面上直接调用解密函数
            # 找所有接受 (string, string) 参数并返回包含 'itms' 的函数
            result = await page.evaluate(f"""(dk) => {{
                const found = [];
                // 找 _0x3672a3 或类似的解密函数
                // 暴力遍历所有全局 _0x 函数
                for (const k of Object.keys(window)) {{
                    if (typeof window[k] !== 'function') continue;
                    try {{
                        const r = window[k](
                            "{enc_data or ''}", dk
                        );
                        if (r && typeof r === 'string' && r.length > 20) {{
                            found.push({{k, r: r.slice(0,200)}});
                            if (r.includes('itms')) {{
                                return {{found: k, url: r.slice(0,500)}};
                            }}
                        }}
                    }} catch(e) {{}}
                }}
                return {{tried: found.length, sample: found.slice(0,3)}};
            }}""", dk)
            print(f"decrypt search: {result}")

        print(f"itms: {itms_urls}")
        print(f"console: {console_logs[:5]}")
        await browser.close()

asyncio.run(main())
