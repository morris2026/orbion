-- Orbion MVP 初始数据库迁移
-- 8张表 + 索引

-- 1. event_log — 不可变事件日志
CREATE TABLE event_log (
    event_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id       VARCHAR(64) NOT NULL,
    event_type       VARCHAR(64) NOT NULL,
    participant_id   VARCHAR(64) NOT NULL,
    participant_type VARCHAR(8)  NOT NULL CHECK (participant_type IN ('human', 'agent', 'system')),
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
    participant_type VARCHAR(8) NOT NULL CHECK (participant_type IN ('human', 'agent', 'system')),
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

-- 9. worktrees — git worktree 生命周期元数据
-- 详见 docs/specs/1.10-mvp-git-worktree-model.md §11
CREATE TABLE worktrees (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id           UUID        NOT NULL REFERENCES projects(id),
    repo_name            VARCHAR(128) NOT NULL,
    worktree_type        VARCHAR(16) NOT NULL CHECK (worktree_type IN ('main', 'task')),
    branch_name          VARCHAR(256) NOT NULL,
    path                 VARCHAR(1024) NOT NULL,  -- worktree 在文件系统的绝对路径
    status               VARCHAR(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'conflicting', 'archived')),
    created_by           UUID        NOT NULL,    -- 创建者 user_id（task 类型为系统时存系统占位 UUID）
    task_id              UUID        NULL,        -- task 类型关联的任务 ID；main 类型为 NULL
    conflict_regen_count INTEGER     NOT NULL DEFAULT 0,  -- 合并冲突重生成次数（§8.1）。MVP 暂存于 worktrees 表，agent-runtime 引入 tasks 表后迁移到 tasks.conflict_regen_count
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_worktrees_project_type ON worktrees (project_id, worktree_type);
CREATE INDEX idx_worktrees_task         ON worktrees (task_id) WHERE task_id IS NOT NULL;

-- 活跃 worktree 唯一约束：DB 层兜底防并发竞态
-- 同项目同分支同时只能有一个非 archived 的 worktree；archived 记录保留多条用于审计
CREATE UNIQUE INDEX uq_worktrees_active_branch
    ON worktrees (project_id, branch_name)
    WHERE status != 'archived';
CREATE UNIQUE INDEX uq_worktrees_active_task
    ON worktrees (task_id)
    WHERE task_id IS NOT NULL AND status != 'archived';
-- Orbion Agent Runtime 重构 迁移脚本
-- 新增 8 张表 + event_log 加 payload_ref_url 字段
-- 对应实施计划 1.11-mvp-agent-runtime-refactor-impl-plan.md 步骤 1

-- 0. event_log 加 payload_ref_url 字段（L2 对象存储引用，AR-1.7）
ALTER TABLE event_log ADD COLUMN payload_ref_url VARCHAR NULL;
COMMENT ON COLUMN event_log.payload_ref_url IS 'L2 对象存储引用，>4KB payload 写入对象存储后指向 s3://orbion-events/{event_id}/{field}';

-- 1. user_models — 用户接入的模型实例（AR-1.1）
CREATE TABLE user_models (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model_id        VARCHAR(64) NOT NULL,  -- 用户自定义友好名（如"我的 GLM-4"）
    provider        VARCHAR(32) NOT NULL CHECK (provider IN ('openai', 'anthropic', 'azure_openai', 'openai_compat')),
    model_name      VARCHAR(128) NOT NULL,  -- 供方原始名（如 gpt-4o, claude-sonnet-4-6）
    base_url        VARCHAR(256) NOT NULL,
    api_key_enc     BYTEA NOT NULL,  -- AES-GCM: nonce(12B) || ciphertext || tag(16B)
    api_key_hash    VARCHAR(64) NOT NULL,  -- SHA-256 hash，用于"是否变更"判断
    extra_config    JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT user_models_user_model_unique UNIQUE (user_id, model_id)
);

CREATE INDEX idx_user_models_user ON user_models (user_id);

-- 2. artifacts — 产出物元数据（AR-1.1, AR-1.2）
CREATE TABLE artifacts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type                VARCHAR(32) NOT NULL CHECK (type IN ('requirement', 'system', 'subsystem', 'module')),
    owner_user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status              VARCHAR(32) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'proposed', 'approved', 'rejected')),
    version             INTEGER NOT NULL DEFAULT 1,
    based_on_artifacts  JSONB NOT NULL DEFAULT '[]',  -- [{"artifact_id": "...", "version": N}]
    content_ref         VARCHAR(512) NOT NULL,  -- git 文件路径
    produced_by_task    UUID NULL,  -- FK 在 tasks 表创建后用 ALTER TABLE 添加（见下文）
    generated_by_model  VARCHAR(64) NULL,
    status_changed_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status_changed_by   UUID NULL,
    last_reminded_at    TIMESTAMPTZ NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_artifacts_project_type_status ON artifacts (project_id, type, status);
