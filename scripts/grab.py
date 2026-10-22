#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, plistlib
from playwright.async_api import async_playwright

TARGET = "https://yjriz.nzctjvr.com/2VHkkYFEvf/vxwmS1ivH7eZWQKy"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

async def main():
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
        async def on_itms(route):
            print(f"[ITMS] {route.request.url}")
            await route.abort()
        await page.route("itms-services://**", on_itms)
        try:
            await page.goto(TARGET, wait_until="load", timeout=30000)
        except: pass
        await asyncio.sleep(25)

        # 获取完整 HTML 并输出关键部分
        html = await page.evaluate("()=>document.documentElement.outerHTML")
        print(f"HTML len={len(html)}")
        # 找所有文本内容
        text = await page.evaluate("()=>document.body.innerText")
        print(f"=== BODY TEXT ===")
        print(text[:1000])

        # 找所有可见元素
        els = await page.evaluate("""()=>{
            return Array.from(document.querySelectorAll('*')).filter(e => {
                const r = e.getBoundingClientRect();
                return r.width > 0 && r.height > 0;
            }).map(e => ({
                tag: e.tagName,
                text: (e.innerText||'').slice(0,50),
                cls: (e.className||'').toString().slice(0,60),
                href: e.href || '',
                src: e.src || ''
            })).filter(e => e.text || e.href || e.src);
        }""")
        print(f"\n=== VISIBLE ELEMENTS ({len(els)}) ===")
        for el in els[:30]:
            print(f"  <{el['tag']}> '{el['text']}' href={el['href'][:60]} src={el['src'][:60]}")

        # 取截图内容（base64）
        screenshot = await page.screenshot()
        with open("/tmp/screenshot.png", "wb") as f:
            f.write(screenshot)
        print(f"\nscreenshot: {len(screenshot)} bytes saved to /tmp/screenshot.png")

        await browser.close()

asyncio.run(main())
