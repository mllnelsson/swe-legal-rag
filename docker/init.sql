CREATE EXTENSION IF NOT EXISTS vector;

-- The integration suite runs against its own database so it can truncate freely
-- without touching crawled data. Only runs on a first initialisation of the
-- pgdata volume; on an existing one, create it by hand:
--   docker compose exec db createdb -U postgres -O postgres overklagan_test
CREATE DATABASE overklagan_test OWNER postgres;
