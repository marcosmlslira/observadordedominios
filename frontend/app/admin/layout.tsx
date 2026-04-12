"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useEffect } from "react"
import { useAuth } from "@/lib/auth-context"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import {
  LayoutDashboard,
  Download,
  Shield,
  Wrench,
  LogOut,
} from "lucide-react"

const navItems = [
  { href: "/admin", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin/ingestion", label: "Ingestion Runs", icon: Download },
  { href: "/admin/brands", label: "Monitored Brands", icon: Shield },
  { href: "/admin/tools", label: "Free Tools", icon: Wrench },
]

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { isAuthenticated, isReady, logout } = useAuth()
  const router = useRouter()
  const pathname = usePathname()

  useEffect(() => {
    if (isReady && !isAuthenticated) {
      router.push("/login")
    }
  }, [isAuthenticated, isReady, router])

  if (!isReady || !isAuthenticated) return null

  function handleLogout() {
    logout()
    router.push("/login")
  }

  return (
    <div className="min-h-screen bg-background flex">
      {/* Sidebar */}
      <aside className="hidden md:flex w-60 flex-col border-r border-border-subtle bg-card">
        <div className="p-4">
          <h1 className="text-sm font-semibold">Observador de Dominios</h1>
          <p className="text-xs text-muted-foreground">Admin</p>
        </div>
        <Separator />
        <nav className="flex-1 p-2 space-y-1">
          {navItems.map((item) => {
            const isActive =
              item.href === "/admin"
                ? pathname === "/admin"
                : pathname.startsWith(item.href)
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? "bg-secondary text-foreground font-medium"
                    : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                }`}
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </Link>
            )
          })}
        </nav>
        <Separator />
        <div className="p-2">
          <Button
            variant="ghost"
            size="sm"
            className="w-full justify-start text-muted-foreground"
            onClick={handleLogout}
          >
            <LogOut className="h-4 w-4 mr-2" />
            Logout
          </Button>
        </div>
      </aside>

      {/* Mobile header */}
      <div className="flex-1 flex flex-col">
        <header className="md:hidden flex items-center justify-between border-b border-border-subtle p-4 bg-card">
          <h1 className="text-sm font-semibold">Observador Admin</h1>
          <div className="flex items-center gap-2">
            {navItems.map((item) => {
              const isActive =
                item.href === "/admin"
                  ? pathname === "/admin"
                  : pathname.startsWith(item.href)
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`p-2 rounded-md ${
                    isActive
                      ? "bg-secondary text-foreground"
                      : "text-muted-foreground"
                  }`}
                  title={item.label}
                >
                  <item.icon className="h-4 w-4" />
                </Link>
              )
            })}
            <Button variant="ghost" size="icon" onClick={handleLogout}>
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </header>

        {/* Main content */}
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  )
}
