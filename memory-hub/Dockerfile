FROM node:22-alpine
WORKDIR /app
COPY package.json ./
COPY bin ./bin
COPY src ./src
COPY public ./public
ENV HOST=0.0.0.0 PORT=8787 OBSIDIAN_VAULT=/vault
VOLUME /vault
EXPOSE 8787
CMD ["node", "bin/server.js"]
