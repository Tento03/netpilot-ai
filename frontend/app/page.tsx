"use client";

import { useRef, useState } from "react";

type Tool = { tool: string; args?: Record<string, unknown>; status?: string; duration_ms?: number; id?: string; simulated?: boolean };
type Hyp = { id: string; status: string; evidence_refs: string[] };
type Report = {
  summary: string;
  observations: { statement: string; evidence_refs: string[] }[];
  recommended_actions: { action: string; rationale: string }[];
  limitations: string[];
  simulated: boolean;
};

const SCENARIOS = ["healthy", "weak_wifi", "upstream_slow", "dns_failure", "packet_loss", "host_unreachable"];

const badge: Record<string, string> = {
  open: "bg-amber-500/20 text-amber-300",
  confirmed: "bg-emerald-500/20 text-emerald-300",
  rejected: "bg-zinc-500/20 text-zinc-400",
  ok: "bg-emerald-500/20 text-emerald-300",
  error: "bg-red-500/20 text-red-300",
  timeout: "bg-red-500/20 text-red-300",
};

export default function Home() {
  const [question, setQuestion] = useState("Kenapa koneksi internet saya terasa lambat?");
  const [mode, setMode] = useState<"replay" | "live">("replay");
  const [scenario, setScenario] = useState("dns_failure");
  const [running, setRunning] = useState(false);
  const [node, setNode] = useState("");
  const [tools, setTools] = useState<Tool[]>([]);
  const [hyps, setHyps] = useState<Hyp[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState("");
  const abort = useRef<AbortController | null>(null);

  function handle(event: string, data: any) {
    if (event === "node_started") setNode(data.node);
    else if (event === "tool_started") setTools((t) => [...t, { tool: data.tool, args: data.args }]);
    else if (event === "tool_finished")
      setTools((t) => {
        const i = [...t].reverse().findIndex((x) => x.tool === data.tool && !x.status);
        if (i < 0) return t;
        const idx = t.length - 1 - i;
        const copy = [...t];
        copy[idx] = { ...copy[idx], status: data.status, duration_ms: data.duration_ms, id: data.tool_call_id, simulated: data.simulated };
        return copy;
      });
    else if (event === "hypothesis_updated") setHyps(data.hypotheses);
    else if (event === "report_ready") setReport(data.report);
    else if (event === "error") setError(`${data.code}: ${data.message}`);
  }

  async function run() {
    setRunning(true); setNode(""); setTools([]); setHyps([]); setReport(null); setError("");
    abort.current = new AbortController();
    try {
      const res = await fetch("/api/investigate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, mode, scenario: mode === "replay" ? scenario : undefined }),
        signal: abort.current.signal,
      });
      if (!res.ok || !res.body) {
        setError(`Permintaan gagal (HTTP ${res.status})`);
        return;
      }
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        const frames = buf.split("\n\n");
        buf = frames.pop() ?? "";
        for (const f of frames) {
          const lines = f.split("\n");
          const ev = lines.find((l) => l.startsWith("event: "))?.slice(7);
          const dl = lines.find((l) => l.startsWith("data: "))?.slice(6);
          if (ev && dl) {
            try { handle(ev, JSON.parse(dl)); } catch { /* ignore malformed frame */ }
          }
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError("Koneksi terputus");
    } finally {
      setRunning(false); setNode("");
    }
  }

  return (
    <main className="mx-auto w-full max-w-6xl p-6 space-y-6">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">NetPilot <span className="text-cyan-400">AI</span></h1>
          <p className="text-sm text-zinc-400">Agen diagnosis jaringan berbasis hipotesis dan bukti</p>
        </div>
        {running && <span className="animate-pulse rounded-full bg-cyan-500/20 px-3 py-1 text-xs text-cyan-300">node: {node || "..."}</span>}
      </header>

      <section className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
        <textarea value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={500} rows={2}
          className="w-full rounded-lg border border-zinc-700 bg-zinc-950 p-3 text-sm outline-none focus:border-cyan-500" />
        <div className="flex flex-wrap items-center gap-3">
          <select value={mode} onChange={(e) => setMode(e.target.value as "replay" | "live")}
            className="rounded-lg border border-zinc-700 bg-zinc-950 p-2 text-sm">
            <option value="replay">Replay (simulasi)</option>
            <option value="live">Live (jaringan nyata + Gemini)</option>
          </select>
          {mode === "replay" && (
            <select value={scenario} onChange={(e) => setScenario(e.target.value)}
              className="rounded-lg border border-zinc-700 bg-zinc-950 p-2 text-sm">
              {SCENARIOS.map((s) => <option key={s}>{s}</option>)}
            </select>
          )}
          <button onClick={run} disabled={running || !question.trim()}
            className="rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-zinc-950 disabled:opacity-40">
            {running ? "Menyelidiki..." : "Jalankan"}
          </button>
          {running && <button onClick={() => abort.current?.abort()} className="text-sm text-zinc-400 underline">Batal</button>}
        </div>
        {mode === "live" && <p className="text-xs text-amber-300">Mode live bisa gagal bila kuota Gemini habis; error akan ditampilkan di bawah.</p>}
        {error && <p className="rounded-lg bg-red-500/10 p-3 text-sm text-red-300">{error}</p>}
      </section>

      <div className="grid gap-6 md:grid-cols-2">
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
          <h2 className="mb-3 font-semibold">Jejak tool</h2>
          <ol className="space-y-2">
            {tools.map((t, i) => (
              <li key={i} className="rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-cyan-300">{i + 1}. {t.tool}</span>
                  <span className={`rounded px-2 py-0.5 text-xs ${badge[t.status ?? ""] ?? "bg-zinc-700/40 text-zinc-300"}`}>
                    {t.status ?? "berjalan"}{t.duration_ms !== undefined ? ` · ${t.duration_ms} ms` : ""}
                  </span>
                </div>
                <div className="mt-1 break-all font-mono text-xs text-zinc-500">{JSON.stringify(t.args)}</div>
              </li>
            ))}
            {tools.length === 0 && <li className="text-sm text-zinc-500">Belum ada tool dijalankan.</li>}
          </ol>
        </section>

        <section className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4">
          <h2 className="mb-3 font-semibold">Hipotesis</h2>
          <ul className="space-y-2">
            {hyps.map((h) => (
              <li key={h.id} className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-sm">
                <span className="font-mono">{h.id}</span>
                <span className="text-xs text-zinc-500">bukti: {h.evidence_refs.length}</span>
                <span className={`rounded px-2 py-0.5 text-xs ${badge[h.status]}`}>{h.status}</span>
              </li>
            ))}
            {hyps.length === 0 && <li className="text-sm text-zinc-500">Belum ada hipotesis.</li>}
          </ul>
        </section>
      </div>

      {report && (
        <section className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-4 space-y-3">
          <div className="flex items-center gap-3">
            <h2 className="font-semibold">Laporan</h2>
            {report.simulated
              ? <span className="rounded bg-fuchsia-500/20 px-2 py-0.5 text-xs font-bold text-fuchsia-300">SIMULATED</span>
              : <span className="rounded bg-emerald-500/20 px-2 py-0.5 text-xs font-bold text-emerald-300">REAL MEASUREMENT</span>}
          </div>
          <p className="text-sm">{report.summary}</p>
          <ul className="space-y-1 text-sm">
            {report.observations.map((o, i) => (
              <li key={i} className="text-zinc-300">• {o.statement} <span className="text-xs text-zinc-500">[{o.evidence_refs.map((r) => r.slice(0, 8)).join(", ")}]</span></li>
            ))}
          </ul>
          {report.recommended_actions.map((a, i) => (
            <p key={i} className="text-sm text-cyan-200">Saran: {a.action} <span className="text-zinc-500">({a.rationale})</span></p>
          ))}
          {report.limitations.map((l, i) => <p key={i} className="text-xs text-amber-300">Batasan: {l}</p>)}
        </section>
      )}
    </main>
  );
}