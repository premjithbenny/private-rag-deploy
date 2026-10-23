# Ninth Dimension branded portal

Files to deploy into `/opt/private-rag-deploy/portal/`:
- `index.html`
- `ninth-dimension-header.png` — supplied horizontal header logo
- `ninth-dimension-logo.png` — supplied standalone logo
- `favicon.png` and `favicon.ico` — browser favicon

The existing Nginx Compose service can keep its read-only mount:
`../portal:/usr/share/nginx/html:ro`

After copying files, verify:
`curl -I http://127.0.0.1/`
