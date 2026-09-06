import { render, screen } from "@testing-library/react";

import { AppHeader } from "./AppHeader";

const burgerProps = vi.hoisted(() => vi.fn());

vi.mock("@fluentui-emoji/react/flat/locomotive", () => ({
  default: () => null,
}));

vi.mock("@mantine/core", () => {
  const Container = ({ children }: { children: React.ReactNode }) => <div>{children}</div>;

  return {
    Badge: Container,
    Button: Container,
    Group: Container,
    Stack: Container,
    Text: Container,
    Title: Container,
    Burger: (props: { readonly "aria-label": string }) => {
      burgerProps(props);
      return <button type="button" aria-label={props["aria-label"]} />;
    },
  };
});

vi.mock("@/src/state/SystemProvider", () => ({
  useSystem: () => ({
    actions: {},
    connection: "loading",
    model: null,
    pendingResources: new Set(),
    refreshing: false,
  }),
}));

it("keeps the navigation toggle visible at every viewport size", () => {
  render(<AppHeader menuOpened={false} onMenuToggle={vi.fn()} />);

  expect(screen.getByRole("button", { name: "Toggle navigation" })).toBeVisible();
  expect(burgerProps.mock.lastCall?.[0]).not.toHaveProperty("hiddenFrom");
});
