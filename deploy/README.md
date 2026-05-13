# Deploy — Hetzner VPS

## Systemd timer: fetch_results co 5 minut

```bash
sudo cp deploy/fetch-results.service /etc/systemd/system/
sudo cp deploy/fetch-results.timer   /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now fetch-results.timer

# Sprawdź status
sudo systemctl status fetch-results.timer
sudo journalctl -u fetch-results.service -n 50
```

## Ręczne odpalenie (test)

```bash
cd /var/www/mundial_typer
source venv/bin/activate
python manage.py fetch_results
```
