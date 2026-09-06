-- GovSync PostgreSQL schema / safe migration
-- This file is intentionally idempotent: it adds missing columns/tables without deleting existing data.

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR(150),
    email VARCHAR(150) UNIQUE NOT NULL,
    password VARCHAR(255),
    password_hash VARCHAR(255),
    phone_number VARCHAR(20),
    preparation_type VARCHAR(50) NOT NULL DEFAULT 'Multiple Exams',
    role VARCHAR(20) NOT NULL DEFAULT 'user',
    preferences_completed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(150);
ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255);
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS preparation_type VARCHAR(50) NOT NULL DEFAULT 'Multiple Exams';
ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'user';
ALTER TABLE users ADD COLUMN IF NOT EXISTS preferences_completed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ALTER COLUMN password DROP NOT NULL;

-- Legacy password column may contain an old hash. New code writes password_hash.
UPDATE users
SET password_hash = password
WHERE password_hash IS NULL
  AND password IS NOT NULL
  AND (password LIKE 'pbkdf2:%' OR password LIKE 'scrypt:%');

CREATE TABLE IF NOT EXISTS user_exams (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    exam_code VARCHAR(50) NOT NULL,
    selected_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_user_exam UNIQUE (user_id, exam_code)
);

CREATE TABLE IF NOT EXISTS subjects (
    id SERIAL PRIMARY KEY,
    subject_code VARCHAR(30) UNIQUE NOT NULL,
    subject_name VARCHAR(100) NOT NULL
);

INSERT INTO subjects (subject_code, subject_name) VALUES
('REASONING', 'General Intelligence & Reasoning'),
('QUANT', 'Quantitative Aptitude'),
('ENGLISH', 'English Language'),
('AWARENESS', 'General Awareness')
ON CONFLICT (subject_code) DO NOTHING;

CREATE TABLE IF NOT EXISTS topics (
    id SERIAL PRIMARY KEY,
    subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    topic_name VARCHAR(100) NOT NULL,
    CONSTRAINT unique_subject_topic UNIQUE(subject_id, topic_name)
);

CREATE TABLE IF NOT EXISTS user_topic_progress (
    id SERIAL PRIMARY KEY,
    user_exam_id INTEGER NOT NULL REFERENCES user_exams(id) ON DELETE CASCADE,
    topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    completed_at TIMESTAMP NULL,
    CONSTRAINT unique_user_exam_topic UNIQUE(user_exam_id, topic_id)
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    theme VARCHAR(10) NOT NULL DEFAULT 'light',
    notify_syllabus_updates BOOLEAN NOT NULL DEFAULT TRUE,
    notify_exam_reminders BOOLEAN NOT NULL DEFAULT TRUE,
    notify_preparation_reminders BOOLEAN NOT NULL DEFAULT FALSE,
    notify_recommended_exams BOOLEAN NOT NULL DEFAULT TRUE,
    exam_category VARCHAR(50) NOT NULL DEFAULT 'all',
    language VARCHAR(20) NOT NULL DEFAULT 'english',
    update_frequency VARCHAR(20) NOT NULL DEFAULT 'important',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS syllabus_updates (
    id SERIAL PRIMARY KEY,
    exam_code VARCHAR(20),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    updated_section VARCHAR(150),
    change_type VARCHAR(100),
    posted_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Structured admin-managed syllabus entries. Existing topics remain untouched.
CREATE TABLE IF NOT EXISTS syllabus_entries (
    id SERIAL PRIMARY KEY,
    exam_code VARCHAR(50) NOT NULL,
    subject VARCHAR(150) NOT NULL,
    topic VARCHAR(200) NOT NULL,
    description TEXT,
    unit_module VARCHAR(100),
    priority VARCHAR(30) NOT NULL DEFAULT 'Medium',
    status VARCHAR(30) NOT NULL DEFAULT 'Active',
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_syllabus_entries_exam ON syllabus_entries(exam_code);

CREATE TABLE IF NOT EXISTS password_reset_otps (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    otp_hash VARCHAR(64) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    verified_at TIMESTAMPTZ NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    used BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_password_reset_otps_user ON password_reset_otps(user_id);
CREATE INDEX IF NOT EXISTS idx_password_reset_otps_expiry ON password_reset_otps(expires_at);

CREATE TABLE IF NOT EXISTS notifications (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    sender_admin_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    exam_code VARCHAR(50),
    target_type VARCHAR(30) NOT NULL DEFAULT 'all',
    priority VARCHAR(20) NOT NULL DEFAULT 'normal',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS notification_recipients (
    id SERIAL PRIMARY KEY,
    notification_id INTEGER NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMPTZ NULL,
    UNIQUE(notification_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_notification_recipients_user ON notification_recipients(user_id, is_read);

-- Common topics used by the existing user syllabus UI
INSERT INTO topics (subject_id, topic_name) SELECT id, v.topic FROM subjects s JOIN (VALUES
('REASONING','Analogy'),('REASONING','Classification'),('REASONING','Coding-Decoding'),('REASONING','Blood Relations'),
('QUANT','Number System'),('QUANT','Percentage'),('QUANT','Profit & Loss'),('QUANT','Time & Work'),
('ENGLISH','Reading Comprehension'),('ENGLISH','Vocabulary'),('ENGLISH','Grammar'),('ENGLISH','Sentence Correction'),
('AWARENESS','Current Affairs'),('AWARENESS','Indian History'),('AWARENESS','Geography'),('AWARENESS','Indian Polity')
) AS v(code, topic) ON s.subject_code=v.code ON CONFLICT DO NOTHING;
