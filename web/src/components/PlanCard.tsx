import { useState } from 'react'
import type { PlanResponse } from '@/types/api'
import { Button } from '@/components/ui/button'

interface PlanCardProps {
  plan: PlanResponse
  onApprove: (planId: string) => void
  onReject: (planId: string, reason: string) => void
}

export default function PlanCard({ plan, onApprove, onReject }: PlanCardProps) {
  const [rejectReason, setRejectReason] = useState('')
  const [showRejectInput, setShowRejectInput] = useState(false)

  const handleReject = () => {
    if (!rejectReason.trim()) return
    onReject(plan.id, rejectReason.trim())
    setRejectReason('')
    setShowRejectInput(false)
  }

  return (
    <div className="p-3 rounded border bg-card" data-testid={`plan-${plan.id}`}>
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium">计划 {plan.id}</span>
        <span className="text-xs text-muted-foreground">{plan.status}</span>
      </div>
      <ul className="space-y-1 mb-3">
        {plan.tasks.map((task) => (
          <li key={task.task_id} className="text-xs">
            <span className="text-muted-foreground">{task.type}:</span> {task.description}
          </li>
        ))}
      </ul>
      {plan.status === 'proposed' && (
        <div className="flex flex-col gap-2">
          <Button variant="default" size="sm" onClick={() => onApprove(plan.id)}>批准</Button>
          {!showRejectInput ? (
            <Button variant="destructive" size="sm" onClick={() => setShowRejectInput(true)}>拒绝</Button>
          ) : (
            <div className="flex flex-col gap-1">
              <input
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                placeholder="拒绝原因..."
                className="px-2 py-1 text-xs border rounded bg-background"
              />
              <div className="flex gap-1">
                <Button variant="destructive" size="sm" onClick={handleReject}>确认拒绝</Button>
                <Button variant="ghost" size="sm" onClick={() => { setShowRejectInput(false); setRejectReason('') }}>取消</Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}