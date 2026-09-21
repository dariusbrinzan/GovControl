import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "GovControl",
  description: "Control operațional pentru administrația publică",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <html lang="ro"><body>{children}</body></html>;
}
