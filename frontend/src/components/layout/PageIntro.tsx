import type { ReactNode } from "react";

export function PageIntro({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <header className="flex flex-wrap items-end justify-between gap-4">
    <div><p className="page-eyebrow mb-2">Sri Lanka · AI research intelligence</p><h1 className="font-display text-h1 text-ink">{title}</h1><p className="mt-2 max-w-prose text-body-sm text-muted">{description}</p></div>
    {action}
  </header>;
}

export function ResearchHero() {
  return <section className="research-hero">
    <div className="hero-copy"><p className="text-[9px] font-semibold tracking-[.18em] text-[#d5ed9b]">ARTIFICIAL INTELLIGENCE. SRI LANKAN DISCOVERY.</p><h2>A clearer picture of<br /><em>AI research in Sri Lanka.</em></h2><p className="max-w-md text-xs leading-relaxed text-[#c2d6c7]">Explore AI methods, applications, and collaborations.<br />Every insight begins with an AI-related publication.</p></div>
    <svg className="research-hero-art" viewBox="0 0 360 270" fill="none" aria-hidden="true">
      <g stroke="#86aa67" strokeWidth=".7" opacity=".6"><ellipse cx="180" cy="137" rx="145" ry="97" transform="rotate(-30 180 137)" /><ellipse cx="180" cy="137" rx="135" ry="66" transform="rotate(40 180 137)" /><ellipse cx="180" cy="137" rx="110" ry="104" /><ellipse cx="180" cy="137" rx="65" ry="120" transform="rotate(30 180 137)" /><path d="M58 183L117 63 230 54 303 132 259 216 145 217 58 183 230 54 259 216 117 63 145 217 303 132 117 63M58 183l245-51M145 217L230 54" /></g>
      <g fill="#d5ed9b">{[[117,63,5],[230,54,4],[303,132,6],[259,216,4],[145,217,5],[58,183,4],[183,137,8]].map(([x,y,r]) => <circle key={`${x}-${y}`} cx={x} cy={y} r={r} />)}</g>
    </svg>
  </section>;
}
