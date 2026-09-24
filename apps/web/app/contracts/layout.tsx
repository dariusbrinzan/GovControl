import type { ReactNode } from "react";

import { AppShell } from "../../components/legal/app-shell";
import { SessionProvider } from "../../components/legal/session-provider";

export default function ContractsLayout({ children }: { children: ReactNode }) {
  return <SessionProvider><AppShell>{children}</AppShell></SessionProvider>;
}
