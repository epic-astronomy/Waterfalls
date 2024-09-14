# EPIC Waterfalls

This project contains the source code for the EPIC Astronomy website and the Waterfalls application. See [https://epic-astronomy.org](https://epic-astronomy.org) for more details.

The frontend is built with the NuxtJS framework and utlilizes Nuxt UI Pro and custom built vue components. The backend is powered by FastAPI and SQLModel to fetch all spectrogram related data from EPIC's Postgres database located at the Long Wavelength Array in Seveilleta, New Mexico.

## Setup

Make sure to install the dependencies:

```bash
# npm
npm install

pip install requirements.txt
```

## Development Server

Start the development server on `http://localhost:3000`:

```bash
# Frontend
npm run dev --port=3000 --host=127.0.0.1
```

```bash
# backend
# configure the .env file. See .env.example for the required environment variables.
cd backend;
uvicorn app.main:app --env-file=../../.env --host=127.0.0.1
```



## Production

Build the application for production:

```bash
npm run build
npm run ./output/server/index.mjs
```
