#!/bin/sh
# Runs before the stock nginx entrypoint (which renders /etc/nginx/templates
# with envsubst). The template proxies to a *variable* upstream, and nginx can
# only resolve variables if an explicit resolver is configured — so export the
# container's own nameserver as ${RESOLVER} (docker compose: 127.0.0.11;
# Render: platform DNS), falling back to a public resolver.
set -e

resolver=$(awk '/^nameserver/ { print $2; exit }' /etc/resolv.conf 2>/dev/null || true)
case "$resolver" in
  *:*) resolver="[$resolver]" ;; # IPv6 addresses need brackets in nginx
esac
RESOLVER="${resolver:-1.1.1.1}"
export RESOLVER

exec /docker-entrypoint.sh "$@"
