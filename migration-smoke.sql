\set ON_ERROR_STOP on
BEGIN;
SET LOCAL search_path TO pg_temp;
CREATE TEMP TABLE groups (id int, models_list_config jsonb);
INSERT INTO groups VALUES (1, '{"enabled":true,"models":["legacy"]}');
\i /tmp/buaga-v023-236.sql
\i /tmp/buaga-v023-236.sql
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM groups WHERE model_allowlist->'models' = '["legacy"]') THEN
    RAISE EXCEPTION 'Legacy rename or replay failed';
  END IF;
END $$;
DROP TABLE pg_temp.groups;
CREATE TEMP TABLE groups (id int, models_list_config jsonb, model_allowlist jsonb);
INSERT INTO groups VALUES
  (1, '{"models":["legacy"]}', '{}'),
  (2, '{"models":["legacy"]}', '{"models":["current"]}');
\i /tmp/buaga-v023-236.sql
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM groups WHERE id=1 AND model_allowlist->'models'='["legacy"]')
    OR NOT EXISTS (SELECT FROM groups WHERE id=2 AND model_allowlist->'models'='["current"]') THEN
    RAISE EXCEPTION 'Backfill preservation failed';
  END IF;
END $$;
DROP TABLE pg_temp.groups;
CREATE TEMP TABLE groups (id int);
INSERT INTO groups VALUES (1);
\i /tmp/buaga-v023-236.sql
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM groups WHERE model_allowlist='{}') THEN
    RAISE EXCEPTION 'Missing column repair failed';
  END IF;
END $$;
ROLLBACK;
SELECT 'migration smoke tests passed; transaction rolled back';
