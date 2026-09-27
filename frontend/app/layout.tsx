import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "TraderX · Research terminal",
  description:
    "Local quantitative research, evidence and controlled paper trading",
  applicationName: "TraderX",
  robots: { index: false, follow: false },
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
