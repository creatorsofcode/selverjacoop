from pathlib import Path
p = Path('/etc/nginx/sites-available/creatorsofcode.com')
s = p.read_text()
if 'location = /selverjacoop' in s:
    print('ALREADY_PRESENT')
else:
    block = """
    location = /selverjacoop {
        return 301 /selverjacoop/;
    }

    location /selverjacoop/ {
        proxy_pass http://127.0.0.1:5005/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
"""
    marker = 'location = /selvercoop {'
    i = s.find(marker)
    if i == -1:
        print('NO_MARKER')
        print(repr(s[1400:1800]))
    else:
        p.write_text(s[:i] + block + s[i:])
        print('UPDATED')
