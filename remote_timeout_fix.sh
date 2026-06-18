#!/usr/bin/env bash
set -euo pipefail

SERVICE_FILE="/etc/systemd/system/selvercoop.service"
NGINX_FILE="/etc/nginx/sites-available/creatorsofcode.com"

# Ensure gunicorn timeout is high enough for Cloudflare-challenged Playwright fetches.
sed -i 's/--timeout 120/--timeout 600/g; s/--timeout 300/--timeout 600/g' "$SERVICE_FILE"
if ! grep -q -- '--timeout 600' "$SERVICE_FILE"; then
  sed -i 's|gunicorn --workers 4 |gunicorn --workers 4 --timeout 600 |' "$SERVICE_FILE"
fi

# Ensure /selverjacoop/ proxy timeouts are high enough.
perl -0777 -i -pe 's|(location /selverjacoop/ \{\n)(\s*proxy_read_timeout\s+\d+s;\n)?(\s*proxy_connect_timeout\s+\d+s;\n)?(\s*proxy_send_timeout\s+\d+s;\n)?|$1        proxy_read_timeout 600s;\n        proxy_connect_timeout 20s;\n        proxy_send_timeout 600s;\n|s' "$NGINX_FILE"

systemctl daemon-reload
systemctl restart selvercoop
nginx -t
systemctl reload nginx

echo '---SERVICE---'
grep ExecStart "$SERVICE_FILE"
echo '---NGINX---'
awk '/location \/selverjacoop\//,/}/' "$NGINX_FILE"
echo '---HEALTH---'
systemctl is-active selvercoop
curl -sk -o /dev/null -w 'PUBLIC:%{http_code}\n' https://www.creatorsofcode.com/selverjacoop/
