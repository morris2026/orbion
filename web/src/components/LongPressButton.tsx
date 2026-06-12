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

  const handleStart = useCallback((e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault()
    startTimeRef.current = Date.now()
    rafRef.current = requestAnimationFrame(animateProgress)
    timerRef.current = setTimeout(() => {
      setProgress(1)
      triggeredRef.current = true
      onLongPress()
    }, duration)
  }, [duration, onLongPress, animateProgress])

  const triggeredRef = useRef(false)

  const handleEnd = useCallback(() => {
    if (triggeredRef.current) {
      triggeredRef.current = false
      clear()
      return
    }
    clear()
  }, [clear])

  const r = 8
  const circumference = 2 * Math.PI * r
  const strokeDashoffset = circumference * (1 - progress)

  return (
    <div className="relative inline-flex">
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
        <svg
          className="absolute inset-0 pointer-events-none text-red-500"
          width="100%"
          height="100%"
          viewBox="0 0 20 20"
        >
          <circle
            cx="10"
            cy="10"
            r={r}
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            transform="rotate(-90 10 10)"
          />
        </svg>
      )}
    </div>
  )
}
