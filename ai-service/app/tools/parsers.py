"""Pure parsers for Windows ping / netsh wlan / ipconfig output (English locale).

No I/O here: text in, dict out. Failures raise ParserError with a stable code.
"""
from __future__ import annotations

import ipaddress
import re


class ParserError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


_CTRL = re.compile(r"[\x00-\x1f\x7f]")


def clean_text(value: str, max_len: int = 64) -> str:
    """Free text from the OS (SSID, adapter names) is untrusted: strip control chars, cap length."""
    return _CTRL.sub("", value).strip()[:max_len]


def mask_mac(value: str) -> str:
    parts = re.split(r"[:-]", value.strip().lower())
    if len(parts) != 6 or not all(re.fullmatch(r"[0-9a-f]{2}", p) for p in parts):
        return "xx:xx:xx:xx:xx:xx"
    return ":".join(parts[:3] + ["xx"] * 3)


# ------------------------------------------------------------------ ping

_PING_NOHOST = re.compile(r"could not find host", re.I)
_PING_OK = re.compile(r"Reply from \S+?: bytes=\d+ time(?P<op>[=<])(?P<ms>\d+)ms", re.I)
_PING_UNREACH = re.compile(r"Reply from \S+?: (?:Destination \w+ unreachable|TTL expired in transit)", re.I)
_PING_TIMEOUT = re.compile(r"Request timed out|General failure", re.I)
_PING_STATS = re.compile(r"Packets: Sent = (\d+), Received = (\d+), Lost = (\d+)", re.I)


def parse_ping(text: str) -> dict:
    if _PING_NOHOST.search(text):
        raise ParserError("dns_resolution_failed", "ping could not resolve the host name")

    rtts: list[float] = []
    sub_ms = 0
    for m in _PING_OK.finditer(text):
        if m["op"] == "<":
            rtts.append(0.5)
            sub_ms += 1
        else:
            rtts.append(float(m["ms"]))

    unreachable = len(_PING_UNREACH.findall(text))
    timeouts = len(_PING_TIMEOUT.findall(text))
    stats = _PING_STATS.search(text)
    sent = int(stats[1]) if stats else len(rtts) + unreachable + timeouts
    if sent == 0:
        raise ParserError("parse_error", "no ping replies or statistics found in output")

    received = len(rtts)  # unreachable replies are NOT successes
    lost = max(sent - received, 0)
    jitter = None
    if len(rtts) >= 2:
        diffs = [abs(b - a) for a, b in zip(rtts, rtts[1:])]
        jitter = round(sum(diffs) / len(diffs), 1)

    return {
        "sent": sent,
        "received": received,
        "lost": lost,
        "loss_pct": round(lost / sent * 100, 1),
        "reachable": received > 0,
        "min_ms": min(rtts) if rtts else None,
        "avg_ms": round(sum(rtts) / len(rtts), 1) if rtts else None,
        "max_ms": max(rtts) if rtts else None,
        "jitter_ms": jitter,
        "rtts_ms": rtts,
        "sub_ms_replies": sub_ms,
        "unreachable_replies": unreachable,
    }


# ------------------------------------------------------------------ netsh wlan

_NETSH_KV = re.compile(r"^\s+(?P<k>[^:]+?)\s+:\s?(?P<v>.*)$")


def _num(value: str | None, cast=int):
    if value is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", value)
    return cast(float(m.group())) if m else None


