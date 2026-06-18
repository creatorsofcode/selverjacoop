from pathlib import Path
import re

nginx = Path('/etc/nginx/sites-available/creatorsofcode.com')
s = nginx.read_text()

# Fix /selverjacoop/ block - add timeouts right after opening brace
old = "    location /selverjacoop/ {\n        proxy_pass http://127.0.0.1:5005/;"
new = "    location /selverjacoop/ {\n        proxy_read_timeout 300s;\n        proxy_connect_timeout 10s;\n        proxy_send_timeout 300s;\n        proxy_pass http://127.0.0.1:5005/;"

if 'proxy_read_timeout' in s and 'location /selverjacoop/' in s:
    # Check if timeout is already IN the selverjacoop block
    idx = s.find('location /selverjacoop/')
    block = s[idx:idx+400]
    if 'proxy_read_timeout' in block:
        print('ALREADY_HAS_TIMEOUT_IN_BLOCK')
    else:
        s = s.replace(old, new, 1)
        nginx.write_text(s)
        print('ADDED_TIMEOUT_TO_SELVERJACOOP_BLOCK')
elif old in s:
    s = s.replace(old, new, 1)
    nginx.write_text(s)
    print('ADDED_TIMEOUT_TO_SELVERJACOOP_BLOCK')
else:
    # Show what we found for debug
    idx = s.find('location /selverjacoop/')
    print('DEBUG:', repr(s[idx:idx+200]))
