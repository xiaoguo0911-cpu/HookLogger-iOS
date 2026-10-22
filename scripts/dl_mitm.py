#!/usr/bin/env python3
import os, sys, urllib.request, re
import xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"

ipa_url = None
plist_url = None

try:
    from mitmproxy import io as mio
    with open("/tmp/traffic.mitm", "rb") as f:
        for flow in mio.FlowReader(f).stream():
            if not hasattr(flow, 'request'):
                continue
            url = flow.request.pretty_url
            print(f"[流量] {url[:120]}")
            if '.ipa' in url:
                ipa_url = url
                print(f"  >> IPA: {url}")
            if 'plist' in url.lower():
                plist_url = url
                print(f"  >> PLIST: {url}")
            if 'itms-services' in url:
                m = re.search(r'url=([^&\s]+)', url)
                if m:
                    import urllib.parse
                    plist_url = urllib.parse.unquote(m.group(1))
                    print(f"  >> ITMS plist: {plist_url}")
except Exception as e:
    print(f"[流量分析失败] {e}")

if plist_url and not ipa_url:
    print(f"\n[*] 获取 plist: {plist_url}")
    try:
        req = urllib.request.Request(plist_url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=15) as r:
            xml_data = r.read().decode()
        print(f"[plist] {xml_data[:400]}")
        root = ET.fromstring(xml_data)
        def find_url(node):
            ch = list(node)
            for i, c in enumerate(ch):
                if c.tag == "key" and c.text == "url":
                    return ch[i+1].text
                r = find_url(c)
                if r:
                    return r
        ipa_url = find_url(root)
        print(f"[IPA URL] {ipa_url}")
    except Exception as e:
        print(f"err: {e}")

if not ipa_url:
    print("[!] 未找到 IPA URL，退出")
    sys.exit(1)

print(f"\n[*] 下载: {ipa_url}")
req = urllib.request.Request(ipa_url, headers={"User-Agent": UA})
with urllib.request.urlopen(req, timeout=300) as r:
    total = int(r.headers.get("Content-Length", 0))
    done = 0
    with open("/tmp/downloaded.ipa", "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total:
                print(f"  {done*100//total}%", end="\r", flush=True)

size = os.path.getsize("/tmp/downloaded.ipa")
magic = open("/tmp/downloaded.ipa", "rb").read(4).hex()
print(f"\n[完成] {size:,} bytes  magic={magic} {'OK' if magic=='504b0304' else 'BAD'}")
