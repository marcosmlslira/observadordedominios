import "./globals.css"
import { AuthWrapper } from "./auth-wrapper"

export const metadata = {
  title: "Observador de Dominios — Admin",
  description: "Admin panel for domain monitoring and threat intelligence",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <AuthWrapper>{children}</AuthWrapper>
      </body>
    </html>
  )
}
