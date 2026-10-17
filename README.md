# EPIC Waterfalls

This project contains the source code for the EPIC Astronomy website and the Waterfalls application. See [https://epic-astronomy.org](https://epic-astronomy.org) for more details.

The frontend is built with the NuxtJS framework and utlilizes Nuxt UI Pro and custom built vue components. The backend is powered by FastAPI and SQLModel to fetch all spectrogram related data from EPIC's PostgreSQL databases located at the Long Wavelength Array in Sevilleta, New Mexico.

## Databases

The backend reads two kinds of PostgreSQL database; no query joins them.

- **Global database** (`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`) on the head node. It holds the watch list (`public.epic_watchdog`), the FRB analysis tables (`epic_frb_*`) and everything else the website writes.
- **Per-node databases**, one per imaging worker. Each worker's imager writes the data of the band it images to the tables `epic_pixels`, `epic_img_metadata2`, `epic_files_metadata2` and `epic_daily_digest` (schema `EPIC_DATA_SCHEMA`) of its own PostgreSQL.

`app/core/nodes.py` is the access layer for the per-node databases. A query for one band (spectrogram, light curve, the FRB analysis of a band) goes to the nodes that hold that band, known from the distinct `chan0` of each node's session table (cached) or from `EPIC_NODE_BANDS`; a band no node is known to hold is asked of every node. Queries across bands (session list, days with data, daily sources, daily digest, the watch list's data status) go to every node in parallel, and the rows are merged, ordered and paginated in Python.

A node that does not answer within its time limits drops out of the result instead of failing the request. Object responses then list it in `nodes_missing` and its bands in `bands_missing`; list responses carry the same in the headers `X-EPIC-Nodes-Missing` and `X-EPIC-Bands-Missing`. The pages show a note naming the missing bands. The FRB analysis leaves a band whose node is down pending, to be analysed on a later run.

### Archive of older data

A curator moves the older partitions of the per-node tables to an archive in the head node's PostgreSQL, into tables with the same columns. Every name the backend assumes about the archive is in the `EPIC_ARCHIVE_*` block of `app/core/config.py`.

- **Boundary.** Each node's data begin at its boundary: its oldest row (`node_oldest`, `min(img_time)` of `epic_pixels`), or the end of what the curator archived from it (`catalogue`, a query on the head). A request whose time range reaches below the boundary of its nodes, plus `EPIC_ARCHIVE_OVERLAP_S`, also reads the archive, over the older part of the range only; the nodes are always asked for the whole range. With `none` the archive is read for every request.
- **Merging.** Lists across bands (sessions, days, daily sources, digest, the watch list's data status) merge both tiers. A row present in both, as in a partition caught mid-move, is returned once: sessions by session and band, digest spectra by time and band, pixels by their values other than the pixel data.
- **Archive down.** The response then carries `archive_missing` and `archive_before` (the oldest boundary of the nodes asked), or the header `X-EPIC-Archive-Missing` (that time, or `true` when it is not known). The pages say "Data older than <day> are not available because the archive database did not respond." The FRB analysis defers a band whose sessions or pixels may be in an archive that does not answer.
- **Not archived.** A node table missing from `EPIC_ARCHIVE_TABLES`, or an archive table that does not exist, is read from the nodes only.

| Variable | Default | Meaning |
|---|---|---|
| `EPIC_ARCHIVE_ENABLED` | true | Read the archive at all |
| `EPIC_ARCHIVE_HOST`, `_PORT`, `_DB`, `_USER`, `_PASSWORD` | the global database's | Connection to the archive |
| `EPIC_ARCHIVE_SCHEMA` | `sevilleta` | Schema of the archive tables |
| `EPIC_ARCHIVE_TABLES` | `epic_pixels=epic_pixels_archive`, and the same `_archive` names for `epic_img_metadata2`, `epic_files_metadata2`, `epic_daily_digest` | Node table = archive table |
| `EPIC_ARCHIVE_BOUNDARY` | `node_oldest` | `node_oldest`, `catalogue` or `none` |
| `EPIC_ARCHIVE_BOUNDARY_TABLE` | `epic_pixels.img_time` | Table and indexed time column whose oldest row is a node's boundary |
| `EPIC_ARCHIVE_CATALOGUE_SQL` | `select node, max(t_end) from {schema}.epic_archive_catalogue group by node` | Rows of (node name or chan0, archived up to), for `catalogue` |
| `EPIC_ARCHIVE_BOUNDARY_CACHE_S` | 120 | Lifetime of the boundaries |
| `EPIC_ARCHIVE_OVERLAP_S` | 86400 | How far above the boundary the archive is also read |

| Variable | Default | Meaning |
|---|---|---|
| `EPIC_NODES` | `epic1=192.168.40.21` … `epic6=192.168.40.26` | Nodes as `name=host` or `name=host:port`, comma separated or a JSON list. The 1 Gb internal network (169.254.128.11–16) also reaches them |
| `EPIC_NODE_PORT` | 5434 | Port of the node databases, unless given per node |
| `EPIC_NODE_DB` | `epic` | Database name on every node |
| `EPIC_NODE_USER`, `EPIC_NODE_PASSWORD` | `epic_reader`, blank | Read-only role on the node databases (blank user: the global database's) |
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

The integration test (three clusters, the third as the head with the global tables and the archive) checks every ported route and the FRB analysis of a band, with node a's older data in the archive and some rows in both tiers, against the code of the `main` branch reading all the data from one database.

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
