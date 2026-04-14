import "./globals.css"
import { GeistSans } from "geist/font/sans"
import { GeistMono } from "geist/font/mono"
import { AuthWrapper } from "./auth-wrapper"

export const metadata = {
  title: "Observador de Dominios — Admin",
  description: "Admin panel for domain monitoring and threat intelligence",
}

const themeScript = `
(function() {
  try {
    var theme = localStorage.getItem('theme');
    var sys = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    if ((theme || sys) === 'dark') {
      document.documentElement.classList.add('dark');
    }
  } catch (e) {}
})();
`

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="pt-BR" className={`${GeistSans.variable} ${GeistMono.variable}`} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body suppressHydrationWarning>
        <AuthWrapper>{children}</AuthWrapper>
      </body>
    </html>
  )
}
