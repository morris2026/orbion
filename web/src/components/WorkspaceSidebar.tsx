import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import { FolderKanban, MessageCircleMore } from 'lucide-react'
import { UserMenu } from '@/components/UserMenu'

/** 自定义图标：台灯（lucide LampDesk 造型）+ 桌子，表示"工作台" */
function WorkbenchIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      {/* 台灯：灯罩 + 关节 + 灯臂（取自 lucide LampDesk，缩放适配桌面） */}
      <g transform="translate(2, -1) scale(0.72)">
        <path d="M10.293 2.293a1 1 0 0 1 1.414 0l2.5 2.5 5.994 1.227a1 1 0 0 1 .506 1.687l-7 7a1 1 0 0 1-1.687-.506l-1.227-5.994-2.5-2.5a1 1 0 0 1 0-1.414z" />
        <path d="m14.207 4.793-3.414 3.414" />
        <path d="m9.086 6.5-4.793 4.793a1 1 0 0 0-.18 1.17L7 16" />
      </g>
      {/* 桌面 */}
      <path d="M3 16 L21 16" />
      {/* 左桌腿 */}
      <path d="M5 16 L3 22" />
      {/* 右桌腿 */}
      <path d="M19 16 L21 22" />
      {/* 台灯支柱连接桌面 */}
      <path d="M7 16 L7 13" />
    </svg>
  )
}

interface WorkspaceSidebarProps {
  showLeft: boolean
  showMiddle: boolean
  showRight: boolean
  onToggleLeft: () => void
  onToggleMiddle: () => void
  onToggleRight: () => void
}

const iconBtn = 'relative inline-flex items-center justify-center h-10 w-10 rounded-md hover:bg-accent hover:text-accent-foreground data-[active=true]:bg-accent/60 data-[active=true]:text-accent-foreground before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:w-0.5 before:h-5 before:bg-foreground before:rounded-r before:scale-x-0 data-[active=true]:before:scale-x-100 before:transition-transform'

export function WorkspaceSidebar({ showLeft, showMiddle, showRight, onToggleLeft, onToggleMiddle, onToggleRight }: WorkspaceSidebarProps) {
  return (
    <TooltipProvider delay={300}>
      <div className="flex flex-col items-center gap-1 py-2 w-12 bg-muted/50 border-r" data-testid="workspace-sidebar">
        {/* 顶部：Orbion 图标 */}
        <div className="flex items-center justify-center h-10 w-10 mb-1" data-testid="sidebar-brand">
          <div className="h-[22px] w-[22px] rounded bg-[#7c3aed] flex items-center justify-center text-white text-[13px] font-bold">
            O
          </div>
        </div>

        {/* 中间：栏切换图标 */}
        <Tooltip>
          <TooltipTrigger
            className={iconBtn}
            data-active={showLeft ? 'true' : undefined}
            aria-label="项目"
            onClick={onToggleLeft}
            data-testid="sidebar-toggle-left"
          >
            <FolderKanban className="h-5 w-5" />
          </TooltipTrigger>
          <TooltipContent side="right">项目</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger
            className={iconBtn}
            data-active={showMiddle ? 'true' : undefined}
            aria-label="对话"
            onClick={onToggleMiddle}
            data-testid="sidebar-toggle-middle"
          >
            <MessageCircleMore className="h-5 w-5" />
          </TooltipTrigger>
          <TooltipContent side="right">对话</TooltipContent>
        </Tooltip>

        <Tooltip>
          <TooltipTrigger
            className={iconBtn}
            data-active={showRight ? 'true' : undefined}
            aria-label="工作台"
            onClick={onToggleRight}
            data-testid="sidebar-toggle-right"
          >
            <WorkbenchIcon className="h-5 w-5" />
          </TooltipTrigger>
          <TooltipContent side="right">工作台</TooltipContent>
        </Tooltip>

        {/* 底部：用户菜单 */}
        <div className="flex-1" />
        <div className="flex items-center justify-center h-10 w-10" data-testid="sidebar-user">
          <UserMenu />
        </div>
      </div>
    </TooltipProvider>
  )
}
