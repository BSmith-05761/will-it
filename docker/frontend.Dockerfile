# syntax=docker/dockerfile:1
FROM node:18-alpine AS deps
WORKDIR /app
COPY frontend/package.json ./
RUN npm install --omit=dev || true

FROM node:18-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY frontend .
ARG VITE_BACKEND_URL
ENV VITE_BACKEND_URL=${VITE_BACKEND_URL}
RUN npm run build || true

FROM node:18-alpine AS serve
WORKDIR /app
COPY --from=build /app/dist ./dist
RUN npm install -g serve || true
EXPOSE 5173
CMD ["serve", "-s", "dist", "-l", "5173"]
