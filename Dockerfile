FROM node:18-alpine

RUN mkdir -p /home/node/app && chown -R node:node /home/node/app
WORKDIR /home/node/app
COPY --chown=node:node package*.json ./
USER node
# RUN npm install

ENV NODE_ENV=production
ENV NITRO_PRESET=node_cluster
# EXPOSE 3000

ENV NUXT_HOST=0.0.0.0
ENV NUXT_PORT=3000

COPY  --chown=node:node .output .output

EXPOSE 3000
# CMD ["/bin/ls","-l"]
CMD [ "node", ".output/server/index.mjs"]