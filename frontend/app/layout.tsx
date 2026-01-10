import './globals.css'

export const metadata = {
  title: 'Hello World',
  description: 'Frontend (Next.js)',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  )
}
