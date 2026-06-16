import { UserMenu } from '@/components/UserMenu'

export function TopBar() {
  return (
    <div className="flex items-center h-9 px-3 border-b bg-card" data-testid="top-bar">
      <div className="flex items-center gap-1.5">
        <div className="h-[18px] w-[18px] rounded bg-[#7c3aed] flex items-center justify-center text-white text-[11px] font-bold">
          O
        </div>
        <span className="text-sm font-semibold">Orbion</span>
      </div>
      <div className="flex-1" />
      <UserMenu />
    </div>
  )
}
