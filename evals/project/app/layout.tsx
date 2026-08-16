import type { Metadata } from "next";
import Navbar from "./ui/Navbar";

export const metadata: Metadata = {
  title: "Eval project",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <Navbar />
        {children}
      </body>
    </html>
  );
}
