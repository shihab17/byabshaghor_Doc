# Custom Domains & Subdomains

Tenants can reach the platform on their own hostname — either an assigned
subdomain (`acme.byabshaghor.com`) or their own domain (`pos.acme.com`).

Tenancy is resolved by JWT, not by hostname — no backend change is needed for
routing. The domain layer only provides:

- **TLS approval** — Caddy asks the backend before issuing a cert
- **White-label branding** — verified domains show the shop's name/logo on
  the login page (`GET /api/v1/platform/domain-info?host=...`)

## Flow

1. Super admin adds the domain: `/admin/tenants/<id>` → **Custom Domains**
2. Customer creates DNS records:
   - `CNAME  pos.acme.com → app.byabshaghor.com`
   - `TXT   pos.acme.com → byabshaghor-verify=<token>` (shown in admin UI)
3. Admin clicks **Verify** → `verified_at` is set → TLS + branding activate.

## Caddyfile

The production config lives in `deploy/Caddyfile` — it routes `/api/v1/*`
and `/uploads/*` to the backend and everything else to Next.js, on the same
origin. Full setup steps: `deploy/README.md`.

```caddy
{
    on_demand_tls {
        ask http://localhost:4000/api/v1/platform/tls-ask
        interval 2m
        burst 5
    }
}

byabshaghor.com, app.byabshaghor.com, *.byabshaghor.com {
    tls {
        dns cloudflare {env.CF_API_TOKEN}   # wildcard needs DNS challenge
    }
    @api path /api/v1/* /uploads/*
    handle @api { reverse_proxy localhost:4000 }
    handle { reverse_proxy localhost:3000 }
}

:443 {
    tls { on_demand }
    @api path /api/v1/* /uploads/*
    handle @api { reverse_proxy localhost:4000 }
    handle { reverse_proxy localhost:3000 }
}
```

The web app resolves the API from `window.location.origin` + `/api/v1` in
production (see `shop-app-web/src/lib/api.ts`), so a custom domain like
`pos.acme.com` calls `pos.acme.com/api/v1` — same origin, no CORS, and no
`NEXT_PUBLIC_API_URL` needed. Leave it empty in production builds.

## Customer checklist

| Step | Record | Value |
|---|---|---|
| 1 | CNAME | `pos.acme.com` → `app.byabshaghor.com` |
| 2 | TXT | `pos.acme.com` → `byabshaghor-verify=<token>` |
| 3 | — | Wait for DNS propagation (minutes–hours), ask admin to Verify |

Cloudflare users: the CNAME must be **DNS only** (grey cloud) — proxied mode
breaks on-demand TLS issuance.
