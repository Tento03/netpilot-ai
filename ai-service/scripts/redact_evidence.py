"""Redact office-identifying data from raw evidence.
Usage: python scripts/redact_evidence.py   (evidence/_raw/*.json -> evidence/*.json)
Requires _raw/network_info.json and _raw/wifi_link.json (source of the real values).
Refuses to write anything if a leak is still detected after redaction."""
import json
import re
import sys
from pathlib import Path

MAC_RE = re.compile(r"\b[0-9A-Fa-f]{2}([:-])(?:[0-9A-Fa-f]{2}\1){4}[0-9A-Fa-f]{2}\b")
PRIVATE_IP_RE = re.compile(
    r"(?<![\d.])(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?![\d])")
MAC_PLACEHOLDER = "XX:XX:XX:XX:XX:XX"
LOCAL_IP_PLACEHOLDER = "192.0.2.10"


def collect_secrets(net: dict, wifi: dict):
    d = (net or {}).get("data") or {}
    w = (wifi or {}).get("data") or {}
    names = {}
    if d.get("hostname"):
        names[d["hostname"]] = "HOST-REDACTED"
    for ssid in (d.get("ssid"), w.get("ssid")):
        if ssid:
            names[ssid] = "SSID-REDACTED"
    ips = {}
    if d.get("local_ip"):
        ips[d["local_ip"]] = LOCAL_IP_PLACEHOLDER
    for i, s in enumerate(d.get("dns_servers") or []):
        ips[s] = f"198.51.100.{i + 1}"
    return names, ips, d.get("default_gateway")


def redact_str(s: str, names: dict, ips: dict) -> str:
    for real, fake in names.items():
        s = re.sub(re.escape(real), fake, s, flags=re.IGNORECASE)
    for real, fake in ips.items():
        s = re.sub(r"(?<![\d.])" + re.escape(real) + r"(?![\d])", fake, s)
    return MAC_RE.sub(MAC_PLACEHOLDER, s)


def redact(o, names: dict, ips: dict):
    if isinstance(o, dict):
        return {k: (MAC_PLACEHOLDER if k == "bssid_masked" and isinstance(v, str)
                    else redact(v, names, ips)) for k, v in o.items()}
    if isinstance(o, list):
        return [redact(v, names, ips) for v in o]
    if isinstance(o, str):
        return redact_str(o, names, ips)
    return o


def find_leaks(text: str, names: dict, ips: dict, gateway: str | None) -> list[str]:
    leaks = []
    for real in names:
        if re.search(re.escape(real), text, flags=re.IGNORECASE):
            leaks.append("sensitive name still present")
    for real in ips:
        if re.search(r"(?<![\d.])" + re.escape(real) + r"(?![\d])", text):
            leaks.append("real IP still present")
    if MAC_RE.search(text):
        leaks.append("MAC address pattern present")
    for m in PRIVATE_IP_RE.findall(text):
        if m != gateway and m != LOCAL_IP_PLACEHOLDER:
            leaks.append("unexpected private IP present")
    return sorted(set(leaks))


def main() -> int:
    root = Path(__file__).resolve().parents[2] / "evidence"
    raw = root / "_raw"
    try:
        net = json.loads((raw / "network_info.json").read_text(encoding="utf-8-sig"))
        wifi = json.loads((raw / "wifi_link.json").read_text(encoding="utf-8-sig"))
    except FileNotFoundError as e:
        print(f"missing source file: {e.filename}")
        return 2
    names, ips, gateway = collect_secrets(net, wifi)
    out, failed = {}, False
    for f in sorted(raw.glob("*.json")):
        data = redact(json.loads(f.read_text(encoding="utf-8-sig")), names, ips)
        text = json.dumps(data, indent=2, ensure_ascii=False)
        leaks = find_leaks(text, names, ips, gateway)
        if leaks:
            print(f"LEAK in {f.name}: {', '.join(leaks)}")
            failed = True
        out[f.name] = text
    if failed:
        print("nothing written")
        return 1
    for name, text in out.items():
        (root / name).write_text(text + "\n", encoding="utf-8")
        print("written:", root / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
