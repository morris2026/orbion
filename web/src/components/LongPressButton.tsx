import { useRef, useCallback, useState } from 'react'
import { Button } from '@/components/ui/button'

interface LongPressButtonProps {
  onLongPress: () => void
  duration?: number
  'aria-label'?: string
  className?: string
  children: React.ReactNode
}

export default function LongPressButton({
  onLongPress,
  duration = 3000,
  'aria-label': ariaLabel,
  className,
  children,
}: LongPressButtonProps) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [progress, setProgress] = useState(0)
  const rafRef = useRef<ReturnType<typeof requestAnimationFrame> | null>(null)
  const startTimeRef = useRef(0)

  const clear = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
    setProgress(0)
  }, [])

  const animateProgress = useCallback(() => {
    const elapsed = Date.now() - startTimeRef.current
    const p = Math.min(elapsed / duration, 1)
    setProgress(p)
    if (p < 1) {
      rafRef.current = requestAnimationFrame(animateProgress)
    }
  }, [duration])

  const handleStart = useCallback(() => {
    startTimeRef.current = Date.now()
    rafRef.current = requestAnimationFrame(animateProgress)
    timerRef.current = setTimeout(() => {
      setProgress(1)
      onLongPress()
    }, duration)
  }, [duration, onLongPress, animateProgress])

  const handleEnd = useCallback(() => {
    clear()
  }, [clear])

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="icon"
        className={className}
        aria-label={ariaLabel}
        onMouseDown={handleStart}
        onMouseUp={handleEnd}
        onMouseLeave={handleEnd}
        onTouchStart={handleStart}
        onTouchEnd={handleEnd}
        onTouchCancel={handleEnd}
      >
        {children}
      </Button>
      {progress > 0 && (
        <div
          className="absolute inset-0 rounded-md pointer-events-none bg-red-500/20"
          style={{ clipPath: `inset(0 ${(1 - progress) * 100}% 0 0)` }}
        />
      )}
    </div>
  )
}
