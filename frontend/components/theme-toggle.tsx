'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'

export function ThemeToggle() {
  const [theme, setTheme] = useState<'light' | 'dark'>('light')

  useEffect(() => {
    // Verificar preferência salva ou do sistema
    const savedTheme = localStorage.getItem('theme') as 'light' | 'dark' | null
    const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    const initialTheme = savedTheme || systemTheme
    
    setTheme(initialTheme)
    applyTheme(initialTheme)
  }, [])

  const applyTheme = (newTheme: 'light' | 'dark') => {
    const root = document.documentElement
    if (newTheme === 'dark') {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
  }

  const toggleTheme = () => {
    const newTheme = theme === 'light' ? 'dark' : 'light'
    setTheme(newTheme)
    applyTheme(newTheme)
    localStorage.setItem('theme', newTheme)
  }

  return (
    <Button
      onClick={toggleTheme}
      variant="outline"
      size="sm"
      className="fixed top-4 right-4 z-50"
    >
      {theme === 'light' ? (
        <span className="flex items-center gap-2">
          🌙 <span className="hidden sm:inline">Dark</span>
        </span>
      ) : (
        <span className="flex items-center gap-2">
          ☀️ <span className="hidden sm:inline">Light</span>
        </span>
      )}
    </Button>
  )
}
