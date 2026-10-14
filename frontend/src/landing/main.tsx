import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../styles/fonts";
import "../styles/base.css";
import "../styles/landing.css";
import { LandingPage } from "./LandingPage";

createRoot(document.getElementById("root")!).render(<StrictMode><LandingPage /></StrictMode>);
