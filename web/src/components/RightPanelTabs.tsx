import { FileTab } from '@/components/FileTab'
import ExecutionPanel from '@/components/ExecutionPanel'
import { File, ListChecks, Package, Bot } from 'lucide-react'
import type { PlanResponse, OutputResponse } from '@/types/api'

export type RightTab = 'file' | 'plan' | 'output' | 'agent'

const TABS: { key: RightTab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { key: 'file', label: '文件', icon: File },
  { key: 'plan', label: '计划', icon: ListChecks },
  { key: 'output', label: '产出', icon: Package },
  { key: 'agent', label: 'Agent', icon: Bot },
]

const PLACEHOLDER: Record<Exclude<RightTab, 'file' | 'plan'>, string> = {
  output: '产出 — 后续实现',
  agent: 'Agent — 后续实现',
}

interface RightPanelTabsProps {
  projectId: string | null
  selectedTab: RightTab
  onTabChange: (tab: RightTab) => void
  plans: PlanResponse[]
  outputs: OutputResponse[]
  onApprovePlan: (planId: string) => void
  onRejectPlan: (planId: string, reason: string) => void
  fileTreeRefreshKey?: number
}

export function RightPanelTabs({
  projectId, selectedTab, onTabChange,
  plans, outputs, onApprovePlan, onRejectPlan,
  fileTreeRefreshKey,
}: RightPanelTabsProps) {
  return (
    <div className="flex flex-col h-full">
      <div role="tablist" className="flex border-b bg-card px-1">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            role="tab"
            aria-selected={selectedTab === tab.key}
            onClick={() => onTabChange(tab.key)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors
              ${selectedTab === tab.key
                ? 'text-foreground border-b-2 border-primary'
                : 'text-muted-foreground hover:text-foreground'
              }`}
          >
            <tab.icon className="h-3.5 w-3.5" />
            {tab.label}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-hidden">
        {selectedTab === 'file' ? (
          <FileTab projectId={projectId} refreshKey={fileTreeRefreshKey} />
        ) : selectedTab === 'plan' ? (
          <ExecutionPanel
            plans={plans}
            outputs={outputs}
            onApprovePlan={onApprovePlan}
            onRejectPlan={onRejectPlan}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
            {PLACEHOLDER[selectedTab]}
          </div>
        )}
      </div>
    </div>
  )
}
