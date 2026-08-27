from __future__ import annotations

"""Inline stylesheet for the M3 judge surface - no CDN, works offline."""
_VIEWER_CSS = """
:root {
  color-scheme: dark;
  --bg:#09090b; --surface:#111113; --surface-2:#18181b;
  --border:#27272a; --border-strong:#3f3f46;
  --text:#fafafa; --text-2:#a1a1aa; --muted:#71717a;
  --ok:#34d399; --ok-bg:rgba(52,211,153,.09);
  --warn:#fbbf24; --warn-bg:rgba(251,191,36,.08);
  --danger:#f87171; --danger-bg:rgba(248,113,113,.09);
  --info:#60a5fa; --info-bg:rgba(96,165,250,.09);
}
* { box-sizing:border-box; }
html { -webkit-text-size-adjust:100%; }
body { margin:0; background:var(--bg); color:var(--text);
  font:15px/1.55 ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif; }
.wrap { max-width:1080px; margin:0 auto; padding:1.6rem 1.25rem 3rem; }
.mono { font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
        font-variant-numeric:tabular-nums; }
a { color:inherit; }
:focus-visible { outline:2px solid var(--info); outline-offset:2px; }
header.site { display:flex; flex-wrap:wrap; align-items:baseline;
  gap:.35rem .9rem; margin-bottom:1.4rem; padding-bottom:1rem;
  border-bottom:1px solid var(--border); }
.brand { font-size:1.06rem; font-weight:700; letter-spacing:-.01em; }
.tagline { color:var(--text-2); font-size:.86rem; flex-basis:100%;
           margin:-.2rem 0 0; }
.site-meta { margin-left:auto; display:flex; gap:.45rem; align-items:center;
             flex-wrap:wrap; }
.chip { font-size:.67rem; font-weight:600; letter-spacing:.08em;
  text-transform:uppercase; color:var(--text-2);
  border:1px solid var(--border); border-radius:999px;
  padding:.16rem .6rem; background:var(--surface); white-space:nowrap; }
.chip.dim { color:var(--muted); }
main { display:flex; flex-direction:column; gap:1rem; }
section.card { background:var(--surface); border:1px solid var(--border);
  border-radius:10px; padding:1.15rem 1.3rem 1.25rem; }
h2.label { margin:0 0 .8rem; font-size:.7rem; font-weight:700;
  letter-spacing:.13em; text-transform:uppercase; color:var(--muted); }
.subtle { margin:-.4rem 0 .9rem; font-size:.84rem; color:var(--text-2); }
.grid2 { display:grid; grid-template-columns:1fr 1fr; gap:1rem; }
.hero.ok { border-top:2px solid var(--ok); }
.hero.warn { border-top:2px solid var(--warn); }
.hero.danger { border-top:2px solid var(--danger); }
.hero .eyebrow { display:flex; justify-content:space-between; gap:.75rem;
  flex-wrap:wrap; font-size:.68rem; font-weight:600; letter-spacing:.1em;
  text-transform:uppercase; color:var(--muted); margin-bottom:.7rem; }
.verdict { margin:0 0 .45rem; font-size:1.42rem; line-height:1.25;
  letter-spacing:-.01em; display:flex; align-items:center; gap:.6rem; }
.glyph { display:inline-flex; align-items:center; justify-content:center;
  border-radius:8px; flex:none; }
.hero .glyph { width:1.9rem; height:1.9rem; font-size:1.05rem; }
.hero.ok .glyph { background:var(--ok-bg); color:var(--ok); }
.hero.warn .glyph { background:var(--warn-bg); color:var(--warn); }
.hero.danger .glyph { background:var(--danger-bg); color:var(--danger); }
.explain { margin:0 0 1.1rem; max-width:62ch; color:var(--text-2);
           font-size:.92rem; }
.metrics { display:grid; grid-template-columns:repeat(4,minmax(0,1fr));
  gap:.75rem; margin:0 0 1.15rem; }
.metrics > div { background:var(--surface-2);
  border:1px solid var(--border); border-radius:8px; padding:.6rem .8rem; }
.metrics dt { font-size:.66rem; font-weight:600; letter-spacing:.09em;
  text-transform:uppercase; color:var(--muted); margin:0 0 .15rem; }
.metrics dd { margin:0; font-size:1.22rem; font-weight:650;
              font-variant-numeric:tabular-nums; }
.btn { display:inline-block; font-size:.82rem; font-weight:600;
  color:var(--text); text-decoration:none;
  border:1px solid var(--border-strong); border-radius:8px;
  padding:.42rem .85rem; background:var(--surface-2); }
.btn:hover { border-color:var(--muted); }
.gate-verdict { display:flex; align-items:center; gap:.6rem; flex-wrap:wrap;
  margin:0 0 .9rem; font-size:.88rem; color:var(--text-2); }
.pill { display:inline-flex; align-items:center; font-size:.7rem;
  font-weight:700; letter-spacing:.07em; text-transform:uppercase;
  border-radius:999px; padding:.22rem .65rem; }
.pill.ok { background:var(--ok-bg); color:var(--ok); }
.pill.warn { background:var(--warn-bg); color:var(--warn); }
.pill.danger { background:var(--danger-bg); color:var(--danger); }
.pill.info { background:var(--info-bg); color:var(--info); }
.checks { list-style:none; margin:0; padding:0; display:flex;
  flex-direction:column; gap:.5rem; }
.check { display:flex; gap:.7rem; align-items:flex-start;
  background:var(--surface-2); border:1px solid var(--border);
  border-radius:8px; padding:.6rem .8rem; }
.check .glyph { width:1.35rem; height:1.35rem; font-size:.85rem;
                margin-top:.05rem; }
.check.pass .glyph { background:var(--ok-bg); color:var(--ok); }
.check.fail { border-color:rgba(248,113,113,.45); background:var(--danger-bg); }
.check.fail .glyph { background:rgba(248,113,113,.18); color:var(--danger); }
.check .cname { font-size:.88rem; font-weight:600; }
.check .tag { font-size:.63rem; font-weight:700; letter-spacing:.08em;
  text-transform:uppercase; border-radius:999px; padding:.1rem .5rem;
  margin-left:.45rem; }
.check.pass .tag { background:var(--ok-bg); color:var(--ok); }
.check.fail .tag { background:rgba(248,113,113,.18); color:var(--danger); }
.check .cdetail { font-size:.8rem; color:var(--text-2); margin-top:.1rem; }
.gate-answer { margin:.95rem 0 0; font-size:.88rem; color:var(--text-2); }
.gate-answer strong { color:var(--text); font-weight:600; }
.chain { list-style:none; margin:0; padding:0; display:flex; flex-wrap:wrap;
  align-items:stretch; gap:.4rem; }
.node { background:var(--surface-2); border:1px solid var(--border);
  border-radius:8px; padding:.5rem .7rem; min-width:8.2rem; display:flex;
  flex-direction:column; gap:.1rem; }
.node.gate { border-color:rgba(251,191,36,.5); }
.ntype { font-size:.72rem; font-weight:600; letter-spacing:.04em;
         color:var(--text-2); }
.node .mono { font-size:.76rem; color:var(--info); word-break:break-all; }
.nnote { font-size:.68rem; color:var(--muted); }
.join { align-self:center; color:var(--muted); font-size:.95rem; }
.evi { list-style:none; margin:0; padding:0; display:flex;
  flex-direction:column; gap:.8rem; }
.evi > li { border-left:2px solid var(--border-strong); padding-left:.8rem; }
.etitle { font-size:.88rem; font-weight:600; }
.ecount { color:var(--text-2); font-weight:400; }
.ids { list-style:none; margin:.3rem 0 0; padding:0; display:flex;
  flex-direction:column; gap:.15rem; }
.ids li { font-size:.74rem; color:var(--info); word-break:break-all; }
.dom-chips { display:flex; flex-wrap:wrap; gap:.35rem; margin-top:.45rem; }
.chip-mini { font-size:.66rem; font-weight:600; letter-spacing:.05em;
  border:1px solid var(--border); border-radius:999px;
  padding:.12rem .55rem; color:var(--text-2); background:var(--surface-2); }
.chip-mini.miss { color:var(--danger); border-color:rgba(248,113,113,.45); }
.warn-text { color:var(--warn); }
.gauge-cap { font-size:.85rem; color:var(--text-2); margin:1rem 0 0; }
.gauge-cap strong { color:var(--text); font-size:1.05rem;
                    font-variant-numeric:tabular-nums; }
.gauge { position:relative; height:.55rem; border-radius:999px;
  background:var(--surface-2); border:1px solid var(--border);
  margin-top:.7rem; }
.gauge-fill { position:absolute; top:0; bottom:0; left:0;
  border-radius:999px; background:var(--warn); opacity:.85; }
.gauge-tick { position:absolute; top:-.4rem; bottom:-.4rem; width:1px;
  background:var(--border-strong); }
.gauge-note { display:flex; justify-content:space-between; gap:.6rem;
  font-size:.7rem; color:var(--muted); margin-top:.4rem; }
.unc-list { margin:.6rem 0 0; padding-left:1.1rem; font-size:.84rem;
            color:var(--text-2); }
.unc-list li { margin-bottom:.25rem; }
.none-note { font-size:.84rem; color:var(--muted); font-style:italic;
             margin:.4rem 0 0; }
.kv { display:grid; grid-template-columns:11rem 1fr; gap:.4rem .9rem;
      margin:0; font-size:.87rem; }
.kv dt { color:var(--muted); }
.kv dd { margin:0; }
.principle { margin:1rem 0 0; padding-top:.9rem;
  border-top:1px solid var(--border); font-size:.85rem;
  color:var(--text-2); }
details.meta-block { margin-top:1rem; }
details.meta-block summary { cursor:pointer; font-size:.76rem;
  font-weight:600; letter-spacing:.08em; text-transform:uppercase;
  color:var(--muted); }
details.meta-block[open] summary { margin-bottom:.6rem; }
footer.site { margin-top:1.6rem; padding-top:1rem;
  border-top:1px solid var(--border); font-size:.75rem; color:var(--muted);
  display:flex; flex-wrap:wrap; gap:.3rem 1rem; }
@media (max-width:760px) {
  .grid2 { grid-template-columns:1fr; }
  .metrics { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .site-meta { margin-left:0; }
  .kv { grid-template-columns:8.5rem 1fr; }
  .chain { flex-direction:column; align-items:stretch; gap:.25rem; }
  .node { min-width:0; }
  .join { transform:rotate(90deg); height:.9rem; line-height:.9rem; }
}
@media (max-width:430px) {
  .metrics { grid-template-columns:1fr; }
}
@media (prefers-reduced-motion:reduce) {
  * { animation-duration:.01ms !important;
      animation-iteration-count:1 !important;
      transition-duration:.01ms !important;
      scroll-behavior:auto !important; }
}
"""
