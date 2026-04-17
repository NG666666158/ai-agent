import { Fragment, type ReactNode } from "react";
import type { CitationSource, ParagraphCitation, Task } from "./api";

export function toChineseSourceKind(kind: string): string {
  const map: Record<string, string> = {
    memory: "记忆",
    profile: "画像",
    session: "会话",
    user: "用户",
    system: "系统",
  };
  return map[kind] ?? kind;
}

export function buildCitationSourceMap(task: Task | null) {
  const mapping = new Map<string, Task["citation_sources"][number]>();
  if (!task) {
    return mapping;
  }
  for (const source of task.citation_sources) {
    mapping.set(source.id, source);
  }
  return mapping;
}

export function buildCitationFootnoteNumbers(paragraphCitations: Task["paragraph_citations"]) {
  const order = new Map<string, number>();
  let index = 1;
  for (const citation of paragraphCitations) {
    for (const sourceId of citation.source_ids) {
      if (!order.has(sourceId)) {
        order.set(sourceId, index);
        index += 1;
      }
    }
  }
  return order;
}

export function buildSourceParagraphMap(paragraphCitations: Task["paragraph_citations"]) {
  const mapping = new Map<string, number[]>();
  for (const citation of paragraphCitations) {
    for (const sourceId of citation.source_ids) {
      const current = mapping.get(sourceId) ?? [];
      current.push(citation.paragraph_index);
      mapping.set(sourceId, current);
    }
  }
  return mapping;
}

export function renderInline(text: string): ReactNode[] {
  const tokens = text.split(/(`[^`]+`|\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*)/g);
  return tokens.map((token, index) => {
    if (!token) {
      return null;
    }
    if (token.startsWith("`") && token.endsWith("`")) {
      return <code key={`${token}-${index}`}>{token.slice(1, -1)}</code>;
    }
    if (token.startsWith("**") && token.endsWith("**")) {
      return <strong key={`${token}-${index}`}>{token.slice(2, -2)}</strong>;
    }
    const linkMatch = token.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (linkMatch) {
      return (
        <a href={linkMatch[2]} key={`${token}-${index}`} rel="noreferrer" target="_blank">
          {linkMatch[1]}
        </a>
      );
    }
    return <Fragment key={`${token}-${index}`}>{token}</Fragment>;
  });
}

function parseTableRow(line: string): string[] {
  const trimmed = line.trim();
  const normalized = trimmed.startsWith("|") ? trimmed.slice(1) : trimmed;
  const withoutTrailing = normalized.endsWith("|") ? normalized.slice(0, -1) : normalized;
  return withoutTrailing.split("|").map((cell) => cell.trim());
}

function isTableSeparator(line: string): boolean {
  return /^\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?$/.test(line.trim());
}

export function renderInlineCitationAnchors(
  sourceIds: string[],
  footnoteNumbers: Map<string, number>,
  paragraphIndex: number,
) {
  if (!sourceIds.length) {
    return null;
  }
  return (
    <span className="inline-source-anchors">
      {sourceIds.map((sourceId) => {
        const footnoteNumber = footnoteNumbers.get(sourceId);
        if (!footnoteNumber) {
          return null;
        }
        return (
          <a
            className="inline-source-anchor"
            href={`#answer-source-${sourceId}`}
            key={`${paragraphIndex}-${sourceId}`}
            title={`查看来源 ${footnoteNumber}`}
          >
            [{footnoteNumber}]
          </a>
        );
      })}
    </span>
  );
}

