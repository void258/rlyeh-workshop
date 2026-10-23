// 剧本格式的高亮、台词 ID 保护、自动补全。格式见 docs/zh/script-format.md；中文写法（全角）和英文写法都认。
import { autocompletion, type Completion, type CompletionContext } from '@codemirror/autocomplete'
import { HighlightStyle, StreamLanguage, syntaxHighlighting, type StringStream } from '@codemirror/language'
import { Annotation, EditorState, RangeSetBuilder, type Text } from '@codemirror/state'
import { Decoration, EditorView, ViewPlugin, type DecorationSet, type ViewUpdate } from '@codemirror/view'
import { tags } from '@lezer/highlight'
import type { ScriptMeta } from './api'

// ── 高亮 ──

type Ctx = 'start' | 'dname' | 'dsep' | 'dargs' | 'speaker' | 'face' | 'colon' | 'tone' | 'body' | 'rest'

interface State {
  front: 0 | 1 | 2 // 0 还没看到第一行，1 在文件头里，2 文件头之后
  comment: boolean
  ctx: Ctx
}

const SPEAKER = /^[^：［[〔<>\s][^：［[]{0,31}?(?=(?:[［[][^］\]]+[］\]])?(?:：|:(?=\s|$)))/
const ANCHOR = /^\s\^[A-Za-z0-9][A-Za-z0-9_-]*\s*$/

function token(stream: StringStream, s: State): string | null {
  if (s.comment) {
    if (stream.skipTo('-->')) {
      stream.match('-->')
      s.comment = false
    } else stream.skipToEnd()
    return 'comment'
  }
  if (stream.sol()) {
    s.ctx = 'start'
    if (s.front === 0) {
      s.front = 2
      if (stream.match(/^---\s*$/)) {
        s.front = 1
        return 'front'
      }
    } else if (s.front === 1) {
      if (stream.match(/^---\s*$/)) s.front = 2
      else stream.skipToEnd()
      return 'front'
    }
  }
  if (stream.match('<!--')) {
    if (stream.skipTo('-->')) stream.match('-->')
    else {
      stream.skipToEnd()
      s.comment = true
    }
    return 'comment'
  }
  return inLine(stream, s)
}

// 一行里面的状态机。只在这里面递归，不回到 token()：行首还没前进时 sol() 一直为真，回去会无限重置
function inLine(stream: StringStream, s: State): string | null {
  switch (s.ctx) {
    case 'start':
      stream.eatSpace()
      if (stream.match(/^#{1,6}\s.*$/)) return 'heading'
      if (stream.match('【') || stream.match('[[')) {
        s.ctx = 'dname'
        return 'bracket'
      }
      if (stream.match(/^>\s*/)) {
        s.ctx = 'speaker'
        return 'ooc'
      }
      s.ctx = 'speaker'
      return inLine(stream, s)
    case 'dname':
      s.ctx = 'dsep'
      if (stream.match(/^[^：:\]】]+/)) return 'dname'
      return inLine(stream, s)
    case 'dsep':
      if (stream.match(/^[：:]\s*/)) {
        s.ctx = 'dargs'
        return 'sep'
      }
      s.ctx = 'dargs'
      return inLine(stream, s)
    case 'dargs':
      if (stream.match(/^(】|\]\])\s*$/)) return 'bracket'
      if (stream.match(/^\s*[｜|]\s*/)) return 'sep'
      if (stream.match(/^[^｜|】\]]+/)) return 'dargs'
      stream.next()
      return null
    case 'speaker':
      if (stream.match(SPEAKER)) {
        s.ctx = 'face'
        return 'speaker'
      }
      s.ctx = 'rest'
      stream.skipToEnd()
      return null
    case 'face':
      s.ctx = 'colon'
      if (stream.match(/^[［[][^］\]]+[］\]]/)) return 'face'
      return inLine(stream, s)
    case 'colon':
      s.ctx = 'tone'
      if (stream.match(/^(：|:)/)) return 'sep'
      return inLine(stream, s)
    case 'tone':
      stream.eatSpace()
      s.ctx = 'body'
      if (stream.match(/^(〔[^〕]+〕|<[^>]+>)/)) return 'tone'
      return inLine(stream, s)
    case 'body':
      if (stream.match(ANCHOR)) return 'anchor'
      if (stream.match(/^\{[^}]+\}/)) return 'bleep'
      if (stream.match(/^\*[^*]+\*/) || stream.match(/^（[^）]*）/)) return 'action'
      if (stream.match(/^\s+/) || stream.match(/^[^{*（\s]+/)) return null
      stream.next()
      return null
    default:
      stream.skipToEnd()
      return null
  }
}

