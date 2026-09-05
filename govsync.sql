

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(150) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_name = 'users';

SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'users'
ORDER BY ordinal_position;
select * from users;


CREATE TABLE user_exams (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    exam_code VARCHAR(50) NOT NULL,
    selected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    CONSTRAINT unique_user_exam
        UNIQUE (user_id, exam_code)
);
select *from user_exams;
SELECT id, full_name, email
FROM users;
SELECT
    user_id,
    exam_code
FROM user_exams
ORDER BY user_id, id;
DELETE FROM user_exams
WHERE user_id = 1
OR exam_code = 'DEFENCE';

CREATE TABLE IF NOT EXISTS subjects (
    id SERIAL PRIMARY KEY,
    subject_code VARCHAR(30) UNIQUE NOT NULL,
    subject_name VARCHAR(100) NOT NULL
);

INSERT INTO subjects (subject_code, subject_name)
VALUES
('REASONING', 'General Intelligence & Reasoning'),
('QUANT', 'Quantitative Aptitude'),
('ENGLISH', 'English Language'),
('AWARENESS', 'General Awareness')
ON CONFLICT (subject_code) DO NOTHING;
SELECT * FROM subjects;
SELECT subject_code, subject_name
FROM subjects;

CREATE TABLE IF NOT EXISTS topics (
    id SERIAL PRIMARY KEY,

    subject_id INTEGER NOT NULL,

    topic_name VARCHAR(100) NOT NULL,

    FOREIGN KEY (subject_id)
        REFERENCES subjects(id)
        ON DELETE CASCADE,

    UNIQUE(subject_id, topic_name)
);
-- REASONING

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Analogy'
FROM subjects
WHERE subject_code = 'REASONING'
ON CONFLICT DO NOTHING;

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Classification'
FROM subjects
WHERE subject_code = 'REASONING'
ON CONFLICT DO NOTHING;

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Coding-Decoding'
FROM subjects
WHERE subject_code = 'REASONING'
ON CONFLICT DO NOTHING;

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Blood Relations'
FROM subjects
WHERE subject_code = 'REASONING'
ON CONFLICT DO NOTHING;


-- QUANTITATIVE APTITUDE

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Number System'
FROM subjects
WHERE subject_code = 'QUANT'
ON CONFLICT DO NOTHING;

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Percentage'
FROM subjects
WHERE subject_code = 'QUANT'
ON CONFLICT DO NOTHING;

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Profit & Loss'
FROM subjects
WHERE subject_code = 'QUANT'
ON CONFLICT DO NOTHING;

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Time & Work'
FROM subjects
WHERE subject_code = 'QUANT'
ON CONFLICT DO NOTHING;


-- ENGLISH

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Reading Comprehension'
FROM subjects
WHERE subject_code = 'ENGLISH'
ON CONFLICT DO NOTHING;

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Vocabulary'
FROM subjects
WHERE subject_code = 'ENGLISH'
ON CONFLICT DO NOTHING;

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Grammar'
FROM subjects
WHERE subject_code = 'ENGLISH'
ON CONFLICT DO NOTHING;

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Sentence Correction'
FROM subjects
WHERE subject_code = 'ENGLISH'
ON CONFLICT DO NOTHING;


-- GENERAL AWARENESS

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Current Affairs'
FROM subjects
WHERE subject_code = 'AWARENESS'
ON CONFLICT DO NOTHING;

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Indian History'
FROM subjects
WHERE subject_code = 'AWARENESS'
ON CONFLICT DO NOTHING;

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Geography'
FROM subjects
WHERE subject_code = 'AWARENESS'
ON CONFLICT DO NOTHING;

INSERT INTO topics (subject_id, topic_name)
SELECT id, 'Indian Polity'
FROM subjects
WHERE subject_code = 'AWARENESS'
ON CONFLICT DO NOTHING;
SELECT * FROM topics;


CREATE TABLE IF NOT EXISTS user_topic_progress (
    id SERIAL PRIMARY KEY,

    user_exam_id INTEGER NOT NULL,

    topic_id INTEGER NOT NULL,

    completed BOOLEAN NOT NULL DEFAULT FALSE,

    completed_at TIMESTAMP NULL,

    FOREIGN KEY (user_exam_id)
        REFERENCES user_exams(id)
        ON DELETE CASCADE,

    FOREIGN KEY (topic_id)
        REFERENCES topics(id)
        ON DELETE CASCADE,

    UNIQUE(user_exam_id, topic_id)
);
SELECT * FROM user_topic_progress;




-- Extend users table with profile fields used by the edit panels
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS preparation_type VARCHAR(50) NOT NULL DEFAULT 'Multiple Exams';

-- Per-user settings: theme, notification toggles, preferences
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
select * from user_settings;




CREATE TABLE syllabus_updates (
    id SERIAL PRIMARY KEY,
    exam_code VARCHAR(20),          -- NULL = general update shown to everyone
    title VARCHAR(255) NOT NULL,
    description TEXT,
    updated_section VARCHAR(150),
    change_type VARCHAR(100),
    posted_by INTEGER REFERENCES users(id),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
select * from syllabus_updates