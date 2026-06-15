import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'

export type ActivityPanel = 'explorer' | 'git'

interface ActivityBarProps {
  activePanel: ActivityPanel
  onActivityChange: (panel: ActivityPanel) => void
}

export function ActivityBar({ activePanel, onActivityChange }: ActivityBarProps) {
  return (
    <TooltipProvider delay={300}>
      <div className="flex flex-col items-center gap-1 py-2 w-12 bg-muted/50 border-r" data-testid="activity-bar">
        <Tooltip>
          <TooltipTrigger
            className="inline-flex items-center justify-center h-10 w-10 rounded-md hover:bg-accent hover:text-accent-foreground"
            data-active={activePanel === 'explorer' ? 'true' : undefined}
            aria-label="Explorer"
            onClick={() => onActivityChange('explorer')}
            data-testid="activity-explorer"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
            </svg>
          </TooltipTrigger>
          <TooltipContent side="right">Explorer</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger
            className="inline-flex items-center justify-center h-10 w-10 rounded-md hover:bg-accent hover:text-accent-foreground"
            data-active={activePanel === 'git' ? 'true' : undefined}
            aria-label="Source Control"
            onClick={() => onActivityChange('git')}
            data-testid="activity-git"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="18" cy="18" r="3" />
              <circle cx="6" cy="6" r="3" />
              <path d="M6 21V9a9 9 0 0 0 9 9" />
            </svg>
          </TooltipTrigger>
          <TooltipContent side="right">Source Control</TooltipContent>
        </Tooltip>
      </div>
    </TooltipProvider>
  )
}
