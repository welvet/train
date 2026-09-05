import type { Metadata } from "next";
import type { ReactNode } from "react";
import { ColorSchemeScript } from "@mantine/core";

import "@mantine/core/styles.css";
import "./globals.css";
import { AppProviders } from "@/src/components/shell/AppProviders";

export const metadata: Metadata = {
  title: "Train",
  description: "Train control web UI",
};

type RootLayoutProps = Readonly<{
  children: ReactNode;
}>;

export default function RootLayout({ children }: RootLayoutProps) {
  return (
    <html lang="en">
      <head>
        <ColorSchemeScript defaultColorScheme="auto" />
      </head>
      <body>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
