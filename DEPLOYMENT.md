# TraceForge deployment

TraceForge is deployed as two free-tier services:

```text
Vercel                         Render
React/Vite frontend  ───────▶  FastAPI analysis API
https://<frontend>.vercel.app  https://<api>.onrender.com
```

The first deployment is intentionally read-only over the synthetic CNC case
bundled in `demo/cnc_vmc_07`. Render's free filesystem is ephemeral, so the
service does not accept uploads or persist user-created cases.

## 1. Deploy the API to Render

1. Push the repository to a Git provider.
2. In Render, choose **New → Blueprint** and select the repository. Render
   will detect `render.yaml`.
3. Set the `FRONTEND_ORIGINS` environment variable after the Vercel URL is
   known. For the first deployment, use:

   ```text
   https://<your-vercel-project>.vercel.app,http://localhost:5173
   ```

4. Deploy and copy the generated API URL, for example:

   ```text
   https://traceforge-api.onrender.com
   ```

5. Verify the service:

   ```text
   GET https://<your-api>.onrender.com/healthz
   ```

   Expected response:

   ```json
   {"status":"ok","service":"traceforge","version":"0.1.0"}
   ```

### Render configuration supplied by the repository

`render.yaml` configures:

```text
Build:  python -m pip install --upgrade pip && python -m pip install -e ".[api]"
Start:  python -m uvicorn traceforge.api:app --host 0.0.0.0 --port $PORT
Health: /healthz
```

Do not use the old Streamlit Docker command for the API service.

## 2. Deploy the frontend to Vercel

1. In Vercel, choose **Add New → Project** and import the repository.
2. Set the project root directory to:

   ```text
   frontend
   ```

3. Use these build settings:

   ```text
   Framework preset: Vite
   Install command: npm ci
   Build command: npm run build
   Output directory: dist
   ```

4. Add these Vercel environment variables:

   ```text
   VITE_API_BASE_URL=https://<your-api>.onrender.com
   VITE_DEFAULT_CASE_KEY=cnc_vmc_07
   ```

5. Deploy the frontend.
6. Copy the Vercel production URL and add it to Render's
   `FRONTEND_ORIGINS` variable.
7. Redeploy the Render API after changing `FRONTEND_ORIGINS`.

All `VITE_*` values are public and compiled into the browser bundle. Never
place API keys, database passwords, or signing secrets in them.

## Local full-stack development

Terminal 1 — API:

```powershell
cd C:\Users\saransh\verigraph
python -m pip install -e ".[api]"
$env:PYTHONPATH = "src"
python -m uvicorn traceforge.api:app --reload --port 8000
```

Terminal 2 — frontend:

```powershell
cd C:\Users\saransh\verigraph\frontend
Copy-Item .env.example .env.local
npm ci
npm run dev
```

Open `http://localhost:5173`. Vite proxies `/api` and `/healthz` to the local
FastAPI service. The frontend can also call Render directly when
`VITE_API_BASE_URL` is set.

## API contract

```text
GET /healthz
GET /api/v1/cases
GET /api/v1/cases/{case_key}/analysis?top_k=8
GET /api/v1/cases/{case_key}/telemetry?signals=...&limit=5000
GET /api/v1/cases/{case_key}/predictions?limit=5000
GET /api/v1/cases/{case_key}/report
GET /api/v1/cases/{case_key}/graph
```

Case keys are allowlisted directory names, not arbitrary filesystem paths.
The initial case key is `cnc_vmc_07`.

## Free-tier behavior

- Render may sleep after inactivity; the first request can be slow while the
  API wakes up. The frontend shows a backend-unavailable state instead of a
  blank dashboard.
- Render's filesystem is ephemeral. Do not add uploads or persistent case
  edits without adding durable storage.
- The initial API is public read-only access. CORS controls browser origins but
  is not authentication. Add authentication before serving private industrial
  data.
- Vercel environment-variable changes require a new frontend deployment.
