# TraceForge Vercel frontend

This is the React/Vite frontend for TraceForge. The Python analysis engine and
FastAPI service live in the repository root and are intended to deploy to
Render separately.

## Local development

Start the API from the repository root:

```powershell
python -m pip install -e ".[api]"
$env:PYTHONPATH = "src"
python -m uvicorn traceforge.api:app --reload --port 8000
```

In another terminal:

```powershell
cd frontend
Copy-Item .env.example .env.local
npm install
npm run dev
```

Open `http://localhost:5173`.

## Deploy to Vercel

Create a Vercel project connected to this repository with:

```text
Root Directory: frontend
Framework preset: Vite
Build command: npm run build
Output directory: dist
Install command: npm ci
```

Set this Vercel environment variable:

```text
VITE_API_BASE_URL=https://<your-render-service>.onrender.com
VITE_DEFAULT_CASE_KEY=cnc_vmc_07
```

`VITE_*` values are public browser configuration. Never put secrets in them.
