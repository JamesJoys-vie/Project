import { useEffect, useState } from 'react'

export function useDebounce(value, delay = 400) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(id)
  }, [value, delay])
  return debounced
}

// Seconds left until `deadline` (epoch ms), ticking every second. null deadline -> 0.
export function useSecondsLeft(deadline) {
  const calc = () => (deadline ? Math.max(0, Math.ceil((deadline - Date.now()) / 1000)) : 0)
  const [left, setLeft] = useState(calc)
  useEffect(() => {
    setLeft(calc())
    if (!deadline) return undefined
    const id = setInterval(() => setLeft(calc()), 1000)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deadline])
  return left
}
