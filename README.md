# EPIC Waterfalls

This project contains the source code for the EPIC Astronomy website and the Waterfalls application. See [https://epic-astronomy.org](https://epic-astronomy.org) for more details.

The frontend is built with the NuxtJS framework and utlilizes Nuxt UI Pro and custom built vue components. The backend is powered by FastAPI and SQLModel to fetch all spectrogram related data from EPIC's PostgreSQL databases located at the Long Wavelength Array in Sevilleta, New Mexico.

## Databases

The backend reads two kinds of PostgreSQL database; no query joins them.

- **Global database** (`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`) on the head node. It holds the watch list (`public.epic_watchdog`), the FRB analysis tables (`epic_frb_*`) and everything else the website writes.
- **Per-node databases**, one per imaging worker. Each worker's imager writes the data of the band it images to the tables `epic_pixels`, `epic_img_metadata2`, `epic_files_metadata2` and `epic_daily_digest` (schema `EPIC_DATA_SCHEMA`) of its own PostgreSQL.

`app/core/nodes.py` is the access layer for the per-node databases. A query for one band (spectrogram, light curve, the FRB analysis of a band) goes to the nodes that hold that band, known from the distinct `chan0` of each node's session table (cached) or from `EPIC_NODE_BANDS`; a band no node is known to hold is asked of every node. Queries across bands (session list, days with data, daily sources, daily digest, the watch list's data status) go to every node in parallel, and the rows are merged, ordered and paginated in Python.

A node that does not answer within its time limits drops out of the result instead of failing the request. Object responses then list it in `nodes_missing` and its bands in `bands_missing`; list responses carry the same in the headers `X-EPIC-Nodes-Missing` and `X-EPIC-Bands-Missing`. The pages show a note naming the missing bands. The FRB analysis leaves a band whose node is down pending, to be analysed on a later run.

| Variable | Default | Meaning |
|---|---|---|
| `EPIC_NODES` | `epic1=192.168.40.21` … `epic6=192.168.40.26` | Nodes as `name=host` or `name=host:port`, comma separated or a JSON list. The 1 Gb internal network (169.254.128.11–16) also reaches them |
| `EPIC_NODE_PORT` | 5432 | Port of the node databases, unless given per node |
| `EPIC_NODE_DB` | `epic` | Database name on every node |
| `EPIC_NODE_USER`, `EPIC_NODE_PASSWORD` | the global database's | Read-only role on the node databases |
| `EPIC_NODE_CONNECT_TIMEOUT_S` | 3 | Connection time limit |
| `EPIC_NODE_STATEMENT_TIMEOUT_MS` | 20000 | Statement time limit on the nodes (sessions are also read-only) |
| `EPIC_NODE_QUERY_TIMEOUT_S` | 25 | Time after which a node that has not answered is left out |
| `EPIC_NODE_RETRY_S` | 30 | Time an unreachable node is skipped before it is tried again |
| `EPIC_NODE_BANDS` | none | Fixed `chan0=node` entries instead of the discovered band map |
| `EPIC_NODE_BANDS_CACHE_S` | 300 | Lifetime of the discovered band map |
| `FRB_NODE_STATEMENT_TIMEOUT_MS` | 600000 | Statement time limit of the FRB analysis on the nodes |

### Tests

Run the backend tests on a worker, from `server/backend`, in the website's Python environment:

```bash
python -m unittest tests.test_nodes      # access layer and routes, with fake nodes
python -m unittest tests.test_localdb    # two throwaway PostgreSQL 16 clusters (initdb; PG_BIN if not on the path)
```

The integration test checks every ported route and the FRB analysis of a band against the code of the `main` branch reading all the data from one database.

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
