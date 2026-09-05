import { Badge } from "@mantine/core";

export function StatusBadge({ connected }: { readonly connected: boolean }) {
  return (
    <Badge color={connected ? "green" : "gray"} variant="light">
      {connected ? "Connected" : "Disconnected"}
    </Badge>
  );
}
