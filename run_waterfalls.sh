#!/bin/bash

eval "$(/home/epic/anaconda/condabin/conda shell.bash hook)"
conda activate waterfalls
NITRO_PORT=3001 NITRO_HOST=127.0.0.1 NITRO_PRESET=node_cluster /usr/bin/node .output/server/index.mjs & 
(cd server/backend; uvicorn app.main:app --env-file=../../.env --host=127.0.0.1)
