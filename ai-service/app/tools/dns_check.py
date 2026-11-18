from __future__ import annotations

import time

import dns.exception
import dns.resolver

from app.config import load_settings
from app.tools.base import ToolContext, ToolFailure, ToolTimeout, execute_tool
from app.tools.models import ToolResult
from app.tools.validation import check_resolved_ips, validate_host

QUERY_TIMEOUT_S = 3.0


def _query(domain: str, resolver_ip: str) -> dict:
    r = dns.resolver.Resolver(configure=False)
    r.nameservers = [resolver_ip]
    r.timeout = QUERY_TIMEOUT_S
    r.lifetime = QUERY_TIMEOUT_S
    t0 = time.perf_counter()
    try:
        answer = r.resolve(domain, "A")
    except dns.resolver.NXDOMAIN:
        return {"resolver": resolver_ip, "ok": False, "rcode": "NXDOMAIN",
                "time_ms": round((time.perf_counter() - t0) * 1000, 1), "ips": []}
    except dns.resolver.NoAnswer:
        return {"resolver": resolver_ip, "ok": False, "rcode": "NOANSWER",
                "time_ms": round((time.perf_counter() - t0) * 1000, 1), "ips": []}
    except (dns.exception.Timeout, dns.resolver.NoNameservers, OSError) as e:
        return {"resolver": resolver_ip, "ok": False, "rcode": type(e).__name__.upper(),
                "time_ms": round((time.perf_counter() - t0) * 1000, 1), "ips": []}
    return {"resolver": resolver_ip, "ok": True, "rcode": "NOERROR",
            "time_ms": round((time.perf_counter() - t0) * 1000, 1),
            "ips": sorted({rr.address for rr in answer})}


def check_dns(domain: str, resolver: str | None = None, ctx: ToolContext | None = None) -> ToolResult:
    ctx = ctx or ToolContext()

    def work() -> dict:
        d = validate_host(domain)
        allowed = set(load_settings().public_resolvers) | set(ctx.system_dns)
        if resolver is not None:
            res = validate_host(resolver, ctx.allowed_private)
            if res not in allowed:
                raise ToolFailure("resolver_not_allowed", f"{res} is not an allowed resolver")
            targets = [res]
        else:
            targets = list(ctx.system_dns[:1]) + sorted(load_settings().public_resolvers)[:1]
            if not targets:
                raise ToolFailure("no_resolver", "no resolver available")
        results = [_query(d, t) for t in targets]
        for r in results:
            if r["ips"]:
                check_resolved_ips(r["ips"], ctx.allowed_private)
        okay = [r for r in results if r["ok"]]
        if not okay and all(r["rcode"] == "TIMEOUT" for r in results):
            raise ToolTimeout("all resolvers timed out")
        return {"domain": d, "results": results,
                "slowest_ms": max(r["time_ms"] for r in results)}

    return execute_tool("check_dns", {"domain": domain, "resolver": resolver}, work)