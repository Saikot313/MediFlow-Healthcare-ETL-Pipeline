
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
    CREATE ROLE warehouse LOGIN PASSWORD 'warehouse';
    CREATE DATABASE warehouse OWNER warehouse;

    -- read-only role for dashboards: SELECT on mart/dwh only (grants are applied by sql/04)
    CREATE ROLE bi_reader LOGIN PASSWORD 'bi_reader';

    CREATE ROLE metabase LOGIN PASSWORD 'metabase';
    CREATE DATABASE metabase OWNER metabase;
EOSQL
