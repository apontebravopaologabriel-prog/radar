// Mediciones de rendimiento de Radar con Chromium por CDP (Node 22, sin dependencias).
//   node scripts/perf/measure.mjs <load|idle|drag|pinresize> [url] [--seen] [--css "…"]
// Requiere la API en marcha (por defecto http://127.0.0.1:8101/radar) y `chromium` en el PATH.
// Ojo: el render es por software (headless), así que sirve para comparar antes/después, no como cifras absolutas.
import { spawn } from "node:child_process";

const args = process.argv.slice(2);
const mode = args[0] ?? "load";
const url = args.find((a, i) => i > 0 && a.startsWith("http")) ?? "http://127.0.0.1:8101/radar";
const seen = args.includes("--seen");
const css = args.includes("--css") ? args[args.indexOf("--css") + 1] : "";
const KEY = "radar.agent.window.v2";
const PRE = {
  drag: `localStorage.setItem("${KEY}",JSON.stringify({x:900,y:300,w:400,h:540,open:true,minimized:false,mode:"float",pinWidth:420}))`,
  pinresize: `localStorage.setItem("${KEY}",JSON.stringify({x:900,y:300,w:400,h:540,open:true,minimized:false,mode:"pinned",pinWidth:420}))`,
}[mode] ?? "";

const port = 9200 + Math.floor(Math.random() * 600);
const chrome = spawn("chromium", ["--headless=new", "--no-sandbox", "--enable-unsafe-swiftshader", `--remote-debugging-port=${port}`, "--window-size=1440,900", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let target;
for (let i = 0; i < 40 && !target; i++) { try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page"); } catch { /* aún no */ } await sleep(250); }
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let id = 0; const waiting = new Map(); let bytes = 0; const urls = new Map(); const api = [];
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.id && waiting.has(d.id)) { waiting.get(d.id)(d); waiting.delete(d.id); }
  if (d.method === "Network.responseReceived") urls.set(d.params.requestId, d.params.response.url);
  if (d.method === "Network.loadingFinished") { bytes += d.params.encodedDataLength; const u = urls.get(d.params.requestId) ?? ""; if (u.includes("/api/")) api.push([u.replace(/^.*\/api/, "/api").slice(0, 60), d.params.encodedDataLength]); }
};
const send = (method, params = {}) => new Promise((r) => { const i = ++id; waiting.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expression) => (await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })).result?.result?.value;
const metrics = async () => Object.fromEntries((await send("Performance.getMetrics")).result.metrics.map((m) => [m.name, m.value]));

