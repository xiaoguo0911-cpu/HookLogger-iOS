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

    async with async_playwright() as p:
        browser = await p.webkit.launch(headless=True)
        context = await browser.new_context(user_agent=UA, viewport={"width": 390, "height": 844})
        page = await context.new_page()

        async def on_response(resp):
            nonlocal ipa_url, plist_url, itms_url, download_key, base_domain
            url = resp.url
            try:
                body = await resp.text()
            except Exception:
                return

            if "/clientapi/" in url:
                print(f"[API {resp.status}] {url}")
                print(f"  {body[:200]}")

            if "getinfo" in url:
                try:
                    data = json.loads(body)
                    info = data.get("data", data)
                    download_key = info.get("downloadKey")
                    from urllib.parse import urlparse
                    base_domain = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
                    print(f"  >> downloadKey={download_key}")
                except Exception:
                    pass

            if "plist" in url.lower() and resp.status == 200 and len(body) > 100:
                print(f"[PLIST] {url}")
                plist_url = url

            if ".ipa" in url:
                print(f"[IPA] {url}")
                ipa_url = url

        # 监听请求（不拦截，只记录）
        def on_request(req):
            nonlocal itms_url
            url = req.url
            if "itms-services" in url or "itms://" in url:
                print(f"[ITMS REQ] {url}")
                itms_url = url
            elif "/clientapi/" in url:
                print(f"[API REQ] {url}")

        page.on("response", on_response)

        print(f"[*] 访问 {TARGET}")
        try:
            await page.goto(TARGET, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"[goto] {e}")

        # 等 React 渲染
        print("[*] 等待页面元素...")
        try:
            await page.wait_for_selector("button, a, [class*='btn'], [class*='download']", timeout=15000)
            print("[*] 元素已出现")
        except Exception:
            print("[*] 等待超时，继续")

        await asyncio.sleep(3)

        # 打印所有文本元素
        texts = await page.evaluate("""
            () => Array.from(document.querySelectorAll('*'))
                .filter(e => !e.children.length && e.innerText && e.innerText.trim().length > 0 && e.innerText.trim().length < 60)
                .map(e => ({tag: e.tagName, cls: e.className.substring(0,30), text: e.innerText.trim()}))
                .slice(0, 40)
        """)
        print(f"[页面文字元素]")
        for t in texts:
            print(f"  <{t['tag']} class='{t['cls']}'> {t['text']}")

        # 监听所有 window.location 变化
        await page.evaluate("""
            () => {
                const origPushState = history.pushState;
                history.pushState = function() {
                    console.log('pushState:', arguments[2]);
                    return origPushState.apply(this, arguments);
                };
                const origOpen = window.open;
                window.open = function(url) {
                    console.log('window.open:', url);
                    return origOpen.apply(this, arguments);
                };
            }
        """)

        # 点击所有可能是下载的按钮
        print("[*] 尝试点击下载按钮...")
        clicked = False
        for sel in ["button", "a", "[role='button']", "[class*='btn']", "[class*='download']", "[class*='install']"]:
            try:
                for el in await page.query_selector_all(sel):
                    text = (await el.inner_text()).strip()
                    href = await el.get_attribute("href") or ""
                    cls = await el.get_attribute("class") or ""
                    if (any(w in text for w in ["下载", "安装", "Install", "Download", "立即", "获取", "点击", "打开"]) or
                        any(w in cls.lower() for w in ["download", "install", "btn-primary", "main-btn"]) or
                        "itms" in href):
                        print(f"  >> 点击: tag={sel} text={text!r} class={cls[:30]!r}")
                        try:
                            await el.click()
                            clicked = True
                            await asyncio.sleep(3)
                        except Exception as e:
                            print(f"    click err: {e}")
            except Exception:
                pass

        if not clicked:
            print("[!] 没找到下载按钮，尝试点击第一个按钮...")
            try:
                btn = await page.query_selector("button")
                if btn:
                    await btn.click()
                    await asyncio.sleep(3)
            except Exception:
                pass

        await asyncio.sleep(5)

        # 从页面源码搜索
        content = await page.content()
        for pattern, label in [
            (r'itms-services://[^\s"\'<>&\\]+', "itms"),
            (r'https?://[^\s"\'<>&\\]+\.plist[^\s"\'<>&\\]*', "plist"),
            (r'https?://[^\s"\'<>&\\]+\.ipa[^\s"\'<>&\\]*', "ipa"),
        ]:
            for m in re.findall(pattern, content):
                print(f"[{label} in HTML] {m}")
                if label == "itms" and not itms_url:
                    itms_url = m
                elif label == "plist" and not plist_url:
                    plist_url = m
                elif label == "ipa" and not ipa_url:
                    ipa_url = m

        print(f"\n[summary] key={download_key} itms={itms_url} plist={plist_url} ipa={ipa_url}")
        await browser.close()

    # 从 itms 提取 plist
    if itms_url and not ipa_url:
        m = re.search(r'url=([^&\s"\']+)', itms_url)
        if m:
            plist_url = urllib.parse.unquote(m.group(1))
            print(f"[plist from itms] {plist_url}")

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
    print(f"[*] 下载 {ipa_url}")
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
                    print(f"  {done*100//total}%  ({done//1024//1024}MB/{total//1024//1024}MB)", end="\r", flush=True)
    size = os.path.getsize(out)
    magic = open(out, "rb").read(4).hex()
    print(f"\n[完成] {size:,} bytes  magic={magic} {'OK' if magic=='504b0304' else 'BAD'}")

asyncio.run(main())
