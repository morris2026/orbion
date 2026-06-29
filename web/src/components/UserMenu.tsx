import { useNavigate } from 'react-router-dom'
import { SettingsIcon, LogOutIcon, UserCheckIcon } from 'lucide-react'
import { clearToken, getIsAdmin, getUsername, getDisplayName } from '@/lib/auth'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'

export function UserMenu() {
  const navigate = useNavigate()
  const username = getUsername()
  const displayName = getDisplayName()
  const isAdmin = getIsAdmin()

  const fallback = displayName ? displayName[0].toUpperCase() : username ? username[0].toUpperCase() : '?'
  const showName = displayName || username || ''

  return (
    <DropdownMenu>
      <DropdownMenuTrigger aria-label="用户菜单" className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-primary">
        <Avatar size="default">
          <AvatarFallback className="text-xs">{fallback}</AvatarFallback>
        </Avatar>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-48">
        {showName && (
          <>
            <div className="px-2 py-1.5">
              <div className="text-sm font-medium">{showName}</div>
              {username && username !== showName && (
                <div className="text-xs text-muted-foreground">@{username}</div>
              )}
            </div>
            <DropdownMenuSeparator />
          </>
        )}
        <DropdownMenuItem onClick={() => navigate('/settings')}>
          <SettingsIcon className="mr-2 h-4 w-4" />
          设置
        </DropdownMenuItem>
        {isAdmin && (
          <DropdownMenuItem onClick={() => navigate('/approval')}>
            <UserCheckIcon className="mr-2 h-4 w-4" />
            新用户审批
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onClick={() => { clearToken(); navigate('/login') }}>
          <LogOutIcon className="mr-2 h-4 w-4" />
          登出
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
