FROM node:22-alpine AS build

WORKDIR /app
COPY frontend/package*.json ./
RUN npm ci

COPY frontend ./
ENV VITE_API_BASE_URL=/api/v1 \
    VITE_SERVER_HOST=__SAME_ORIGIN__
RUN npm run build

FROM nginx:1.27-alpine
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080
