import type { Monitoring } from "@/lib/monitoring";
import { age, humanize } from "@/lib/presentation";

export function WebsiteScheduleStatus({ settings, now }: { settings: Monitoring | null; now: number }) {
  const schedule = settings?.website_schedule;
  if (!settings) return <p>Automatic-check settings are unavailable.</p>;
  if (!settings.automatic_monitoring) return <p>Automatic checks are off. Use Run checks for a fresh result.</p>;
  if (!schedule) return <p>Automatic checks are configured, but their activity is unavailable.</p>;
  return <div className="space-y-1">
    <p>Automatic checks: {humanize(schedule.state)}. The backend waits {schedule.interval_seconds} seconds after each scan before starting the next.</p>
    <p>Checks run while the backend is awake. Hosting sleep or downtime can cause gaps; missed scans are not replayed.</p>
    <p>{schedule.last_finished_at ? `Last scan finished ${age(schedule.last_finished_at, now)}. Result: ${humanize(schedule.last_outcome ?? "unknown")}; ${schedule.last_checks_saved} checks saved.` : "No completed scan has been recorded in this backend session."} See Checks history for the observed website health.</p>
  </div>;
}
