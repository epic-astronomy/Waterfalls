# EPIC Waterfalls

This project contains the source code for the EPIC Astronomy website and the Waterfalls application. See [https://epic-astronomy.org](https://epic-astronomy.org) for more details.

The frontend is built with Nuxt 4, Nuxt UI 4 and Nuxt Content 3, with custom Vue components for the spectrograms. The backend is powered by FastAPI and SQLModel to fetch all spectrogram related data from EPIC's Postgres database located at the Long Wavelength Array in Sevilleta, New Mexico.

## Setup

Node.js 22.21 or later (or 24.11 or later) is required.

```bash
npm ci
pip install -r server/backend/requirements.txt
```

## Development server

```bash
# frontend, with /api/v1 passed to the backend at NUXT_API_ORIGIN (default http://127.0.0.1:8000)
npx nuxt dev --port 3010 --host 127.0.0.1
```

```bash
# backend; see app/core/config.py for the settings it reads from the environment
cd server/backend
uvicorn app.main:app --env-file=../../.env --host=127.0.0.1 --port 8000
```

## Production

Every push builds two images with GitHub Actions (`.github/workflows/images.yml`) and publishes them to the GitHub Container Registry:

- `ghcr.io/epic-astronomy/waterfalls-frontend`, the Nuxt server on port 3000;
- `ghcr.io/epic-astronomy/waterfalls-backend`, the FastAPI server on port 8000.

Each image is tagged with its branch, `sha-<short sha>`, and `latest` for `main`. The Nomad job `waterfalls` runs both. The website reads its settings at run time:

| Variable | Meaning |
| --- | --- |
| `NUXT_API_ORIGIN` | the backend that `/api/v1` is passed to |
| `NUXT_PUBLIC_HANKO_API_URL` | the Hanko project |
| `NUXT_PUBLIC_SITE_URL` | the canonical origin, `https://epic-astronomy.org` by default |

To build and run the images locally:

```bash
docker build -t waterfalls-frontend .
docker build -t waterfalls-backend server/backend
docker run --rm --network host --env-file backend.env waterfalls-backend --host 127.0.0.1 --port 8000
docker run --rm --network host -e PORT=3000 -e NUXT_API_ORIGIN=http://127.0.0.1:8000 waterfalls-frontend
```
