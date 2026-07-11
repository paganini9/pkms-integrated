# syntax=docker/dockerfile:1
# 프론트(React/Vite) — 빌드 후 정적 파일을 nginx 로 서빙. /api 는 bff 로 프록시.
FROM node:24-slim AS build
WORKDIR /app
# 실 BFF(/api/v1) 사용 빌드
ENV VITE_USE_MOCK=false
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build   # tsc -b && vite build → dist/

FROM nginx:1.27-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
