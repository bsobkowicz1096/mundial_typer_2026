# Deploy — Hetzner VPS (Ubuntu 24.04)

## 1. Serwer — pierwsza instalacja

```bash
apt update && apt install -y python3-venv python3-pip caddy postgresql git

# Utwórz użytkownika
useradd -m -d /var/www/mundial_typer www-data || true

# Sklonuj repo
git clone https://github.com/TWOJ_USER/mundial_typer_2026 /var/www/mundial_typer
cd /var/www/mundial_typer

# Virtualenv + zależności
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## 2. Baza danych (PostgreSQL)

```bash
sudo -u postgres psql <<EOF
CREATE USER mundial_user WITH PASSWORD 'ZMIEN_HASLO';
CREATE DATABASE mundial_typer OWNER mundial_user;
EOF
```

## 3. Plik .env

```bash
cp .env.example .env
nano .env
# Uzupełnij:
#   SECRET_KEY=...          (wygeneruj: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
#   DATABASE_URL=postgresql://mundial_user:HASLO@localhost/mundial_typer
#   FOOTBALL_DATA_API_KEY=...
#   DEBUG=False
#   ALLOWED_HOSTS=typer.mundial2026.pl,TWOJ_IP
```

## 4. Migracje i dane startowe

```bash
source venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
python manage.py create_special_questions   # jeśli istnieje
```

## 5. Systemd — Gunicorn

```bash
cp deploy/gunicorn.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now gunicorn
```

## 6. Caddy

```bash
cp deploy/Caddyfile /etc/caddy/Caddyfile
# Zmień domenę w Caddyfile jeśli inna
systemctl reload caddy
```

## 7. Systemd — fetch_results (co 5 min)

```bash
cp deploy/fetch-results.service /etc/systemd/system/
cp deploy/fetch-results.timer   /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now fetch-results.timer
```

## Przydatne komendy

```bash
# Logi Gunicorn
journalctl -u gunicorn -f

# Logi fetch_results
journalctl -u fetch-results.service -n 50

# Ręczne pobranie wyników
cd /var/www/mundial_typer && source venv/bin/activate
python manage.py fetch_results

# Symulacja MC
python manage.py run_simulation

# Aktualizacja kodu
git pull
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
systemctl restart gunicorn
```