const scriptLanguage = StreamLanguage.define<State>({
  name: 'rlyeh-script',
  startState: () => ({ front: 0, comment: false, ctx: 'start' }),
  copyState: (s) => ({ ...s }),
  token,
  tokenTable: {
    front: tags.meta,
    comment: tags.comment,
    heading: tags.heading,
    bracket: tags.bracket,
    dname: tags.keyword,
    dargs: tags.string,
    sep: tags.punctuation,
    ooc: tags.quote,
    speaker: tags.labelName,
    face: tags.typeName,
    tone: tags.emphasis,
    action: tags.special(tags.comment),
    bleep: tags.deleted,
    anchor: tags.annotation,
  },
})

const highlight = HighlightStyle.define([
  { tag: tags.meta, color: '#8a8073' },
  { tag: tags.comment, color: '#6f675c', fontStyle: 'italic' },
  { tag: tags.heading, color: '#f0c27a', fontWeight: '700' },
  { tag: tags.bracket, color: '#8a8073' },
  { tag: tags.punctuation, color: '#8a8073' },
  { tag: tags.keyword, color: '#e0954f', fontWeight: '600' },
  { tag: tags.string, color: '#d8cfc0' },
  { tag: tags.quote, color: '#7fa6d9', fontWeight: '700' },
  { tag: tags.labelName, color: '#d9a85b', fontWeight: '600' },
  { tag: tags.typeName, color: '#c7a8e8' },
  { tag: tags.emphasis, color: '#7fa6d9', fontStyle: 'italic' },
  { tag: tags.special(tags.comment), color: '#9b9083', fontStyle: 'italic' },
  { tag: tags.deleted, color: '#e06a5a', textDecoration: 'underline wavy #e06a5a80' },
  { tag: tags.annotation, color: '#5f584f' },
])

export const theme = EditorView.theme(
  {
    '&': { height: '100%', backgroundColor: '#100e0c', color: '#ece4d6', fontSize: '14.5px' },
    '.cm-scroller': { fontFamily: "'PingFang SC','Microsoft YaHei','Noto Sans SC',system-ui,sans-serif", lineHeight: '1.75' },
    '.cm-content': { caretColor: '#f0c27a', padding: '10px 0' },
    '.cm-cursor, .cm-dropCursor': { borderLeftColor: '#f0c27a', borderLeftWidth: '2px' },
    '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection': { backgroundColor: '#5b4520 !important' },
    '.cm-gutters': { backgroundColor: '#141210', color: '#5f584f', border: 'none', borderRight: '1px solid #3a332b' },
    '.cm-activeLine': { backgroundColor: '#1d1a1780' },
    '.cm-activeLineGutter': { backgroundColor: '#1d1a17', color: '#9b9083' },
    '.cm-anchor': { color: '#5f584f', fontFamily: "'Cascadia Mono',Consolas,monospace", fontSize: '12px' },
    '.cm-tooltip': { backgroundColor: '#24201c', border: '1px solid #3a332b', color: '#ece4d6' },
    '.cm-tooltip-autocomplete > ul > li[aria-selected]': { backgroundColor: '#5b4520', color: '#ece4d6' },
    '.cm-completionDetail': { color: '#9b9083', fontStyle: 'normal', marginLeft: '1em' },
    '.cm-diagnostic-error': { borderLeft: '4px solid #e06a5a' },
    '.cm-diagnostic-warning': { borderLeft: '4px solid #e0954f' },
    '.cm-panels': { backgroundColor: '#1d1a17', color: '#ece4d6' },
    '.cm-panels.cm-panels-bottom': { borderTop: '1px solid #3a332b' },
    '.cm-searchMatch': { backgroundColor: '#d9a85b40' },
    '.cm-searchMatch.cm-searchMatch-selected': { backgroundColor: '#d9a85b80' },
    '.cm-panel input, .cm-panel button': { color: '#ece4d6', backgroundColor: '#141210', border: '1px solid #3a332b' },
  },
  { dark: true },
)

