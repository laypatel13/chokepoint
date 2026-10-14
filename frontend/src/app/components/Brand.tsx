import { Icon } from "../../components/Icon";
import { Logo } from "../../components/Logo";

/** Name, logo and tagline. On the website: a link back to the story; in `chokepoint map`: a badge
 * saying it runs on this machine. */
export function Brand({ local }: { local: boolean }) {
  return (
    <header>
      <div className="brand">
        <h1><a href="/"><Logo />Chokepoint</a></h1>
        {local ? (
          <span className="badge blue local-badge" title="Served by `chokepoint map` on 127.0.0.1: nothing leaves this machine">
            <Icon name="lock" size="sm" />On this machine
          </span>
        ) : (
          <a className="back" href="/"><Icon name="left" size="sm" />The story</a>
        )}
      </div>
      <p className="tagline">Who can poison your app?</p>
    </header>
  );
}
