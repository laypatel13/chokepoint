// The privacy page: what the website and the CLI collect (very little), where it goes, and how to get
// something removed. Every sentence here describes what the code does; change them together.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../styles/fonts";
import "../styles/base.css";
import "./privacy.css";
import { Logo } from "../components/Logo";

const ISSUES = "https://github.com/laypatel13/chokepoint/issues";
const UPDATED = "October 16, 2026";

function Privacy() {
  return (
    <main className="pv">
      <a className="pv-brand" href="/"><Logo /><span>Chokepoint</span></a>
      <article className="pv-card">
        <p className="pv-kicker">Privacy</p>
        <h1>What Chokepoint knows about you: very little.</h1>
        <p className="pv-lead">Chokepoint is an open-source hackathon project. It has no accounts, no ads, no analytics and no
          trackers. This page says exactly what the website and the CLI handle, where it goes, and how to have something
          removed. Last updated {UPDATED}.</p>

        <h2>The website</h2>
        <ul>
          <li><b>Scanning a repo is public.</b> You can only scan <b>public</b> GitHub repos. The repo's name, its graph and
            the results can be opened by anyone, and the repo is listed under "Recently scanned by visitors". Only the 8
            newest visitor scans are kept; older ones are deleted automatically.</li>
          <li><b>What a scan reads:</b> the repo's public <code>package-lock.json</code> from GitHub, public package data
            from the npm registry, and public advisories from OSV. Nothing else from the repo.</li>
          <li><b>People in the results:</b> the npm accounts that can publish each package, by their public npm{" "}
            <b>username</b> only. Emails are dropped as soon as they're read and never stored.</li>
          <li><b>Questions you type in "Ask"</b> may be sent to our AI provider (Groq) so it can pick which graph query
            to run. Please don't type personal information there. Without the AI, simple keyword rules answer instead.</li>
          <li><b>The "Open PR" button</b> opens or updates a pull request on our own sandbox fork of webpack-dev-server,
            and adds a note with a visit number and the time. Every word of it is written by the server; nothing you type,
            and nothing about you, goes into it.</li>
          <li><b>Your address</b> is used only to rate-limit the free server (so one visitor can't use it all). It's kept
            in memory for at most an hour, never written to disk, and forgotten whenever the server restarts.</li>
          <li><b>Your browser</b> remembers two small preferences on your own device: whether you dismissed the "How to
            read this" hint and whether the replay card is folded, plus the logo's spin count for the current tab. No
            cookies are set by Chokepoint.</li>
          <li><b>Our hosting</b> (Render, behind Cloudflare) and database (FalkorDB Cloud) may keep their own standard
            request logs and may set strictly necessary security cookies, under their own privacy policies.</li>
        </ul>

        <h2>The CLI (<code>pip install ckpoint</code>)</h2>
        <ul>
          <li><b>It runs on your machine.</b> Your code and your lockfile never leave it. Only <b>package names</b> are
            sent to the npm registry and OSV, to look them up. The graph is stored locally, in your user data folder.</li>
          <li><b>Your AI key</b> (if you add one) is kept in your system keychain and sent only to the provider you chose,
            only over an encrypted connection. <b>Your GitHub token</b> (if you add one) is kept in your keychain and sent
            only to GitHub. Neither is ever printed, logged or sent to Chokepoint's website.</li>
          <li><b><code>chokepoint share</code></b> sends only a <b>public</b> repo's name to the website, after asking you
            first, and the result becomes public as described above.</li>
          <li><b>No telemetry.</b> The CLI doesn't report usage, errors or anything else to anyone.</li>
        </ul>

        <h2>Removal and questions</h2>
        <p>If you'd like a scanned repo removed from the website, or you're an npm maintainer with a question about how your
          public username appears, open an issue at <a href={ISSUES}>github.com/laypatel13/chokepoint/issues</a>. Scans are
          also removed automatically as newer ones come in.</p>
        <p className="pv-foot">If this page changes, the date at the top changes too.</p>

        <div className="pv-cta">
          <a className="btn primary" href="/">Back to the story</a>
          <a className="btn" href="/app">Open the app</a>
        </div>
      </article>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><Privacy /></StrictMode>);
