# Chama System Setup Guide

## 1. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
venv\Scripts\activate           # Windows
```

## 2. Install dependencies
```bash
pip install -r requirements.txt
```

## 3. Configure database
Edit `.env` with your MySQL credentials:
```
DB_NAME=chama_db
DB_USER=root
DB_PASSWORD=yourpassword
DB_HOST=localhost
DB_PORT=3306
```

Create the MySQL database:
```sql
CREATE DATABASE chama_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

## 4. Run migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

## 5. Create superuser
```bash
python manage.py createsuperuser
```

## 6. Run the server
```bash
python manage.py runserver
```

## 7. Access
- App: http://127.0.0.1:8000/
- Admin: http://127.0.0.1:8000/admin/
