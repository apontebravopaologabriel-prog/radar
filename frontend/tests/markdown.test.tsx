import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import Markdown from "../components/agent/Markdown";

const html = (text: string) => renderToStaticMarkup(<Markdown text={text} />);

describe("Markdown seguro", () => {
  it("escapa HTML crudo en lugar de interpretarlo", () => {
    const out = html('<img src=x onerror="alert(1)"> <script>alert(1)</script>');
    expect(out).not.toContain("<img");
    expect(out).not.toContain("<script");
    expect(out).toContain("&lt;script&gt;");
  });

  it("solo enlaza http, https y mailto", () => {
    expect(html("[ok](https://example.com)")).toContain('href="https://example.com"');
    expect(html("[mail](mailto:a@b.pe)")).toContain('href="mailto:a@b.pe"');
    for (const bad of ["javascript:alert(1)", "data:text/html,x", "vbscript:x"]) {
      const out = html(`[clic](${bad})`);
      expect(out).not.toContain("href=");
      expect(out).toContain("clic");
    }
  });

  it("los enlaces externos llevan rel noopener noreferrer", () => {
    expect(html("[x](https://example.com)")).toContain('rel="noopener noreferrer"');
    expect(html("ver https://example.com/a.")).toContain('href="https://example.com/a"');
  });

  it("renderiza listas, tablas, código y encabezados", () => {
    expect(html("- a\n- b")).toContain("<ul><li>a</li><li>b</li></ul>");
    expect(html("1. a\n2. b")).toContain("<ol>");
    expect(html("| A | B |\n|---|---|\n| 1 | 2 |")).toContain("<th>A</th>");
    const code = html("```\n<b>x</b>\n```");
    expect(code).toContain("<pre><code>");
    expect(code).toContain("&lt;b&gt;");
    expect(html("## Título")).toContain("md-h2");
  });

  it("rellena las filas cortas de una tabla para no correr las columnas", () => {
    const out = html("| A | B | C |\n|---|---|---|\n| 1 | 2 |");
    expect(out.match(/<td>/g)).toHaveLength(3);
  });

  it("negritas y cursivas simples", () => {
    expect(html("**a** y *b* y `c`")).toBe('<div class="md"><p><strong>a</strong> y <em>b</em> y <code>c</code></p></div>');
  });
});

describe("enlace interno a una oferta", () => {
  it("radar:job:<id> abre la oferta en el mapa y no navega", () => {
    const out = html("[Analista](radar:job:abc-123)");
    expect(out).toContain('class="md-job-link"');
    expect(out).toContain("Analista");
    expect(out).not.toContain("radar:job");
  });

  it("un esquema interno inválido se queda como texto", () => {
    const out = html("[x](radar:job:../../etc)");
    expect(out).not.toContain("<a");
  });
});
