import { fireEvent, render, screen } from "@testing-library/react";

import { AppFrame } from "./AppFrame";

const appShellProps = vi.hoisted(() => vi.fn());

vi.mock("@mantine/core", () => {
  const AppShell = Object.assign(
    ({ children, ...props }: { children: React.ReactNode }) => {
      appShellProps(props);
      return <div>{children}</div>;
    },
    {
      Header: ({ children }: { children: React.ReactNode }) => <header>{children}</header>,
      Navbar: ({ children }: { children: React.ReactNode }) => <nav>{children}</nav>,
      Main: ({ children }: { children: React.ReactNode }) => <main>{children}</main>,
    },
  );

  return {
    AppShell,
    NavLink: ({ label, onClick }: { label: string; onClick: () => void }) => (
      <button type="button" onClick={onClick}>
        {label}
      </button>
    ),
    Text: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  };
});

vi.mock("./AppHeader", () => ({
  AppHeader: ({
    menuOpened,
    onMenuToggle,
  }: {
    menuOpened: boolean;
    onMenuToggle: () => void;
  }) => (
    <button type="button" aria-label="Toggle navigation" onClick={onMenuToggle}>
      {menuOpened ? "Close" : "Open"}
    </button>
  ),
}));

vi.mock("./PageHost", () => ({ PageHost: () => null }));

it("keeps navigation collapsed by default at every viewport size", () => {
  render(<AppFrame />);

  expect(appShellProps).toHaveBeenLastCalledWith(
    expect.objectContaining({
      navbar: expect.objectContaining({
        collapsed: { mobile: true, desktop: true },
      }),
    }),
  );

  fireEvent.click(screen.getByRole("button", { name: "Toggle navigation" }));

  expect(appShellProps).toHaveBeenLastCalledWith(
    expect.objectContaining({
      navbar: expect.objectContaining({
        collapsed: { mobile: false, desktop: false },
      }),
    }),
  );

  fireEvent.click(screen.getByRole("button", { name: "Configuration" }));

  expect(appShellProps).toHaveBeenLastCalledWith(
    expect.objectContaining({
      navbar: expect.objectContaining({
        collapsed: { mobile: true, desktop: true },
      }),
    }),
  );
});
