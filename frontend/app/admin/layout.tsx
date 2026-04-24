"use client"

import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useEffect, useState } from "react"
import { useAuth } from "@/lib/auth-context"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { ThemeToggle } from "@/components/theme-toggle"
import {
  ChevronLeft,
  ChevronRight,
  LayoutDashboard,
  Download,
  Shield,
  Wrench,
  LogOut,
  AlertTriangle,
} from "lucide-react"

const navItems = [
  { href: "/admin", label: "Dashboard", icon: LayoutDashboard },
  { href: "/admin/ingestion", label: "Ingestão de Dados", icon: Download },
  { href: "/admin/brands", label: "Perfis de Marca", icon: Shield },
  { href: "/admin/matches", label: "Ameaças", icon: AlertTriangle },
  { href: "/admin/tools", label: "Ferramentas", icon: Wrench },
]

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const { isAuthenticated, isReady, logout } = useAuth()
  const router = useRouter()
  const pathname = usePathname()
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

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
      <aside className={`hidden md:flex md:sticky md:top-0 h-screen flex-col border-r border-border-subtle bg-card transition-all ${sidebarCollapsed ? "w-16" : "w-60"}`}>
        <div className={`flex items-start ${sidebarCollapsed ? "justify-center px-2 py-3" : "justify-between p-4"} gap-2`}>
          {!sidebarCollapsed && (
            <div className="min-w-0">
              <h1 className="truncate text-sm font-semibold">Observador de Dominios</h1>
              <p className="text-xs text-muted-foreground">Admin</p>
            </div>
          )}
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8 shrink-0"
            onClick={() => setSidebarCollapsed((value) => !value)}
            title={sidebarCollapsed ? "Expandir menu" : "Colapsar menu"}
            aria-label={sidebarCollapsed ? "Expandir menu" : "Colapsar menu"}
          >
            {sidebarCollapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
          </Button>
        </div>
        <Separator />
        <nav className="flex-1 overflow-y-auto p-2 space-y-1">
          {navItems.map((item) => {
            const isActive =
              item.href === "/admin"
                ? pathname === "/admin"
                : pathname.startsWith(item.href)
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center rounded-md py-2 text-sm transition-colors ${
                  sidebarCollapsed ? "justify-center px-2" : "gap-2 px-3"
                } ${
                  isActive
                    ? "bg-secondary text-foreground font-medium"
                    : "text-muted-foreground hover:bg-secondary hover:text-foreground"
                }`}
                title={item.label}
              >
                <item.icon className="h-4 w-4" />
                {!sidebarCollapsed && item.label}
              </Link>
            )
          })}
        </nav>
        <Separator />
        <div className={`p-2 flex items-center gap-1 ${sidebarCollapsed ? "justify-center" : ""}`}>
          <ThemeToggle />
          <Button
            variant="ghost"
            size="sm"
            className={`${sidebarCollapsed ? "w-8 px-0" : "flex-1 justify-start"} text-muted-foreground`}
            onClick={handleLogout}
            title="Sair"
          >
            <LogOut className={`h-4 w-4 ${sidebarCollapsed ? "" : "mr-2"}`} />
            {!sidebarCollapsed && "Sair"}
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
            <ThemeToggle />
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
