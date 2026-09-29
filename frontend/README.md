# LisheBora frontend (Next.js)

```
src/
├── app/
│   ├── (public)/        public website — server-rendered from the CMS API (/, about, opportunities, news, faq, resources, contact, p/[slug])
│   ├── (auth)/          sign-in (password · SMS code · 2-step), register (5 steps + phone OTP), forgot-password
│   └── app/             signed-in portal — dashboard, supplier registry & review, my supplier profile, sourcing,
│                         users & roles, website content (CMS), audit trail, profile & security
├── components/          Brand (logo, leaf-vein motif), shells, UI helpers
└── lib/                 api.ts (fetch + silent refresh), auth.tsx (session context), server.ts, types, format
public/brand/            official AATF logo files (unaltered — see Brand Manual rules)
```

- `BACKEND_URL` in `.env.local` tells Next where FastAPI runs. `/api/*` is proxied, so there are no CORS or cookie issues.
- The menu is built from the permissions returned by `/api/v1/auth/me`, and the API enforces every permission again.
- Styles are in `src/app/globals.css`, using AATF tokens (`--green #507435`, `--gold #AB822D`, …). Red is used only for status.

`npm run dev` · `npm run build` · `npm run typecheck`
