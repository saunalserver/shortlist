import type { Metadata } from "next";
import { Bricolage_Grotesque, Fira_Code } from "next/font/google";
import "./globals.css";
import { Sidebar } from "@/components/layout/sidebar";
import { ApplicationPanel } from "@/components/applications/application-panel";
import { QuickAddDialog } from "@/components/applications/quick-add-dialog";

const bricolageGrotesque = Bricolage_Grotesque({
  variable: "--font-sans",
  subsets: ["latin"],
  weight: ["400", "600", "700"],
});

const firaCode = Fira_Code({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

export const metadata: Metadata = {
  title: "Job Search Command Center",
  description: "Track your job applications and pipeline",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        className={`${bricolageGrotesque.variable} ${firaCode.variable} antialiased`}
        suppressHydrationWarning
      >
        <div className="flex h-screen">
          <Sidebar />
          <main className="flex-1 flex flex-col overflow-hidden">
            {children}
          </main>
        </div>
        <ApplicationPanel />
        <QuickAddDialog />
      </body>
    </html>
  );
}
