// What an answer card can ask the app to do (a button inside a card runs another question).
import { createContext, useContext } from "react";

export interface AnswerActions {
  /** Run a graph tool; tools that need a version use the Q1 box. */
  run: (tool: string, args?: Record<string, unknown>) => void;
  /** Show the fix for package@version (a PR on the website, commands in `chokepoint map`). */
  fix: (key: string) => void;
  /** Q1 on this package@version (puts it in the Q1 box first). */
  check: (key: string) => void;
  /** Local mode (`chokepoint map`): fixes are commands, not PRs. */
  local: boolean;
}

export const ActionsContext = createContext<AnswerActions | null>(null);

export function useActions(): AnswerActions {
  const actions = useContext(ActionsContext);
  if (!actions) throw new Error("answer cards need an ActionsContext provider");
  return actions;
}
