/**
 * Markdown 渲染：标题带锚点（供侧边大纲使用）、原始 HTML 一律转义、代码块轻量语法高亮。
 * 高亮只覆盖卡片中常见的 json / python / bash，避免引入额外依赖。
 */
import { Marked, type Tokens } from 'marked'

export interface TocItem {
  id: string
  text: string
  depth: number
}

const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

function slugify(text: string, used: Map<string, number>): string {
  const base =
    text
      .toLowerCase()
      .replace(/<[^>]+>/g, '')
      .replace(/[^\p{L}\p{N}]+/gu, '-')
      .replace(/^-+|-+$/g, '') || 'section'
  const n = used.get(base) ?? 0
  used.set(base, n + 1)
  return n ? `${base}-${n}` : base
}

/** 按顺序匹配多条规则，未命中的部分原样转义 */
function tokenize(code: string, rules: [RegExp, string][]): string {
  const re = new RegExp(rules.map(([r]) => `(${r.source})`).join('|'), 'gm')
  let out = ''
  let last = 0
  for (const m of code.matchAll(re)) {
    const i = m.index ?? 0
    out += esc(code.slice(last, i))
    const g = m.slice(1).findIndex((x) => x !== undefined)
    out += `<span class="${rules[g][1]}">${esc(m[0])}</span>`
    last = i + m[0].length
  }
  return out + esc(code.slice(last))
}

const LANGS: Record<string, [RegExp, string][]> = {
  json: [
    [/"(?:[^"\\]|\\.)*"(?=\s*:)/, 'tk-key'],
    [/"(?:[^"\\]|\\.)*"/, 'tk-str'],
    [/\b(?:true|false|null)\b/, 'tk-kw'],
    [/-?\b\d+(?:\.\d+)?(?:[eE][+-]?\d+)?\b/, 'tk-num'],
  ],
  python: [
    [/#[^\n]*/, 'tk-com'],
    [/"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'/, 'tk-str'],
    [/\b(?:from|import|as|def|class|return|if|else|elif|for|in|while|with|try|except|raise|None|True|False|self|lambda|yield|async|await)\b/, 'tk-kw'],
    [/\b\d+(?:\.\d+)?\b/, 'tk-num'],
  ],
  bash: [
    [/#[^\n]*/, 'tk-com'],
    [/"(?:[^"\\\n]|\\.)*"|'[^'\n]*'/, 'tk-str'],
    [/(?:^|\s)-{1,2}[\w-]+/, 'tk-kw'],
    [/\b(?:git|pip|python|curl|docker|sh|cd|npm|cp)\b/, 'tk-fn'],
  ],
}
LANGS.sh = LANGS.bash
LANGS.shell = LANGS.bash
LANGS.py = LANGS.python

export function renderMarkdown(source: string): { html: string; toc: TocItem[] } {
  const toc: TocItem[] = []
  const used = new Map<string, number>()
  const md = new Marked({
    gfm: true,
    renderer: {
      // 不渲染原始 HTML，直接转义显示
      html(token: Tokens.HTML | Tokens.Tag) {
        return esc(token.text)
      },
      heading(this: { parser: { parseInline: (t: Tokens.Heading['tokens']) => string } }, token: Tokens.Heading) {
        const inner = this.parser.parseInline(token.tokens)
        const id = slugify(token.text, used)
        if (token.depth >= 2 && token.depth <= 3) toc.push({ id, text: token.text.replace(/`/g, ''), depth: token.depth })
        return `<h${token.depth} id="${id}">${inner}</h${token.depth}>\n`
      },
      code(token: Tokens.Code) {
        const lang = (token.lang ?? '').trim().toLowerCase()
        const rules = LANGS[lang]
        const body = rules ? tokenize(token.text, rules) : esc(token.text)
        const label = lang ? `<span class="code-lang">${esc(lang)}</span>` : ''
        return `<pre class="code-block">${label}<code>${body}</code></pre>\n`
      },
      link(this: { parser: { parseInline: (t: Tokens.Link['tokens']) => string } }, token: Tokens.Link) {
        const href = /^(https?:|mailto:|#|\/)/i.test(token.href) ? token.href : '#'
        const ext = /^https?:/i.test(href)
        return `<a href="${esc(href)}"${ext ? ' target="_blank" rel="noopener noreferrer"' : ''}>${this.parser.parseInline(token.tokens)}</a>`
      },
    },
  })
  const html = md.parse(source, { async: false }) as string
  return { html, toc }
}
