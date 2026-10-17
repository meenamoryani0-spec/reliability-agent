"use client";
import { useRef, useState } from "react";
import { ArrowRightIcon, LockClosedIcon } from "@radix-ui/react-icons";

export function OperatorLogin() {
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const busy = useRef(false);
  return <form className="operator-form" onSubmit={async (event) => {
    event.preventDefault();
    if (busy.current) return;
    const form = event.currentTarget;
    const key = String(new FormData(form).get("key") ?? "");
    busy.current = true; setPending(true); setError("");
    try {
      const response = await fetch("/api/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key }), cache: "no-store", signal: AbortSignal.timeout(10_000) });
      form.reset();
      if (!response.ok) { setError(response.status === 429 ? "Too many attempts. Wait a minute before trying again." : "Access wasn’t granted. Check the key and try again."); return; }
      window.location.replace("/dashboard");
    } catch { setError("Couldn’t connect. Please try again."); }
    finally { busy.current = false; setPending(false); }
  }}><label htmlFor="operator-key">Operator access key</label><div className="login-input"><LockClosedIcon /><input id="operator-key" name="key" type="password" required minLength={43} maxLength={128} autoComplete="current-password" spellCheck={false} aria-describedby={error ? "login-help login-error" : "login-help"} disabled={pending} /></div><p id="login-help">Enter the generated key from your deployment operator.</p>{error && <p id="login-error" role="alert">{error}</p>}<button className="landing-button" type="submit" disabled={pending}>{pending ? "Checking access…" : "Open workspace"}<ArrowRightIcon /></button></form>;
}

export function OperatorLogout() {
  const [error, setError] = useState(false);
  const [pending, setPending] = useState(false);
  return <div className="flex items-center gap-2"><button className="text-button" disabled={pending} onClick={async () => {
    setPending(true); setError(false);
    try {
      const response = await fetch("/api/session", { method: "DELETE", headers: { "Content-Type": "application/json" }, cache: "no-store", signal: AbortSignal.timeout(10_000) });
      if (!response.ok) throw new Error();
      window.location.replace("/login");
    } catch { setError(true); setPending(false); }
  }}>{pending ? "Signing out…" : "Sign out"}</button>{error && <span role="alert" className="text-xs">Sign-out failed. Try again.</span>}</div>;
}
