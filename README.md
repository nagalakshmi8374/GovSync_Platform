# GovSync Platform

GovSync is a government-exam syllabus synchronization and preparation platform. The existing SyllabusSync interface is preserved while the application is connected to PostgreSQL-backed authentication, persistent preferences, profile management, admin syllabus management, and database-backed notifications.

## Technology stack

- Python + Flask
- PostgreSQL
- psycopg 3
- Jinja2 HTML templates
- Existing HTML/CSS/JavaScript UI
- Werkzeug password hashing
- SMTP email for password-reset OTPs

This project is intentionally **not** migrated to React, Node.js, Django, MongoDB, Firebase, or another stack.

## Project structure

```text
GovSync_Platform-main/
├── app.py
├── config/
│   ├── config.py
│   └── database.py
├── routes/
│   ├── auth_routes.py
│   ├── dashboard_routes.py
│   ├── preference_routes.py
│   ├── profile_routes.py
│   ├── notification_routes.py
│   └── admin_routes.py
├── services/
│   ├── email_service.py
│   └── otp_service.py
├── utils/
│   ├── auth.py
│   └── password.py
├── models/
├── database/
│   ├── govsync.sql
│   └── schema.sql
├── templates/
├── static/
├── requirements.txt
├── .env.example
└── README.md
```

### What each layer does

- `app.py`: creates Flask, registers route modules, and can apply the safe database schema.
- `routes/`: HTTP pages and APIs, grouped by responsibility.
- `services/`: reusable email and OTP logic.
- `utils/`: authentication decorators and password helpers.
- `config/`: environment-variable and PostgreSQL connection configuration.
- `database/schema.sql`: idempotent schema/migration script. It uses `IF NOT EXISTS`/`ADD COLUMN IF NOT EXISTS` and does not delete existing rows.
- `templates/` and `static/`: the existing GovSync UI plus the three password-reset screens.

## Requirements

Install:

1. Python 3.10+
2. PostgreSQL 14+ (16 recommended)
3. A working SMTP account for real password-reset emails

## Installation

### 1. Clone / enter the project

```bash
git clone <your-repository-url>
cd GovSync_Platform-main
```

### 2. Create a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows:

```powershell
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

## Database setup

Create the PostgreSQL database first:

```bash
sudo -u postgres psql
```

Inside `psql`:

```sql
CREATE DATABASE govsync;
\q
```

Copy the environment file:

```bash
cp .env.example .env
```

Edit `.env` and set the real PostgreSQL password:

```text
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/govsync
```

The application automatically applies `database/schema.sql` when started with `AUTO_INIT_DB=true` (the default).

You can also apply it manually:

```bash
psql "postgresql://postgres:YOUR_PASSWORD@localhost:5432/govsync" -f database/schema.sql
```

**Existing data is preserved.** The schema adds the missing columns/tables instead of dropping or recreating the database.

## Environment variables

| Variable | Purpose |
|---|---|
| `SECRET_KEY` | Signs Flask sessions. Use a long random value. |
| `DATABASE_URL` | PostgreSQL connection string. |
| `FRONTEND_ORIGIN` | Browser/frontend origin if API separation is introduced later. |
| `SMTP_HOST` | SMTP server hostname. |
| `SMTP_PORT` | Usually `587` for STARTTLS or `465` for SSL. |
| `SMTP_USERNAME` | SMTP account. |
| `SMTP_PASSWORD` | SMTP password/app password. |
| `SMTP_FROM` | From address shown in OTP emails. |
| `OTP_EXPIRY_MINUTES` | OTP lifetime; default is 10 minutes. |
| `ADMIN_EMAILS` | Optional bootstrap list of admin emails. |

Never commit `.env`.

## Email / OTP setup

For Gmail, use an **App Password** rather than your normal account password when SMTP authentication requires it.

Example:

```text
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_gmail_app_password
SMTP_FROM=GovSync <your_email@gmail.com>
```

The password-reset code is generated with a secure random generator and only its SHA-256 hash is stored in PostgreSQL.

The email contains:

- six-digit OTP
- expiration time
- security warning
- GovSync branding

## Run the application

```bash
source .venv/bin/activate
python app.py
```

The server runs at:

```text
http://127.0.0.1:5000
```

For production, use a production WSGI server and set `FLASK_DEBUG=false`.

## User flow

### New user

```text
Register
   ↓
Login
   ↓
Preferences
   ↓
Dashboard
```

When the preference form is submitted, `users.preferences_completed` becomes `TRUE`.

### Returning user

```text
Login
   ↓
Dashboard
```

The preference page is no longer shown because the completion state is read from PostgreSQL.

This works after logout, refresh, browser restart, and another device because it is not based on localStorage.

## Forgot password flow

```text
Login
 ↓
