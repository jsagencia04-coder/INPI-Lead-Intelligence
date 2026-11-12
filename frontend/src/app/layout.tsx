import type { Metadata } from "next";
import "./globals.css";
import { AuthGate } from "@/components/auth-gate";
import { CommandPalette } from "@/components/command-palette";
import { Sidebar } from "@/components/sidebar";
import { Topbar } from "@/components/topbar";

export const metadata: Metadata = {
  title: "INPI Lead Intelligence",
  description: "Plataforma de inteligência comercial para titulares de marcas a partir da RPI",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>
        <AuthGate>
          <div className="flex min-h-screen">
            <Sidebar />
            <div className="flex min-w-0 flex-1 flex-col">
              <Topbar />
              <main className="min-w-0 flex-1 p-4 md:p-6 lg:p-8">{children}</main>
            </div>
          </div>
          <CommandPalette />
        </AuthGate>
      </body>
    </html>
  );
}
