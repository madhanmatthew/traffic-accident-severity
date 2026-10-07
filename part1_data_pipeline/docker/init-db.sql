-- Runs once (inside $POSTGRES_DB) when the PostGIS container is first created.
CREATE DATABASE airflow;
CREATE EXTENSION IF NOT EXISTS postgis;
