import { memo, type ReactNode } from "react";

/** Markdown seguro para el chat: se construye con elementos de React (sin HTML crudo) y solo enlaza http(s) y mailto. */

const SAFE_LINK = /^(https?:\/\/|mailto:)/i;

function inline(text: string, keyBase: string): ReactNode[] {
  const out: ReactNode[] = [];
  const pattern = /(`[^`\n]+`)|(\*\*[^*\n]+\*\*|__[^_\n]+__)|(\[[^\]\n]+\]\([^)\s]+\))|(\*[^*\n]+\*|_[^_\n]+_)/;
  let rest = text;
  let index = 0;
  while (rest) {
    const match = pattern.exec(rest);
    if (!match) { out.push(rest); break; }
    if (match.index > 0) out.push(rest.slice(0, match.index));
    const token = match[0];
    const key = `${keyBase}-${index++}`;
    if (match[1]) out.push(<code key={key}>{token.slice(1, -1)}</code>);
    else if (match[2]) out.push(<strong key={key}>{inline(token.slice(2, -2), key)}</strong>);
    else if (match[3]) {
      const [, label, href] = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token) ?? [];
      out.push(SAFE_LINK.test(href ?? "")
        ? <a key={key} href={href} target="_blank" rel="noopener noreferrer">{label}</a>
        : <span key={key}>{label}</span>);
    } else out.push(<em key={key}>{inline(token.slice(1, -1), key)}</em>);
    rest = rest.slice(match.index + token.length);
  }
  return out;
}

type Block =
  | { t: "code"; lang: string; text: string }
  | { t: "h"; level: number; text: string }
  | { t: "hr" }
  | { t: "quote"; text: string }
  | { t: "list"; ordered: boolean; items: string[] }
  | { t: "table"; head: string[]; rows: string[][] }
  | { t: "p"; text: string };

const cells = (line: string) => line.trim().replace(/^\|/, "").replace(/(?<!\\)\|$/, "").split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));
const isDivider = (line: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);

function parse(source: string): Block[] {
  const lines = source.replace(/\r\n/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    const fence = /^```\s*(\w*)/.exec(line);
    if (fence) {
      const body: string[] = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) body.push(lines[i++]);
      i++;
      blocks.push({ t: "code", lang: fence[1], text: body.join("\n") });
      continue;
    }
    const heading = /^(#{1,6})\s+(.*)$/.exec(line);
    if (heading) { blocks.push({ t: "h", level: heading[1].length, text: heading[2] }); i++; continue; }
    if (/^\s*([-*_])(\s*\1){2,}\s*$/.test(line)) { blocks.push({ t: "hr" }); i++; continue; }
    if (line.includes("|") && i + 1 < lines.length && isDivider(lines[i + 1])) {
      const head = cells(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) rows.push(cells(lines[i++]));
      blocks.push({ t: "table", head, rows });
      continue;
    }
    if (/^\s*>/.test(line)) {
      const body: string[] = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) body.push(lines[i++].replace(/^\s*>\s?/, ""));
      blocks.push({ t: "quote", text: body.join("\n") });
      continue;
    }
    const listMatch = /^\s*([-*+]|\d+[.)])\s+/.exec(line);
    if (listMatch) {
      const ordered = /\d/.test(listMatch[1]);
      const items: string[] = [];
      while (i < lines.length) {
        const m = /^\s*([-*+]|\d+[.)])\s+(.*)$/.exec(lines[i]);
        if (m) { items.push(m[2]); i++; }
        else if (/^\s{2,}\S/.test(lines[i]) && items.length) { items[items.length - 1] += ` ${lines[i].trim()}`; i++; }
        else break;
      }
      blocks.push({ t: "list", ordered, items });
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(```|#{1,6}\s|\s*>|\s*([-*+]|\d+[.)])\s+)/.test(lines[i])
      && !(lines[i].includes("|") && i + 1 < lines.length && isDivider(lines[i + 1]))) para.push(lines[i++]);
    if (para.length === 0) { para.push(lines[i++]); }
    blocks.push({ t: "p", text: para.join("\n") });
  }
  return blocks;
}

function Markdown({ text }: { text: string }) {
  const blocks = parse(text);
  return (
    <div className="md">
      {blocks.map((b, n) => {
        const key = `b${n}`;
        switch (b.t) {
          case "code": return <pre key={key}><code>{b.text}</code></pre>;
          case "h": return <p key={key} className={`md-h md-h${Math.min(b.level, 3)}`}>{inline(b.text, key)}</p>;
          case "hr": return <hr key={key} />;
          case "quote": return <blockquote key={key}>{inline(b.text, key)}</blockquote>;
          case "list": {
            const items = b.items.map((item, k) => <li key={k}>{inline(item, `${key}-${k}`)}</li>);
            return b.ordered ? <ol key={key}>{items}</ol> : <ul key={key}>{items}</ul>;
          }
          case "table": return (
            <div key={key} className="md-table"><table>
              <thead><tr>{b.head.map((c, k) => <th key={k}>{inline(c, `${key}h${k}`)}</th>)}</tr></thead>
              <tbody>{b.rows.map((row, r) => <tr key={r}>{row.map((c, k) => <td key={k}>{inline(c, `${key}r${r}c${k}`)}</td>)}</tr>)}</tbody>
            </table></div>
          );
          default: return (
            <p key={key}>{b.text.split("\n").flatMap((l, k, arr) => k < arr.length - 1 ? [...inline(l, `${key}-${k}`), <br key={`br${k}`} />] : inline(l, `${key}-${k}`))}</p>
          );
        }
      })}
    </div>
  );
}

/** Memoizado: una línea ya renderizada no se vuelve a analizar mientras llegan respuestas nuevas. */
export default memo(Markdown);
