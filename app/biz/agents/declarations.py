"""AgentDeclaration定义 + 3个内置Agent声明模板"""

from pydantic import BaseModel

from app.biz.agents.adapters.base import ModelConfig
from app.biz.agents.skills import SkillDeclaration


class AgentDeclaration(BaseModel):
    """Agent声明——描述Agent的完整定义"""

    agent_id: str
    agent_type: str
    display_name: str
    role: str
    goal: str
    backstory: str
    subscribed_events: list[str]
    output_event_type: str
    model_config_obj: ModelConfig
    capabilities: list[str] = []
    skills: list[SkillDeclaration] = []
    max_concurrent_tasks: int = 1
    requires_approval: bool = False
    checkpoint_on_output: bool = False


# -- 3个内置Agent声明模板 --


SUMMARY_DECLARATION = AgentDeclaration(
    agent_id="agent-summary-template",
    agent_type="summary",
    display_name="总结助手",
    role="讨论总结专家",
    goal="从讨论线程中提炼共识点、分歧点和行动项",
    backstory=(
        "你是一个讨论总结 Agent。你订阅讨论线程中的消息事件，"
        "当收到 request_summary 标志或讨论消息累积到阈值时，"
        "你从 EventStore 获取该线程的完整消息历史，"
        "提炼共识点（所有人都同意的结论）、分歧点（尚有争议的观点）、"
        "行动项（需要后续执行的任务）。输出格式必须是结构化 JSON。"
    ),
    subscribed_events=["DiscussionMessageCreated"],
    output_event_type="DiscussionSummaryGenerated",
    model_config_obj=ModelConfig(model_id="claude-haiku-4-5-20251001", temperature=0.3, max_tokens=2048),
    capabilities=["discussion.summarize", "knowledge.query"],
    skills=[
        SkillDeclaration(
            name="discussion.summarize",
            description="总结讨论线程内容",
            input_schema={"thread_id": "string"},
            output_schema={"consensus_points": "list", "divergence_points": "list", "action_items": "list"},
            risk_level="low",
            requires_approval=False,
        ),
    ],
    max_concurrent_tasks=1,
    requires_approval=False,
    checkpoint_on_output=False,
)

DECOMPOSE_DECLARATION = AgentDeclaration(
    agent_id="agent-decompose-template",
    agent_type="decompose",
    display_name="任务分解助手",
    role="任务分解规划师",
    goal="根据讨论共识和行动项，分解为可执行的任务计划",
    backstory=(
        "你是一个任务分解 Agent。当收到讨论摘要事件后，"
        "你从摘要中提取行动项，将其分解为具体的执行任务。"
        "每个任务包含类型（code/document/configuration）、描述、依赖关系和优先级。"
        "你产出的执行计划需要人类审批后才交给执行 Agent。输出格式必须是结构化 JSON。"
    ),
    subscribed_events=["DiscussionSummaryGenerated"],
    output_event_type="ExecutionPlanProposed",
    model_config_obj=ModelConfig(model_id="claude-haiku-4-5-20251001", temperature=0.5, max_tokens=4096),
    capabilities=["task.plan", "discussion.post"],
    skills=[
        SkillDeclaration(
            name="task.plan",
            description="分解行动项为执行任务",
            input_schema={"action_items": "list", "context": "string"},
            output_schema={"tasks": "list"},
            risk_level="medium",
            requires_approval=True,
        ),
    ],
    max_concurrent_tasks=2,
    requires_approval=True,
    checkpoint_on_output=True,
)

EXECUTE_DECLARATION = AgentDeclaration(
    agent_id="agent-execute-template",
    agent_type="execute",
    display_name="代码执行助手",
    role="代码与文档执行者",
    goal="根据审批通过的任务计划，生成代码或文档产出",
    backstory=(
        "你是一个代码执行 Agent。当收到审批通过的任务计划后，"
        "你按任务逐个生成代码或文档产出。代码产出包含 diff，"
        "每个产出需要人类审核。输出格式必须是结构化 JSON。"
    ),
    subscribed_events=["ExecutionPlanApproved", "TaskOutputRevisionRequested"],
    output_event_type="TaskOutputGenerated",
    model_config_obj=ModelConfig(model_id="claude-haiku-4-5-20251001", temperature=0.2, max_tokens=8192),
    capabilities=["code.generate", "document.generate", "approval.request"],
    skills=[
        SkillDeclaration(
            name="code.generate",
            description="根据任务描述生成代码",
            input_schema={"task_description": "string", "context": "string"},
            output_schema={"content": "string", "diff": "string", "file_paths": "list"},
            risk_level="high",
            requires_approval=True,
        ),
        SkillDeclaration(
            name="document.generate",
            description="根据任务描述生成文档",
            input_schema={"task_description": "string", "context": "string"},
            output_schema={"content": "string"},
            risk_level="medium",
            requires_approval=True,
        ),
    ],
    max_concurrent_tasks=3,
    requires_approval=True,
    checkpoint_on_output=True,
)

BUILTIN_AGENT_DECLARATIONS: dict[str, AgentDeclaration] = {
    "summary": SUMMARY_DECLARATION,
    "decompose": DECOMPOSE_DECLARATION,
    "execute": EXECUTE_DECLARATION,
}
