// Builds "docs/Claude Interactions.docx" from interactions.json (the learning log).
// Usage (from docs/_source):  npm run interactions
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, Footer, PageNumber, LevelFormat,
} = require('docx');

const SRC = path.join(__dirname, 'interactions.json');
const OUT = path.join(__dirname, '..', 'Claude Interactions.docx');
const BLUE = '1F3A93', INK = '1F2937', MUTE = '4B5563';
const WIDTH = 9026; // A4 portrait with 1-inch margins

const data = JSON.parse(fs.readFileSync(SRC, 'utf8'));
const entries = data.entries;

function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const t = m[0];
    if (t.startsWith('**')) out.push(new TextRun({ text: t.slice(2, -2), bold: true, ...base }));
    else out.push(new TextRun({ text: t.slice(1, -1), font: 'Consolas', size: 19, color: '7A1F5C', ...base }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}
const P = (text, run = {}) => new Paragraph({ children: runs(text, run), spacing: { after: 100, line: 276 } });
const H1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const H3 = t => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const bullets = items => items.map(t => new Paragraph({ numbering: { reference: 'bul', level: 0 }, children: runs(t), spacing: { after: 50, line: 276 } }));
const code = text => text.split('\n').map((line, i, all) => new Paragraph({
  children: [new TextRun({ text: line === '' ? ' ' : line, font: 'Consolas', size: 17 })],
  shading: { type: ShadingType.CLEAR, color: 'auto', fill: 'F3F4F6' },
  spacing: { after: i === all.length - 1 ? 140 : 0, before: i === 0 ? 40 : 0, line: 240 },
  indent: { left: 200, right: 200 }, keepNext: i < all.length - 1, keepLines: true,
}));
const border = { style: BorderStyle.SINGLE, size: 4, color: 'BFC7D5' };
function table(headers, rows, ratios) {
  const sum = ratios.reduce((a, b) => a + b, 0);
  const widths = ratios.map(r => Math.floor(WIDTH * r / sum));
  widths[widths.length - 1] += WIDTH - widths.reduce((a, b) => a + b, 0);
  const cell = (txt, w, head, zebra) => new TableCell({
    width: { size: w, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, color: 'auto', fill: head ? 'DCE5F7' : (zebra ? 'F8FAFC' : 'FFFFFF') },
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    borders: { top: border, bottom: border, left: border, right: border },
    children: String(txt ?? '').split('\n').map(l => new Paragraph({ children: runs(l, head ? { bold: true, color: BLUE, size: 19 } : { size: 19 }), spacing: { after: 20 } })),
  });
  return [new Table({
    width: { size: WIDTH, type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, widths[i], true)) }),
      ...rows.map((r, ri) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, widths[i], false, ri % 2)) }))],
  }), new Paragraph({ spacing: { after: 120 }, children: [] })];
}

const children = [];
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 600 }, children: [new TextRun({ text: 'Claude Interactions', bold: true, size: 52, color: BLUE })] }));
children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 300 }, children: [new TextRun({ text: 'Learning log of the AI Teaching Studio build — what changed, why, and every mistake', size: 26, color: MUTE })] }));
children.push(P(`Last updated: ${entries[entries.length - 1].date} · ${entries.length} sessions · generated from docs/_source/interactions.json`, { italics: true, color: MUTE, size: 18 }));

children.push(H1('How to read this log'));
children.push(...bullets([
  '**One entry per working session**, newest at the end. Each entry has: your request, what was done, files changed, **issues & mistakes** (problem → cause → fix, and whose mistake it was), the **key code with an explanation of why**, the commands run, and the lessons learned.',
  '**Mistake types:** *Claude mistake / bug / design mistake* = an error in my work (found by tests, checks or you); *Model behaviour* = an AI model did something unexpected; *Tool/library* = a limitation of software we use; *Data* = something about the input files.',
  '**Full code changes:** this log shows the important snippets. To see every changed line, run `git diff` (before committing) or look at the commit on GitHub (after you commit).',
]));

children.push(H1('Summary of sessions'));
children.push(...table(['#', 'Date', 'Session', 'Issues'], entries.map((e, i) => [String(i + 1), e.date, e.title, String((e.issues || []).length)]), [0.4, 1.1, 5.5, 0.8]));

const allIssues = entries.flatMap((e, i) => (e.issues || []).map(x => [String(i + 1), x.problem, x.cause, x.fix, x.type]));
children.push(H1('All issues and mistakes (learning list)'));
children.push(P('Every problem found so far, in one place. The first column refers to the session number above.'));
children.push(...table(['#', 'Problem', 'Root cause', 'Fix', 'Type'], allIssues, [0.35, 2.4, 2.3, 2.4, 1.2]));

entries.forEach((e, i) => {
  children.push(H1(`${i + 1}. ${e.title}`));
  children.push(P(`**Date:** ${e.date}`));
  children.push(H2('Your request'));
  children.push(P(e.request));
  if (e.what_i_did?.length) { children.push(H2('What was done')); children.push(...bullets(e.what_i_did)); }
  if (e.files?.length) { children.push(H2('Files changed')); children.push(...table(['File', 'Change'], e.files.map(f => [f.path, f.change]), [3, 5])); }
  if (e.issues?.length) {
    children.push(H2('Issues and mistakes'));
    children.push(...table(['Problem', 'Root cause', 'Fix', 'Type'], e.issues.map(x => [x.problem, x.cause, x.fix, x.type]), [2.5, 2.3, 2.5, 1.2]));
  }
  if (e.code?.length) {
    children.push(H2('Key code and why'));
    e.code.forEach(c => { children.push(H3(c.file)); children.push(P(c.why)); children.push(...code(c.snippet)); });
  }
  if (e.commands?.length) { children.push(H2('Commands')); children.push(...code(e.commands.join('\n'))); }
  if (e.lessons?.length) { children.push(H2('Lessons')); children.push(...bullets(e.lessons)); }
});

const doc = new Document({
  creator: 'Claude Code for Santosh',
  title: 'Claude Interactions — learning log',
  styles: {
    default: { document: { run: { font: 'Calibri', size: 21, color: INK } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 30, bold: true, color: BLUE }, paragraph: { spacing: { before: 320, after: 140 }, outlineLevel: 0, keepNext: true } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 24, bold: true, color: '2F5FD0' }, paragraph: { spacing: { before: 200, after: 90 }, outlineLevel: 1, keepNext: true } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 21, bold: true, color: '7A1F5C', font: 'Consolas' }, paragraph: { spacing: { before: 140, after: 60 }, outlineLevel: 2, keepNext: true } },
    ],
  },
  numbering: { config: [{ reference: 'bul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 500, hanging: 260 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'Claude Interactions · page ', size: 16, color: MUTE }), new TextRun({ children: [PageNumber.CURRENT], size: 16, color: MUTE })] })] }) },
    children,
  }],
});
Packer.toBuffer(doc).then(buf => { fs.writeFileSync(OUT, buf); console.log('wrote', OUT, buf.length, 'bytes'); });