CREATE INDEX idx_artifacts_owner ON artifacts (owner_user_id);
CREATE INDEX idx_artifacts_produced_by_task ON artifacts (produced_by_task) WHERE produced_by_task IS NOT NULL;
CREATE INDEX idx_artifacts_based_on_gin ON artifacts USING GIN (based_on_artifacts);

-- 3. tasks — 任务工作单元（AR-1.1）
CREATE TABLE tasks (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id              UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    type                    VARCHAR(16) NOT NULL CHECK (type IN ('analysis', 'design', 'development')),
    status                  VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'paused', 'completed', 'timeout', 'cancelled')),
    owner_user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    instruction             TEXT NOT NULL,
    based_on_artifacts      JSONB NOT NULL DEFAULT '[]',
    based_on_tasks          JSONB NOT NULL DEFAULT '[]',
    output_artifact_id      UUID NULL,
    worktree_id             UUID NULL,  -- FK 在下方用 ALTER TABLE 添加（worktrees 表已存在于 001）
    agent_type              VARCHAR(32) NOT NULL,
    priority                INTEGER NULL,
    due_date                TIMESTAMPTZ NULL,
    revision_count          INTEGER NOT NULL DEFAULT 0,
    conflict_regen_count    INTEGER NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at              TIMESTAMPTZ NULL,
    completed_at            TIMESTAMPTZ NULL,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tasks_project_status_priority ON tasks (project_id, status, priority);
CREATE INDEX idx_tasks_owner ON tasks (owner_user_id);
CREATE INDEX idx_tasks_based_on_artifacts ON tasks (based_on_artifacts);
CREATE INDEX idx_tasks_based_on_tasks_gin ON tasks USING GIN (based_on_tasks);

-- 4. agent_runs — 执行记录（AR-1.1, AR-1.3, AR-1.4）
CREATE TABLE agent_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id      UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    run_kind        VARCHAR(16) NOT NULL CHECK (run_kind IN ('dispatch', 'chat', 'critic', 'lightweight')),
    agent_type      VARCHAR(32) NOT NULL,
    event_id        UUID NULL,
    task_id         UUID NULL,
    artifact_id     UUID NULL,
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model_id        VARCHAR(64) NOT NULL,
    status          VARCHAR(16) NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'completed', 'failed', 'cancelled', 'interrupted')),
    cancel_reason   VARCHAR(32) NULL
        CHECK (cancel_reason IS NULL OR cancel_reason IN ('user_cancel', 'timeout', 'system_shutdown', 'crash_recovery')),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at        TIMESTAMPTZ NULL,
    token_total     INTEGER NOT NULL DEFAULT 0,
    error_message   TEXT NULL,
    trace_id        VARCHAR(64) NULL
);

CREATE INDEX idx_agent_runs_project_status_started ON agent_runs (project_id, status, started_at);
CREATE INDEX idx_agent_runs_user_started ON agent_runs (user_id, started_at);
CREATE INDEX idx_agent_runs_task_status ON agent_runs (task_id, status) WHERE task_id IS NOT NULL;
-- 幂等键：同一事件 + 同一 agent 只能创建一个 run
CREATE UNIQUE INDEX agent_runs_event_agent_unique ON agent_runs (event_id, agent_type) WHERE event_id IS NOT NULL;
-- 同 task 串行化：同 task 只能有一个 running
-- NULL task_id 不受约束（chat/lightweight run 无 task，可并发运行）
CREATE UNIQUE INDEX agent_runs_task_running_idx ON agent_runs (task_id) WHERE status = 'running';

