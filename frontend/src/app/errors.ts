// Turn a failed request into something a person can act on: what happened, and what to do next.
import { ApiError } from "../lib/api";

export interface Problem {
  title: string;
  text: string;
  hint?: string;
}

export function describe(e: unknown, local: boolean): Problem {
  const text = e instanceof Error ? e.message : String(e);
  const status = e instanceof ApiError ? e.status : -1;
  if (status === 0) {
    return { title: "The server isn't answering", text,
      hint: local ? "Is `chokepoint map` still running in your terminal? Start it again, then try again."
        : "The free host sleeps when nobody is using it; it takes about 30 seconds to wake up. Try again in a moment." };
  }
  if (status === 404 && /project/i.test(text)) {
    return { title: "That project isn't loaded", text, hint: "Pick another project from the list above." };
  }
  if (status === 429) return { title: "Too many questions at once", text, hint: "Wait a few seconds, then try again." };
  if (status === 400 || status === 422) return { title: "The graph can't answer that", text };
  if (status >= 500) {
    return { title: "Something broke on the server", text,
      hint: local ? "The terminal running `chokepoint map` shows the details." : "Try again; if it keeps failing, the database may be restarting." };
  }
  return { title: "That didn't work", text };
}