export function renderMarkdownBlocks(
  markdown: string,
  paragraphCitations: ParagraphCitation[],
  footnoteNumbers: Map<string, number>,
): ReactNode[] {
  const normalized = markdown.replace(/\r\n/g, "\n").trim();
  if (!normalized) {
    return [<p key="empty">正在等待内容生成...</p>];
  }

  const lines = normalized.split("\n");
  const elements: ReactNode[] = [];
  let index = 0;
  let key = 0;
  let paragraphCursor = 0;

  while (index < lines.length) {
    const rawLine = lines[index];
    const trimmed = rawLine.trim();

    if (!trimmed) {
      index += 1;
      continue;
    }

    if (trimmed === "---") {
      elements.push(<hr key={`hr-${key++}`} />);
      index += 1;
      continue;
    }

    if (trimmed.startsWith("```")) {
      const language = trimmed.slice(3).trim();
      const codeLines: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) {
        index += 1;
      }
      elements.push(
        <pre className="markdown-code-block" key={`code-${key++}`}>
          {language ? <div className="markdown-code-lang">{language}</div> : null}
          <code>{codeLines.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    if (/^#{1,6}\s+/.test(trimmed)) {
      const level = trimmed.match(/^#+/)?.[0].length ?? 1;
      const content = trimmed.replace(/^#{1,6}\s+/, "");
      const node = level <= 1 ? "h1" : level === 2 ? "h2" : "h3";
      elements.push(
        node === "h1" ? (
          <h1 key={`h1-${key++}`}>{renderInline(content)}</h1>
        ) : node === "h2" ? (
          <h2 key={`h2-${key++}`}>{renderInline(content)}</h2>
        ) : (
          <h3 key={`h3-${key++}`}>{renderInline(content)}</h3>
        ),
      );
      index += 1;
      continue;
    }

    if (trimmed.startsWith(">")) {
      const quoteLines: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith(">")) {
        quoteLines.push(lines[index].trim().replace(/^>\s?/, ""));
        index += 1;
      }
      elements.push(
        <blockquote className="markdown-blockquote" key={`quote-${key++}`}>
          {quoteLines.map((line, lineIndex) => (
            <p key={`quote-line-${lineIndex}`}>{renderInline(line)}</p>
          ))}
        </blockquote>,
      );
      continue;
    }

    if (trimmed.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1])) {
      const headers = parseTableRow(lines[index]);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && lines[index].trim().includes("|")) {
        rows.push(parseTableRow(lines[index]));
        index += 1;
      }
      elements.push(
        <div className="markdown-table-wrap" key={`table-${key++}`}>
          <table className="markdown-table">
            <thead>
              <tr>
                {headers.map((header, headerIndex) => (
                  <th key={`th-${headerIndex}`}>{renderInline(header)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={`tr-${rowIndex}`}>
                  {row.map((cell, cellIndex) => (
                    <td key={`td-${rowIndex}-${cellIndex}`}>{renderInline(cell)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }

    if (/^[-*]\s+/.test(trimmed) || /^\d+\.\s+/.test(trimmed)) {
      const items: { ordered: boolean; text: string }[] = [];
      while (index < lines.length) {
        const current = lines[index].trim();
        if (/^[-*]\s+/.test(current)) {
          items.push({ ordered: false, text: current.replace(/^[-*]\s+/, "") });
          index += 1;
          continue;
        }
        if (/^\d+\.\s+/.test(current)) {
          items.push({ ordered: true, text: current.replace(/^\d+\.\s+/, "") });
          index += 1;
          continue;
        }
        break;
      }
      const ListTag = items.every((item) => item.ordered) ? "ol" : "ul";
      elements.push(
        <ListTag key={`list-${key++}`}>
          {items.map((item, itemIndex) => (
            <li key={`${item.text}-${itemIndex}`}>{renderInline(item.text)}</li>
          ))}
        </ListTag>,
      );
      continue;
    }

    const paragraphLines = [trimmed];
    index += 1;
    while (index < lines.length) {
      const current = lines[index].trim();
      if (
        !current ||
        current === "---" ||
        /^#{1,6}\s+/.test(current) ||
        /^[-*]\s+/.test(current) ||
        /^\d+\.\s+/.test(current) ||
        current.startsWith(">") ||
        current.startsWith("```") ||
        (current.includes("|") && index + 1 < lines.length && isTableSeparator(lines[index + 1]))
      ) {
        break;
      }
      paragraphLines.push(current);
      index += 1;
    }

    const paragraphCitation = paragraphCitations.find((item) => item.paragraph_index === paragraphCursor);
    const paragraphId = paragraphCitation ? `answer-paragraph-${paragraphCitation.paragraph_index}` : undefined;
    elements.push(
      <p className="answer-paragraph" id={paragraphId} key={`p-${key++}`}>
        {renderInline(paragraphLines.join(" "))}
        {paragraphCitation
          ? renderInlineCitationAnchors(paragraphCitation.source_ids, footnoteNumbers, paragraphCitation.paragraph_index)
          : null}
      </p>,
    );
    paragraphCursor += 1;
  }

  return elements;
}

export function renderFootnoteSection(
  citationSourceMap: Map<string, CitationSource>,
  footnoteNumbers: Map<string, number>,
  sourceParagraphMap: Map<string, number[]>,
) {
  return (
    <section className="answer-footnotes">
      <strong>引用脚注与来源映射</strong>
      <div className="source-hit-list">
        {Array.from(footnoteNumbers.entries()).map(([sourceId, footnoteNumber]) => {
          const source = citationSourceMap.get(sourceId);
          if (!source) {
            return null;
          }
          const paragraphIndexes = sourceParagraphMap.get(sourceId) ?? [];
          return (
            <article className="source-hit-card source-footnote-card" id={`answer-source-${sourceId}`} key={sourceId}>
              <div className="tool-card-head">
                <strong>
                  [{footnoteNumber}] {source.label}
                </strong>
                <span className="tool-badge">
                  来源：{toChineseSourceKind(source.kind)}
                </span>
              </div>
              <div className="meta">{source.detail}</div>
              {paragraphIndexes.length ? (
                <div className="tag-row">
                  {paragraphIndexes.map((paragraphIndex) => (
                    <a className="inline-source-anchor" href={`#answer-paragraph-${paragraphIndex}`} key={`${sourceId}-${paragraphIndex}`}>
                      段落 {paragraphIndex + 1}
                    </a>
                  ))}
                </div>
              ) : null}
              {source.excerpt ? <pre>{source.excerpt}</pre> : null}
            </article>
          );
        })}
      </div>
    </section>
  );
}