-- 补充 FK 约束（tasks 表已创建，artifacts.produced_by_task 和 tasks.worktree_id 后置添加）
ALTER TABLE artifacts ADD CONSTRAINT artifacts_produced_by_task_fk
    FOREIGN KEY (produced_by_task) REFERENCES tasks(id) ON DELETE SET NULL;
ALTER TABLE tasks ADD CONSTRAINT tasks_worktree_id_fk
    FOREIGN KEY (worktree_id) REFERENCES worktrees(id) ON DELETE SET NULL;

-- 5. model_usage_details — token 明细（热数据，AR-1.1）
CREATE TABLE model_usage_details (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model_id            VARCHAR(64) NOT NULL,
    agent_type          VARCHAR(32) NOT NULL,
    project_id          UUID NULL,
    thread_id           UUID NULL,
    input_tokens        INTEGER NOT NULL DEFAULT 0,
    output_tokens       INTEGER NOT NULL DEFAULT 0,
    cache_hit_tokens    INTEGER NOT NULL DEFAULT 0,
    latency_ms          INTEGER NOT NULL DEFAULT 0,
    status              VARCHAR(16) NOT NULL CHECK (status IN ('success', 'error')),
    error_message       TEXT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_model_usage_details_user_created ON model_usage_details (user_id, created_at);
CREATE INDEX idx_model_usage_details_user_model_created ON model_usage_details (user_id, model_id, created_at);

-- 6. model_usage_daily — 按天聚合（AR-1.1, AR-1.5）
CREATE TABLE model_usage_daily (
    user_id                 UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    model_id                VARCHAR(64) NOT NULL,
    agent_type              VARCHAR(32) NOT NULL,
    date                    DATE NOT NULL,
    call_count              INTEGER NOT NULL DEFAULT 0,
    input_tokens_sum        BIGINT NOT NULL DEFAULT 0,
    output_tokens_sum       BIGINT NOT NULL DEFAULT 0,
    cache_hit_tokens_sum    BIGINT NOT NULL DEFAULT 0,
    latency_avg_ms          INTEGER NOT NULL DEFAULT 0,
    error_count             INTEGER NOT NULL DEFAULT 0,
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT model_usage_daily_unique UNIQUE (user_id, model_id, agent_type, date)
);

-- 7. model_usage_archive — 30 天前明细压缩包（AR-1.1, AR-1.6）
CREATE TABLE model_usage_archive (
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    date            DATE NOT NULL,
    compressed_data BYTEA NOT NULL,  -- gzip + MessagePack
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT model_usage_archive_unique UNIQUE (user_id, date)
);

-- 8. skill_calls — Skill 调用审计（AR-1.1）
CREATE TABLE skill_calls (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
    skill_id        VARCHAR(64) NOT NULL,
    params          JSONB NOT NULL DEFAULT '{}',
    result_summary  TEXT NULL,
    risk_level      VARCHAR(8) NOT NULL CHECK (risk_level IN ('low', 'medium', 'high')),
    user_approved_at TIMESTAMPTZ NULL,
    status          VARCHAR(16) NOT NULL CHECK (status IN ('success', 'failed', 'forbidden')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_skill_calls_run ON skill_calls (run_id);

-- 9. outbox_events — Outbox 模式事件发布（AR-1.1）
CREATE TABLE outbox_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID NOT NULL UNIQUE,
    event_type      VARCHAR(64) NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}',
    status          VARCHAR(16) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processed', 'dead_lettered')),
    retry_count     INTEGER NOT NULL DEFAULT 0,
    next_retry_at   TIMESTAMPTZ NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ NULL
);

CREATE INDEX idx_outbox_events_status_retry ON outbox_events (status, next_retry_at) WHERE status = 'pending';

-- 10. dead_letter_events — 死信队列（AR-1.1）
CREATE TABLE dead_letter_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID NOT NULL,
    event_type      VARCHAR(64) NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}',
    error_message   TEXT NOT NULL,
    retry_count     INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_dead_letter_events_event ON dead_letter_events (event_id);
