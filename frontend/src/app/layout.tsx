import type { Metadata } from "next";
import "./globals.css";
import { AuthGate } from "@/components/auth-gate";
import { Sidebar } from "@/components/sidebar";

export const metadata: Metadata = {
  title: "INPI Lead Intelligence",
  description: "Prospecção de titulares de marcas a partir da RPI",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="pt-BR">
      <body>
        <AuthGate>
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="min-w-0 flex-1 p-4 pt-16 md:p-6">{children}</main>
          </div>
        </AuthGate>
      </body>
    </html>
  );
}
