#!/usr/bin/env python3
import asyncio, sys, os, re, urllib.request, urllib.parse, json
import xml.etree.ElementTree as ET
from playwright.async_api import async_playwright

TARGET = os.environ.get("TARGET_URL", "")
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

def extract_ipa_url(plist_xml):
    root = ET.fromstring(plist_xml)
    def find_url(node):
        ch = list(node)
        for i, child in enumerate(ch):
            if child.tag == "key" and child.text == "url":
                return ch[i+1].text
            r = find_url(child)
            if r:
                return r
    return find_url(root)

async def main():
    ipa_url = None
    plist_url = None
    itms_url = None
    download_key = None
    base_domain = None
    app_id = None
    captured_opens = []

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(
            user_agent=UA,
            viewport={"width": 390, "height": 844},
            extra_http_headers={"Accept-Language": "zh-CN,zh;q=0.9"},
        )

        # 在页面加载前注入脚本，拦截 window.open 和 location
        await context.add_init_script("""
            (function() {
                window.__captured__ = [];
                const orig_open = window.open;
                window.open = function(url) {
                    console.log('[OPEN]' + url);
                    window.__captured__.push(url);
                    return orig_open ? orig_open.apply(this, arguments) : null;
                };

                // 模拟 iOS 环境
                Object.defineProperty(navigator, 'platform', {get: () => 'iPhone'});
                Object.defineProperty(navigator, 'maxTouchPoints', {get: () => 5});
            })();
        """)

        page = await context.new_page()

        # 监听 console 日志
        page.on("console", lambda msg: (
            print(f"[JS {msg.type}] {msg.text}") if "[OPEN]" in msg.text or "itms" in msg.text.lower() or "plist" in msg.text.lower() else None
        ))

        async def on_response(resp):
            nonlocal ipa_url, plist_url, download_key, base_domain, app_id
            url = resp.url
            try:
                body = await resp.text()
            except Exception:
                body = ""

            # 打印所有响应
            print(f"[{resp.status}] {url[:100]}")
            if resp.status >= 400:
                print(f"  ERR BODY: {body[:100]}")

            if "getinfo" in url:
                print(f"[getinfo] {url}")
                try:
                    data = json.loads(body)
                    info = data.get("data", data)
                    download_key = info.get("downloadKey")
                    from urllib.parse import urlparse
                    parsed = urlparse(url)
                    base_domain = f"{parsed.scheme}://{parsed.netloc}"
                    m = re.search(r'appid=([^&]+)', url)
                    if m:
                        app_id = m.group(1)
                    print(f"  downloadKey={download_key}  appid={app_id}")
                except Exception as e:
                    print(f"  err: {e}")

            # 关键: inhouse API 直接返回 itms-services URL
            if "inhouse" in url and resp.status == 200:
                print(f"[inhouse] {url}")
                print(f"  body={body[:300]}")
                try:
                    data = json.loads(body)
                    itms_data = data.get("data", "")
                    if "itms-services" in str(itms_data):
                        itms_url = itms_data
                        print(f"  >> ITMS: {itms_url}")
                except Exception as e:
                    print(f"  err: {e}")

            if "plist" in url.lower() and resp.status == 200 and len(body) > 100:
                print(f"[PLIST RESP] {url}")
                plist_url = url

            if ".ipa" in url:
                print(f"[IPA RESP] {url}")
                ipa_url = url

        page.on("response", on_response)

        print(f"[*] 访问 {TARGET}")
        try:
            await page.goto(TARGET, wait_until="load", timeout=60000)
        except Exception as e:
            print(f"[goto] {e}")

        # 等 React 和 API 完成
        print("[*] 等待 30s (React + API)...")
        await asyncio.sleep(30)

        # 读取拦截到的 window.open 调用
        try:
            captured_opens = await page.evaluate("() => window.__captured__ || []")
            print(f"[window.open calls] {captured_opens}")
            for u in captured_opens:
                if "itms-services" in u:
                    itms_url = u
                    print(f"  >> ITMS: {u}")
                elif "plist" in u.lower():
                    plist_url = u
                    print(f"  >> PLIST: {u}")
        except Exception as e:
            print(f"[captured err] {e}")

        # 获取页面文字
        try:
            texts = await page.evaluate("""
                () => Array.from(document.querySelectorAll('*'))
                    .filter(e => !e.children.length && e.innerText && e.innerText.trim().length > 0 && e.innerText.trim().length < 80)
                    .map(e => e.innerText.trim()).slice(0, 20)
            """)
            print(f"[页面文字] {texts}")
        except Exception:
            pass

        # JS 点击所有元素
        try:
            count = await page.evaluate("""
                () => {
                    let n = 0;
                    document.querySelectorAll('button,a,[role=button],[onclick]').forEach(el => {
                        try { el.click(); n++; } catch(e) {}
                    });
                    return n;
                }
            """)
            print(f"[JS click] 点击了 {count} 个元素")
        except Exception:
            pass

        await asyncio.sleep(5)

        # 再次读取
        try:
            captured_opens2 = await page.evaluate("() => window.__captured__ || []")
            for u in captured_opens2:
                if u not in captured_opens:
                    print(f"[新 window.open] {u}")
                    if "itms-services" in u:
                        itms_url = u
        except Exception:
            pass

        print(f"\n[summary] key={download_key} itms={itms_url} plist={plist_url} ipa={ipa_url}")
        await browser.close()

    # 从 itms 提取 plist URL
    if itms_url and not plist_url:
        m = re.search(r'url=([^&\s]+)', itms_url)
        if m:
            plist_url = urllib.parse.unquote(m.group(1))
            print(f"[plist from itms] {plist_url}")

    # 从 plist 获取 IPA URL
    if plist_url and not ipa_url:
        print(f"[*] 获取 plist: {plist_url}")
        req = urllib.request.Request(plist_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            xml_data = r.read().decode()
        print(f"[plist] {xml_data[:400]}")
        ipa_url = extract_ipa_url(xml_data)
        print(f"[IPA URL] {ipa_url}")

    if not ipa_url:
        print("[!] 未获取 IPA URL")
        sys.exit(1)

    out = "/tmp/downloaded.ipa"
    print(f"\n[*] 下载: {ipa_url}")
    req = urllib.request.Request(ipa_url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=300) as r:
        total = int(r.headers.get("Content-Length", 0))
        done = 0
        with open(out, "wb") as f:
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"  {done*100//total}%  {done//1024//1024}MB/{total//1024//1024}MB", end="\r", flush=True)
    size = os.path.getsize(out)
    magic = open(out, "rb").read(4).hex()
    print(f"\n[完成] {size:,} bytes  magic={magic} {'OK' if magic=='504b0304' else 'BAD'}")

asyncio.run(main())
