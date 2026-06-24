#!/bin/bash
# Orbion dev PG 初始化：创建测试数据库 + 在所有数据库上执行全部 migration
# docker-entrypoint-initdb.d 只在 PG 首次初始化时执行
set -e

apply_migrations() {
    local db="$1"
    for sql_file in /migrations/*.sql; do
        echo "==> 在 $db 上执行 $sql_file..."
        psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$db" -f "$sql_file"
    done
}

echo "==> 在默认数据库 $POSTGRES_DB 上执行 migration..."
apply_migrations "$POSTGRES_DB"

echo "==> 创建测试数据库 orbion_test 和 orbion_e2e..."
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -c "CREATE DATABASE orbion_test;"
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -c "CREATE DATABASE orbion_e2e;"

echo "==> 在 orbion_test 上执行 migration..."
apply_migrations "orbion_test"

echo "==> 在 orbion_e2e 上执行 migration..."
apply_migrations "orbion_e2e"

echo "==> PG 初始化完成"
