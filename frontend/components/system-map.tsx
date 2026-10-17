import { ArrowTopRightIcon, GlobeIcon, LayersIcon, LightningBoltIcon } from "@radix-ui/react-icons";
import type { Check } from "@/lib/contracts";
import { isStale } from "@/lib/presentation";

const systems = [
  { category: "website", title: "Websites & APIs", subtitle: "Availability and browser flows", icon: GlobeIcon, number: "01" },
  { category: "n8n", title: "Automations", subtitle: "n8n execution evidence", icon: LightningBoltIcon, number: "02" },
  { category: "infrastructure", title: "Infrastructure", subtitle: "Database and platform signals", icon: LayersIcon, number: "03" },
] as const;

export function SystemMap({ checks, now, available, onSelect }: {
  checks: Check[]; now: number; available: boolean; onSelect: (category: string) => void;
}) {
  return <section className="system-map" aria-labelledby="system-map-title">
    <div className="system-map-heading"><div><span className="workspace-kicker">YOUR MONITORING SURFACE</span><h2 id="system-map-title">Three systems. One place to look.</h2></div><span>Recorded signals</span></div>
    <div className="system-map-grid">{systems.map(({ category, title, subtitle, icon: Icon, number }) => {
      const signals = checks.filter((check) => check.category === category);
      const failures = signals.filter((check) => check.status === "UNHEALTHY").length;
      const stale = signals.filter((check) => isStale(check, now)).length;
      const uncertain = signals.filter((check) => !["HEALTHY", "UNHEALTHY"].includes(check.status)).length;
      const description = !available ? "History unavailable" : !signals.length ? "No recorded observations"
        : failures ? `${failures} recorded ${failures === 1 ? "failure" : "failures"}`
        : stale ? "Evidence needs refreshing" : uncertain ? "Evidence is inconclusive" : "Latest observations passed";
      return <button className={`system-map-node ${failures ? "has-failure" : ""}`} key={category}
        disabled={!available || !signals.length} onClick={() => onSelect(category)} aria-label={`View ${category} observations`}>
        <div className="map-node-top"><span className="map-node-icon"><Icon /></span><span className="map-node-number">{number}</span></div>
        <h3>{title}</h3><p>{subtitle}</p>
        <div className="map-node-state"><span className={`map-state-dot ${failures ? "is-failure" : !signals.length || stale || uncertain ? "is-unknown" : ""}`} />{description}</div>
        <div className="map-node-bottom"><span>{available ? `${signals.length} ${signals.length === 1 ? "signal" : "signals"}${stale ? ` · ${stale} stale` : ""}` : "Unavailable"}</span><ArrowTopRightIcon /></div>
      </button>;
    })}</div>
    <p className="system-map-note">Latest observation per service and check type. Passing observations cover only what was checked.</p>
  </section>;
}
