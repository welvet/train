"use client";

import Joystick from "@fluentui-emoji/react/flat/joystick";
import { AppShell, NavLink } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { useState } from "react";

import { AppHeader } from "./AppHeader";
import { type AppPage, PageHost } from "./PageHost";

export function AppFrame() {
  const [mobileOpened, { toggle, close }] = useDisclosure(false);
  const [page, setPage] = useState<AppPage>("controller");

  return (
    <AppShell
      header={{ height: 72 }}
      navbar={{
        width: 230,
        breakpoint: "sm",
        collapsed: { mobile: !mobileOpened },
      }}
      padding={{ base: "sm", sm: "lg" }}
    >
      <AppShell.Header>
        <AppHeader menuOpened={mobileOpened} onMenuToggle={toggle} />
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
      </AppShell.Navbar>
      <AppShell.Main>
        <PageHost page={page} />
      </AppShell.Main>
    </AppShell>
  );
}
