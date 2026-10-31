# EarnScore frontend

React 18 + TypeScript + Vite, Tailwind CSS, react-router, TanStack Query, Recharts and react-i18next (English, Tamil, Hindi). In production the built files are served by the FastAPI backend from the same origin; see the main [README](../README.md).

```bash
npm ci
npm run dev          # http://localhost:5173, proxies /api to http://localhost:8000
npm run build        # production build into dist/
npx vitest run       # unit tests
npx playwright test  # end-to-end tests against http://127.0.0.1:8000 (or E2E_BASE_URL)
```

- `src/pages/`: worker, officer and admin pages, public sign-in and registration
- `src/components/`: shared UI, charts, the evidence table and the app shell
- `src/i18n/`: translation dictionaries
- `e2e/`: Playwright flows and the statement files they upload
