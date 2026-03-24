"""Quick test: connect to CertStream, count messages, filter .br"""
import json
import time
import websocket

url = "wss://certstream.calidog.io/"
total = 0
br_count = 0
br_domains = []
start = time.time()

def on_message(ws, message):
    global total, br_count, br_domains
    total += 1
    try:
        data = json.loads(message)
    except json.JSONDecodeError:
        return
    if data.get("message_type") != "certificate_update":
        return
    all_domains = data.get("data", {}).get("leaf_cert", {}).get("all_domains", [])
    for d in all_domains:
        if isinstance(d, str) and d.lower().endswith(".br"):
            br_count += 1
            br_domains.append(d.lower())
    if total % 100 == 0:
        elapsed = time.time() - start
        print(f"  {total} msgs in {elapsed:.0f}s | .br domains found: {br_count}")
        if br_domains:
            print(f"    Last .br: {br_domains[-5:]}")

def on_open(ws):
    print(f"Connected to {url}")

def on_error(ws, error):
    print(f"Error: {error}")

def on_close(ws, status, msg):
    elapsed = time.time() - start
    print(f"\nClosed after {elapsed:.0f}s: status={status} msg={msg}")
    print(f"Total messages: {total}")
    print(f"Total .br domains: {br_count}")
    if br_domains:
        print(f"Sample .br domains: {br_domains[:20]}")

ws = websocket.WebSocketApp(
    url,
    on_message=on_message,
    on_open=on_open,
    on_error=on_error,
    on_close=on_close,
)
ws.run_forever(ping_interval=30, ping_timeout=10)
