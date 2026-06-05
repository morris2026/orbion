import type { PlanResponse, OutputResponse } from '@/types/api'
import PlanCard from './PlanCard'
import OutputDiff from './OutputDiff'

interface ExecutionPanelProps {
  plans: PlanResponse[]
  outputs: OutputResponse[]
  onApprovePlan: (planId: string) => void
  onRejectPlan: (planId: string, reason: string) => void
}

export default function ExecutionPanel({ plans, outputs, onApprovePlan, onRejectPlan }: ExecutionPanelProps) {
  return (
    <div className="flex flex-col h-full overflow-y-auto p-4 space-y-4">
      {plans.length === 0 && (
        <p className="text-xs text-muted-foreground">暂无执行计划</p>
      )}
      {plans.map((plan) => (
        <PlanCard key={plan.id} plan={plan} onApprove={onApprovePlan} onReject={onRejectPlan} />
      ))}
      {outputs.map((output) => (
        output.diff && (
          <div key={output.id} className="space-y-1">
            <span className="text-xs font-medium">产出 {output.id}</span>
            <OutputDiff diff={output.diff} />
          </div>
        )
      ))}
    </div>
  )
}