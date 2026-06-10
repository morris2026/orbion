-- Orbion MVP 初始数据库迁移
-- 8张表 + 索引

-- 1. event_log — 不可变事件日志
CREATE TABLE event_log (
    event_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       VARCHAR(64) NOT NULL,
    event_type       VARCHAR(64) NOT NULL,
    participant_id   VARCHAR(64) NOT NULL,
    participant_type VARCHAR(8)  NOT NULL CHECK (participant_type IN ('human', 'agent')),
    participant_display_name VARCHAR(64) NOT NULL DEFAULT '',
    payload          JSONB       NOT NULL DEFAULT '{}',
    correlation_id   UUID        NOT NULL,
    causation_id     UUID        NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_event_log_project    ON event_log (project_id, created_at DESC);
CREATE INDEX idx_event_log_correlation ON event_log (correlation_id, created_at);
CREATE INDEX idx_event_log_type       ON event_log (project_id, event_type);

-- 2. users — 用户表
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username        VARCHAR(32) NOT NULL UNIQUE,
    password_hash   VARCHAR(128) NOT NULL,  -- bcrypt hash
    display_name    VARCHAR(64) NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'rejected')),  -- Admin审批注册
    is_admin        BOOLEAN NOT NULL DEFAULT FALSE,  -- 第一个用户自动成为管理员
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_status ON users (status) WHERE status = 'pending';  -- 管理员查询待审批用户

-- 3. projects — 项目表
CREATE TABLE projects (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(128) NOT NULL,
    description     TEXT         NULL,
    tenant_id       VARCHAR(64) NOT NULL DEFAULT 'default',
    default_thread_id UUID      NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT projects_name_unique UNIQUE (name)  -- 项目名全局唯一（DB兜底，service层前置检查返回409）
);

-- 4. project_members — 项目成员投影表
CREATE TABLE project_members (
    participant_id  VARCHAR(64) NOT NULL,
    project_id      UUID        NOT NULL REFERENCES projects(id),
    type            VARCHAR(8)  NOT NULL CHECK (type IN ('human', 'agent')),
    display_name    VARCHAR(64) NOT NULL,
    roles           BIGINT      NOT NULL DEFAULT 0,
    agent_type      VARCHAR(32) NULL,
    model_id        VARCHAR(64) NULL,
    status          VARCHAR(16) NULL DEFAULT 'idle',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (participant_id, project_id)
);

CREATE INDEX idx_project_members_project ON project_members (project_id, type);
CREATE INDEX idx_project_members_agent   ON project_members (project_id, agent_type) WHERE type = 'agent';

-- 5. threads — 讨论线程表
CREATE TABLE threads (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID        NOT NULL REFERENCES projects(id),
    title           VARCHAR(256) NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived', 'resolved')),
    type            VARCHAR(32) NOT NULL DEFAULT 'discussion',
    created_by      VARCHAR(64) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_threads_project ON threads (project_id, created_at DESC);

-- 线程标题同项目内唯一（不同项目可同名）
ALTER TABLE threads ADD CONSTRAINT threads_project_title_unique UNIQUE (project_id, title);

-- 6. thread_messages — 线程消息投影表
CREATE TABLE thread_messages (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id       UUID        NOT NULL REFERENCES threads(id),
    project_id      UUID        NOT NULL,
    participant_id  VARCHAR(64) NOT NULL,
    participant_type VARCHAR(8) NOT NULL CHECK (participant_type IN ('human', 'agent')),
    display_name    VARCHAR(64) NOT NULL,
    content         TEXT        NOT NULL,
    event_type      VARCHAR(64) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_thread_messages_thread ON thread_messages (thread_id, created_at);
CREATE INDEX idx_thread_messages_summary ON thread_messages (thread_id, event_type)
    WHERE event_type = 'DiscussionSummaryGenerated';

-- 7. execution_plans — 执行计划投影表
CREATE TABLE execution_plans (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID        NOT NULL,
    thread_id       UUID        NULL REFERENCES threads(id),
    correlation_id  UUID        NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed', 'approved', 'rejected', 'executing', 'completed')),
    proposed_by     VARCHAR(64) NOT NULL,
    approved_by     JSONB       NOT NULL DEFAULT '[]',
    tasks           JSONB       NOT NULL DEFAULT '[]',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_execution_plans_project  ON execution_plans (project_id, created_at DESC);
CREATE INDEX idx_execution_plans_thread   ON execution_plans (thread_id) WHERE thread_id IS NOT NULL;
CREATE INDEX idx_execution_plans_status   ON execution_plans (project_id, status) WHERE status = 'proposed';

-- 8. task_outputs — 任务产出投影表
CREATE TABLE task_outputs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID        NOT NULL,
    task_id         VARCHAR(64) NOT NULL,
    plan_id         UUID        NOT NULL REFERENCES execution_plans(id),
    output_type     VARCHAR(16) NOT NULL CHECK (output_type IN ('code', 'document')),
    content         TEXT        NOT NULL,
    diff            TEXT        NULL,
    file_paths      JSONB       NOT NULL DEFAULT '[]',
    status          VARCHAR(24) NOT NULL DEFAULT 'generated'
        CHECK (status IN ('generated', 'approved', 'revision_requested')),
    version         INT         NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_task_outputs_project ON task_outputs (project_id, plan_id);
CREATE INDEX idx_task_outputs_status  ON task_outputs (project_id, status);