"use client";
export default function ErrorPage({ reset }: { reset: () => void }) {
  return <main className="grid min-h-dvh place-content-center gap-4 p-8"><h1 className="text-2xl font-medium">The workspace couldn’t load.</h1><p>Your backend records remain available. Reload to try again.</p><button className="button-primary" onClick={reset}>Reload workspace</button></main>;
}
