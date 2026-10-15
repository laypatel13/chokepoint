// The 404 page: Nightjar dozing on a branch, and the two ways back. Same fonts and colours as the site.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../styles/fonts";
import "../styles/base.css";
import "./notfound.css";
import { Logo } from "../components/Logo";
import { NightjarBird } from "../components/NightjarBird";

function NotFound() {
  const path = location.pathname.length > 60 ? `${location.pathname.slice(0, 57)}…` : location.pathname;
  return (
    <main className="nf">
      <a className="nf-brand" href="/"><Logo /><span>Chokepoint</span></a>
      <div className="nf-card">
        <div className="nf-perch"><NightjarBird state="resting" px={6} label="Nightjar, asleep on a branch" /><span className="nf-branch" /></div>
        <p className="nf-code">404</p>
        <h1>Nothing to watch here.</h1>
        <p className="nf-text">Nightjar looked everywhere, but <code>{path}</code> isn't a page on this site. It may have moved, or the link has a typo.</p>
        <div className="nf-cta">
          <a className="btn primary" href="/">Back to the story</a>
          <a className="btn" href="/app">Open the app</a>
        </div>
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><NotFound /></StrictMode>);