def parse_netsh_wlan(text: str) -> dict:
    fields: dict[str, str] = {}
    for line in text.splitlines():
        m = _NETSH_KV.match(line.rstrip())
        if not m:
            continue
        key = m["k"].strip().lower()
        if key == "name" and "name" in fields:
            break  # only the first interface
        fields.setdefault(key, m["v"].strip())

    if not fields:
        first = next((ln for ln in text.splitlines() if ln.strip()), "empty output")
        raise ParserError("wlan_unavailable", clean_text(first, 120))

    state = fields.get("state", "").lower()
    data = {
        "interface_name": clean_text(fields.get("name", "")),
        "state": state,
        "connected": state == "connected",
        "ssid": None, "bssid_masked": None, "band": None, "channel": None,
        "radio_type": None, "authentication": None,
        "receive_rate_mbps": None, "transmit_rate_mbps": None,
        "signal_pct": None, "rssi_dbm": None,
    }
    if not data["connected"]:
        return data

    data.update({
        "ssid": clean_text(fields.get("ssid", "")) or None,
        "bssid_masked": mask_mac(fields["ap bssid"]) if "ap bssid" in fields else None,
        "band": clean_text(fields.get("band", "")) or None,
        "channel": _num(fields.get("channel")),
        "radio_type": clean_text(fields.get("radio type", "")) or None,
        "authentication": clean_text(fields.get("authentication", "")) or None,
        "receive_rate_mbps": _num(fields.get("receive rate (mbps)"), float),
        "transmit_rate_mbps": _num(fields.get("transmit rate (mbps)"), float),
        "signal_pct": _num(fields.get("signal")),
        "rssi_dbm": _num(fields.get("rssi")),
    })
    return data


# ------------------------------------------------------------------ ipconfig /all

_IP_ADAPTER = re.compile(r"^(?!\s)(?P<kind>.+?) adapter (?P<name>.+):\s*$")
_IP_KV = re.compile(r"^ {3}(?P<key>\S.*?)[ .]*:\s?(?P<val>.*)$")
_IP_CONT = re.compile(r"^ {10,}(?P<v>\S.*)$")
_VIRTUAL = re.compile(r"virtual|vpn|fortinet|vmware|hyper-v|tap-|bluetooth|wi-fi direct|loopback", re.I)


def _clean_ip(value: str) -> str:
    value = re.sub(r"\(.*\)$", "", value).strip()
    return value.split("%")[0]


def _ips(values: list[str], version: int) -> list[str]:
    out = []
    for v in values:
        try:
            ip = ipaddress.ip_address(_clean_ip(v))
        except ValueError:
            continue
        if ip.version == version and str(ip) not in out:
            out.append(str(ip))
    return out


def parse_ipconfig(text: str) -> dict:
    top: dict[str, list[str]] = {}
    adapters: list[dict] = []
    cur: dict | None = None
    last: tuple[dict, str] | None = None

    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        m = _IP_ADAPTER.match(line)
        if m:
            cur = {"name": clean_text(m["name"]), "fields": {}}
            adapters.append(cur)
            last = None
            continue
        m = _IP_KV.match(line)
        if m:
            target = cur["fields"] if cur else top
            key = m["key"].strip().lower()
            target.setdefault(key, [])
            if m["val"].strip():
                target[key].append(m["val"].strip())
            last = (target, key)
            continue
        m = _IP_CONT.match(line)
        if m and last:
            last[0][last[1]].append(m["v"].strip())

    if not adapters:
        raise ParserError("parse_error", "no adapter blocks found in ipconfig output")

    result = []
    for a in adapters:
        f = a["fields"]
        desc = clean_text((f.get("description") or [""])[0], 80)
        mac = (f.get("physical address") or [""])[0]
        connected = "media disconnected" not in " ".join(f.get("media state", [])).lower()
        ipv4 = _ips(f.get("ipv4 address", []), 4)
        gateway = _ips(f.get("default gateway", []), 4)
        result.append({
            "name": a["name"],
            "description": desc,
            "mac_masked": mask_mac(mac) if mac else None,
            "media_connected": connected,
            "ipv4": ipv4,
            "default_gateway": gateway,
            "dns_servers": _ips(f.get("dns servers", []), 4),
            "dhcp_server": next(iter(_ips(f.get("dhcp server", []), 4)), None),
            "virtual": bool(_VIRTUAL.search(desc)),
            "active": connected and bool(ipv4) and bool(gateway),
        })

    active = [a for a in result if a["active"]]
    primary = active[0] if active else None
    return {
        "hostname": clean_text((top.get("host name") or [""])[0]) or None,
        "adapters": result,
        "active_interfaces": [a["name"] for a in active],
        "default_gateway": primary["default_gateway"][0] if primary else None,
        "dns_servers": primary["dns_servers"] if primary else [],
        "local_ip": primary["ipv4"][0] if primary else None,
    }