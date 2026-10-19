// 临时探针：验证 Edge 运行时能否访问国内公开行情接口。
// 正式版会把这里换成 handler.ts，本文件仅用于第一次发布后的可行性检查。

const TARGETS: Array<[string, string, string, string]> = [
  ["tencent_quote", "https://qt.gtimg.cn/q=sh510300", "https://gu.qq.com/", "gbk"],
  ["tencent_kline", "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh510300,day,2024-01-01,2026-12-31,320,qfq", "https://gu.qq.com/", "utf-8"],
  ["sina_universe", "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=20&sort=amount&asc=0&node=etf_hq_fund&symbol=&_s_r_a=init", "https://finance.sina.com.cn/", "utf-8"],
  ["danjuan_valuation", "https://danjuanfunds.com/djapi/index_eva/dj", "https://danjuanfunds.com/djmodule/value-center", "utf-8"],
  ["eastmoney_quote", "https://push2.eastmoney.com/api/qt/stock/get?secid=1.510300&fields=f43,f57,f58,f60,f170", "https://quote.eastmoney.com/", "utf-8"],
];

function decode(buf: ArrayBuffer, label: string): string {
  try {
    return new TextDecoder(label).decode(buf);
  } catch {
    return new TextDecoder("utf-8").decode(buf) + " [decoder-fallback:" + label + "]";
  }
}

async function probe(name: string, url: string, referer: string, enc: string) {
  const t0 = Date.now();
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 12000);
    const res = await fetch(url, {
      headers: {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        referer,
        accept: "*/*",
      },
      signal: ctrl.signal,
    });
    clearTimeout(timer);
    const buf = await res.arrayBuffer();
    const text = decode(buf, enc);
    return {
      name, ok: res.ok, status: res.status, ms: Date.now() - t0,
      bytes: buf.byteLength, head: text.slice(0, 90).replace(/\s+/g, " "),
    };
  } catch (e) {
    return { name, ok: false, ms: Date.now() - t0, error: String(e).slice(0, 160) };
  }
}

const server = (globalThis as Record<string, any>).Deno;
server.serve(async (req: Request) => {
  const url = new URL(req.url);
  if (url.pathname !== "/functions/v1/app" && url.pathname !== "/") {
    return new Response(JSON.stringify({ error: "not found" }), { status: 404, headers: { "content-type": "application/json" } });
  }
  const results = [];
  for (const [n, u, r, e] of TARGETS) results.push(await probe(n, u, r, e));
  const okCount = results.filter((x: any) => x.ok).length;
  return new Response(JSON.stringify({ probe: true, ok: okCount, total: TARGETS.length, results }, null, 2),
    { headers: { "content-type": "application/json; charset=utf-8" } });
});
