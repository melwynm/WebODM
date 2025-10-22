# syntax=docker/dockerfile:1
FROM postgis/postgis:14-3.4

# Ensure UTF-8 locale matches previous image expectations
ENV LANG en_US.utf8

# Seed the database with the same initialization script used previously
COPY init.sql /docker-entrypoint-initdb.d/init-db.sql
