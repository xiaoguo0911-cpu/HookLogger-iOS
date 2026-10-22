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

        # 重要: 拦截 inhouse 响应，记录加密数据
        # 然后直接调用页面中的解密函数
        await context.add_init_script("""
            Object.defineProperty(navigator,'platform',{get:()=>'iPhone'});
            Object.defineProperty(navigator,'maxTouchPoints',{get:()=>5});
            window.__inhouseData = null;
            window.__inhouseKey = null;
            const _o=XMLHttpRequest.prototype.open,_s=XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open=function(m,u){this._u=u;return _o.apply(this,arguments)};
            XMLHttpRequest.prototype.send=function(b){
                const s=this;
                s.addEventListener('readystatechange',function(){
                    if(s.readyState===4 && s._u && s._u.includes('inhouse')) {
                        try {
                            const d = JSON.parse(s.responseText);
                            window.__inhouseData = d.data;
                            window.__inhouseUrl = s._u;
                            console.log('[INHOUSE DATA]', s._u, d.data ? d.data.slice(0,50) : 'null');
                        } catch(e) {}
                    }
                });
                return _s.apply(this,arguments);
            };
        """)

        page = await context.new_page()
        console_logs = []
        page.on("console", lambda m: console_logs.append(m.text))

        async def on_itms(route):
            itms_urls.append(route.request.url)
            print(f"[ITMS ROUTE] {route.request.url}")
            await route.abort()
        await page.route("itms-services://**", on_itms)

        print("loading page...")
        await page.goto(BASE+"/"+APPID, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(20)

        print(f"console: {[m for m in console_logs if 'INHOUSE' in m or 'itms' in m.lower()][:5]}")

        # 读取 inhouse 加密数据
        inhouse_data = await page.evaluate("()=>window.__inhouseData")
        inhouse_url = await page.evaluate("()=>window.__inhouseUrl")
        print(f"inhouse URL: {inhouse_url}")
        print(f"inhouse data: {inhouse_data[:50] if inhouse_data else None}...")

        if not inhouse_data:
            print("no inhouse data"); sys.exit(1)

        # 找页面中所有以 _0x 开头的全局函数，找解密函数
        # 直接调用页面里可能的解密函数
        dec_result = await page.evaluate("""(enc) => {
            // 搜索所有全局函数，找名字像解密函数的
            const candidates = [];
            for (const k of Object.keys(window)) {
                if (typeof window[k] === 'function' && k.startsWith('_0x')) {
                    candidates.push(k);
                }
            }
            console.log('[FUNCS]', candidates.slice(0,20).join(','));
            
            // 尝试找 _0x3672a3 (or similar)
            for (const fname of candidates) {
                try {
                    const f = window[fname];
                    const result = f(enc, '1cfhnSTQ1T3tLpjtE');
                    if (result && typeof result === 'string' && result.includes('itms')) {
                        return {func: fname, result: result};
                    }
                } catch(e) {}
            }
            
            // 找所有长度为3-8字节的字符串，作为 key 尝试
            return {found: candidates.length, sample: candidates.slice(0,5)};
        }""", inhouse_data)
        print(f"dec result: {dec_result}")

        if dec_result and isinstance(dec_result, dict) and 'result' in dec_result:
            itms_url = dec_result['result']
            print(f"DECRYPTED: {itms_url}")
            if 'itms-services' in itms_url:
                m = re.search(r'url=([^&\s"]+)', itms_url)
                if m:
                    plist_url = urllib.parse.unquote(m.group(1))
                    print(f"plist: {plist_url}")
                    # download...

        print(f"route itms: {itms_urls}")
        await browser.close()

asyncio.run(main())
