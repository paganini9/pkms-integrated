# syntax=docker/dockerfile:1
# BFF (Node/Express, ESM). 멀티스테이지: tsc 빌드 → 런타임은 prod 의존만.
FROM node:24-slim AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build   # tsc → dist/

FROM node:24-slim AS runtime
WORKDIR /app
ENV NODE_ENV=production
COPY package*.json ./
RUN npm ci --omit=dev && npm cache clean --force
COPY --from=build /app/dist ./dist
EXPOSE 4000
# 키는 이미지에 넣지 않는다 — 런타임 env(Studio_API_Key 등)로만 주입. 로그 마스킹.
CMD ["node", "dist/index.js"]
