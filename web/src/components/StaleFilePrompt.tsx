import { Button } from '@/components/ui/button'
import { RefreshCw, Clock } from 'lucide-react'

interface StaleFilePromptProps {
  onReload: () => void
  onKeep: () => void
}

/**
 * 30 分钟过期提示（设计 §5.2.2 适用边界）
 * 打开超过 30 分钟未保存，提示重新加载——基于陈旧 original 合并结果可能偏离语义
 */
export function StaleFilePrompt({ onReload, onKeep }: StaleFilePromptProps) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
      data-testid="stale-file-prompt"
    >
      <div className="bg-background border rounded-lg shadow-lg max-w-md w-full mx-4 p-4">
        <div className="flex items-center gap-2 mb-2">
          <Clock className="h-4 w-4 text-yellow-600" />
          <h3 className="text-sm font-medium">文件已过期</h3>
        </div>
        <p className="text-xs text-muted-foreground mb-3">
          文件打开已超过 30 分钟，期间可能有其他人修改。建议重新加载后再编辑保存，
          避免基于陈旧内容合并产生偏差。
        </p>
        <div className="flex justify-end gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={onKeep}
            data-testid="btn-stale-keep"
          >
            仍要保存
          </Button>
          <Button
            variant="default"
            size="sm"
            onClick={onReload}
            data-testid="btn-stale-reload"
          >
            <RefreshCw className="h-3.5 w-3.5 mr-1" />
            重新加载
          </Button>
        </div>
      </div>
    </div>
  )
}
