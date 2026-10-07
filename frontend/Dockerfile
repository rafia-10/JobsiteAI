FROM node:22-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
# Rendered at container start by nginx's entrypoint (envsubst):
# ${BACKEND_URL} -> base URL of the API
# (docker compose: "http://backend:8000" · Render: "https://…onrender.com")
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# Exports ${RESOLVER} (from /etc/resolv.conf) before rendering the template;
# nginx needs it because the template proxies to a variable upstream.
COPY docker-entrypoint.sh /usr/local/bin/resolver-entrypoint.sh
RUN chmod +x /usr/local/bin/resolver-entrypoint.sh

# ${PORT}: docker compose leaves it unset (nginx listens on 80);
# Render sets PORT=10000 and forwards traffic there.
ENV PORT=80 \
    BACKEND_URL=http://backend:8000

ENTRYPOINT ["resolver-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
EXPOSE 80
