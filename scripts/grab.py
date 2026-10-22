#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, urllib.parse, plistlib
from playwright.async_api import async_playwright

TARGET = os.environ.get("TARGET_URL","")
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
BASE = "https://doe29x10dqvat.cloudfront.net"

async def main():
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
            const _o=XMLHttpRequest.prototype.open,_s=XMLHttpRequest.prototype.send;
            XMLHttpRequest.prototype.open=function(m,u){this._u=u;return _o.apply(this,arguments)};
            XMLHttpRequest.prototype.send=function(b){
                const s=this;
                s.addEventListener('readystatechange',function(){
                    if(s.readyState===4) window.__log.push({url:s._u,status:s.status,resp:(s.responseText||'').slice(0,5000)});
                });
                return _s.apply(this,arguments);
            };
        """)
        page = await context.new_page()
        print("goto CF...")
        await page.goto(BASE+"/1cfhnSTQ1T3tLpjtE", wait_until="networkidle", timeout=30000)
        await asyncio.sleep(15)
        xhr = await page.evaluate("()=>window.__log||[]")
        await browser.close()

    for e in xhr:
        print(f"XHR [{e['status']}] {e['url']}")
        if 'inhouse' in e['url']:
            print(f"  INHOUSE RESP: {e['resp'][:1000]}")
            # 解析 inhouse 响应
            try:
                data = json.loads(e['resp'])
                print(f"  parsed: {json.dumps(data, ensure_ascii=False, indent=2)[:2000]}")
                # 找 itms 或 plist URL
                resp_str = json.dumps(data)
                itms = re.findall(r'itms-services://[^\s"\']+', resp_str)
                plist = re.findall(r'https?://[^\s"\']+\.plist[^\s"\']*', resp_str)
                ipa = re.findall(r'https?://[^\s"\']+\.ipa[^\s"\']*', resp_str)
                print(f"  itms: {itms}")
                print(f"  plist: {plist}")
                print(f"  ipa: {ipa}")
                if itms:
                    m = re.search(r'url=([^&\s"]+)', itms[0])
                    if m:
                        plist_url = urllib.parse.unquote(m.group(1))
                        print(f"  plist_url: {plist_url}")
                        download_from_plist(plist_url)
                elif plist:
                    download_from_plist(plist[0])
                elif ipa:
                    download_ipa(ipa[0])
            except Exception as ex:
                print(f"  parse err: {ex}")

def download_from_plist(plist_url):
    print(f"getting plist: {plist_url}")
    r = urllib.request.urlopen(urllib.request.Request(plist_url, headers={"User-Agent": UA}), timeout=15)
    p = plistlib.loads(r.read())
    for a in p.get('items',[{}])[0].get('assets',[]):
        if a.get('kind')=='software-package':
            download_ipa(a['url'])
            break

def download_ipa(url):
    print(f"downloading IPA: {url}")
    r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=300)
    total = int(r.headers.get("Content-Length", 0))
    done = 0
    with open("/tmp/downloaded.ipa", "wb") as f:
        while True:
            c = r.read(65536)
            if not c: break
            f.write(c); done += len(c)
            if total: print(f"{done*100//total}%", end="\r", flush=True)
    print(f"\nDone: {os.path.getsize('/tmp/downloaded.ipa'):,} bytes")

asyncio.run(main())
