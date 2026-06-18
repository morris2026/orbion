import { FileTab } from '@/components/FileTab'
import ExecutionPanel from '@/components/ExecutionPanel'
import { Workflow, File } from 'lucide-react'
import type { PlanResponse, OutputResponse } from '@/types/api'

export type RightTab = 'flow' | 'file'

const TABS: { key: RightTab; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
  { key: 'flow', label: '流程', icon: Workflow },
  { key: 'file', label: '文件', icon: File },
]

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
        {selectedTab === 'flow' ? (
          <ExecutionPanel
            plans={plans}
            outputs={outputs}
            onApprovePlan={onApprovePlan}
            onRejectPlan={onRejectPlan}
          />
        ) : (
          <FileTab projectId={projectId} refreshKey={fileTreeRefreshKey} />
        )}
      </div>
    </div>
  )
}
