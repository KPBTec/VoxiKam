'use client'
import { useEffect, useRef } from 'react'

const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), textarea, input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'

export function Modal({
  onClose, children, className, labelledBy,
}: {
  onClose: () => void
  children: React.ReactNode
  className?: string
  labelledBy?: string
}) {
  const dialogRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null
    dialogRef.current?.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)?.focus()

    function onKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') { onClose(); return }
      if (e.key !== 'Tab') return
      const node = dialogRef.current
      if (!node) return
      const items = Array.from(node.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
      if (items.length === 0) return
      const first = items[0], last = items[items.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }

    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      previouslyFocused?.focus()
    }
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby={labelledBy} className={className}>
        {children}
      </div>
    </div>
  )
}
