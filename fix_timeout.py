import subprocess, re
from pathlib import Path

# 1. Fix systemd service - increase timeout and workers
svc = Path('/etc/systemd/system/selvercoop.service')
s = svc.read_text()
s = s.replace(
    '--workers 2 --bind 127.0.0.1:5005 app:app',
    '--workers 4 --timeout 120 --bind 127.0.0.1:5005 app:app'
)
svc.write_text(s)
print('SERVICE UPDATED:', s[s.find('ExecStart'):s.find('ExecStart')+120])

# 2. Fix nginx - add proxy_read_timeout to /selverjacoop/ block
nginx = Path('/etc/nginx/sites-available/creatorsofcode.com')
n = nginx.read_text()
if 'proxy_read_timeout' not in n:
    n = n.replace(
        'location /selverjacoop/ {',
        'location /selverjacoop/ {\n        proxy_read_timeout 120s;\n        proxy_connect_timeout 10s;\n        proxy_send_timeout 120s;'
    )
    nginx.write_text(n)
    print('NGINX TIMEOUT ADDED')
else:
    print('NGINX TIMEOUT ALREADY PRESENT')

# 3. Reload
subprocess.run(['systemctl', 'daemon-reload'], check=True)
subprocess.run(['systemctl', 'restart', 'selvercoop'], check=True)
subprocess.run(['nginx', '-t'], check=True)
subprocess.run(['systemctl', 'reload', 'nginx'], check=True)
print('ALL RELOADED')
