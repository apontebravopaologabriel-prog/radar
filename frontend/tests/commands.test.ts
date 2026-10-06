import { describe, expect, it } from "vitest";
import { COMMANDS, findCommand, matchCommands } from "../components/agent/commands";

describe("comandos del chat", () => {
  it("nombres y alias son únicos", () => {
    const names = COMMANDS.flatMap((c) => [c.name, ...(c.aliases ?? [])]);
    expect(new Set(names).size).toBe(names.length);
  });

  it("cada comando tiene ayuda y tipo válido", () => {
    for (const c of COMMANDS) {
      expect(c.hint.length).toBeGreaterThan(0);
      expect(["local", "prompt"]).toContain(c.kind);
    }
  });

  it("findCommand resuelve nombre y alias", () => {
    const withAlias = COMMANDS.find((c) => c.aliases?.length);
    if (withAlias) expect(findCommand(withAlias.aliases![0])).toBe(withAlias);
    expect(findCommand(COMMANDS[0].name)).toBe(COMMANDS[0]);
    expect(findCommand("no-existe")).toBeUndefined();
  });

  it("matchCommands solo sugiere con / y sin espacios", () => {
    expect(matchCommands("hola")).toEqual([]);
    expect(matchCommands("/plan algo")).toEqual([]);
    expect(matchCommands("/").length).toBe(COMMANDS.length);
    const first = COMMANDS[0];
    expect(matchCommands(`/${first.name.slice(0, 2)}`)).toContain(first);
  });
});
