"use client";

import Joystick from "@fluentui-emoji/react/flat/joystick";
import { AppShell, NavLink, Text } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useState } from "react";

import { AppHeader } from "./AppHeader";
import { type AppPage, PageHost } from "./PageHost";

export function AppFrame() {
  const [menuOpened, { toggle, close }] = useDisclosure(false);
  const [page, setPage] = useState<AppPage>("controller");

  return (
    <AppShell
      header={{ height: 72 }}
      navbar={{
        width: 230,
        breakpoint: "sm",
        collapsed: { mobile: !menuOpened, desktop: !menuOpened },
      }}
      padding={{ base: "sm", sm: "lg" }}
    >
      <AppShell.Header>
        <AppHeader menuOpened={menuOpened} onMenuToggle={toggle} />
      </AppShell.Header>
      <AppShell.Navbar p="sm">
        <NavLink
          active={page === "controller"}
          label="Controller"
          leftSection={<Joystick width={28} aria-hidden />}
          onClick={() => {
            setPage("controller");
            close();
          }}
        />
        <NavLink
          active={page === "configuration"}
          label="Configuration"
          leftSection={<Text size="xl" aria-hidden>⚙️</Text>}
          onClick={() => {
            setPage("configuration");
            close();
          }}
        />
      </AppShell.Navbar>
      <AppShell.Main>
        <PageHost page={page} />
      </AppShell.Main>
    </AppShell>
  );
}
