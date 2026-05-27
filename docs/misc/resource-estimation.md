# Orbion 系统资源评估

## MVP（单服务 + InProcessEventBus + Redis + PostgreSQL）

### 小团队（10 人）

| 资源 | 估算 | 说明 |
|------|------|------|
| CPU | 1-2 核 | 单 FastAPI 进程，主要负载是 SSE 推送和事件路由，LLM 调用是外部 API 不消耗本地 CPU |
| 内存 | 512-768 MB | FastAPI 进程 ~300MB，Redis ~50MB，PostgreSQL ~200MB，连接池和 SSE 连接各占少量 |
| 存储 | 1-5 GB/年 | event_log 行数 ~1-3 万/月，每行 JSONB payload ~1-5KB，投影表更小 |
| 网络 | 低 | 用户 HTTP/SSE 带宽极低；LLM API 是主要出站流量（每次 Agent 调用 ~10-50KB prompt + response） |

### 中等团队（100 人）

| 资源 | 估算 | 说明 |
|------|------|------|
| CPU | 2-4 核 | SSE 连接数增多，事件吞吐量上升 |
| 内存 | 1-2 GB | FastAPI ~500MB（更多 SSE 连接），Redis ~100MB，PostgreSQL ~500MB |
| 存储 | 10-50 GB/年 | event_log ~10-30 万行/月 |
| 网络 | 中 | LLM API 调用频率随用户数线性增长 |

## 完整版（Hub + 4 业务服务 + NATS + PostgreSQL + 对象存储）

### 小团队（10 人）

| 资源 | 估算 | 说明 |
|------|------|------|
| CPU | 2-4 核 | 5 个 FastAPI 进程，NATS JetStream，IM Channel webhook 接收 |
| 内存 | 1.5-2 GB | Hub ~400MB，4 业务服务各 ~200MB，NATS ~200MB，PostgreSQL ~300MB |
| 存储 | 2-8 GB/年 | event_log + agent_trace（TTL 30-90 天）+ 大 payload 在对象存储 |
| 网络 | 低-中 | 加了 IM Channel webhook 入站流量 |

### 中等团队（100 人）

| 资源 | 估算 | 说明 |
|------|------|------|
| CPU | 4-8 核 | Agent Runtime 是瓶颈——10-20 个 Agent 并发执行，每个持有 LLM API 流式连接 |
| 内存 | 4-6 GB | Hub ~800MB，Agent Runtime ~1GB（并发 Agent 上下文），Collaboration ~500MB，NATS ~300MB，PostgreSQL ~1GB |
| 存储 | 50-200 GB/年 | event_log 增长 + IM 交互数据 + Agent 过程 trace（TTL 控制后约 1/3 有效存储） |
| 网络 | 中-高 | LLM API + IM webhook 双向流量 |

## 关键瓶颈分析

| 组件 | MVP 瓶颈 | 完整版瓶颈 | 原因 |
|------|---------|-----------|------|
| Agent Runtime | 不明显（2-3 并发） | **最可能瓶颈** | 每个 Agent 执行持有 LLM 流式连接 10-60 秒，20 并发 = 20 个长连接 + 大内存上下文 |
| SSE 推送 | 不明显 | 中等 | 100 个 SSE 连接常驻，每个 ~10KB 内存 |
| PostgreSQL | 不明显 | 存储 > 性能 | event_log 追加写入，按 project_id 分区后查询性能可控；容量是长期问题 |
| NATS | MVP 不用 | 不明显 | JetStream 事件路由很轻，百万级事件吞吐无压力 |
| LLM API 费用 | 不在系统资源内 | **实际最大成本** | 100 人团队每天 ~500-2000 次 Agent 调用，每次 $0.01-0.10，月费 $500-2000 |

## 结论

- MVP 私有化部署：一台 2 核 2GB VPS 就够，成本极低
- 完整版 100 人：需要 8 核 8GB 服务器，但真正的瓶颈不在系统资源，而在 LLM API 费用和 Agent Runtime 并发上限
- 系统资源不是 Orbion 的瓶颈——它是事件驱动的协调平台，不是计算密集型系统。Agent 的"计算"发生在 LLM 云端，本地只做路由和调度