import { hydrateRoot } from "react-dom/client";
import { StartClient } from "@tanstack/react-start/client";

if (import.meta.env.DEV) {
  void import("virtual:stylex:runtime");
}

hydrateRoot(document, <StartClient />);