export const language = [scriptLanguage, syntaxHighlighting(highlight)]

// ── 台词 ID 保护 ──
// 行尾的 ^ID 是配音、审核记录的钥匙：不能改，也不能在后面接着打字。整行删掉、或者跨行删掉可以（保存时会提醒），
// 单独把 ID 删掉不行（光标在行尾按一下退格，原子范围会把整个 ID 删掉）。

export const external = Annotation.define<boolean>() // 重新载入、补 ID 这类程序改动，不拦

const ANCHOR_IN_LINE = /\s\^[A-Za-z0-9][A-Za-z0-9_-]*\s*$/

export function anchorRanges(doc: Text, from = 0, to = doc.length) {
  const out: { from: number; to: number; line: number }[] = []
  for (let pos = from; pos <= to; ) {
    const line = doc.lineAt(pos)
    const m = ANCHOR_IN_LINE.exec(line.text)
    if (m) out.push({ from: line.from + m.index, to: line.to, line: line.from })
    pos = line.to + 1
  }
  return out
}

export function protectIds(onBlocked: () => void) {
  return EditorState.transactionFilter.of((tr) => {
    if (!tr.docChanged || tr.annotation(external)) return tr
    const ranges = anchorRanges(tr.startState.doc)
    let bad = false
    tr.changes.iterChanges((fromA, toA, _fromB, _toB, inserted) => {
      for (const r of ranges) {
        if (bad || toA < r.from || fromA > r.to) continue
        if (fromA <= r.line && toA >= r.to) continue // 整行内容一起删掉
        if (fromA <= r.from && toA > r.to) continue // 跨到下一行的删除
        if (fromA === toA) {
          // 只插入：插在 ID 前面（空格之前）可以，ID 后面只能换行
          if (fromA === r.from) continue
          if (fromA === r.to && inserted.sliceString(0, 1) === '\n') continue
          bad = true
        } else bad = true
      }
    })
    if (bad) {
      window.setTimeout(onBlocked)
      return []
    }
    return tr
  })
}

const anchorMark = Decoration.mark({ class: 'cm-anchor' })

export const anchorDecorations = ViewPlugin.fromClass(
  class {
    decorations: DecorationSet
    constructor(view: EditorView) {
      this.decorations = this.build(view)
    }
    update(u: ViewUpdate) {
      if (u.docChanged || u.viewportChanged) this.decorations = this.build(u.view)
    }
    build(view: EditorView) {
      const b = new RangeSetBuilder<Decoration>()
      for (const { from, to } of view.visibleRanges)
        for (const r of anchorRanges(view.state.doc, from, to)) if (r.to > r.from) b.add(r.from, r.to, anchorMark)
      return b.finish()
    }
  },
  {
    decorations: (v) => v.decorations,
    provide: (p) => EditorView.atomicRanges.of((view) => view.plugin(p)?.decorations ?? Decoration.none),
  },
)

// ── 自动补全 ──

