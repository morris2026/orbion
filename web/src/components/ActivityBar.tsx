import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { Files, GitFork } from 'lucide-react'

export type ActivityPanel = 'explorer' | 'git'

interface ActivityBarProps {
  activePanel: ActivityPanel
  sidebarCollapsed: boolean
  onActivityChange: (panel: ActivityPanel) => void
}

const iconBtn = 'relative inline-flex items-center justify-center h-10 w-10 rounded-md hover:bg-accent hover:text-accent-foreground data-[active=true]:bg-accent/60 data-[active=true]:text-accent-foreground before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:w-0.5 before:h-5 before:bg-foreground before:rounded-r before:scale-x-0 data-[active=true]:before:scale-x-100 before:transition-transform'

export function ActivityBar({ activePanel, sidebarCollapsed, onActivityChange }: ActivityBarProps) {
  return (
    <TooltipProvider delay={300}>
      <div className="flex flex-col items-center gap-1 py-2 w-12 bg-muted/50 border-r" data-testid="activity-bar">
        <Tooltip>
          <TooltipTrigger
            className={iconBtn}
            data-active={!sidebarCollapsed && activePanel === 'explorer' ? 'true' : undefined}
            aria-label="Explorer"
            onClick={() => onActivityChange('explorer')}
            data-testid="activity-explorer"
          >
            <Files className="h-5 w-5" />
          </TooltipTrigger>
          <TooltipContent side="right">Explorer</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger
            className={iconBtn}
            data-active={!sidebarCollapsed && activePanel === 'git' ? 'true' : undefined}
            aria-label="Source Control"
            onClick={() => onActivityChange('git')}
            data-testid="activity-git"
          >
            <GitFork className="h-5 w-5" />
          </TooltipTrigger>
          <TooltipContent side="right">Source Control</TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  )
}