Forgot Password
 ↓
Enter registered email
 ↓
Generate OTP
 ↓
Store OTP hash + expiry
 ↓
Send OTP by SMTP
 ↓
Verify OTP
 ↓
New password + confirmation
 ↓
Hash password
 ↓
Update users.password_hash
 ↓
Invalidate OTP
 ↓
Login with new password
```

The OTP has a five-attempt limit and expires after the configured period.

## Change password

From the existing Settings/Profile page:

```text
Current password
       ↓
Verify against stored hash
       ↓
New password
       ↓
Confirmation
       ↓
Generate new hash
       ↓
Update database
```

Users cannot provide another user's ID to change that user's password. The backend always uses the authenticated session user ID.

## Admin access

A user needs `role='admin'`, or their email can be listed in `ADMIN_EMAILS` for bootstrap access.

To promote an existing account:

```sql
UPDATE users
SET role = 'admin'
WHERE email = 'admin@example.com';
```

Then log out and log in again.

Admin-only URLs/API endpoints are protected on the backend, so changing the browser URL does not grant admin access.

## Admin syllabus management

Open:

```text
/admin
```

The existing admin UI now uses database-backed operations for:

- Add syllabus
- View syllabus
- Edit syllabus
- Delete syllabus
- Exam-wise entries
- Priority
- Status
- Unit/module
- Description

The new `syllabus_entries` table is separate from the existing common-topic tables so existing user progress is not destroyed.

## Notifications

Admin flow:

```text
Admin Dashboard
 ↓
Create notification
 ↓
Choose All Users / Exam Users / Specific Users
 ↓
Choose priority
 ↓
Save notification
 ↓
Create recipient records
```

User flow:

```text
Notifications page
 ↓
Read notification
 ↓
notification_recipients.is_read = TRUE
```

Each user gets an independent read/unread state. Notifications are not stored only in browser state.

## Database changes

The safe schema adds/maintains:

### `users`

- `full_name`
- `password_hash`
- `phone_number`
- `preparation_type`
- `role`
- `preferences_completed`

The old `password` column is retained for compatibility but new passwords are written only to `password_hash`.

### `password_reset_otps`

Stores:

- user ID
- hashed OTP
- expiry
- verification timestamp
- attempt count
- used flag
- creation timestamp

### `syllabus_entries`

Stores structured admin syllabus records:

- exam
- subject
- topic
- description
- unit/module
- priority
- status
- creator
- timestamps

### `notifications`

Stores the notification message and its target metadata.

### `notification_recipients`

Connects each notification to its recipients and stores each user's read/unread state.

## Security notes

- Passwords are hashed with Werkzeug.
- Password-reset OTPs are not stored as plain text.
- OTP attempts are limited.
- OTP records expire.
- Admin routes use backend authorization.
- User profile/password APIs use the authenticated session user ID.
- SQL queries use parameterized values.
- Secrets belong in `.env`.
- Database errors are logged server-side rather than exposed to users.

## Troubleshooting

### `DATABASE_URL is not configured`

```bash
cp .env.example .env
```

Then set `DATABASE_URL`.

### PostgreSQL connection refused

Check PostgreSQL:

```bash
sudo systemctl status postgresql
```

Start it if necessary:

```bash
sudo systemctl start postgresql
```

### `password authentication failed`

Verify the PostgreSQL username/password in `.env`.

### OTP email is not sent

Check all of:

```text
SMTP_HOST
SMTP_PORT
SMTP_USERNAME
SMTP_PASSWORD
SMTP_FROM
```

For Gmail, use an App Password.

### Existing old database

Start the app once with:

```bash
AUTO_INIT_DB=true python app.py
```

The schema is designed to add missing structures without deleting existing user data.

### Admin page says access denied

Promote the account:

```sql
UPDATE users SET role='admin' WHERE email='your-admin-email@example.com';
```

Log out and log in again.

## Understanding the code

Start here:

1. `app.py` — see how Flask and route modules are connected.
2. `routes/auth_routes.py` — registration, login, forgot password, OTP and reset.
3. `routes/preference_routes.py` — persistent preference completion.
4. `routes/profile_routes.py` — profile and change-password APIs.
5. `routes/admin_routes.py` — admin authorization, syllabus CRUD and notification creation.
6. `routes/notification_routes.py` — user's notifications and read state.
7. `routes/dashboard_routes.py` — existing dashboard, syllabus, progress and updates.
8. `services/otp_service.py` — OTP generation/hashing.
9. `services/email_service.py` — SMTP delivery.
10. `database/schema.sql` — all database structures.

This organization intentionally keeps one responsibility in one understandable module while preserving the original GovSync templates and CSS.
