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
    all_api_calls = []

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(user_agent=UA, viewport={"width": 390, "height": 844})
        page = await context.new_page()

        async def on_request(req):
            url = req.url
            # 记录所有 API 调用
            if "/clientapi/" in url or "api" in url.lower():
                print(f"[REQ] {req.method} {url}")
                all_api_calls.append(url)

        async def on_response(resp):
            nonlocal ipa_url, plist_url, itms_url, download_key, base_domain
            url = resp.url
            try:
                body = await resp.text()
            except Exception:
                return

            # 所有 API 响应都打印
            if "/clientapi/" in url:
                print(f"[API {resp.status}] {url}")
                print(f"  {body[:300]}")

            if "getinfo" in url:
                try:
                    data = json.loads(body)
                    info = data.get("data", data)
                    download_key = info.get("downloadKey") or info.get("download_key")
                    from urllib.parse import urlparse
                    base_domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
                    print(f"  [downloadKey] {download_key}")
                    print(f"  [appName] {info.get('name')} v{info.get('version')}")
                except Exception:
                    pass

            if "plist" in url.lower() and resp.status == 200:
                plist_url = url
                print(f"[PLIST URL] {url}")

            if ".ipa" in url:
                ipa_url = url
                print(f"[IPA URL] {url}")

            if "itms-services" in url:
                itms_url = url

        page.on("request", on_request)
        page.on("response", on_response)

        print(f"[*] 访问 {TARGET}")
        try:
            await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"[goto] {e}")

        # 等 React 完全渲染
        print("[*] 等待页面渲染...")
        await asyncio.sleep(8)

        # 查找并点击下载按钮
        print("[*] 查找下载按钮...")
        for selector in ["button", "a", "[role='button']", "div[onclick]"]:
            try:
                for el in await page.query_selector_all(selector):
                    text = (await el.inner_text()).strip()
                    if any(w in text for w in ["下载", "安装", "Install", "Download", "立即", "获取", "点击"]):
                        print(f"  >> 点击: {text!r}")
                        await el.click()
                        await asyncio.sleep(5)
            except Exception:
                pass

        await asyncio.sleep(5)

        # 打印所有元素
        try:
            all_els = await page.evaluate("""
                () => Array.from(document.querySelectorAll('*')).filter(e =>
                    e.children.length == 0 && e.innerText && e.innerText.trim().length > 0 && e.innerText.trim().length < 50
                ).map(e => e.innerText.trim()).slice(0, 30)
            """)
            print(f"[页面文字] {all_els}")
        except Exception:
            pass

        content = await page.content()

        # 从页面内容搜索
        for pattern, label in [
            (r'itms-services://[^\s"\'<>&]+', "itms"),
            (r'https?://[^\s"\'<>&]+\.plist[^\s"\'<>&]*', "plist"),
            (r'https?://[^\s"\'<>&]+\.ipa[^\s"\'<>&]*', "ipa"),
        ]:
            matches = re.findall(pattern, content)
            if matches:
                print(f"[{label} in page] {matches[0]}")
                if label == "itms" and not itms_url:
                    itms_url = matches[0]
                elif label == "plist" and not plist_url:
                    plist_url = matches[0]
                elif label == "ipa" and not ipa_url:
                    ipa_url = matches[0]

        print(f"\n[所有API] {all_api_calls}")
        print(f"[summary] key={download_key} base={base_domain}")
        await browser.close()

    # 用 downloadKey 枚举可能的 API
    if download_key and base_domain and not ipa_url and not plist_url:
        paths = [
            f"/clientapi/app/download?appid=1cfhnSTQ1T3tLpjtE&downloadKey={download_key}",
            f"/clientapi/app/downloadipa?downloadKey={download_key}",
            f"/clientapi/ipa/sign?downloadKey={download_key}",
            f"/clientapi/ipa/url?downloadKey={download_key}",
            f"/clientapi/app/installurl?downloadKey={download_key}",
            f"/clientapi/install?downloadKey={download_key}",
        ]
        for path in paths:
            url = base_domain + path
            print(f"[*] 试 {url}")
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": base_domain})
                with urllib.request.urlopen(req, timeout=10) as r:
                    rb = r.read().decode()
                print(f"  OK -> {rb[:300]}")
                try:
                    d = json.loads(rb)
                    candidate = d.get("url") or d.get("downloadUrl") or (d.get("data") or {}).get("url")
                    if candidate:
                        ipa_url = candidate
                        break
                    # 可能直接是 plist
                    pl = (d.get("data") or {}).get("plistUrl") or d.get("plistUrl")
                    if pl:
                        plist_url = pl
                        break
                except Exception:
                    if ".ipa" in rb:
                        ipa_url = url
                    elif "plist" in rb:
                        plist_url = url
            except Exception as e:
                print(f"  err: {e}")

    # itms -> plist -> IPA
    if itms_url and not ipa_url:
        m = re.search(r'url=([^&\s"\']+)', itms_url)
        if m:
            plist_url = urllib.parse.unquote(m.group(1))
            print(f"[plist from itms] {plist_url}")

    if plist_url and not ipa_url:
        print(f"[*] 获取 plist: {plist_url}")
        req = urllib.request.Request(plist_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            plist_xml = r.read().decode()
        print(f"[plist] {plist_xml[:400]}")
        ipa_url = extract_ipa_url(plist_xml)

    if not ipa_url:
        print("[!] 未能获取 IPA URL，请查看上方日志")
        sys.exit(1)

    print(f"[*] 下载 IPA: {ipa_url}")
    out = "/tmp/downloaded.ipa"
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
                    print(f"  {done*100//total}% ({done//1024//1024}MB)", end="\r", flush=True)
    size = os.path.getsize(out)
    magic = open(out, "rb").read(4).hex()
    print(f"\n[完成] {size:,} bytes  magic={magic} {'OK' if magic=='504b0304' else 'BAD'}")

asyncio.run(main())
