import { MainController } from "@/src/components/controller/MainController";

export type AppPage = "controller";

export function PageHost({ page }: { readonly page: AppPage }) {
  switch (page) {
    case "controller":
      return <MainController />;
  }
}
