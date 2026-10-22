#!/usr/bin/env python3
import asyncio, sys, os, json, re, urllib.request, base64
from playwright.async_api import async_playwright
try:
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
except ImportError:
    print("need pycryptodome"); sys.exit(1)

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

    print(f"downloadKey: {dk}")
    if not dk: sys.exit(1)

    # 直接调用 inhouse API 获取完整响应
    k = dk
    url = f"{BASE}/clientapi/app/inhouse?appid={APPID}&k={k}&c=&lang=zh_CN&zh=1"
    print(f"calling: {url}")
    r = urllib.request.urlopen(urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": BASE+"/"+APPID,
        "Origin": BASE
    }), timeout=15)
    resp = r.read().decode()
    print(f"inhouse resp: {resp[:500]}")

    # 解析
    data = json.loads(resp)
    enc = data.get('data', '')
    print(f"enc len={len(enc)}, first 50: {enc[:50]}")

    # 分析加密数据
    raw = base64.b64decode(enc)
    print(f"decoded len={len(raw)}, first 32 bytes: {raw[:32].hex()}")

    # k 格式: timestamp_hash (e.g. 1792683672_3da2cb330d35768e52c889b7bfec67c4)
    # hash 部分是 32 hex chars = 16 bytes = 可能是 AES key
    parts = k.split('_', 1)
    ts = parts[0] if len(parts) > 1 else ''
    hash_part = parts[1] if len(parts) > 1 else k
    print(f"ts={ts}, hash={hash_part}")

    # 尝试 hash 作为 key/iv
    key_bytes = bytes.fromhex(hash_part) if len(hash_part) == 32 else None
    if key_bytes:
        print(f"key_bytes: {key_bytes.hex()}")
        for iv in [b'\x00'*16, key_bytes[:16], ts.encode()[:16].ljust(16,b'\x00')]:
            try:
                c = AES.new(key_bytes, AES.MODE_CBC, iv)
                dec = unpad(c.decrypt(raw), 16)
                print(f"DECRYPTED (iv={iv.hex()[:32]}): {dec.decode()[:300]}")
            except Exception as e:
                print(f"  failed (iv={iv.hex()[:32]}): {e}")

    # 尝试 ECB
    if key_bytes:
        try:
            c = AES.new(key_bytes, AES.MODE_ECB)
            dec = unpad(c.decrypt(raw), 16)
            print(f"ECB DECRYPTED: {dec.decode()[:300]}")
        except Exception as e:
            print(f"ECB failed: {e}")

asyncio.run(main())