const NAME_END = /[：:［[]/

function speakerOptions(meta: ScriptMeta, ooc: boolean): Completion[] {
  if (ooc) return meta.players.map((p) => ({ label: p, type: 'variable', detail: 'OOC' }))
  const seen = new Set<string>()
  const out: Completion[] = []
  for (const sp of meta.speakers)
    for (const n of sp.names)
      if (!seen.has(n)) {
        seen.add(n)
        out.push({ label: n, type: 'variable', detail: sp.id })
      }
  for (const n of meta.narrators) if (!seen.has(n)) out.push({ label: n, type: 'variable', detail: 'narrator' })
  return out
}

function enumOptions(meta: ScriptMeta, kind: string, zh: boolean): Completion[] {
  const table = meta.enums[kind] ?? {}
  return Object.entries(table).flatMap(([key, aliases]) =>
    zh && aliases.length ? aliases.map((a) => ({ label: a, detail: key, type: 'enum' })) : [{ label: key, type: 'enum' }],
  )
}

function argOptions(meta: ScriptMeta, directive: string, index: number, zh: boolean): Completion[] {
  const spec = meta.directives.find((d) => d.name === directive || d.aliases.includes(directive) || d.aliases.map((a) => a.toLowerCase()).includes(directive.toLowerCase()))
  if (!spec) return []
  const params = spec.params
  if (!params.length) return []
  const p = params[Math.min(index, params.length - 1)]
  if (p.kind === 'char') return speakerOptions(meta, false)
  if (meta.enums[p.kind]) return enumOptions(meta, p.kind, zh)
  if (spec.name === 'bgm') return meta.cues.flatMap((c) => c.names.map((n) => ({ label: n, detail: c.id, type: 'constant' })))
  if (spec.name === 'sfx') return meta.sounds.flatMap((s) => [s.id, ...s.aliases].map((n) => ({ label: n, detail: s.id, type: 'constant' })))
  return []
}

export function completions(getMeta: () => ScriptMeta | null) {
  return autocompletion({
    activateOnTyping: true,
    override: [
      (ctx: CompletionContext) => {
        const meta = getMeta()
        if (!meta) return null
        const zh = !meta.lang.toLowerCase().startsWith('en')
        const line = ctx.state.doc.lineAt(ctx.pos)
        const before = line.text.slice(0, ctx.pos - line.from)

        // 指令：【名字：参数｜参数】 或 [[name: arg | arg]]
        const d = /^\s*(【|\[\[)([^：:\]】]*)(?:([：:])(.*))?$/.exec(before)
        if (d) {
          if (d[3] === undefined) {
            const word = d[2]
            const options = meta.directives.flatMap((s) => {
              const names = zh ? [...s.aliases.filter((a) => /[^\x00-\x7f]/.test(a)), s.name] : [s.name]
              return names.map((n) => ({ label: n, detail: zh && n !== s.name ? s.name : undefined, type: 'keyword' }))
            })
            return { from: ctx.pos - word.length, options, validFor: /^[^：:\]】]*$/ }
          }
          const args = d[4].split(/[｜|]/)
          const current = args[args.length - 1]
          const lead = current.length - current.trimStart().length
          const options = argOptions(meta, d[2].trim(), args.length - 1, zh)
          if (!options.length) return null
          return { from: ctx.pos - current.length + lead, options, validFor: /^[^｜|】\]]*$/ }
        }

        // 说话人后面的表情：名字［ 或 Name[
        const f = /^\s*(?:>\s*)?([^：［[〔<>\s][^：［[]{0,31}?)[［[]([^］\]]*)$/.exec(before)
        if (f) {
          const sp = meta.speakers.find((s) => s.names.includes(f[1].trim()) || s.id === f[1].trim())
          if (!sp?.expressions.length) return null
          return { from: ctx.pos - f[2].length, options: sp.expressions.map((e) => ({ label: e, type: 'type' })) }
        }

        // 行首：说话人（> 开头是场外玩家）
        const s = /^(\s*)(>\s*)?([^\s]*)$/.exec(before)
        if (s && !NAME_END.test(s[3]) && (s[3].length > 0 || ctx.explicit)) {
          return { from: ctx.pos - s[3].length, options: speakerOptions(meta, !!s[2]), validFor: /^[^：:［[\s]*$/ }
        }
        return null
      },
    ],
  })
}
