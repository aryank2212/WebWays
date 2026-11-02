import { createRoot } from "react-dom/client";
import App from "./App";
import "@fontsource/bodoni-moda/latin-700.css"; // bundled locally: the UI never fetches fonts from a third party
import "./styles.css";

createRoot(document.getElementById("root")!).render(<App />);
