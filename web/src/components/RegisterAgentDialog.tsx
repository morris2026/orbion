import { useState } from 'react'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { apiPost, ApiError } from '@/lib/api'
import type { RegisterAgentRequest } from '@/types/api'

interface RegisterAgentDialogProps {
  open: boolean
  projectId: string
  onClose: () => void
  onRegisterAgent: (projectId: string, req: RegisterAgentRequest) => void
}

const AGENT_TYPES: { value: RegisterAgentRequest['agent_type']; label: string; defaultName: string }[] = [
  { value: 'summary', label: 'summary', defaultName: '总结Agent' },
  { value: 'decompose', label: 'decompose', defaultName: '分解Agent' },
  { value: 'execute', label: 'execute', defaultName: '执行Agent' },
]

const MODELS = [
  { value: 'claude-haiku-4-5-20251001', label: 'claude-haiku-4-5-20251001' },
  { value: 'claude-sonnet-4-6', label: 'claude-sonnet-4-6' },
]

export default function RegisterAgentDialog({ open, projectId, onClose, onRegisterAgent }: RegisterAgentDialogProps) {
  const [agentType, setAgentType] = useState<RegisterAgentRequest['agent_type'] | null>(null)
  const [modelId, setModelId] = useState(MODELS[0].value)
  const [displayName, setDisplayName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 选择类型时预填display_name
  const handleTypeSelect = (type: RegisterAgentRequest['agent_type']) => {
    setAgentType(type)
    const defaultName = AGENT_TYPES.find((t) => t.value === type)?.defaultName ?? ''
    setDisplayName(defaultName)
  }

  const canSubmit = agentType !== null && displayName.trim().length > 0 && !submitting

  const handleSubmit = async () => {
    if (!canSubmit || !agentType) return
    setSubmitting(true)
    setError(null)
    try {
      await apiPost(`/projects/${projectId}/agents`, {
        agent_type: agentType,
        model_id: modelId,
        display_name: displayName.trim(),
      })
      onRegisterAgent(projectId, {
        agent_type: agentType,
        model_id: modelId,
        display_name: displayName.trim(),
      })
      onClose()
    } catch (e) {
      if (e instanceof ApiError) {
        setError(`注册失败：${e.detail}`)
      } else {
        setError('注册失败')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) onClose() }}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>注册Agent</DialogTitle>
          <DialogDescription>为项目注册一个AI Agent</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {/* Agent类型单选 */}
          <div>
            <span className="text-sm font-medium">Agent类型</span>
            <div className="flex gap-2 mt-1">
              {AGENT_TYPES.map((t) => (
                <Button
                  key={t.value}
                  variant={agentType === t.value ? 'default' : 'outline'}
                  size="sm"
                  onClick={() => handleTypeSelect(t.value)}
                  data-selected={agentType === t.value ? 'true' : undefined}
                >
                  {t.label}
                </Button>
              ))}
            </div>
          </div>
          {/* 模型下拉 */}
          <div>
            <label htmlFor="agent-model" className="text-sm font-medium">模型</label>
            <select
              id="agent-model"
              aria-label="模型"
              role="combobox"
              className="w-full mt-1 p-2 border rounded text-sm"
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
            >
              {MODELS.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>
          {/* 显示名称 */}
          <div>
            <label htmlFor="agent-name" className="text-sm font-medium">显示名称</label>
            <input
              id="agent-name"
              aria-label="显示名称"
              className="w-full mt-1 p-2 border rounded text-sm"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="输入Agent显示名称"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>取消</DialogClose>
          <Button onClick={handleSubmit} disabled={!canSubmit}>{submitting ? '注册中...' : '注册'}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}