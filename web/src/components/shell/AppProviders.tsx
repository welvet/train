"use client";

import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";

import { SystemProvider } from "@/src/state/SystemProvider";

export function AppProviders({ children }: { readonly children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { gcTime: 10 * 60_000 },
        },
      }),
  );

  return (
    <MantineProvider defaultColorScheme="auto">
      <QueryClientProvider client={queryClient}>
        <SystemProvider>{children}</SystemProvider>
      </QueryClientProvider>
    </MantineProvider>
  );
}
