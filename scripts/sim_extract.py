#!/usr/bin/env python3
import sys, os, urllib.request, xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15"

try:
    from mitmproxy import io as mio
except ImportError:
    print("mitmproxy not available"); sys.exit(1)

ipa_url = None
plist_url = None

try:
    with open("/tmp/traffic.mitm", "rb") as f:
        reader = mio.FlowReader(f)
        for flow in reader.stream():
            try:
                url = flow.request.pretty_url
                print(f"[FLOW] {url}")
                if '.ipa' in url.lower(): ipa_url = url
                if 'plist' in url.lower(): plist_url = url
            except: pass
except Exception as e:
    print(f"err: {e}")

print(f"ipa_url: {ipa_url}")
print(f"plist_url: {plist_url}")

def dl(url, out):
    r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=300)
    with open(out, "wb") as f:
        while True:
            chunk = r.read(65536)
            if not chunk: break
            f.write(chunk)
    print(f"Done: {os.path.getsize(out):,} bytes")

if ipa_url:
    dl(ipa_url, "/tmp/downloaded.ipa")
elif plist_url:
    xml_data = urllib.request.urlopen(urllib.request.Request(plist_url, headers={"User-Agent": UA}), timeout=15).read().decode()
    root = ET.fromstring(xml_data)
    def fu(node):
        ch = list(node)
        for i,c in enumerate(ch):
            if c.tag=="key" and c.text=="url": return ch[i+1].text
            r=fu(c)
            if r: return r
    u = fu(root)
    print(f"IPA from plist: {u}")
    if u: dl(u, "/tmp/downloaded.ipa")
    else: sys.exit(1)
else:
    print("No IPA/plist found"); sys.exit(1)
