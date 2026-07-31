#!/bin/sh

#!/usr/bin/env bash
set -o errexit

echo "📦 Installing dependencies..."
pip install -r requirements.txt

echo "📁 Collecting static files..."
python manage.py collectstatic --no-input

echo "🔄 Creating database tables..."
python manage.py makemigrations
python manage.py migrate --no-input

echo "✅ Build completed successfully!"


DATE=$(date +%Y-%m-%d_%H-%M-%S)
BACKUP_FILE="/backups/AIBusinessAssistant$DATE.sql"

echo "Creating backup..."

mysqldump \
  --no-tablespaces \
  -h db \
  -u"$DB_USER" \
  -p"$DB_PASSWORD" \
  "$DB_NAME" \
  > "$BACKUP_FILE"

echo "Backup saved to $BACKUP_FILE"

# Delete backups older than 7 days
find /backups -type f -mtime +7 -delete
