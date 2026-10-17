# Supabase public certificate authority

`supabase-ca.crt` is a public CA certificate, not a password or private key.
It is explicitly selected with `STORAGE_SSL_CA_FILE`; no global trust store is changed.

- Official download: https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt
- URL template published by Supabase Studio: https://github.com/supabase/supabase/blob/master/apps/studio/hooks/custom-content/custom-content.json
- DER SHA-256: `807025ad50d4ed219d2c9c7d299c004f824eb00cf7f65afef607d07b72e6cafa`
- Subject: Supabase Root 2021 CA; valid until 26 April 2031.
- Verified against the selected session pooler's TLS chain on 17 October 2026.

The backend image places this file at `/app/backend/certs/supabase-ca.crt`.
PostgreSQL continues to use `sslmode=verify-full`, including hostname verification.
Revalidate the official source, fingerprint and live TLS chain before replacing it.
