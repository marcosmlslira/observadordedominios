"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { useAuth } from "@/lib/auth-context"

export default function Home() {
  const { isAuthenticated } = useAuth()
  const router = useRouter()

  useEffect(() => {
    router.replace(isAuthenticated ? "/admin" : "/login")
  }, [isAuthenticated, router])

  return null
}