await send("Network.enable"); await send("Page.enable"); await send("Performance.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1440, height: 900, deviceScaleFactor: 1, mobile: false });
if (seen) await send("Page.addScriptToEvaluateOnNewDocument", { source: "try{sessionStorage.setItem('radar.boot.seen','1')}catch(e){}" });

const out = { mode };
if (mode === "load") {
  const t0 = Date.now(); await send("Page.navigate", { url });
  let first = null, ready = null;
  for (let i = 0; i < 300; i++) {
    const v = JSON.parse(await ev('JSON.stringify({c:document.querySelectorAll(".offer-scroll-card, .job-card").length,boot:!!document.querySelector(".boot-screen")})'));
    if (v.c > 0 && first === null) first = Date.now() - t0;
    if (v.c > 0 && !v.boot) { ready = Date.now() - t0; break; }
    await sleep(100);
  }
  await sleep(1500);
  const m = await metrics();
  Object.assign(out, { firstCardMs: first, interactiveMs: ready, transferKB: Math.round(bytes / 1024), nodes: m.Nodes, heapMB: +(m.JSHeapUsedSize / 1e6).toFixed(1), cards: await ev('document.querySelectorAll(".offer-scroll-card").length'), api });
} else if (mode === "scroll") {
  // Lista por tramos: al bajar aparecen más tarjetas hasta completar la lista.
  await send("Page.navigate", { url });
  await ev(`new Promise(async r=>{for(let n=0;n<120&&!document.querySelector(".offer-scroll-card");n++)await new Promise(x=>setTimeout(x,300));r(1)})`);
  await sleep(3000);
  const counts = [await ev('document.querySelectorAll(".offer-scroll-card").length')];
  for (let i = 0; i < 40; i++) {
    await ev('(()=>{const l=document.querySelector(".offer-scroll-list");l.scrollTop=l.scrollHeight;return 1})()');
    await sleep(250);
    const c = await ev('document.querySelectorAll(".offer-scroll-card").length');
    if (c === counts.at(-1) && i > 3) break;
    counts.push(c);
  }
  const m = await metrics();
  Object.assign(out, { cardsAfterEachScroll: counts.filter((c, i) => i % 3 === 0 || i === counts.length - 1), finalCards: counts.at(-1), listTotal: await ev('Number(document.querySelector(".offer-scroll-heading strong")?.textContent)'), nodesAtEnd: m.Nodes });
} else if (mode === "detail") {
  // Abrir una oferta: la descripción llega bajo demanda (los listados van sin ella).
  await send("Page.navigate", { url });
  await ev(`new Promise(async r=>{for(let n=0;n<120&&!document.querySelector(".offer-scroll-card");n++)await new Promise(x=>setTimeout(x,300));r(1)})`);
  await sleep(3000);
  const t0 = Date.now();
  await ev('document.querySelector(".offer-scroll-card").click()');
  const text = await ev(`new Promise(async r=>{for(let n=0;n<100;n++){const el=document.querySelector(".popover-description-wrap, .reading-description");const t=el?el.innerText.trim():"";if(t&&!t.includes("Cargando descripción")){r(t.slice(0,80));return}await new Promise(x=>setTimeout(x,100))}r("")})`);
  Object.assign(out, { descriptionMs: Date.now() - t0, descriptionOk: text.length > 20, sample: text, descriptionRequests: api.filter(([u]) => u.includes("/description")).length });
} else {
  await send("Page.navigate", { url }); await sleep(2500);
  if (PRE) { await ev(PRE); await send("Page.reload"); }
  await ev(`new Promise(async r=>{for(let n=0;n<120&&!document.querySelector(".offer-scroll-card");n++)await new Promise(x=>setTimeout(x,500));r(1)})`);
  if (mode !== "idle") await ev(`new Promise(async r=>{for(let n=0;n<120&&!document.querySelector(".agent-window, .agent-pinned");n++)await new Promise(x=>setTimeout(x,500));r(1)})`);
  if (css) await ev(`(()=>{const s=document.createElement("style");s.textContent=${JSON.stringify(css)};document.head.appendChild(s);return 1})()`);
  await sleep(3000);
  await ev(`window.__f=[];let l=performance.now();const L=(t)=>{window.__f.push(t-l);l=t;requestAnimationFrame(L)};requestAnimationFrame(L);window.__lt=[];try{new PerformanceObserver(x=>x.getEntries().forEach(e=>window.__lt.push(e.duration))).observe({entryTypes:["longtask"]})}catch(e){}`);
  const m0 = await metrics(); const t0 = Date.now();
  if (mode === "idle") await sleep(5000);
  else {
    const sel = mode === "drag" ? ".agent-titlebar" : ".agent-pinned-resize";
    const r = await ev(`(()=>{const el=document.querySelector("${sel}");if(!el)return null;const b=el.getBoundingClientRect();return {x:b.x+b.width/2,y:b.y+b.height/2}})()`);
    if (!r) throw new Error(`No se encontró ${sel}: ¿el agente está activado en Ajustes?`);
    await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: r.x, y: r.y });
    await send("Input.dispatchMouseEvent", { type: "mousePressed", x: r.x, y: r.y, button: "left", clickCount: 1 });
    for (let i = 1; i <= 60; i++) {
      await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: r.x - (mode === "drag" ? 6 : 4) * i, y: r.y - (mode === "drag" ? 4 * i : 0), button: "left", buttons: 1 });
      await sleep(16);
    }
    await send("Input.dispatchMouseEvent", { type: "mouseReleased", x: r.x - 240, y: r.y - (mode === "drag" ? 240 : 0), button: "left", clickCount: 1 });
    await sleep(600);
  }
  const m1 = await metrics(); const secs = (Date.now() - t0) / 1000;
  const f = await ev(`(()=>{const a=window.__f.slice(2),s=[...a].sort((x,y)=>x-y);return {frames:a.length,avgMs:+(a.reduce((x,y)=>x+y,0)/a.length).toFixed(1),p95Ms:+(s[Math.floor(s.length*.95)]||0).toFixed(1),maxMs:+Math.max(...a).toFixed(1),longTasks:window.__lt.length,longMs:Math.round(window.__lt.reduce((x,y)=>x+y,0))}})()`);
  Object.assign(out, { secs: +secs.toFixed(1), taskMsPerSec: Math.round(((m1.TaskDuration - m0.TaskDuration) * 1000) / secs), layouts: m1.LayoutCount - m0.LayoutCount, recalcs: m1.RecalcStyleCount - m0.RecalcStyleCount, nodes: m1.Nodes, heapMB: +(m1.JSHeapUsedSize / 1e6).toFixed(1), ...f });
}
console.log(JSON.stringify(out));
ws.close(); chrome.kill();
