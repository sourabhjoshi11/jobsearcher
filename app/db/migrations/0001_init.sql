-- ---------------------------------------------------------------------------
-- 0001_init.sql — initial schema for Job Alert Bot
-- Idempotent: uses IF NOT EXISTS so re-applying is safe.
-- ---------------------------------------------------------------------------

-- Extension for gen_random_uuid() (used if we ever need UUID PKs).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- users
-- One row per Telegram user. Skills and cities are arrays so the matching
-- engine can do ANY-overlap checks in SQL without a join table.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    user_id         BIGSERIAL PRIMARY KEY,
    telegram_id     BIGINT       NOT NULL UNIQUE,
    username        TEXT,
    first_name      TEXT,
    skills          TEXT[]       NOT NULL DEFAULT '{}',   -- e.g. {python, django}
    cities          TEXT[]       NOT NULL DEFAULT '{}',   -- e.g. {bangalore, pune}
    include_remote  BOOLEAN      NOT NULL DEFAULT TRUE,   -- match remote-global roles
    experience      TEXT         NOT NULL DEFAULT 'fresher',
                    -- one of: fresher, 0_2, 2_5, 5_10, 10_plus
    min_salary_lpa  NUMERIC(6,2),                         -- premium-only filter
    plan            TEXT         NOT NULL DEFAULT 'free', -- free | premium
    paused          BOOLEAN      NOT NULL DEFAULT FALSE,
    onboarded_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_users_plan       ON users (plan);
CREATE INDEX IF NOT EXISTS idx_users_skills_gin ON users USING GIN (skills);
CREATE INDEX IF NOT EXISTS idx_users_cities_gin ON users USING GIN (cities);

-- ---------------------------------------------------------------------------
-- jobs
-- Cached scraped listings. (source, url) is unique so re-scraping the same
-- job is a no-op. Skills is an array for fast GIN-indexed matching.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS jobs (
    job_id         BIGSERIAL PRIMARY KEY,
    source         TEXT         NOT NULL,  -- naukri | linkedin | wellfound | remoteok | ...
    external_id    TEXT,                   -- source's native id, if exposed
    url            TEXT         NOT NULL,
    title          TEXT         NOT NULL,
    company        TEXT,
    location       TEXT,                   -- raw location string from source
    is_remote      BOOLEAN      NOT NULL DEFAULT FALSE,
    skills         TEXT[]       NOT NULL DEFAULT '{}',
    experience_min NUMERIC(4,1),           -- min years of experience required
    experience_max NUMERIC(4,1),
    salary_min_lpa NUMERIC(6,2),
    salary_max_lpa NUMERIC(6,2),
    description    TEXT,
    posted_at      TIMESTAMPTZ,
    scraped_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    meta           JSONB        NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (source, url)
);

CREATE INDEX IF NOT EXISTS idx_jobs_source      ON jobs (source);
CREATE INDEX IF NOT EXISTS idx_jobs_posted_at   ON jobs (posted_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at  ON jobs (scraped_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_skills_gin  ON jobs USING GIN (skills);
CREATE INDEX IF NOT EXISTS idx_jobs_is_remote   ON jobs (is_remote);

-- ---------------------------------------------------------------------------
-- subscriptions
-- Premium subscription tracking. One user can have many rows over time;
-- the active one is whichever has end_date in the future and status='active'.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS subscriptions (
    sub_id             BIGSERIAL PRIMARY KEY,
    user_id            BIGINT       NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    plan               TEXT         NOT NULL,   -- premium_monthly | premium_quarterly
    status             TEXT         NOT NULL,   -- active | cancelled | expired
    start_date         TIMESTAMPTZ  NOT NULL,
    end_date           TIMESTAMPTZ  NOT NULL,
    razorpay_order_id  TEXT,
    razorpay_payment_id TEXT,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_subs_user   ON subscriptions (user_id);
CREATE INDEX IF NOT EXISTS idx_subs_active ON subscriptions (user_id, status, end_date);

-- ---------------------------------------------------------------------------
-- alerts_sent
-- Audit log of which user received which job. Unique constraint prevents
-- the same alert going out twice even if the matcher misbehaves.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts_sent (
    alert_id   BIGSERIAL PRIMARY KEY,
    user_id    BIGINT       NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    job_id     BIGINT       NOT NULL REFERENCES jobs(job_id)   ON DELETE CASCADE,
    sent_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    clicked    BOOLEAN      NOT NULL DEFAULT FALSE,
    UNIQUE (user_id, job_id)
);

CREATE INDEX IF NOT EXISTS idx_alerts_user    ON alerts_sent (user_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_sent_at ON alerts_sent (sent_at DESC);

-- ---------------------------------------------------------------------------
-- payments
-- Log of every Razorpay transaction (success or failure).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS payments (
    payment_id          BIGSERIAL PRIMARY KEY,
    user_id             BIGINT       NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    amount_paise        BIGINT       NOT NULL,          -- store in paise to avoid float drift
    currency            TEXT         NOT NULL DEFAULT 'INR',
    status              TEXT         NOT NULL,          -- created | captured | failed | refunded
    razorpay_order_id   TEXT         NOT NULL,
    razorpay_payment_id TEXT,
    razorpay_signature  TEXT,
    meta                JSONB        NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_payments_user  ON payments (user_id);
CREATE INDEX IF NOT EXISTS idx_payments_order ON payments (razorpay_order_id);
