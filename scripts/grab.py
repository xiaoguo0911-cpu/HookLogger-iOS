#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, base64, hashlib
from playwright.async_api import async_playwright
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
BASE = "https://doe29x10dqvat.cloudfront.net"
APPID = "1cfhnSTQ1T3tLpjtE"

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
                    if(s.readyState===4) window.__log.push({url:s._u,status:s.status,resp:(s.responseText||'').slice(0,8000)});
                });
                return _s.apply(this,arguments);
            };
        """)
        page = await context.new_page()
        await page.goto(BASE+"/"+APPID, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(15)
        xhr = await page.evaluate("()=>window.__log||[]")
        await browser.close()

    dk = None
    for e in xhr:
        if 'getinfo' in e['url']:
            try: dk = json.loads(e['resp'])['data']['downloadKey']
            except: pass

    print(f"DK: {dk}")
    if not dk: sys.exit(1)

    url = f"{BASE}/clientapi/app/inhouse?appid={APPID}&k={dk}&c=&lang=zh_CN&zh=1"
    r = urllib.request.urlopen(urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": BASE+"/"+APPID, "Origin": BASE
    }), timeout=15)
    resp = json.loads(r.read())
    enc = resp.get('data','')
    raw = base64.b64decode(enc)
    print(f"raw len={len(raw)}: {raw.hex()}")

    ts, h = dk.split('_', 1)
    key = bytes.fromhex(h)  # 16 bytes

    # 策略1: 前16字节是IV
    iv = raw[:16]
    ct = raw[16:]
    try:
        dec = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(ct), 16)
        print(f"[1] IV=first16: {dec.decode()[:300]}")
    except Exception as e:
        print(f"[1] fail: {e}")

    # 策略2: 全部是密文，IV=0
    try:
        dec = unpad(AES.new(key, AES.MODE_CBC, b'\x00'*16).decrypt(raw), 16)
        print(f"[2] IV=0: {dec.decode()[:300]}")
    except Exception as e:
        print(f"[2] fail: {e}")

    # 策略3: AES-128-CTR
    try:
        from Crypto.Util import Counter
        ctr = Counter.new(128, initial_value=0)
        dec = AES.new(key, AES.MODE_CTR, counter=ctr).decrypt(raw)
        if dec[:1] in [b'{', b'[', b'"']:
            print(f"[3] CTR: {dec.decode()[:300]}")
        else:
            print(f"[3] CTR (not json): {dec[:20]}")
    except Exception as e:
        print(f"[3] CTR fail: {e}")

    # 策略4: 不同密钥推导方式
    # key = MD5(ts + h)
    for formula in [ts+h, h+ts, ts, h, dk]:
        k2 = hashlib.md5(formula.encode()).digest()  # 16 bytes
        for iv2 in [b'\x00'*16, raw[:16], key]:
            try:
                ct2 = raw[16:] if iv2 == raw[:16] else raw
                dec = unpad(AES.new(k2, AES.MODE_CBC, iv2).decrypt(ct2), 16)
                if dec[:1] in [b'{', b'[']:
                    print(f"[4] MD5({formula[:10]})+iv={iv2[:4].hex()}: {dec.decode()[:300]}")
            except: pass

    # 策略5: PKCS5 padding (= PKCS7 for 16-byte blocks, same thing)
    # 策略6: NoPadding
    try:
        dec = AES.new(key, AES.MODE_CBC, b'\x00'*16).decrypt(raw)
        print(f"[6] NoPad: {dec[:50]}")
    except Exception as e:
        print(f"[6] fail: {e}")

asyncio.run(main())
