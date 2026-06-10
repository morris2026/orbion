#!/bin/bash
# Orbion dev PG 初始化：创建测试数据库 + 在所有数据库上执行 migration
# docker-entrypoint-initdb.d 只在 PG 首次初始化时执行
set -e

echo "==> 在默认数据库 $POSTGRES_DB 上执行 migration..."
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /migrations/001_initial.sql

echo "==> 创建测试数据库 orbion_test 和 orbion_e2e..."
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -c "CREATE DATABASE orbion_test;"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -c "CREATE DATABASE orbion_e2e;"

echo "==> 在 orbion_test 上执行 migration..."
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d orbion_test -f /migrations/001_initial.sql

echo "==> 在 orbion_e2e 上执行 migration..."
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d orbion_e2e -f /migrations/001_initial.sql

echo "==> PG 初始化完成"
