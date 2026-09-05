import { MainController } from "@/src/components/controller/MainController";
import { ConfigurationPage } from "@/src/components/configuration/ConfigurationPage";

export type AppPage = "controller" | "configuration";

export function PageHost({ page }: { readonly page: AppPage }) {
  switch (page) {
    case "controller":
      return <MainController />;
    case "configuration":
      return <ConfigurationPage />;
  }
}
